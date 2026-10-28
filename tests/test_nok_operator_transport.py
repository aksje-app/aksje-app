"""Real framed PC/Render operator integration using isolated PostgreSQL and keys.

SSH is replaced ONLY by a local child-process channel. Remote worker, encrypted
archive, crypto delegation, production request/sign/activate, settings and SQL
are real. Fixture identity pins are synthetic, never production approvals.
"""
from copy import deepcopy
from datetime import datetime,timezone
import io,json,os,shlex,shutil,subprocess,sys,tarfile
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/nok_operator'))
import windows_operator as pc
import wire
from test_production_restart import ready
from test_revision_trade_postgres import pg
from test_simulation_restart import sources,certificate
from services import production_restart as control,simulation_restart as restart,simulation_archive as archive
from services.economic_opening import digest


def test_interrupted_stream_resumes_only_matching_original_bytes(tmp_path):
    original=tmp_path/'original.cms';original.write_bytes(os.urandom(2*1024**2+13))
    data=original.read_bytes();target=tmp_path/'remote.cms'
    header=dict(size=len(data),sha256=wire.sha(original),offset=0,total_size=len(data),total_sha256=wire.sha(original))
    with pytest.raises(ValueError,match='Incomplete'):
        wire.receive_file(io.BytesIO(data[:137]),target,header)
    assert not target.exists() and target.with_name('remote.cms.part').stat().st_size==137
    stream=io.BytesIO();wire.send_file(stream,original,offset=137,prefix_sha256=wire.sha(target.with_name('remote.cms.part')))
    stream.seek(0);wire.receive_file(stream,target,offset=137,expected_sha256=wire.sha(original))
    assert target.read_bytes()==data
    with pytest.raises(ValueError,match='differs'):
        wire.send_file(io.BytesIO(),original,offset=137,prefix_sha256='wrong')


@pytest.fixture
def operator_ready(pg,sources,certificate,tmp_path,monkeypatch):
    original_create=archive.create_archive
    def seal_fixture(*args,**kwargs):
        from services.market_snapshot_service import MarketSnapshotService
        from services.strategy_registry_service import StrategyRegistryService
        from repositories.application import RepositoryRegistry
        repositories=RepositoryRegistry(pg);registry=StrategyRegistryService(repositories);registry.ensure_defaults()
        snapshots=MarketSnapshotService(repositories)
        snap=snapshots.build_market_snapshot([dict(ticker='EQNR.OL',price=300,currency='NOK',score=6.2,
            technical=dict(rsi=55,trend='up',macd_bullish=True,channel_pos=50))],run_id='ISOLATED-SCAN',source='paper_scanner')
        assert snapshots.save(snap)['saved']
        pg.write_json('market_intelligence/latest_run.json',dict(run_id='ISOLATED-MI',completion_status='FULLFØRT',candidates=[dict(ticker='AAPL',portfolio_action='HOLD')]))
        pg.write_json('super_portfolio/market_pipeline.json',dict(run_id='SPM-20261024-001559',candidates=[dict(ticker='ORNBV.HE',source='Super Portfolio independent market universe')]))
        pg.write_json('superfund/retained.json',dict(original_loss=-25000,learning=[1,2,3]))
        return original_create(*args,**kwargs)
    monkeypatch.setattr(archive,'create_archive',seal_fixture)
    yield from ready.__wrapped__(pg,sources,certificate,tmp_path,monkeypatch)


