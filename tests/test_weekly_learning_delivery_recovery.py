from copy import deepcopy
from datetime import datetime,timedelta,timezone
import learning_observation_engine as engine


def seed(monkeypatch,notification):
    now=datetime(2026,11,7,12,tzinfo=timezone.utc)
    record={'report_id':'LWR-W45','week_key':'2026-W45','created_at':(now-timedelta(days=1)).isoformat(),
        'analysis':{'observation_count':91,'matured_count':0,'horizons':[],'health':{'status':'OK'}},
        'public_report_token':'A'*43,'technical_report_token':'B'*43,'pdf_sizes':{'main':100,'technical':200},'notification':notification}
    store={engine.WEEKLY_KEY:[record]}
    monkeypatch.setattr(engine,'read_json',lambda k,p,d:deepcopy(store.get(k,d)))
    monkeypatch.setattr(engine,'write_json',lambda k,p,v:store.__setitem__(k,deepcopy(v)))
    def no_regeneration(*a,**kw):raise AssertionError('Existing evidence/PDF must not be regenerated for delivery')
    monkeypatch.setattr(engine,'build_weekly_analysis',no_regeneration)
    monkeypatch.setattr(engine,'build_weekly_pdf',no_regeneration)
    return now,store,deepcopy(record)


def test_failed_weekly_delivery_retries_same_report_once_without_routine_suppression(monkeypatch):
    now,store,before=seed(monkeypatch,{'attempted':True,'sent':False,'detail':'relevance suppressed: in-app only'})
    calls=[]
    def send(*args,**kwargs):
        from notification_relevance_policy import classify
        assert classify(kwargs['relevance_event'])!='in_app'
        calls.append(kwargs);return True,'HTTP 200'
    monkeypatch.setattr('notifier.send_pushover_alert',send)
    assert engine._weekly_due(now)
    result=engine.generate_weekly_report(now=now)
    after=store[engine.WEEKLY_KEY][0]
    assert result['status']=='COMPLETED' and result['delivery_retry'] and not result['evidence_regenerated']
    assert len(store[engine.WEEKLY_KEY])==1 and after['notification']['sent']
    for field in ('analysis','report_id','created_at','pdf_sizes','public_report_token','technical_report_token'):
        assert before[field]==after[field]
    assert not engine._weekly_due(now+timedelta(hours=1))
    assert engine.generate_weekly_report(now=now+timedelta(hours=1))['status']=='ALREADY_COMPLETED'
    assert len(calls)==1


def test_weekly_cooldown_retry_limit_and_explicit_no_notifications(monkeypatch):
    now,store,_=seed(monkeypatch,{'required':True,'attempted':True,'sent':False,'attempts':2,'attempted_at':'2026-11-07T11:45:00+00:00'})
    assert not engine._weekly_due(now)
    assert engine.generate_weekly_report(now=now)['status']=='PUSHOVER_FAILED'
    store[engine.WEEKLY_KEY][0]['notification']['attempts']=5
    assert not engine._weekly_due(now+timedelta(hours=2))
    store[engine.WEEKLY_KEY][0]['notification']={'required':False,'attempted':False,'sent':False}
    assert not engine._weekly_due(now+timedelta(hours=2))


def test_weekly_duplicate_suppression_is_not_reported_as_new_delivery(monkeypatch):
    now,store,_=seed(monkeypatch,{'attempted':True,'sent':False})
    monkeypatch.setattr('notifier.send_pushover_alert',lambda *a,**kw:(True,'duplicate suppressed'))
    result=engine.generate_weekly_report(now=now)
    assert result['status']=='PUSHOVER_FAILED' and not store[engine.WEEKLY_KEY][0]['notification']['sent']
