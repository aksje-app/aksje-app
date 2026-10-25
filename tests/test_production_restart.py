"""Production-mode lifecycle on disposable local PostgreSQL; no live data."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,os,shlex,shutil,subprocess,uuid
from urllib.parse import urlsplit,urlunsplit
import pytest
from test_revision_trade_postgres import pg
from test_simulation_restart import sources,certificate
from test_restart_trading import evidence,candidate,paper_signal
from services import production_restart as control,simulation_restart as restart,simulation_archive as archive
from services import portfolio_accounting as ledger,restart_trading as trading,production_routing as routing
from services.economic_opening import digest
from services.economic_ledger import reconcile
from services import autonomy_nok_companion as companion
REAL_PREPARE,REAL_COMPLETE=companion.prepare,companion.complete


@pytest.fixture
def ready(pg,sources,certificate,tmp_path,monkeypatch):
    cert,key=certificate
    monkeypatch.setenv('APP_ENVIRONMENT','production');monkeypatch.setenv('NOK_DEPLOYMENT_ID','ISOLATED_LOCAL_PG_ONLY')
    monkeypatch.setenv('NOK_APPROVAL_CERTIFICATE',str(cert));monkeypatch.setenv('NOK_APPROVAL_CERT_SHA256',hashlib.sha256(cert.read_bytes()).hexdigest())
    monkeypatch.setenv('PAPER_TRADING_ENABLED','true')
    for module in (control,restart,ledger,trading):monkeypatch.setattr(module,'get_storage_service',lambda:pg)
    from trading_settings import DEFAULT_RULES
    from autonomous_portfolio import AutonomousParameters
    from super_portfolio import SuperPortfolioConfig
    settings={'paper':deepcopy(DEFAULT_RULES),'autonomy':asdict(AutonomousParameters()),'super_portfolio':asdict(SuperPortfolioConfig())}
    pg.write_json('settings/trading_rules.json',settings['paper'])
    pg.write_json('autonomous_portfolio/parameters.json',settings['autonomy'])
    pg.write_json('learning/observations.json',{'observations':81,'loss':-25000})
    for name in ('paper_trading/portfolio.json','autonomous_portfolio/portfolio.json','super_portfolio/state.json'):
        pg.write_json(name,{'cash':123,'positions':{'OLD':{'quantity':7}},'realized_pnl':-25000})
    root=tmp_path/'archives';root.mkdir(mode=0o700)
    if shutil.which('pg_dump') and shutil.which('pg_restore'):
        dump=[shutil.which('pg_dump')];restore=[shutil.which('pg_restore')]
    else:
        ids=subprocess.check_output(['docker','ps','--format','{{.ID}}'],text=True).split()
        matches=[]
        for identity in ids:
            ports=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .NetworkSettings.Ports}}',identity],text=True))
            if any(b['HostPort']==str(urlsplit(pg.database_url).port or 5432) for b in ports.get('5432/tcp',[]) or []):matches.append(identity)
        assert len(matches)==1
        prefix=['docker','exec','-i','-e','PGDATABASE','-e','PGUSER','-e','PGHOST=/var/run/postgresql','-e','PGPORT=5432',matches[0]]
        dump=prefix+['pg_dump'];restore=prefix+['pg_restore']
    programs=[]
    for name,command in [('dump',dump),('restore',restore)]:
        program=tmp_path/name;program.write_text('#!/bin/sh\nexec '+shlex.join(command)+' "$@"\n');program.chmod(0o700);programs.append(program)
    conn=pg._conn()
    try:
        receipt=archive.create_archive(root,runtime_roots={'runtime':sources},databases={'database':conn},certificate=cert,
            coverage={c:['runtime','database'] for c in archive.CATEGORIES},source_quiesced=True,coverage_confirmed=True,pg_dump_program=programs[0])
    finally:conn.close()
    import psycopg2
    from psycopg2 import sql
    admin=pg._conn();admin.autocommit=True;dbname='nok_restore_'+uuid.uuid4().hex
    with admin.cursor() as cur:cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(dbname)))
    target=urlunsplit(urlsplit(pg.database_url)._replace(path='/'+dbname))
    destination=tmp_path/'restored'
    try:
        review=archive.restore_drill(root,receipt['archive_id'],certificate=cert,private_key=key,destination=destination,
            database_targets={'database':target},pg_restore_program=programs[1])
        start=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        bundle=restart.prepare('production-ready',start_at=start,prepared_by='ISOLATED operator',archive_root=root,
            archive_id=receipt['archive_id'],certificate=cert,private_key=key,storage=pg)
        import time
        time.sleep(max(0,(datetime.fromisoformat(start)-datetime.now(timezone.utc)).total_seconds()))
        cost=dict(components_per_fill={'brokerage_nok':6,'fx_cost_nok':4,'other_nok':0},source_ref='ISOLATED documented simulation policy')
        from services.trading_costs import super_portfolio_proposal
        costs={f:deepcopy(cost) for f in restart.CAPITALS}
        costs['super_portfolio']=super_portfolio_proposal(settings['super_portfolio'],source_ref='ISOLATED existing 10bps',
            fx_component={'fixed_nok':4,'source_ref':'ISOLATED documented FX charge'})
        def isolated_prepare(chosen,run_id,candidates,*,storage=None):
            value=dict(candidates=deepcopy(candidates),settings=deepcopy(settings['autonomy']),market_snapshot={},parallel_strategy_run={},technical_contribution={},portfolio_before={})
            return pg.write_json_immutable(companion.preparation_key(chosen,run_id),value)
        monkeypatch.setattr(companion,'prepare',isolated_prepare)
        monkeypatch.setattr(companion,'complete',lambda *a,**kw:{'learning_trades':[],'learning_decisions':[]})
        yield dict(pg=pg,bundle=bundle,review=review,root=root,cert=cert,key=key,destination=destination,settings=settings,cost=cost,costs=costs,
            sources=sources,source_files=archive._inventory(sources),target=target,restore_program=programs[1])
    finally:
        with admin.cursor() as cur:
            cur.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(dbname)))
        admin.close()


def bound_cost_evidence(row,policy):
    row=deepcopy(row)
    row['cost_source_ref']=policy['source_ref']
    if 'schema' in policy:
        row.pop('cost_components',None);row['cost_policy']=deepcopy(policy)
    else:row.setdefault('cost_components',deepcopy(policy['components_per_fill']))
    return row


def grant(ready,family='paper'):
    r=ready
    payload=control.request(r['bundle']['period_id'],family,actor='ISOLATED operator',approval_ref='ISOLATED exact approval',
        at=datetime.now(timezone.utc).isoformat(),restore_review=r['review'],settings=r['settings'][family],cost_policy=r['costs'][family])
    return control.sign(payload,r['key'])


def activate(ready,family='paper',signed=None):
    r=ready;signed=signed or grant(r,family)
    return control.activate(signed,confirmation=digest(signed['payload']),archive_root=r['root'],certificate=r['cert'],
        private_key=r['key'],restore_destination=r['destination'])


def direct(ready,family,run,at,inputs,ev=None):
    r=ready;period=r['bundle']['period_id']
    common=dict(period_id=period,run_id=run,at=at,evidence=ev or evidence(at),
        account_ref=trading.account_reference(period,family),storage=r['pg'])
    common['evidence']={ticker:bound_cost_evidence(row,r['costs'][family]) for ticker,row in common['evidence'].items()}
    if family=='paper':return trading.paper(**common,rules=r['settings'][family],signals=inputs)
    if family=='autonomy':return trading.autonomy(**common,parameters=r['settings'][family],candidates=inputs)
    pipeline=dict(run_id=run,created_at=at,candidates=inputs,market_activation_levels={'USA':'PRODUCTION'},regime_fit_score=70)
    return trading.super_portfolio(**common,config=r['settings'][family],pipeline=pipeline,rebalance_policy='FORCE')


def doc(r,family):return restart.AccountStorage(r['bundle']['period_id']).read_json(ledger.key(family))


@pytest.mark.parametrize('family',list(restart.CAPITALS))
def test_production_approved_full_trade_stop_recover_and_preserve(ready,family):
    r=ready;activate(r,family);period=r['bundle']['period_id']
    assert os.environ['APP_ENVIRONMENT']=='production'
    assert doc(r,family)['account']['cash']==restart.CAPITALS[family]
    assert doc(r,family)['account']['positions']=={}
    # Real ordinary strategies, documented USD/NOK and explicit nonzero costs.
    start=datetime.now(timezone.utc);at=start.isoformat();second=(start+timedelta(days=3)).isoformat();third=(start+timedelta(days=4)).isoformat()
    if family=='paper':
        inputs=[dict(ticker='TEST',operation='BUY',amount_nok=10010,confidence=90)]
        direct(r,family,'buy',at,inputs)
        direct(r,family,'addition',at,[dict(ticker='TEST',operation='BUY',amount_nok=5010,confidence=90)])
        assert doc(r,family)['account']['positions']['TEST']['quantity']==15
        direct(r,family,'partial',at,[dict(ticker='TEST',operation='SELL',sell_pct=20)],evidence(at,110,11))
        assert doc(r,family)['account']['positions']['TEST']['quantity']==12
        direct(r,family,'final',at,[dict(ticker='TEST',operation='SELL')],evidence(at,110,11))
    else:
        first=(start+timedelta(days=(7-start.weekday())%7 or 7)).replace(hour=15,minute=0,second=0,microsecond=0)
        at=first.isoformat();second=(first+timedelta(days=3)).isoformat();third=(first+timedelta(days=4)).isoformat()
        direct(r,family,'search',at,[candidate(at)])
        inputs=[candidate(second)]
        direct(r,family,'buy',second,inputs)
        assert doc(r,family)['account']['positions']
        # No candidate is required to supervise an existing Autonomi position.
        direct(r,family,'risk',third,[] if family=='autonomy' else [candidate(third,price=80)],evidence(third,80))
        assert doc(r,family)['account']['positions']=={}
    account=doc(r,family)['account'];assert reconcile(account)==[] and account['realized_pnl']!=0
    before=deepcopy(doc(r,family));confirmation=digest(dict(period_id=period,family=family,action='STOP',deployment_id=control.installation()))
    assert control.stop(period,family,actor='operator',reason='ISOLATED rollback drill',confirmation=confirmation)=='PAUSED'
    with pytest.raises(ValueError,match='stopped'):direct(r,family,'blocked',third,[])
    assert doc(r,family)==before
    assert control.selected(family,require_running=False)['pointer']['period_id']==period
    confirmation=digest(dict(period_id=period,family=family,action='RESUME',deployment_id=control.installation()))
    assert control.stop(period,family,actor='operator',reason='ISOLATED recovery',confirmation=confirmation,resume=True)=='RUNNING'
    # New process/storage instance sees the same authoritative journal.
    from services.storage_service import StorageService
    restarted=StorageService(r['pg'].base_dir,database_url=r['pg'].database_url,mode='postgres',allow_local_fallback=False)
    assert restart.AccountStorage(period,restarted).read_json(ledger.key(family))==before
    assert archive._inventory(r['sources'])==r['source_files']
    assert r['pg'].read_json('learning/observations.json')=={'observations':81,'loss':-25000}
    for name in ('paper_trading/portfolio.json','autonomous_portfolio/portfolio.json','super_portfolio/state.json'):
        assert r['pg'].read_json(name)['realized_pnl']==-25000


@pytest.mark.parametrize('failure',['signature','capital','environment','deployment','opening','archive','confirmation','restore-file','certificate','fallback'])
def test_invalid_approval_or_archive_cannot_activate(ready,failure,monkeypatch):
    r=ready;signed=grant(r);confirmation=digest(signed['payload'])
    if failure in {'capital','environment','deployment','opening','archive'}:
        key={'capital':'capital_nok','environment':'environment','deployment':'deployment_id','opening':'opening_sha256','archive':'archive'}[failure]
        signed['payload'][key]='INVALID'
        signed=control.sign(signed['payload'],r['key']);confirmation=digest(signed['payload'])
    if failure=='signature':signed['signature']='AAAA'
    if failure=='confirmation':confirmation='wrong'
    if failure=='restore-file':(r['destination']/'payload'/'runtime'/'runtime'/'learning.json').write_text('CORRUPTED')
    if failure=='certificate':monkeypatch.setenv('NOK_APPROVAL_CERT_SHA256','wrong')
    if failure=='fallback':r['pg'].allow_local_fallback=True
    before=r['pg'].read_json(restart._key(r['bundle']['period_id']))
    with pytest.raises((ValueError,TypeError,KeyError)):
        control.activate(signed,confirmation=confirmation,archive_root=r['root'],certificate=r['cert'],private_key=r['key'],restore_destination=r['destination'])
    assert r['pg'].read_json(restart._key(r['bundle']['period_id']))==before
    assert r['pg'].read_json(control.route_key('paper')) is None


def test_production_atomic_retry_interruption_and_duplicate_delivery(ready):
    r=ready;activate(r);at=datetime.now(timezone.utc).isoformat()
    args=dict(period_id=r['bundle']['period_id'],family='paper',run_id='stable-job',at=at,evidence=evidence(at),
        settings=r['settings']['paper'],strategy_input={},account_ref=trading.account_reference(r['bundle']['period_id'],'paper'))
    args['evidence']['TEST']['cost_source_ref']=r['cost']['source_ref']
    def operation(session):session.fill('TEST','BUY',10,100,'ISOLATED');return {'ok':True}
    before=doc(r,'paper')
    def interrupted(session):operation(session);raise RuntimeError('ISOLATED interruption')
    with pytest.raises(RuntimeError):trading.run(**args,operation=interrupted)
    assert doc(r,'paper')==before
    with ThreadPoolExecutor(max_workers=3) as pool:assert all(x=={'ok':True} for x in pool.map(lambda _:trading.run(**args,operation=operation),range(3)))
    assert len(doc(r,'paper')['account']['trades'])==1
    with pytest.raises(ValueError):trading.run(**{**args,'settings':{}},operation=operation)


@pytest.mark.parametrize('family',list(restart.CAPITALS))
def test_dry_run_production_draft_does_not_activate_or_persist(ready,family):
    r=ready;at=datetime.now(timezone.utc).isoformat();before=r['pg'].read_json(restart._key(r['bundle']['period_id']))
    inputs=[dict(ticker='TEST',operation='BUY',amount_nok=10010,confidence=90)] if family=='paper' else [candidate(at)]
    if family=='super_portfolio':inputs=dict(run_id='preview-pipeline',created_at=at,candidates=inputs,market_activation_levels={'USA':'PRODUCTION'},regime_fit_score=70)
    result=trading.preview(period_id=r['bundle']['period_id'],family=family,at=at,evidence=evidence(at),settings=r['settings'][family],strategy_input=inputs)
    assert result['mode']=='DRY_RUN_NO_ORDERS_NO_PERSISTENT_WRITES'
    assert r['pg'].read_json(restart._key(r['bundle']['period_id']))==before
    assert control.selected(family) is None and doc(r,family)['status']=='DRAFT'
    assert os.environ['APP_ENVIRONMENT']=='production'


@pytest.mark.parametrize('family',list(restart.CAPITALS))
def test_ordinary_scheduler_entrypoints_route_selected_account(ready,family,monkeypatch):
    r=ready;activate(r,family)
    def provider(ticker,*,currency=None,quote=None,fx_quote=None,at,cost_policy):
        return bound_cost_evidence(evidence(at)['TEST'],cost_policy)
    monkeypatch.setattr(routing,'market_evidence',provider)
    if family=='paper':
        import trading_engine as engine
        ok,_=engine.paper_buy('TEST',100,90,amount_override=10010,trade_context={'run_id':'ordinary'})
        assert ok
        assert engine.load_portfolio()['economic_period_id']==r['bundle']['period_id']
        assert engine.portfolio_value()==pytest.approx(99990)
        from services.economic_accounting_audit import audit
        assert audit(engine.load_portfolio())['status']=='BESTÅTT'
    elif family=='autonomy':
        import autonomous_portfolio as engine
        result=engine.run_autonomous_cycle([],run_id='ordinary')
        assert result['family']=='autonomy'
        assert result['performance']['equity']==500000 and result['performance']['total_return_pct']==0
        assert engine.load_portfolio()['economic_period_id']==r['bundle']['period_id']
    else:
        import super_portfolio as engine
        at=datetime.now(timezone.utc).isoformat()
        pipeline=dict(run_id='ordinary',created_at=at,candidates=[],market_activation_levels={'USA':'PRODUCTION'},regime_fit_score=70)
        result=engine.run_scheduled_shadow_cycle(pipeline)
        assert result['family']=='super_portfolio'
        assert engine.load_state()['economic_period_id']==r['bundle']['period_id']
    assert any(e['kind']=='STRATEGY_RUN' for e in doc(r,family)['events'])


def test_partial_activation_failure_retries_without_reset(ready,monkeypatch):
    r=ready;signed=grant(r);original=r['pg'].write_json_immutable
    monkeypatch.setattr(r['pg'],'write_json_immutable',lambda *a,**k:(_ for _ in ()).throw(OSError('ISOLATED after account approval')))
    with pytest.raises(OSError):activate(r,signed=signed)
    before=doc(r,'paper');assert before['status']=='ACTIVE'
    assert control.selected('paper') is None
    monkeypatch.setattr(r['pg'],'write_json_immutable',original)
    activate(r,signed=signed)
    assert doc(r,'paper')==before and control.selected('paper') is not None


def test_ordinary_retries_use_receipt_during_provider_outage(ready,monkeypatch):
    r=ready
    for family in restart.CAPITALS:activate(r,family)
    def provider(ticker,*,currency=None,quote=None,fx_quote=None,at,cost_policy):
        return bound_cost_evidence(evidence(at)['TEST'],cost_policy)
    monkeypatch.setattr(routing,'market_evidence',provider)
    import trading_engine as paper
    import autonomous_portfolio as autonomy
    import super_portfolio as sp
    command=dict(confidence=90,amount_override=10010,trade_context={'run_id':'lost-ack'})
    first=paper.paper_buy('TEST',100,**command)
    ap=autonomy.run_autonomous_cycle([],run_id='autonomy-lost-ack')
    at=datetime.now(timezone.utc).isoformat();pipeline=dict(run_id='pipeline-lost-ack',created_at=at,candidates=[],market_activation_levels={'USA':'PRODUCTION'},regime_fit_score=70)
    sp.run_scheduled_shadow_cycle(pipeline)
    # Same broad feed now uses the existing risk-only strategy, no native ledger.
    watch=sp.run_scheduled_shadow_cycle(pipeline)
    assert watch['state']=='NOT_DUE' and watch['reason']=='NO_POSITIONS'
    before=r['pg'].read_json(restart._key(r['bundle']['period_id']))
    monkeypatch.setattr(routing,'market_evidence',lambda *a,**k:(_ for _ in ()).throw(OSError('ISOLATED provider down')))
    assert paper.paper_buy('TEST',100,**command)==first
    assert autonomy.run_autonomous_cycle([],run_id='autonomy-lost-ack')['already_committed']
    assert sp.run_scheduled_shadow_cycle(pipeline)['already_committed']
    assert r['pg'].read_json(restart._key(r['bundle']['period_id']))==before
    with pytest.raises(ValueError,match='reused'):paper.paper_buy('TEST',100,**{**command,'amount_override':999})


def test_superportfolio_risk_surveillance_books_only_authoritative_journal(ready,monkeypatch):
    r=ready;family='super_portfolio';activate(r,family)
    first=datetime.now(timezone.utc)
    first=(first+timedelta(days=(7-first.weekday())%7 or 7)).replace(hour=15,minute=0,second=0,microsecond=0)
    second=first+timedelta(days=3);third=second+timedelta(minutes=16)
    direct(r,family,'search',first.isoformat(),[candidate(first.isoformat())])
    direct(r,family,'buy',second.isoformat(),[candidate(second.isoformat())])
    assert doc(r,family)['account']['positions']
    def provider(ticker,*,currency=None,quote=None,fx_quote=None,at,cost_policy):
        return bound_cost_evidence(evidence(at,80)['TEST'],cost_policy)
    monkeypatch.setattr(routing,'market_evidence',provider)
    import super_portfolio as sp
    old=r['pg'].read_json('super_portfolio/state.json')
    result=sp.run_lightweight_stop_surveillance(now=third)
    assert result['changes'] and doc(r,family)['account']['positions']=={}
    assert doc(r,family)['account']['realized_pnl']<0
    assert reconcile(doc(r,family)['account'])==[]
    assert r['pg'].read_json('super_portfolio/state.json')==old


@pytest.mark.parametrize('failure',['stale','fx','cost','future'])
def test_production_rejects_invalid_execution_without_writes(ready,failure):
    r=ready;activate(r);at=datetime.now(timezone.utc).isoformat();ev=evidence(at)
    ev['TEST']['cost_source_ref']=r['cost']['source_ref']
    if failure=='stale':ev['TEST']['observed_at']=(datetime.fromisoformat(at)-timedelta(minutes=16)).isoformat()
    if failure=='future':ev['TEST']['observed_at']=(datetime.fromisoformat(at)+timedelta(minutes=2)).isoformat()
    if failure=='fx':ev['TEST']['fx_quote']=None
    if failure=='cost':ev['TEST']['cost_components']['fx_cost_nok']=999
    before=doc(r,'paper')
    with pytest.raises(ValueError):direct(r,'paper','invalid-proof',at,[dict(ticker='TEST',operation='BUY',amount_nok=10010)],ev)
    assert doc(r,'paper')==before


def test_fresh_cached_raw_quote_and_fx_survive_provider_outage(monkeypatch):
    from scanner_fresh_quote import fresh_paper_buy_quote
    import scanner_fresh_quote
    at=datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(scanner_fresh_quote,'fresh_paper_buy_quote',lambda *a,**k:(_ for _ in ()).throw(OSError('ISOLATED no network')))
    quote=dict(price=100,market_data_at=at,source='yfinance 5m Close',adjustment='raw')
    fx=evidence(at)['TEST']['fx_quote'];policy={'components_per_fill':{'brokerage_nok':6,'fx_cost_nok':4,'other_nok':0},'source_ref':'ISOLATED policy'}
    row=routing.market_evidence('TEST',currency='USD',quote=quote,fx_quote=fx,at=at,cost_policy=policy)
    assert row['price']==100 and row['fx_quote']['rate']==10
    for broken in ({},dict(quote,market_data_at=(datetime.fromisoformat(at)-timedelta(minutes=16)).isoformat())):
        with pytest.raises(OSError):routing.market_evidence('TEST',currency='USD',quote=broken,fx_quote=fx,at=at,cost_policy=policy)


def test_archive_restore_rejects_existing_target_and_keeps_original_files(ready):
    r=ready
    with pytest.raises(ValueError,match='new'):
        archive.restore_drill(r['root'],r['review']['archive']['archive_id'],certificate=r['cert'],private_key=r['key'],destination=r['destination'],database_targets={'database':r['target']},pg_restore_program=r['restore_program'])
    import psycopg2
    connection=psycopg2.connect(r['target'])
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT payload FROM app_kv_store WHERE name='learning/observations.json'")
            value=cur.fetchone()[0];value=json.loads(value) if isinstance(value,str) else value
            assert value['loss']==-25000 and value['observations']==81
    finally:connection.close()
    assert archive._inventory(r['sources'])==r['source_files']


def test_live_dry_run_uses_actual_adapter_and_never_persists(ready,monkeypatch):
    r=ready;calls=[]
    def provider(ticker,*,currency=None,quote=None,fx_quote=None,at,cost_policy):
        calls.append(ticker);return bound_cost_evidence(evidence(at)['TEST'],cost_policy)
    monkeypatch.setattr(routing,'market_evidence',provider)
    before=doc(r,'paper')
    result=routing.live_preview(r['bundle']['period_id'],'paper',strategy_input=[dict(ticker='TEST',operation='BUY',amount_nok=10010,confidence=90)],cost_policy=r['cost'],storage=r['pg'])
    assert calls==['TEST'] and result['account']['new_period']['positions']['TEST']['quantity']==10
    assert doc(r,'paper')==before and control.selected('paper') is None


def test_documented_economic_event_requires_exact_operator_confirmation(ready):
    r=ready;activate(r);period=r['bundle']['period_id'];at=datetime.now(timezone.utc).isoformat()
    event=dict(type='DEPOSIT',event_id='ISOLATED deposit',at=at,amount_nok=10000,valuation_marks={},source_ref='ISOLATED approved additional simulation capital',
        cost_currency='NOK',cost_source_ref='ISOLATED zero costs',cost_components=dict(brokerage_nok=0,fx_cost_nok=0,other_nok=0))
    confirmation=digest(dict(period_id=period,family='paper',event=event,actor='ISOLATED operator',deployment_id=control.installation()))
    before=doc(r,'paper')
    with pytest.raises(ValueError):control.economic_event(period,'paper',event,actor='ISOLATED operator',confirmation='wrong')
    assert doc(r,'paper')==before
    result=control.economic_event(period,'paper',event,actor='ISOLATED operator',confirmation=confirmation)
    assert result['account']['cash']==110000
    assert ledger.report('paper',storage=restart.AccountStorage(period),at=datetime.fromisoformat(at))['new_period']['period_net_pnl_nok']==0


def test_request_cannot_silently_change_existing_strategy(ready):
    r=ready
    with pytest.raises(ValueError,match='unchanged'):
        control.request(r['bundle']['period_id'],'paper',actor='ISOLATED operator',approval_ref='ISOLATED',at=datetime.now(timezone.utc).isoformat(),
            restore_review=r['review'],settings={**r['settings']['paper'],'position_size_pct':99},cost_policy=r['cost'])


def test_inventory_cli_outputs_only_to_new_private_files(tmp_path):
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1];config=tmp_path/'config.json';config.write_text('{}')
    output=tmp_path/'inventory.json'
    args=[sys.executable,str(root/'scripts/production_restart.py'),'inventory','--config',str(config),'--output',str(output)]
    result=subprocess.run(args,cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    inventory=json.loads(output.read_text())
    assert inventory['coverage_confirmed'] is False and inventory['required_operator_review']
    assert output.stat().st_mode & 0o077 == 0
    previous=output.read_bytes()
    result=subprocess.run(args,cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode!=0 and output.read_bytes()==previous


def test_single_legacy_runtime_file_is_inventoried_and_archivable(tmp_path):
    path=tmp_path/'paper_portfolio.json';path.write_text('{"historical_loss":-25000}')
    assert archive._inventory(path)=={'paper_portfolio.json':archive.sha(path)}


@pytest.mark.parametrize('source',['runtime','database','older-period'])
def test_activation_blocks_sources_changed_since_archive(ready,source):
    r=ready;signed=grant(r)
    if source=='runtime':(r['sources']/'learning.json').write_text('{"observations":999}')
    elif source=='database':r['pg'].write_json('learning/observations.json',{'observations':999,'loss':-25000})
    else:r['pg'].write_json('simulation_restarts/OLDER/bundle.json',{'historical_loss':-999})
    before=doc(r,'paper')
    with pytest.raises(ValueError,match='changed'):activate(r,signed=signed)
    assert doc(r,'paper')==before and control.selected('paper') is None


def test_real_upstream_contribution_and_learning_continue_with_new_book(ready,monkeypatch):
    from types import SimpleNamespace
    import autonomous_portfolio as ap
    import paper_trading
    import learning_runtime
    from services.autonomy_technical_contribution_service import AutonomyTechnicalContributionService
    r=ready;activate(r,'autonomy');chosen=control.selected('autonomy');at=datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(companion,'prepare',REAL_PREPARE);monkeypatch.setattr(companion,'complete',REAL_COMPLETE)
    monkeypatch.setattr(paper_trading,'load_portfolio',lambda:{'cash':0,'positions':{}})
    row=candidate(at);row['investment_score']=80
    snapshot=SimpleNamespace(to_dict=lambda:{'snapshot_id':'ISOLATED snapshot','candidates':[row]})
    saves=[]
    monkeypatch.setattr(ap,'get_market_snapshot_service',lambda:SimpleNamespace(build_market_snapshot=lambda *a,**k:snapshot,save=lambda value:saves.append(value)))
    monkeypatch.setattr(ap,'_evaluate_parallel_strategies_isolated',lambda *a,**k:{'decisions':[dict(ticker='TEST',strategy_family='technical',strategy_status='PRODUCTION',strategy_version_id='technical_benchmark@legacy-1.0.0',action='BUY',score=9,confidence=90)]})
    service=AutonomyTechnicalContributionService.__new__(AutonomyTechnicalContributionService)
    service.policy=lambda:service.default_policy();service.events=SimpleNamespace(append=lambda *a,**k:None)
    monkeypatch.setattr(ap,'get_autonomy_technical_contribution_service',lambda:service)
    monkeypatch.setattr(ap,'_append_audit',lambda *a,**k:None)
    monkeypatch.setattr(ap,'_notification',lambda *a,**k:{'status':'ISOLATED_NO_SEND'})
    def read(path,default=None):return r['pg'].read_json(ap._PERSISTENT_PATH_KEYS[path],deepcopy(default))
    def write(path,value):
        assert path not in {ap.PORTFOLIO_PATH,ap.TRADES_PATH,ap.PERFORMANCE_PATH,ap.EQUITY_HISTORY_PATH}
        r['pg'].write_json(ap._PERSISTENT_PATH_KEYS[path],value)
    monkeypatch.setattr(ap,'_read',read);monkeypatch.setattr(ap,'_write',write)
    learning=ap.default_learning_portfolio(ap.AutonomousParameters())
    learning['closed_positions']=[{'ticker':'OLD','pnl':-500,'observation_days':60}]
    r['pg'].write_json(ap._PERSISTENT_PATH_KEYS[ap.LEARNING_PORTFOLIO_PATH],learning)
    r['pg'].write_json(ap._PERSISTENT_PATH_KEYS[ap.LEARNING_OBSERVATIONS_PATH],[dict(observation_id='OLD',ticker='OLD',status='CLOSED',entry_price=100,last_price=80,return_pct=-20)])
    mirrored=[];synced=[];captures=[]
    monkeypatch.setattr(ap,'get_strategy_account_service',lambda:SimpleNamespace(sync_legacy_account=lambda identity,*a,**k:(synced.append(identity) or {'account_id':identity}),metrics=lambda *a:{}))
    monkeypatch.setattr(ap,'get_simulated_execution_service',lambda:SimpleNamespace(mirror_legacy_trade=lambda **k:(mirrored.append(k) or {})))
    monkeypatch.setattr(learning_runtime,'capture_autonomy',lambda *a,**k:captures.append(k))
    prepared=companion.prepare(chosen,'upstream',[row],storage=r['pg'])
    assert saves and prepared['candidates'][0]['autonomy_adjusted_investment_score']==84
    assert prepared['candidates'][0]['technical_contribution_applied']
    before=doc(r,'autonomy')
    result=companion.complete(chosen,'upstream',prepared,routing.view('autonomy'),[],[],storage=r['pg'])
    assert result['learning_portfolio']['closed_positions'][0]['pnl']==-500
    assert read(ap.LEARNING_OBSERVATIONS_PATH)[-1]['observation_id']=='OLD'
    assert result['learning_observations']['total']>=2
    assert synced==['autonomy_learning'] and captures
    assert doc(r,'autonomy')==before
    assert companion.complete(chosen,'upstream',prepared,routing.view('autonomy'),[],[],storage=r['pg'])==result
    assert synced==['autonomy_learning'] # no duplicate learning bridge


def test_canonical_governed_parameter_updates_are_not_frozen(ready,monkeypatch):
    r=ready;activate(r)
    r['pg'].write_json('settings/trading_rules.json',{**r['settings']['paper'],'min_buy_confidence':95})
    def provider(ticker,*,currency=None,quote=None,fx_quote=None,at,cost_policy):
        return bound_cost_evidence(evidence(at)['TEST'],cost_policy)
    monkeypatch.setattr(routing,'market_evidence',provider)
    import trading_engine as engine
    ok,message=engine.paper_buy('TEST',100,90,amount_override=10010,trade_context={'run_id':'updated-configuration'})
    assert not ok and doc(r,'paper')['account']['trades']==[]
    assert doc(r,'paper')['account']['initial_cash']==100000


def test_learning_interruption_retries_without_repeating_financial_job(ready,monkeypatch):
    r=ready;activate(r,'autonomy');calls=[]
    def failure(*a,**k):calls.append('failed');raise RuntimeError('ISOLATED learning interruption after NOK commit')
    monkeypatch.setattr(companion,'complete',failure)
    import autonomous_portfolio as engine
    with pytest.raises(RuntimeError):engine.run_autonomous_cycle([],run_id='learning-interrupted')
    before=doc(r,'autonomy')
    monkeypatch.setattr(companion,'complete',lambda *a,**k:{'learning_trades':[],'learning_decisions':[]})
    result=engine.run_autonomous_cycle([],run_id='learning-interrupted')
    assert result['already_committed'] and calls==['failed']
    assert doc(r,'autonomy')==before


def test_paper_overview_does_not_report_deposits_as_profit(ready):
    r=ready;activate(r);period=r['bundle']['period_id'];at=datetime.now(timezone.utc).isoformat()
    event=dict(type='DEPOSIT',event_id='ISOLATED capital flow',at=at,amount_nok=10000,valuation_marks={},source_ref='ISOLATED approved simulated capital',
        cost_currency='NOK',cost_source_ref='ISOLATED zero costs',cost_components=dict(brokerage_nok=0,fx_cost_nok=0,other_nok=0))
    confirmation=digest(dict(period_id=period,family='paper',event=event,actor='operator',deployment_id=control.installation()))
    control.economic_event(period,'paper',event,actor='operator',confirmation=confirmation)
    from paper_trading import performance_stats
    result=performance_stats()
    assert result['total_value']==110000 and result['total_return_pct']==0 and result['drawdown_pct']==0


def test_autonomy_overview_uses_new_flow_adjusted_results_not_legacy_performance(ready,monkeypatch):
    r=ready;activate(r,'autonomy');period=r['bundle']['period_id'];at=datetime.now(timezone.utc).isoformat()
    event=dict(type='DEPOSIT',event_id='ISOLATED autonomy flow',at=at,amount_nok=100000,valuation_marks={},source_ref='ISOLATED simulated capital',
        cost_currency='NOK',cost_source_ref='ISOLATED zero costs',cost_components=dict(brokerage_nok=0,fx_cost_nok=0,other_nok=0))
    confirmation=digest(dict(period_id=period,family='autonomy',event=event,actor='operator',deployment_id=control.installation()))
    control.economic_event(period,'autonomy',event,actor='operator',confirmation=confirmation)
    import autonomy_overview as overview
    import autonomous_portfolio as ap
    import autonomi_core.configuration.registry as registry
    monkeypatch.setattr(overview,'get_active_status',lambda:{})
    monkeypatch.setattr(overview,'load_jobs',lambda:[])
    monkeypatch.setattr(overview,'_load_report_archive',lambda:[])
    monkeypatch.setattr(overview,'_rows',lambda *a:[{'ticker':'OLD','action':'SELL','pnl':-500}])
    monkeypatch.setattr(overview,'read_json',lambda *a,**k:{'drawdown_pct':88,'total_return_pct':-88})
    monkeypatch.setattr(overview,'pushover_audit',lambda *a:[])
    monkeypatch.setattr(overview,'get_storage_service',lambda:r['pg'])
    monkeypatch.setattr(overview,'load_parameters',lambda:ap.AutonomousParameters())
    monkeypatch.setattr(registry,'load_registry',lambda:{'approvals':[]})
    result=overview.collect_autonomy_overview()
    assert result['equity']==600000 and result['return_pct']==0 and result['drawdown_pct']==0
    assert result['decisions']==[]
    performance=ap.calculate_performance()
    assert performance['equity']==600000 and performance['total_return_pct']==0


def test_paused_autonomy_continues_learning_without_financial_writes(ready,monkeypatch):
    r=ready;activate(r,'autonomy');period=r['bundle']['period_id']
    confirmation=digest(dict(period_id=period,family='autonomy',action='STOP',deployment_id=control.installation()))
    control.stop(period,'autonomy',actor='operator',reason='ISOLATED primary pause',confirmation=confirmation)
    before=doc(r,'autonomy');calls=[]
    def learning(*a,**kw):
        calls.append(True);old=r['pg'].read_json('learning/observations.json')
        r['pg'].write_json('learning/observations.json',{**old,'observations':old['observations']+1})
        return {'learning_trades':[],'learning_decisions':[]}
    monkeypatch.setattr(companion,'complete',learning)
    monkeypatch.setattr(routing,'market_evidence',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No financial execution during pause')))
    import autonomous_portfolio as engine
    result=engine.run_autonomous_cycle([],run_id='ISOLATED paused learning')
    assert result['financial_status']=='PAUSED' and result['portfolio_trades']==[] and calls==[True]
    assert doc(r,'autonomy')==before
    assert r['pg'].read_json('learning/observations.json')=={'observations':82,'loss':-25000}


def test_recent_but_out_of_order_quote_never_overwrites_mark_or_authorizes_sale(ready):
    r=ready;activate(r);first=datetime.now(timezone.utc)
    direct(r,'paper','ISOLATED first quote',first.isoformat(),[dict(ticker='TEST',operation='BUY',amount_nok=10010,confidence=90)])
    second=first+timedelta(minutes=5);ev=evidence(second.isoformat())
    ev['TEST']['observed_at']=(first+timedelta(minutes=1)).isoformat()
    direct(r,'paper','ISOLATED later mark',second.isoformat(),[dict(ticker='TEST',operation='AUTO',signal='HOLD')],ev)
    before=doc(r,'paper')
    third=first+timedelta(minutes=6);older=evidence(third.isoformat(),80)
    older['TEST']['observed_at']=first.isoformat() # within 15 minutes, but older than the prior mark
    with pytest.raises(ValueError,match='predates'):
        direct(r,'paper','ISOLATED backward quote',third.isoformat(),[dict(ticker='TEST',operation='AUTO',signal='HOLD')],older)
    assert doc(r,'paper')==before


@pytest.mark.parametrize('internal_permission',[False,True])
def test_even_valid_opening_draft_cannot_truncate_an_approved_journal(ready,internal_permission,monkeypatch):
    r=ready;activate(r);at=datetime.now(timezone.utc).isoformat()
    direct(r,'paper','ISOLATED immutable history',at,[dict(ticker='TEST',operation='BUY',amount_nok=10010,confidence=90)])
    before=doc(r,'paper');period=r['bundle']['period_id']
    monkeypatch.setenv('ECONOMIC_PRODUCTION_ACTIVATION_ENABLED','true')
    from contextlib import nullcontext
    with control.permission(period,'paper') if internal_permission else nullcontext():
        with pytest.raises(ValueError,match='rewritten or truncated'):
            restart.AccountStorage(period).mutate_json(ledger.key('paper'),lambda _:deepcopy(r['bundle']['accounts']['paper']))
    assert doc(r,'paper')==before


def test_selected_account_uses_approved_snapshot_if_canonical_pg_config_is_missing(ready,monkeypatch,tmp_path):
    r=ready;activate(r,'autonomy')
    import autonomous_portfolio as ap
    stray=tmp_path/'other-runtime-parameters.json'
    stray.write_text(json.dumps({**r['settings']['autonomy'],'minimum_investment_score':99}))
    monkeypatch.setattr(ap,'PARAMETERS_PATH',stray)
    original=r['pg'].read_json
    def missing(name,default=None):
        if name=='autonomous_portfolio/parameters.json':return None
        return original(name,default)
    monkeypatch.setattr(r['pg'],'read_json',missing)
    assert digest(routing.strategy_settings('autonomy',storage=r['pg']))==digest(r['settings']['autonomy'])


@pytest.mark.parametrize('operation',['trade','event','stop'])
def test_active_production_never_uses_a_fallback_enabled_backend(ready,monkeypatch,operation):
    r=ready;activate(r);period=r['bundle']['period_id'];at=datetime.now(timezone.utc).isoformat()
    before=r['pg'].read_json(restart._key(period))
    monkeypatch.setattr(r['pg'],'allow_local_fallback',True)
    with pytest.raises(ValueError,match='without local fallback'):
        if operation=='trade':direct(r,'paper','ISOLATED forbidden fallback',at,[dict(ticker='TEST',operation='BUY',amount_nok=10010)])
        elif operation=='stop':
            confirmation=digest(dict(period_id=period,family='paper',action='STOP',deployment_id=control.installation()))
            control.stop(period,'paper',actor='operator',reason='ISOLATED',confirmation=confirmation)
        else:
            event=dict(type='DEPOSIT',event_id='ISOLATED no fallback',at=at,amount_nok=10000,valuation_marks={},source_ref='ISOLATED capital',
                cost_currency='NOK',cost_source_ref='ISOLATED zero costs',cost_components=dict(brokerage_nok=0,fx_cost_nok=0,other_nok=0))
            confirmation=digest(dict(period_id=period,family='paper',event=event,actor='operator',deployment_id=control.installation()))
            control.economic_event(period,'paper',event,actor='operator',confirmation=confirmation)
    assert r['pg'].read_json(restart._key(period))==before


@pytest.mark.parametrize('family',['paper','autonomy'])
def test_signed_variable_policy_is_bound_to_production_execution_and_refuses_tamper(ready,family):
    from test_trading_costs import policy
    r=ready;r['costs'][family]=policy(10)
    activate(r,family)
    now=datetime.now(timezone.utc)
    first=(now+timedelta(days=(7-now.weekday())%7 or 7)).replace(hour=15,minute=0,second=0,microsecond=0)
    second=first+timedelta(days=3)
    if family=='paper':direct(r,family,'variable-buy',first.isoformat(),[dict(ticker='TEST',operation='BUY',amount_nok=10000,confidence=90)])
    else:
        direct(r,family,'search',first.isoformat(),[candidate(first.isoformat())])
        direct(r,family,'buy',second.isoformat(),[candidate(second.isoformat())])
    actual=doc(r,family);assert actual['account']['trades']
    assert all(t['cost_calculation']['policy']==r['costs'][family] for t in actual['account']['trades'])
    ev={k:bound_cost_evidence(v,r['costs'][family]) for k,v in evidence(second.isoformat()).items()}
    ev['TEST']['cost_policy']['components']['fx_cost_nok']['rate_bps']=999
    common=dict(period_id=r['bundle']['period_id'],family=family,run_id='tamper',at=second.isoformat(),evidence=ev,
                settings=r['settings'][family],strategy_input={},account_ref=trading.account_reference(r['bundle']['period_id'],family),storage=r['pg'])
    with pytest.raises(ValueError,match='Unapproved'):trading.run(**common,operation=lambda s:{})
    assert doc(r,family)==actual


def test_superportfolio_signed_variable_cost_is_exactly_once_and_unknown_fx_refuses_request(ready):
    r=ready;family='super_portfolio'
    before=deepcopy(r['pg'].read_json(restart._key(r['bundle']['period_id'])))
    proposed=deepcopy(r['costs'][family]);proposed['components']['fx_cost_nok']=None
    with pytest.raises(ValueError):control.request(r['bundle']['period_id'],family,actor='test',approval_ref='test',
        at=datetime.now(timezone.utc).isoformat(),restore_review=r['review'],settings=r['settings'][family],cost_policy=proposed)
    assert r['pg'].read_json(restart._key(r['bundle']['period_id']))==before
    assert all(a['status']=='DRAFT' for a in before['accounts'].values())
    activate(r,family)
    now=datetime.now(timezone.utc)
    first=(now+timedelta(days=(7-now.weekday())%7 or 7)).replace(hour=15,minute=0,second=0,microsecond=0)
    second=first+timedelta(days=3)
    direct(r,family,'search',first.isoformat(),[candidate(first.isoformat())])
    direct(r,family,'buy',second.isoformat(),[candidate(second.isoformat())])
    account=doc(r,family)['account'];assert account['trades']
    for t in account['trades']:
        assert t['cost_components']['model_transaction_cost_nok']==pytest.approx(t['gross_value']*.001)
        assert t['cost_components']['fx_cost_nok']==4  # explicitly documented synthetic fixture only
        assert t['fee']==pytest.approx(t['gross_value']*.001+4)
    assert reconcile(account)==[]


def test_v2_concurrent_delivery_commits_one_policy_calculation(ready):
    from test_trading_costs import policy
    r=ready;r['costs']['paper']=policy(10);activate(r)
    at=datetime.now(timezone.utc).isoformat();ev={k:bound_cost_evidence(v,r['costs']['paper']) for k,v in evidence(at).items()}
    args=dict(period_id=r['bundle']['period_id'],family='paper',run_id='v2-concurrent',at=at,evidence=ev,
        settings=r['settings']['paper'],strategy_input={},account_ref=trading.account_reference(r['bundle']['period_id'],'paper'),storage=r['pg'])
    def operation(s):s.fill('TEST','BUY',1,100,'SYNTHETIC duplicate delivery');return {'ok':True}
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers=list(pool.map(lambda _:trading.run(**args,operation=operation),range(2)))
    assert answers==[{'ok':True},{'ok':True}]
    account=doc(r,'paper')['account'];assert len(account['trades'])==1
    assert account['cash']==pytest.approx(100000-1001-(1001*.0033+3))
    assert reconcile(account)==[]