def test_windows_and_remote_full_prepare_B_disconnect_redeploy_and_complete(operator_ready,monkeypatch,tmp_path):
    r=operator_ready;folder=tmp_path/'pc-results';folder.mkdir()
    program=shutil.which('openssl');cipher=r['root']/r['bundle']['archive']['archive_id']/'archive.cms'
    receipt=json.loads((cipher.parent/'receipt.json').read_text())
    config=tmp_path/'config.json';config.write_text(json.dumps(dict(database_environment_variables={'database':'DATABASE_URL'})))
    review=tmp_path/'review.json';review.write_text(json.dumps(r['review']))
    receipt_file=tmp_path/'receipt.json';receipt_file.write_text(json.dumps(receipt))
    files={'config.json':config,'restore-result.json':review,'archive-receipt.json':receipt_file,
           'archive-certificate.pem':r['cert'],'archive.cms':cipher}
    # These override only test identity/certificate/archive pins, not validators.
    profile=dict(PERIOD=r['bundle']['period_id'],ARCHIVE=receipt['archive_id'],REVIEW_SHA=r['review']['review_sha256'],
        CIPHER_SHA=receipt['cipher_sha256'],SERVICE='ISOLATED-CHILD-NOT-RENDER',DEPLOYMENT=control.installation())
    monkeypatch.setattr(pc.shared,'PERIOD',profile['PERIOD']);monkeypatch.setattr(pc.shared,'ARCHIVE',profile['ARCHIVE'])
    monkeypatch.setattr(pc,'CIPHER_SHA',profile['CIPHER_SHA']);monkeypatch.setattr(pc,'CERT_SHA',wire.sha(r['cert']))
    # The underlying serialized operators remain the exact repository sources.
    original_popen=subprocess.Popen;children=[];cut_next=[False]
    class CutAfterReceipt:
        def __init__(self,stream):self.stream=stream;self.cut=False
        def readline(self,*args):
            if self.cut:return b''
            raw=self.stream.readline(*args)
            try:
                message=json.loads(raw)
                if message.get('kind')=='download' and message.get('name')=='paper-activation-receipt.json':self.cut=True
            except (ValueError,TypeError):pass
            return raw
        def read(self,*args):return self.stream.read(*args)
    def child_transport(command,*args,**kwargs):
        if command[0]!=shutil.which('ssh'):return original_popen(command,*args,**kwargs)
        assert 'StrictHostKeyChecking=yes' in command and '-i' in command
        code=shlex.split(command[-1])[-1]
        extra="import operator_common as shared;"+''.join('shared.'+k+'='+repr(v)+';' for k,v in profile.items())
        code=code.replace("runpy.run_path(p+'/render_worker.py',run_name='__main__')",extra+"runpy.run_path(p+'/render_worker.py',run_name='__main__')")
        env={k:v for k,v in os.environ.items() if k not in ('RENDER_API_KEY','GH_TOKEN','AUTH_DATABASE_URL')}
        env.update(DATABASE_URL=r['pg'].database_url,RENDER_SERVICE_ID=profile['SERVICE'],APP_ENVIRONMENT='production',
            STORAGE_MODE='postgres',ALLOW_LOCAL_STORAGE_FALLBACK='false',NOK_DEPLOYMENT_ID=profile['DEPLOYMENT'],
            NOK_APPROVAL_CERTIFICATE=str(r['cert']),NOK_APPROVAL_CERT_SHA256=wire.sha(r['cert']),PYTHONPATH=str(Path.cwd()))
        process=original_popen([sys.executable,'-u','-c',code],*args,**kwargs,env=env);children.append(process)
        if cut_next[0]:process.stdout=CutAfterReceipt(process.stdout);cut_next[0]=False
        return process
    monkeypatch.setattr(subprocess,'Popen',child_transport)
    before=deepcopy(r['pg'].read_json(restart._key(profile['PERIOD'])))
    remote_roots=[]
    try:
        result=pc.session('prepare',dict(ssh_key=r['key']),files,program,r['key'],r['cert'],None,folder,dict(actor='ISOLATED OPERATOR'))
        remote_roots.append(Path(result['remote_work']))
        assert result['result']['approval_B_ready'] is True
        assert r['pg'].read_json(restart._key(profile['PERIOD']))==before
        assert len(list(folder.glob('*-activation-preflight.json')))==3
        for f in restart.CAPITALS:
            pre=json.loads((folder/(f+'-activation-preflight.json')).read_text())
            assert pre['quotes_obtained'] is False and pre['actual_market_run_performed'] is False
        catalog=pc.shared.load(folder/'catalog.json');reference=digest(catalog)
        # Wrong personal B cannot produce a signature.
        with pytest.raises(ValueError,match='B-katalog'):pc.sign_grants(folder,r['key'],program,'wrong')
        signed=pc.sign_grants(folder,r['key'],program,reference)
        for name in ['catalog.json','status.json']+[f+'-request.json' for f in restart.CAPITALS]:files[name]=folder/name
        files['signed-grants.json']=signed
        first=folder/'disconnected-activation';first.mkdir();cut_next[0]=True
        header=dict(remote_work=result['remote_work'],remote_package=result['result']['remote_package'],approval_b=reference)
        with pytest.raises(ValueError,match='SSH connection ended'):
            pc.session('activate',dict(ssh_key=r['key']),files,program,r['key'],r['cert'],None,first,header)
        assert (first/'paper-activation-receipt.json').is_file()
        # Simulate redeploy losing remote /tmp; never touch the PC's encrypted original.
        shutil.rmtree(result['remote_work'])
        second=folder/'resumed-activation';second.mkdir()
        done=pc.session('activate',dict(ssh_key=r['key']),files,program,r['key'],r['cert'],None,second,header)
        remote_roots.append(Path(done['remote_work']))
        assert done['result']['status']=='ACTIVATED_AND_CONFIRMED_IN_POSTGRESQL'
        assert done['result']['scheduler_started'] is False
        for family,capital in restart.CAPITALS.items():
            selected=control.selected(family,storage=r['pg'])
            assert selected['bundle']['accounts'][family]['account']['cash']==capital
            assert selected['bundle']['accounts'][family]['account']['trades']==[]
            assert selected['bundle']['accounts'][family]['account']['positions']=={}
            assert len(selected['bundle']['production_controls'][family]['transitions'])==1
        assert r['pg'].read_json('superfund/retained.json')==dict(original_loss=-25000,learning=[1,2,3])
        # Only the PC test fixture owns a private key, never any remote context.
        for root in remote_roots:
            if root.exists():
                assert all(b'-----BEGIN PRIVATE KEY-----' not in p.read_bytes() for p in root.rglob('*') if p.is_file())
    finally:
        for child in children:
            if child.poll() is None:child.kill();child.wait(timeout=10)
        for root in remote_roots:
            if root.exists():shutil.rmtree(root)
