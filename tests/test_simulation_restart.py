"""Synthetic preservation and isolation tests; no production archive is claimed."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import pytest
from services import simulation_archive as archive
from services import simulation_restart as restart
from services import portfolio_accounting as ledger
from services.storage_service import StorageService
from test_revision_trade_postgres import pg


@pytest.fixture(scope='module')
def certificate(tmp_path_factory):
    root=tmp_path_factory.mktemp('archive-key');key=root/'private.pem';cert=root/'public.pem'
    result=subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),
        '-subj','/CN=SYNTHETIC ARCHIVE TEST ONLY','-days','1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert result.returncode==0
    key.chmod(0o600)
    return cert,key


@pytest.fixture
def sources(tmp_path):
    root=tmp_path/'old-model-runtime';root.mkdir()
    values={'portfolios.json':{'cash':123,'positions':{'LEGACY':{'quantity':7}},'reported_loss':-25000},
        'trades.json':[{'side':'SELL','pnl':-500}], 'decisions.json':[{'reason':'TEST ONLY original signal'}],
        'parameters.json':{'stop_loss':3,'rank_weight':.7},'learning.json':{'observations':81,'weights':[.3,.7]},
        'nav.json':[100000,75000], 'audit.jsonl':{'original':'TEST ONLY preserved audit'}}
    for name,value in values.items():(root/name).write_text(json.dumps(value))
    (root/'report.pdf').write_bytes(b'%PDF-1.4 TEST ONLY original report')
    (root/'model.bin').write_bytes(bytes(range(256)))
    return root


@pytest.fixture
def dump_program(tmp_path):
    # Unit archive fixture, explicitly synthetic; real PostgreSQL test below uses
    # actual pg_dump from the already provisioned local PostgreSQL container.
    program=tmp_path/'synthetic_dump'
    program.write_text('#!/bin/sh\nprintf "SYNTHETIC DATABASE DUMP FOR UNIT TEST ONLY"\n')
    program.chmod(0o700)
    return program


class SyntheticCursor:
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def execute(self,query):self.query=query
    def fetchone(self):return ('on',) if 'SHOW' in self.query else ('TEST-SNAPSHOT',datetime.now(timezone.utc).isoformat())


class SyntheticDatabase:
    class Info:password=None
    info=Info()
    def set_session(self,**kw):assert kw['readonly'] is True
    def get_dsn_parameters(self):return {}
    def cursor(self):return SyntheticCursor()
    def rollback(self):pass


@pytest.fixture
def sealed(tmp_path,sources,certificate,dump_program):
    cert,key=certificate;root=tmp_path/'private-archive';root.mkdir(mode=0o700)
    coverage={category:['runtime','database'] for category in archive.CATEGORIES}
    receipt=archive.create_archive(root,runtime_roots={'runtime':sources},databases={'database':SyntheticDatabase()},
        certificate=cert,coverage=coverage,source_quiesced=True,coverage_confirmed=True,pg_dump_program=dump_program)
    return root,receipt,cert,key


def prepare(storage,sealed,period='fresh-2026'):
    root,receipt,cert,key=sealed
    at=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
    return restart.prepare(period,start_at=at,prepared_by='TEST ONLY reviewer',archive_root=root,
        archive_id=receipt['archive_id'],certificate=cert,private_key=key,storage=storage)


@pytest.fixture
def storage(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    return StorageService(tmp_path/'application',database_url='',mode='local')


def test_archive_roundtrip_preserves_learning_reports_losses_and_all_bytes(sealed,sources,tmp_path):
    root,receipt,cert,key=sealed
    verified=archive.verify_archive(root,receipt['archive_id'],certificate=cert,private_key=key)
    assert verified['status']=='VERIFIED_RESTORE_REVIEW'
    assert set(verified['manifest']['coverage'])==archive.CATEGORIES
    assert verified['manifest']['source_inventory']['runtime']==archive._inventory(sources)
    packed=tmp_path/'review.tar'
    archive._openssl(['cms','-decrypt','-binary','-inform','DER','-in',root/receipt['archive_id']/'archive.cms',
        '-recip',cert,'-inkey',key,'-out',packed])
    with tarfile.open(packed) as tar:
        for path in sources.iterdir():assert tar.extractfile('runtime/runtime/'+path.name).read()==path.read_bytes()
    assert stat_mode(root/receipt['archive_id'])==0o500
    with pytest.raises(PermissionError):(root/receipt['archive_id']/'archive.cms').write_bytes(b'overwrite')
    with pytest.raises(PermissionError):StorageService(root/receipt['archive_id'],database_url='',mode='local').write_json('receipt.json',{})


def stat_mode(path):return path.stat().st_mode&0o777


def test_new_accounts_are_empty_separate_and_leave_all_old_stores_unchanged(storage,sealed,sources):
    old={'cash':123,'positions':{'LEGACY':{'quantity':7}},'loss':-25000}
    for key in ('paper_trading/portfolio.json','autonomous_portfolio/portfolio.json','super_portfolio/state.json','learning/observations.json'):
        storage.write_json(key,old)
    before=archive._inventory(sources)
    bundle=prepare(storage,sealed)
    scoped=restart.AccountStorage('fresh-2026',storage)
    for family,capital in restart.CAPITALS.items():
        account=scoped.read_json(ledger.key(family))['account']
        assert account['cash']==capital and account['initial_cash']==capital
        assert account['positions']=={} and account['trades']==[]
        assert account['base_currency']=='NOK'
        assert account['opening_document']['capital_kind']=='NEW_SIMULATED_CAPITAL_NOT_BROKER_BALANCE'
    assert bundle['legacy_sales_created'] is False and bundle['learning_reset'] is False
    for key in ('paper_trading/portfolio.json','autonomous_portfolio/portfolio.json','super_portfolio/state.json','learning/observations.json'):
        assert storage.read_json(key)==old
    assert archive._inventory(sources)==before
    with pytest.raises(ValueError):scoped.read_json('paper_trading/portfolio.json')
    with pytest.raises(ValueError):restart.AccountStorage('missing',storage).read_json(ledger.key('paper'))


def test_restart_retries_cannot_reset_or_overwrite_existing_period(storage,sealed):
    bundle=prepare(storage,sealed)
    root,receipt,cert,key=sealed
    request=dict(start_at=bundle['start_at'],prepared_by='TEST ONLY reviewer',archive_root=root,
        archive_id=receipt['archive_id'],certificate=cert,private_key=key,storage=storage)
    assert restart.prepare('fresh-2026',**request)==bundle
    with pytest.raises(ValueError):restart.prepare('fresh-2026',**{**request,'prepared_by':'changed'})
    assert storage.read_json(restart._key('fresh-2026'))==bundle


def test_archive_is_required_and_wrong_key_or_missing_scope_stops(storage,sealed,certificate,sources,tmp_path):
    root,receipt,cert,key=sealed
    with pytest.raises((ValueError,FileNotFoundError)):
        restart.prepare('blocked',start_at=datetime.now(timezone.utc).isoformat(),prepared_by='test',
            archive_root=root,archive_id='missing',certificate=cert,private_key=key,storage=storage)
    assert storage.read_json(restart._key('blocked')) is None
    with pytest.raises(ValueError):archive.create_archive(tmp_path/'bad',runtime_roots={'runtime':sources},databases={},
        certificate=cert,coverage={},source_quiesced=True,coverage_confirmed=True)
    with pytest.raises(ValueError):archive.create_archive(sources/'archives',runtime_roots={'runtime':sources},databases={'db':SyntheticDatabase()},
        certificate=cert,coverage={k:['runtime'] for k in archive.CATEGORIES},source_quiesced=True,coverage_confirmed=True)


def test_production_activation_remains_blocked_and_tampering_cannot_import_legacy_cash(storage,sealed,monkeypatch):
    bundle=prepare(storage,sealed);scoped=restart.AccountStorage('fresh-2026',storage)
    doc=scoped.read_json(ledger.key('paper'))
    monkeypatch.setenv('APP_ENVIRONMENT','production');monkeypatch.setenv('ECONOMIC_PRODUCTION_ACTIVATION_ENABLED','true')
    approval=dict(approved_by='test',approval_ref='TEST ONLY must be blocked',family='paper',opening_sha256=doc['opening_sha256'],
        start_at=bundle['start_at'],approved_at=bundle['start_at'],scope='production')
    with pytest.raises(ValueError,match='Restart activation'):ledger.approve('paper',approval,storage=scoped)
    assert storage.read_json(restart._key('fresh-2026'))==bundle
    tampered=deepcopy(bundle);tampered['accounts']['paper']['account']['cash']=123
    storage.write_json(restart._key('fresh-2026'),tampered)
    with pytest.raises(ValueError):scoped.read_json(ledger.key('paper'))


def test_legacy_reset_apis_cannot_delete_any_data(monkeypatch):
    import paper_store,autonomous_portfolio
    monkeypatch.setattr(paper_store,'save_portfolio',lambda *_:pytest.fail('must not write'))
    monkeypatch.setattr(autonomous_portfolio,'_write',lambda *_:pytest.fail('must not write'))
    with pytest.raises(ValueError,match='sperret'):paper_store.reset_portfolio(100000)
    with pytest.raises(ValueError,match='sperret'):autonomous_portfolio.reset_portfolio('RESET')


def test_pg_full_database_archive_and_atomic_three_account_preparation(pg,tmp_path,sources,certificate,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    pg.write_json('learning/observations.json',{'TEST ONLY observations':81,'loss':-25000})
    import shlex
    from urllib.parse import urlsplit
    if shutil.which('pg_dump') and shutil.which('pg_restore'):
        dump_command=[shutil.which('pg_dump')];restore_command=[shutil.which('pg_restore')]
    else:
        # Find the container serving THIS fixture's localhost port; works for
        # both CI service names and the local cloud environment.
        port=str(urlsplit(pg.database_url).port or 5432)
        ids=subprocess.check_output(['docker','ps','--format','{{.ID}}'],text=True).split()
        matching=[]
        for identity in ids:
            mappings=json.loads(subprocess.check_output(['docker','inspect','--format',
                '{{json .NetworkSettings.Ports}}',identity],text=True))
            if any(binding['HostPort']==port for binding in mappings.get('5432/tcp',[]) or []):matching.append(identity)
        assert len(matching)==1,'A PostgreSQL client or the matching test container is required'
        prefix=['docker','exec','-i','-e','PGDATABASE','-e','PGUSER',
            '-e','PGHOST=/var/run/postgresql','-e','PGPORT=5432',matching[0]]
        dump_command=prefix+['pg_dump'];restore_command=prefix+['pg_restore']
    program=tmp_path/'pg_dump'
    program.write_text('#!/bin/sh\nexec '+shlex.join(dump_command)+' "$@"\n')
    program.chmod(0o700)
    cert,key=certificate;root=tmp_path/'archive';root.mkdir(mode=0o700)
    connection=pg._conn()
    try:
        receipt=archive.create_archive(root,runtime_roots={'runtime':sources},databases={'database':connection},
            certificate=cert,coverage={k:['runtime','database'] for k in archive.CATEGORIES},
            source_quiesced=True,coverage_confirmed=True,pg_dump_program=program)
    finally:connection.close()
    # A real restore into a newly created isolated test database proves that
    # the archived dump is reviewable, beyond just being nonempty/checksummed.
    import uuid
    from psycopg2 import sql
    import psycopg2
    from urllib.parse import urlsplit,urlunsplit
    packed=tmp_path/'restore.tar'
    archive._openssl(['cms','-decrypt','-binary','-inform','DER','-in',root/receipt['archive_id']/'archive.cms',
        '-recip',cert,'-inkey',key,'-out',packed])
    with tarfile.open(packed) as tar:dump=tar.extractfile('databases/database.dump').read()
    assert dump.startswith(b'PGDMP')
    restored='restart_restore_'+uuid.uuid4().hex
    admin=pg._conn();admin.autocommit=True
    try:
        with admin.cursor() as cur:cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(restored)))
        from psycopg2.extensions import parse_dsn
        client_env={**os.environ}
        for k,v in parse_dsn(pg.database_url).items():client_env['PGDATABASE' if k=='dbname' else 'PG'+k.upper()]=v
        result=subprocess.run(restore_command+['--clean','--if-exists','--exit-on-error','--dbname='+restored],
            input=dump,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=client_env)
        assert result.returncode==0,result.stderr.decode()
        parts=urlsplit(pg.database_url);connection=psycopg2.connect(urlunsplit(parts._replace(path='/'+restored)))
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT payload FROM app_kv_store WHERE name='learning/observations.json'")
                assert json.loads(cur.fetchone()[0])['loss']==-25000
        finally:connection.close()
    finally:
        with admin.cursor() as cur:cur.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(restored)))
        admin.close()
    sealed=(root,receipt,cert,key)
    bundle=prepare(pg,sealed)
    assert all(a['status']=='DRAFT' for a in bundle['accounts'].values())
    assert pg.read_json('learning/observations.json')['loss']==-25000
    assert restart.report('fresh-2026',storage=pg,at=datetime.fromisoformat(bundle['start_at']))['accounts']['paper']['new_period']['cash_nok']==100000


def test_declared_paper_capital_matches_original_repository_configuration():
    from trading_settings import DEFAULT_RULES
    from paper_store import DEFAULT_PORTFOLIO
    assert restart.CAPITALS['paper']==DEFAULT_RULES['start_cash']==DEFAULT_PORTFOLIO['cash']==100000


def test_bundle_creation_failure_leaves_no_partial_accounts(storage,sealed,monkeypatch):
    def reject(key,transform,default=None):
        candidate=transform(default)
        assert set(candidate['accounts'])==set(restart.CAPITALS)
        raise OSError('TEST ONLY write interruption')
    monkeypatch.setattr(storage,'mutate_json',reject)
    with pytest.raises(OSError):prepare(storage,sealed)
    assert storage.read_json(restart._key('fresh-2026')) is None
    assert not any(storage.read_json(ledger.key(f)) for f in restart.CAPITALS)


def test_runtime_changes_abort_archive_without_a_valid_receipt(tmp_path,sources,certificate,dump_program,monkeypatch):
    real=archive._pg_dump
    def changed(*a,**kw):
        result=real(*a,**kw)
        (sources/'learning.json').write_text('TEST ONLY changed while archiving')
        return result
    monkeypatch.setattr(archive,'_pg_dump',changed)
    root=tmp_path/'private';root.mkdir(mode=0o700)
    with pytest.raises(ValueError,match='Runtime changed'):
        archive.create_archive(root,runtime_roots={'runtime':sources},databases={'database':SyntheticDatabase()},
            certificate=certificate[0],coverage={k:['runtime','database'] for k in archive.CATEGORIES},
            source_quiesced=True,coverage_confirmed=True,pg_dump_program=dump_program)
    assert not list(root.glob('*/receipt.json'))


def test_checksum_corruption_stops_restart_preparation(storage,sealed):
    root,receipt,cert,key=sealed
    target=root/receipt['archive_id']/'archive.cms'
    target.chmod(0o600);target.write_bytes(b'TEST ONLY corrupted encrypted archive');target.chmod(0o400)
    with pytest.raises(ValueError,match='checksum'):prepare(storage,sealed)
    assert storage.read_json(restart._key('fresh-2026')) is None


def test_new_model_fill_cannot_change_archive_learning_or_legacy_holdings(storage,sealed,sources):
    from test_portfolio_accounting import fill
    before=archive._inventory(sources)
    old={'cash':12,'positions':{'LEGACY':{'quantity':77}},'loss':-25000,'learning_weight':.7}
    storage.write_json('paper_trading/portfolio.json',old)
    storage.write_json('learning/observations.json',{'count':81,'weights':[.3,.7]})
    bundle=prepare(storage,sealed)
    scoped=restart.AccountStorage('fresh-2026',storage)
    doc=scoped.read_json(ledger.key('paper'));at=bundle['start_at']
    ledger.approve('paper',dict(approved_by='TEST ONLY',approval_ref='TEST ONLY isolated execution',family='paper',
        opening_sha256=doc['opening_sha256'],start_at=at,approved_at=at,scope='test'),storage=scoped)
    request=fill(at=at)
    ledger.settle('paper',request,storage=scoped)
    ledger.settle('paper',request,storage=scoped)
    account=scoped.read_json(ledger.key('paper'))['account']
    assert account['cash']==89990
    assert set(account['positions'])=={'TEST'}
    assert len(account['trades'])==1
    assert scoped.read_json(ledger.key('autonomy'))['account']['cash']==500000
    assert storage.read_json('paper_trading/portfolio.json')==old
    assert storage.read_json('learning/observations.json')=={'count':81,'weights':[.3,.7]}
    assert archive._inventory(sources)==before
    root,receipt,cert,key=sealed
    assert archive.verify_archive(root,receipt['archive_id'],certificate=cert,private_key=key)['status']=='VERIFIED_RESTORE_REVIEW'
    storage.write_json('paper_trading/portfolio.json',{'cash':1,'positions':{'OLD_NEW':{'quantity':99}}})
    assert scoped.read_json(ledger.key('paper'))['account']['cash']==89990
    assert set(scoped.read_json(ledger.key('paper'))['account']['positions'])=={'TEST'}


def test_plan_has_no_implicit_period_date_or_legacy_capital_fallback():
    with pytest.raises(ValueError):restart.plan('new',start_at=None,prepared_by='test')
    with pytest.raises(ValueError):restart.plan('../old',start_at=datetime.now(timezone.utc).isoformat(),prepared_by='test')


def test_new_default_capital_cannot_reprice_an_existing_period(storage,sealed,monkeypatch):
    bundle=prepare(storage,sealed)
    monkeypatch.setitem(restart.CAPITALS,'paper',200000.0)
    # Previously documented openings are authoritative even if future policy
    # chooses another starting amount. No historical balance may be repriced.
    scoped=restart.AccountStorage('fresh-2026',storage)
    assert scoped.read_json(ledger.key('paper'))['account']['initial_cash']==100000
    snapshot=restart.report('fresh-2026',storage=storage,at=datetime.fromisoformat(bundle['start_at']))
    assert snapshot['accounts']['paper']['new_period']['opening_nav_nok']==100000
