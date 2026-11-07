from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import learning_runtime as lr
from test_learning_runtime import MemoryStorage, frame
from services.learning_progress import snapshot, KEYS
from services.shadow_daily_guard import evaluate, send_daily_if_due


def test_increased_disk_capacity_resumes_without_deleting_history_or_gaps(monkeypatch):
    store=MemoryStorage();monkeypatch.setattr(lr,'storage',lambda:store)
    lr.archive(frame());original=deepcopy(store.rows)
    budget=lr.MAX_ARCHIVE_BYTES
    monkeypatch.setattr(lr,'MAX_ARCHIVE_BYTES',store.rows[lr.INDEX]['bytes'])
    assert lr.archive(frame(1))['status']=='STORAGE_BUDGET_REACHED'
    monkeypatch.setattr(lr,'MAX_ARCHIVE_BYTES',budget)
    assert lr.archive(frame(1))['status']=='CAPTURED'
    index=store.rows[lr.INDEX]
    assert index['gaps']==1 and index['status']=='COLLECTING'
    assert len(index['records'])==2 and index['records'][0]==original[lr.INDEX]['records'][0]
    for row in original[lr.INDEX]['records']:
        assert store.rows[row['key']]==original[row['key']]
        assert lr.load_frame(row)['sha256']==row['sha256']
    assert lr.MAX_FRAME_BYTES==8*1024**2


def test_budget_blocked_legacy_backfill_can_retry_but_invalid_input_cannot(monkeypatch):
    store=MemoryStorage();monkeypatch.setattr(lr,'storage',lambda:store)
    key='controlled_learning/history/backfill.json'
    store.rows['full_replay/index.json']=[{'run_id':'blocked'},{'run_id':'invalid'}]
    store.rows[key]={'processed':{'blocked':{'status':'STORAGE_BUDGET_REACHED'},'invalid':{'status':'REJECTED_INCOMPLETE_HISTORY'}}}
    calls=[]
    monkeypatch.setattr(lr,'import_replay_bundle',lambda bundle:calls.append(bundle) or {'status':'CAPTURED'})
    assert lr.backfill_legacy_batch()['captured']==1
    assert len(calls)==1 and store.rows[key]['processed']['invalid']['status']=='REJECTED_INCOMPLETE_HISTORY'


def test_three_streams_and_real_20_day_results_do_not_become_validated():
    data={KEYS['observations']:[{'status':'ACTIVE','entry_at':'2026-08-31','horizon_measurements':{'20':{'return_pct':2,'excess_return_pct':1}}}],
        KEYS['history']:{'status':'STORAGE_BUDGET_REACHED','gaps':105,'records':[{'engine':e,'status':'READY','at':'2026-10-29','complete_universe':e!='AUTONOMY'}for e in ('AUTONOMY','SUPER_PORTFOLIO','AUTONOMY_UNIVERSE')]},
        KEYS['autonomy_forward']:{'status':'ACTIVE_SHADOW','observed_trading_dates':11},
        KEYS['super_forward']:{'status':'ACTIVE_SHADOW','observed_trading_dates':13}}
    report=snapshot(data.get)
    assert report['measured_shadow_horizons'][0]['measured_count']==1
    assert report['measured_shadow_horizons'][0]['mean_excess_return_pct']==1
    assert report['replay_streams']['AUTONOMY']['forward_trading_dates']==11
    assert report['replay_streams']['SUPER_PORTFOLIO']['forward_trading_dates']==13
    assert report['replay_streams']['AUTONOMY_UNIVERSE']['forward_status']=='CAPTURE_ONLY'
    assert report['replay_streams']['AUTONOMY_UNIVERSE']['independent_strategy_test'] is False
    assert report['can_authorize_buy'] is False


def test_daily_is_red_for_stopped_archives_even_when_jobs_run_and_shows_results():
    now=datetime(2026,11,7,12,tzinfo=timezone.utc)
    data={KEYS['acceptance']:{'evaluated_at':now.isoformat(),'strategy_readiness':'NOT_VALIDATED'},
          KEYS['history']:{'status':'STORAGE_BUDGET_REACHED','gaps':105,'records':[{'engine':e,'status':'READY','at':'2026-10-29T00:00:00Z'} for e in ('AUTONOMY','SUPER_PORTFOLIO','AUTONOMY_UNIVERSE')]},
          KEYS['observations']:[{'status':'ACTIVE','horizon_measurements':{str(d):{'return_pct':2,'excess_return_pct':1}for d in (1,5,20)}}]}
    audit=[{'at':now.isoformat(),'event':'OBSERVATIONS_REGISTERED','created':0},{'at':now.isoformat(),'event':'OUTCOMES_EVALUATED','updated':0,'active':91,'matured':0}]
    with patch('services.shadow_daily_guard.read_json',side_effect=lambda k,p,d:data.get(k,d)),patch('services.shadow_daily_guard.read_events',return_value=audit):
        report=evaluate(now)
    assert report['status']=='RØD' and report['new_observations']==report['new_measurements']==0
    assert any('fullt' in r for r in report['failures'])
    with patch('services.shadow_daily_guard.read_json',return_value={}),patch('services.shadow_daily_guard.evaluate',return_value=report),patch('services.shadow_daily_guard.write_json'),patch('notifier.send_pushover_alert',return_value=(True,'HTTP 200')) as sender:
        result=send_daily_if_due(now=now)
    text=sender.call_args.args[0]
    assert all(label in text for label in ('Autonomi:','Superporteføljen:','Aksjeunivers:','1/1/1/0','+1.00 pp','fullt'))
    assert len(text)<=1024 and result['sent'] is True
