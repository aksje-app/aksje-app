from io import BytesIO
from pathlib import Path
import json
import zipfile
import pytest
from ui_library.work_progress import progress_values
from services.storage_service import StorageService
import superfund_runtime as runtime


@pytest.fixture
def local(tmp_path,monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    service=StorageService(base_dir=tmp_path,mode='local',database_url='')
    monkeypatch.setattr(runtime,'storage',lambda:service)
    monkeypatch.setattr('ui_library.work_progress._save',lambda *a:None)
    return service


def test_progress_is_unknown_or_bounded_until_result_saved():
    assert progress_values('RUNNING') is None
    assert progress_values('RUNNING',12,33)==36
    assert progress_values('RUNNING',33,33)==99
    assert progress_values('INTERRUPTED',percent=100)==99
    assert progress_values('FAILED') is None
    assert progress_values('COMPLETED')==100


def test_host_load_does_not_veto_container_with_capacity(monkeypatch):
    import resource_coordinator as r
    monkeypatch.setattr('autonomous_portfolio._available_memory_mb',lambda:1725)
    monkeypatch.setattr(r.os,'getloadavg',lambda:(215,0,0))
    monkeypatch.setattr(r.os,'cpu_count',lambda:100)
    monkeypatch.setattr(r,'_container_cpu_pressure',lambda:0.5)
    result=r.optional_capacity()
    assert result['ready'] and result['host_load_per_cpu']==2.15
    monkeypatch.setattr(r,'_container_cpu_pressure',lambda:50)
    assert r.optional_capacity()['reasons']==['CONTAINER_CPU_PRESSURE']
    monkeypatch.setattr('autonomous_portfolio._available_memory_mb',lambda:100)
    assert r.optional_capacity()['reasons']==['MEMORY_HEADROOM','CONTAINER_CPU_PRESSURE']


def test_cpu_pressure_requires_scoped_quota_and_valid_values(tmp_path):
    from resource_coordinator import _container_cpu_pressure
    (tmp_path/'cpu.max').write_text('50000 100000')
    (tmp_path/'cpu.pressure').write_text('some avg10=62.5 avg60=20 total=30\nfull avg10=1.0 avg60=0 total=0')
    assert _container_cpu_pressure(tmp_path)==62.5
    (tmp_path/'cpu.max').write_text('max 100000')
    assert _container_cpu_pressure(tmp_path) is None
    (tmp_path/'cpu.max').write_text('50000 100000')
    (tmp_path/'cpu.pressure').write_text('some avg10=nan')
    assert _container_cpu_pressure(tmp_path) is None


def test_zip_before_snapshot_contains_diagnostics_and_redacts(local):
    from superfund_diagnostics import diagnostic_zip
    runtime.write('job.json',{'state':'DEFERRED_CAPACITY','headroom_mb':1725,'api_key':'sensitive'})
    data,name=diagnostic_zip()
    with zipfile.ZipFile(BytesIO(data)) as archive:
        job=json.loads(archive.read('job.json'));manifest=json.loads(archive.read('manifest.json'))
        assert job['api_key']=='[REDACTED]'
        assert 'parameter_audit.json' in archive.namelist()
        assert json.loads(archive.read('controls.json'))['findings'][0]['check']=='SNAPSHOT'
        assert manifest['included'] and 'diagnose' in name
    assert b'sensitive' not in data


def test_zip_includes_shadow_learning_history_and_flags_future(local):
    import gzip,base64,hashlib
    from superfund_diagnostics import diagnostic_zip
    frame={'at':'2026-10-10T12:00:00+00:00','items':[{'observed_at':'2026-10-11T12:00:00+00:00'}]}
    packed=gzip.compress(json.dumps(frame).encode());sha=hashlib.sha256(packed).hexdigest()
    runtime.write('history/2026-10-10.json',{'gzip_base64':base64.b64encode(packed).decode(),'sha256':sha})
    runtime.write('learning_index.json',{'frames':[{'key':'superfund/history/2026-10-10.json','sha256':sha}]})
    runtime.write('snapshot.json',{'model':{'initial_capital':100},'shadows':{'fast':{'initial_capital':100,'trades':[{'side':'BUY'}]}},'shadow_rules':{'fast':{'min_week_pct':0.5}},'learning':{'paired_dates':3}})
    data,_=diagnostic_zip()
    with zipfile.ZipFile(BytesIO(data)) as z:
        assert json.loads(z.read('snapshot.json'))['shadows']['fast']['trades']
        assert json.loads(z.read('controls.json'))['frames'][0]['future_evidence'] is True


def test_zip_budget_omissions_are_explicit(local,monkeypatch):
    import superfund_diagnostics as d
    runtime.write('catalog_index.json',{'pages':{'fond-1':{}}})
    runtime.write('catalog/fond-1.json',{'items':['x'*5000]})
    monkeypatch.setattr(d,'MAX_RAW_BYTES',128*1024+3000)
    data,_=d.diagnostic_zip()
    with zipfile.ZipFile(BytesIO(data)) as z:
        assert any(r['path']=='catalog/fond-1.json' for r in json.loads(z.read('manifest.json'))['omitted'])
        assert 'controls.json' in z.namelist()


def test_empty_report_ui_explains_and_builds_zip(local,monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(runtime,'catalog_page',lambda *a:pytest.fail('UI fetch'))
    app=AppTest.from_string('import streamlit as st\nfrom pages.superfund import render_superfund\nrender_superfund(st)').run()
    assert not app.exception
    assert any('Diagnose-ZIP kan lages allerede nå' in i.value for i in app.info)
    app.button(key='sf_build_diagnostic').click().run()
    assert not app.exception
    data,name=app.session_state['sf_diagnostic_download']
    assert data.startswith(b'PK') and name.endswith('.zip')


def test_watchdog_one_stall_notice_and_recovery(local,monkeypatch):
    import notifier
    calls=[]
    monkeypatch.setattr(notifier,'send_pushover_alert',lambda *a,**k:calls.append(a[0]) or True)
    bad={'ready':False,'reasons':['CONTAINER_CPU_PRESSURE']}
    for minute in (0,20,40,60,80):runtime.capacity_watch(bad,f'2026-10-10T{12+minute//60:02d}:{minute%60:02d}:00+00:00')
    assert len(calls)==1
    runtime.capacity_watch({'ready':True},'2026-10-10T14:00:00+00:00')
    runtime.capacity_watch({'ready':True},'2026-10-10T14:20:00+00:00')
    assert len(calls)==2


def test_tracked_job_preserves_deferral_and_exception(monkeypatch):
    import ui_library.work_progress as w
    saved=[];monkeypatch.setattr(w,'_save',lambda row:saved.append(dict(row)))
    @w.tracked_job('shadow')
    def deferred():return {'status':'DEFERRED_MEMORY'}
    assert deferred()['status']=='DEFERRED_MEMORY' and saved[-1]['state']=='DEFERRED_MEMORY'
    @w.tracked_job('test')
    def fails():raise ValueError('bad')
    with pytest.raises(ValueError):fails()
    assert saved[-1]['state']=='FAILED'


def test_job_bar_never_marks_aborted_or_failed_complete(monkeypatch):
    import ui_library.work_progress as w
    saved=[];monkeypatch.setattr(w,'_save',lambda row:saved.append(dict(row)))
    class Widget:
        def progress(self,*a,**kw):return self
    bar=w.job_bar(Widget(),'Tester')
    bar.progress(100,text='Avbrutt')
    assert saved[-1]['state']=='INTERRUPTED' and saved[-1]['percent']==99
    bar.progress(100,text='Lagring feilet')
    assert saved[-1]['state']=='FAILED' and saved[-1]['percent']==99


def test_archive_export_redacts_encoded_credentials(local):
    import gzip,base64,hashlib
    from superfund_diagnostics import diagnostic_zip
    frame={'at':'2026-10-10T12:00:00+00:00','items':[{'observed_at':'2026-10-10T11:00:00+00:00','api_key':'never_export'}]}
    packed=gzip.compress(json.dumps(frame).encode());sha=hashlib.sha256(packed).hexdigest()
    runtime.write('history/2026-10-10.json',{'gzip_base64':base64.b64encode(packed).decode(),'sha256':sha})
    runtime.write('learning_index.json',{'frames':[{'key':'superfund/history/2026-10-10.json','sha256':sha}]})
    data,_=diagnostic_zip()
    with zipfile.ZipFile(BytesIO(data)) as z:
        assert 'history/2026-10-10.json' not in z.namelist()
        assert json.loads(z.read('frames/2026-10-10.json'))['items'][0]['api_key']=='[REDACTED]'
        assert json.loads(z.read('controls.json'))['frames'][0]['checksum']=='OK'
