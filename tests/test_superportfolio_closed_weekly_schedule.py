"""A closed weekly rebalance must not force broad scans every cron wake-up."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest
import super_portfolio as engine
import super_portfolio_jobs as jobs


@pytest.fixture
def scenario(monkeypatch):
    now=datetime(2026,11,6,0,0,tzinfo=timezone.utc)  # Friday, Stockholm closed.
    state={'economic_period_id':'signed-test-period','status':'ACTIVE',
           'positions':{'EVO.ST':{'currency':'SEK'}}, 'last_rebalance_date':'2026-10-30',
           'config':{'rebalance_weekday':4,'market_refresh_hours':12}}
    pipeline={'created_at':(now-timedelta(hours=1)).isoformat(),'candidates':[{'ticker':'EVO.ST'}]}
    monkeypatch.setattr(engine,'load_state',lambda:deepcopy(state))
    monkeypatch.setattr(engine,'load_latest_super_portfolio_market_pipeline',lambda:deepcopy(pipeline))
    return now,state,pipeline


def test_weekly_due_stays_pending_without_repeated_closed_market_broad_scan(scenario):
    now,state,pipeline=scenario;original=deepcopy(state)
    for minute in (0,15,30,45):
        assert jobs._scheduled_job_due(now+timedelta(minutes=minute))==(False,'WEEKLY_REBALANCE_MARKET_CLOSED')
    assert state==original  # Never claim the weekly rebalance completed.


def test_weekly_rebalance_runs_when_held_exchange_opens(scenario):
    now,state,pipeline=scenario
    assert jobs._scheduled_job_due(now.replace(hour=9))==(True,'WEEKLY_REBALANCE_DUE')


@pytest.mark.parametrize('missing',[False,True])
def test_closed_weekly_deferral_preserves_due_research_refresh(scenario,missing):
    now,state,pipeline=scenario
    pipeline['created_at']=(now-timedelta(hours=13)).isoformat()
    if missing:pipeline['candidates']=[]
    assert jobs._scheduled_job_due(now)==(True,'NO_VERIFIED_PIPELINE' if missing else 'REFRESH_DUE')


@pytest.mark.parametrize('change',['unknown','paused','legacy'])
def test_ambiguous_or_stopped_accounts_retain_original_strict_path(scenario,change):
    now,state,pipeline=scenario
    if change=='unknown':state['positions']={'BTC-USD':{}}
    if change=='paused':state['status']='PAUSED'
    if change=='legacy':state.pop('economic_period_id')
    assert jobs._scheduled_job_due(now)==(True,'WEEKLY_REBALANCE_DUE')


@pytest.mark.parametrize('verified,changes',[(True,0),(True,1),(False,0)])
def test_worker_publishes_research_and_deferred_execution_separately(monkeypatch,verified,changes):
    import super_portfolio_worker as worker
    monkeypatch.setattr(jobs,'get_job',lambda *args:{})
    monkeypatch.setattr(jobs,'_require_worker',lambda *args:None)
    def update(*args,**fields):return fields
    monkeypatch.setattr(jobs,'update_job',update)
    pipeline={'run_id':'research','verification':{'ok':verified}}
    execution={'execution_state':'DEFERRED_MARKET_CLOSED','reason':'MARKET_CLOSED','next_market_open':{'SVERIGE':{'utc':'opening'}}}
    if not verified or changes:
        with pytest.raises(RuntimeError):worker.publish_verified_result('job','token',pipeline,applied_changes=changes,execution=execution)
    else:
        result=worker.publish_verified_result('job','token',pipeline,execution=execution)
        assert result['state']=='COMPLETED' and result['applied_changes']==0
        assert result['execution_state']=='DEFERRED_MARKET_CLOSED'
        assert result['execution_reason']=='MARKET_CLOSED' and 'venter' in result['message']
        assert result['next_market_open']==execution['next_market_open']
