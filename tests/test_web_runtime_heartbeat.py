"""Identity requires a healthy local server, independent of browser activity."""
from unittest.mock import MagicMock
import pytest
import runtime_identity
import web_runner


def test_healthy_server_publishes_exact_current_web_identity_without_app_session(monkeypatch):
    opener=MagicMock();response=opener.open.return_value.__enter__.return_value;response.status=200
    monkeypatch.setattr(web_runner,'build_opener',lambda *a:opener)
    publish=MagicMock(return_value={'commit':'deployed-source','version':'current'})
    monkeypatch.setattr(runtime_identity,'publish_runtime_identity',publish)
    assert web_runner.publish_healthy_identity(10000)
    publish.assert_called_once_with('web')
    request=opener.open.call_args.args[0]
    assert request.full_url=='http://127.0.0.1:10000/_stcore/health'


@pytest.mark.parametrize('failure',['unhealthy','unreachable'])
def test_failed_local_health_never_renews_identity(monkeypatch,failure):
    opener=MagicMock();opener.open.return_value.__enter__.return_value.status=503
    if failure=='unreachable':opener.open.side_effect=OSError('server stopped')
    monkeypatch.setattr(web_runner,'build_opener',lambda *a:opener)
    publish=MagicMock();monkeypatch.setattr(runtime_identity,'publish_runtime_identity',publish)
    if failure=='unreachable':
        with pytest.raises(OSError):web_runner.publish_healthy_identity(10000)
    else:assert not web_runner.publish_healthy_identity(10000)
    publish.assert_not_called()


def test_heartbeat_repeats_without_browser_and_stops_with_server(monkeypatch):
    stop=MagicMock();stop.wait.side_effect=[False,False,True]
    publish=MagicMock(return_value=True)
    monkeypatch.setattr(web_runner,'publish_healthy_identity',publish)
    web_runner.heartbeat(stop,10000)
    assert [c.args[0] for c in stop.wait.call_args_list]==[1,60,60]
    assert publish.call_count==2


def test_real_server_registers_identity_without_opening_app(tmp_path):
    import json,os,socket,subprocess,sys,time
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'PORT':str(port),'APP_RUNTIME_ROOT':str(tmp_path),'STORAGE_MODE':'local',
        'DATABASE_URL':'','AUTH_DATABASE_URL':'','ALLOW_LOCAL_STORAGE_FALLBACK':'true',
        'APP_ENVIRONMENT':'test','SOURCE_COMMIT':'fixture-web-commit','RENDER_GIT_COMMIT':'fixture-web-commit',
        'STREAMLIT_BROWSER_GATHER_USAGE_STATS':'false'}
    proc=subprocess.Popen([sys.executable,'web_runner.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            paths=list(tmp_path.rglob('identities.json'))
            if paths:
                document=json.loads(paths[0].read_text())
                assert document['web']['commit']=='fixture-web-commit'
                assert proc.poll() is None
                break
            time.sleep(.1)
        else:raise AssertionError('Healthy web server did not register without a browser')
    finally:
        proc.terminate();proc.wait(timeout=10)


def test_direct_pdf_survives_real_web_launcher_cold_restart(tmp_path):
    import base64,json,os,socket,subprocess,sys,time
    from urllib.request import build_opener,ProxyHandler
    from services.storage_service import StorageService
    from datetime import datetime,timedelta,timezone
    token='R'*43;raw=b'%PDF-1.4\ndurable PDF survives server restart\n%%EOF'
    storage=StorageService(tmp_path/'data'/'services',database_url='',mode='local')
    storage.write_json('public_reports/'+token+'.json',{'token':token,'filename':'report.pdf',
        'expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'pdf_base64':base64.b64encode(raw).decode()})
    opener=build_opener(ProxyHandler({}))
    for _ in range(2):
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env={**os.environ,'PORT':str(port),'APP_RUNTIME_ROOT':str(tmp_path),'STORAGE_MODE':'local',
            'DATABASE_URL':'','AUTH_DATABASE_URL':'','ALLOW_LOCAL_STORAGE_FALLBACK':'true','APP_ENVIRONMENT':'test',
            'RENDER_GIT_COMMIT':'cold-restart-test','STREAMLIT_BROWSER_GATHER_USAGE_STATS':'false'}
        proc=subprocess.Popen([sys.executable,'web_runner.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        base='http://127.0.0.1:'+str(port)
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                try:
                    with opener.open(base+'/_stcore/health',timeout=1) as r:
                        if r.status==200:break
                except Exception:time.sleep(.1)
            else:raise AssertionError('Web launcher did not start')
            with opener.open(base+'/?public_report_token='+token,timeout=5) as r:
                assert r.headers.get_content_type()=='application/pdf'
                assert r.headers['Content-Disposition'].startswith('inline;')
                assert r.read()==raw and r.url.endswith('/reports/'+token+'.pdf')
            with opener.open(base+'/?public_report_token='+token+'&report_view=page',timeout=5) as r:
                assert r.headers.get_content_type()=='text/html'
        finally:proc.terminate();proc.wait(timeout=10)
