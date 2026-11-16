"""Report-death detection is observational and never replays a financial job."""
from datetime import datetime, timezone
from types import SimpleNamespace
import importlib
import sys
import pytest
import market_intelligence as mi

SLOT='2026-11-16T13:00:00+00:00'
ROW=dict(job_id='MI-REQUIRED-AFTERNOON',planned_at=SLOT,name='Ettermiddag',schedule='14:00',status='FORSINKET',grace_minutes=60,pdf_created=False,stored=False,error='')
OWNER=dict(state='ACTIVE',job_id=ROW['job_id'],scheduled_for=SLOT,trace_id='REPORT-20261116T130025Z-TEST',heartbeat_at='2026-11-16T13:18:20+00:00',stage='PREFLIGHT')


def watchdog():return importlib.import_module('services.required_report_watchdog')


@pytest.fixture
def alerts(monkeypatch):
    calls=[];receipts={}
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.setattr(mi,'required_report_delivery_ledger',lambda now=None:{'date':'2026-11-16','rows':[dict(ROW)]})
    monkeypatch.setattr(mi,'read_persistent_json',lambda *a,**kw:dict(receipts))
    monkeypatch.setattr(mi,'write_persistent_json',lambda key,data:receipts.update(data) or True)
    monkeypatch.setitem(sys.modules,'notifier',SimpleNamespace(send_pushover_alert=lambda body,**kw:(calls.append(body) or (True,'TEST MOCK')),normalize_notification_result=lambda x:x))
    monkeypatch.setattr('execution_coordination.report_execution_owner',lambda:dict(OWNER))
    return calls,receipts


def test_dead_owner_no_longer_suppresses_overdue_alert(alerts,monkeypatch):
    calls,_=alerts
    w=watchdog()
    monkeypatch.setattr(w,'observe_owner',lambda **kw:{'state':'ORPHANED','owner':dict(OWNER)})
    monkeypatch.setattr(w,'failure_detail',lambda *a,**kw:'Rapportprosessen forsvant uten ferdigkvittering.')
    result=mi.notify_overdue_required_reports()
    assert result['alerts_sent']==[ROW['job_id']]
    assert len(calls)==1 and 'forsvant' in calls[0]
    assert mi.notify_overdue_required_reports()['alerts_sent']==[]


def test_orphan_detection_uses_actual_local_lock_not_heartbeat(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    w=watchdog()
    assert w.observe_owner(owner=OWNER)['state']=='ORPHANED'
    from execution_coordination import _LOCAL_LOCK
    with _LOCAL_LOCK:
        assert w.observe_owner(owner=OWNER)['state']=='LIVE'


def test_live_long_report_remains_protected(alerts,monkeypatch):
    calls,_=alerts
    w=watchdog()
    monkeypatch.setattr(w,'observe_owner',lambda **kw:{'state':'LIVE','owner':dict(OWNER)})
    assert mi.notify_overdue_required_reports()['alerts_sent']==[]
    assert calls==[]


def test_same_job_manual_or_different_slot_does_not_hide_fixed_report(alerts,monkeypatch):
    calls,_=alerts;w=watchdog()
    monkeypatch.setattr(w,'observe_owner',lambda **kw:{'state':'LIVE','owner':{**OWNER,'scheduled_for':''}})
    monkeypatch.setattr(w,'failure_detail',lambda *a,**kw:'Ingen leveringskvittering for fast rapport.')
    assert mi.notify_overdue_required_reports()['alerts_sent']==[ROW['job_id']]
    assert calls


def test_unknown_lock_state_does_not_invent_process_death(alerts,monkeypatch):
    calls,_=alerts;w=watchdog()
    monkeypatch.setattr(w,'observe_owner',lambda **kw:{'state':'UNKNOWN','owner':dict(OWNER),'error_type':'OperationalError'})
    assert mi.notify_overdue_required_reports()['alerts_sent']==[]
    assert not calls


def test_details_use_matching_trace_and_do_not_invent_oom():
    w=watchdog();trace={'job_id':ROW['job_id'],'metadata':{'scheduled_for':SLOT},'current_stage':'AUTONOMOUS','error':''}
    detail=w.failure_detail(ROW,{'state':'ORPHANED','owner':OWNER},read_trace=lambda key:trace)
    assert 'AUTONOMOUS' in detail and '14:18:20' in detail
    assert 'ikke lagret' in detail and 'OOM' not in detail
    trace['error']='ExecutionEvidenceError: mangler dokumentert valutakurs'
    assert 'mangler dokumentert valutakurs' in w.failure_detail(ROW,{'state':'ORPHANED','owner':OWNER},read_trace=lambda key:trace)
    trace['metadata']['scheduled_for']='2026-11-16T21:00:00+00:00'
    assert 'mangler dokumentert valutakurs' not in w.failure_detail(ROW,{'state':'ORPHANED','owner':OWNER},read_trace=lambda key:trace)


def test_released_after_restart_is_terminal(alerts,monkeypatch):
    calls,_=alerts;w=watchdog()
    monkeypatch.setattr(w,'observe_owner',lambda **kw:{'state':'INACTIVE','owner':{**OWNER,'state':'RELEASED_AFTER_PROCESS_RESTART'}})
    monkeypatch.setattr(w,'failure_detail',lambda *a,**kw:'Avbrutt etter prosessomstart.')
    assert mi.notify_overdue_required_reports()['alerts_sent']==[ROW['job_id']]
    assert calls


def test_startup_check_does_not_prevent_heavy_work_on_observer_failure(monkeypatch):
    import scheduled_runner as runner
    w=watchdog();order=[]
    monkeypatch.setattr(w,'run_startup_check',lambda:order.append('watchdog') or {'state':'UNAVAILABLE'})
    monkeypatch.setattr(runner,'run_once',lambda:order.append('heavy_lane') or {'state':'DEFERRED_BUSY'})
    assert runner.main()==0
    assert order==['watchdog','heavy_lane']


def test_missing_production_database_cannot_send_false_missing_alert(monkeypatch):
    w=watchdog();calls=[]
    monkeypatch.setenv('APP_ENVIRONMENT','production');monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.setattr(mi,'notify_overdue_required_reports',lambda:calls.append('unsafe'))
    assert w.run_startup_check()['state']=='DEFERRED_DATABASE'
    assert not calls


def test_matching_trace_error_is_redacted_and_bounded():
    w=watchdog();trace={'job_id':ROW['job_id'],'metadata':{'scheduled_for':SLOT},'error':'Fetch failed api_key=TOPSECRET '+('x'*1000)}
    detail=w.failure_detail(ROW,{'state':'ORPHANED','owner':OWNER},read_trace=lambda key:trace)
    assert len(detail)<=500 and 'TOPSECRET' not in detail


def test_malformed_diagnostic_metadata_cannot_prevent_alarm():
    w=watchdog()
    for metadata in ('invalid',[],[1]):
        detail=w.failure_detail(ROW,{'state':'ORPHANED','owner':OWNER},read_trace=lambda key:{'job_id':ROW['job_id'],'metadata':metadata,'error':'must not be attributed'})
        assert 'ikke lagret' in detail and 'must not be attributed' not in detail


def test_delivery_finishing_during_observation_does_not_trigger_false_alarm(alerts,monkeypatch):
    calls,_=alerts;w=watchdog();delivered=[]
    monkeypatch.setattr(mi,'required_report_delivery_ledger',lambda now=None:{'date':'2026-11-16','rows':[{**ROW,'status':'SENDT' if delivered else 'FORSINKET'}]})
    def observe(**kw):
        delivered.append(True)
        return {'state':'INACTIVE','owner':{}}
    monkeypatch.setattr(w,'observe_owner',observe)
    assert mi.notify_overdue_required_reports()['alerts_sent']==[]
    assert not calls
