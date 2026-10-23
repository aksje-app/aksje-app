"""Executable regressions for F1–F10; synthetic data are not recovered fills."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json

import pandas as pd
import pytest

import autonomous_portfolio as ap
import super_portfolio as sp
from services import super_portfolio_store as journal
from services.storage_service import StorageService
from strategy_history_worker import simulate
from portfolio_history_optimizer import _score, METHOD_VERSION

NOW = datetime(2026, 10, 22, 14, tzinfo=timezone.utc)


def quote(price, at=NOW):
    return {'price':price,'market_data_at':at.isoformat(),'source':'yfinance 5m Close','adjustment':'raw'}


def test_real_scheduled_benchmark_no_self_conflict_and_retry(monkeypatch,tmp_path):
    storage=StorageService(tmp_path,mode='local',database_url='')
    monkeypatch.setattr(journal,'get_storage_service',lambda:storage)
    monkeypatch.setattr(sp,'load_state',lambda:deepcopy(storage.read_json(journal.STATE_KEY,{})))
    state=sp.default_state(sp.SuperPortfolioConfig(auto_pushover=False))
    storage.write_json(journal.STATE_KEY,state)
    monkeypatch.setattr(sp,'_now_dt',lambda:NOW)
    monkeypatch.setattr(sp,'append_event',lambda *a,**k:None)
    monkeypatch.setattr(sp,'resource_health',lambda:{})
    import yfinance
    monkeypatch.setattr(yfinance,'download',lambda *a,**k:pd.DataFrame())
    monkeypatch.setattr(sp,'_execution_quotes',lambda *a:{})
    pipeline={'run_id':'AUDIT-BENCHMARK','job_id':'AUDIT-BENCHMARK-JOB','created_at':NOW.isoformat(),'candidates':[]}
    first=sp.run_scheduled_shadow_cycle(pipeline)
    assert first['state']=='COMPLETED'
    saved=storage.read_json(journal.STATE_KEY)
    assert saved['last_scheduled_source_run_id']=='AUDIT-BENCHMARK'
    assert saved['benchmark']['index']['status']=='UNAVAILABLE'
    assert journal.committed_job('AUDIT-BENCHMARK-JOB',storage)
    assert journal.transactions(storage)==[]
    sp.run_scheduled_shadow_cycle(pipeline)
    assert journal.transactions(storage)==[]


def test_fixed_benchmark_inception_does_not_follow_current_positions(monkeypatch):
    starts=[]
    import yfinance
    monkeypatch.setattr(yfinance,'download',lambda *a,**k:starts.append(k['start']) or pd.DataFrame())
    state={'created_at':'2026-10-01T00:00:00Z','positions':{'NEW':{'entry_date':'2026-10-21'}}}
    sp.refresh_index_benchmark(state,persist=False)
    assert starts==['2026-10-01']


def run_exit(price=90, execution_quote=None):
    pos={'ticker':'DNO.OL','quantity':10,'average_price':100,'last_price':100,'highest_price':100,
         'opened_at':(NOW-timedelta(hours=1)).isoformat(),'entry_score':90,'sector':'Energy'}
    portfolio={'cash':99000,'initial_cash':100000,'positions':{'DNO.OL':pos},'status':'PAUSED','high_watermark':100000}
    candidate={'ticker':'DNO.OL','price':price,'investment_score':90,'price_timestamp':'2020-01-01T12:00:00Z',
               'valid_for_decision':False,'evidence_valid_for_decision':False}
    if execution_quote is not None:candidate['execution_quote']=execution_quote
    return ap.simulate_autonomy_cycle([candidate],parameters=asdict(ap.AutonomousParameters()),
                                     portfolio=portfolio,trades=[],now=NOW,run_id='AUDIT-F2')


@pytest.mark.parametrize('evidence',[None,quote(90,NOW-timedelta(minutes=16)),quote(90,NOW+timedelta(minutes=2)),
                                    {'price':90,'market_data_at':NOW.isoformat()}])
def test_stale_or_unproven_autonomy_price_never_sells(evidence):
    result=run_exit(execution_quote=evidence)
    assert not result['trades']
    assert result['portfolio']['positions']['DNO.OL']['last_price']==100
    assert result['portfolio']['cash']==99000


def test_fresh_autonomy_stop_inside_one_hour_requires_no_buy_authority():
    result=run_exit(execution_quote=quote(90))
    assert len(result['trades'])==1
    assert result['trades'][0]['action']=='SELL'
    assert result['trades'][0]['price_observed_at']==NOW.isoformat()
    assert not result['portfolio']['positions']
    assert result['portfolio']['cash']==99900
    assert ap.portfolio_equity(result['portfolio'])==99900


def test_historical_stop_in_entry_bar_and_no_reused_capital():
    assert simulate([{'open':100,'low':100,'close':100}, {'open':100,'low':50,'close':100},
                     {'open':100,'low':100,'close':100}],3,1)==pytest.approx([-3])
    bars=[{'open':100*1.01**i,'low':100*1.01**i,'close':100*1.01**i} for i in range(40)]
    overlapping=simulate(bars,50,5)
    independent=simulate(bars,50,5,non_overlapping=True)
    assert len(overlapping)==34 and len(independent)==6
    score=_score(independent,1)
    assert score['total_pct']<47.42


def test_frame_capture_none_return_means_success(monkeypatch,tmp_path):
    import durable_runtime as d
    import learning_experiments as le
    monkeypatch.setattr(d,'read_json',lambda *a:[])
    writes=[]
    monkeypatch.setattr(d,'write_json',lambda *a:writes.append(a))
    result=le.record_frame({'run_id':'TEST','candidates':[]},config={'x':1})
    assert result['status']=='CAPTURED' and len(writes)==1
    def fail(*a):raise OSError('test failure')
    monkeypatch.setattr(d,'write_json',fail)
    assert le.record_frame({'run_id':'TEST'},config={'x':1})['status']=='CAPTURE_FAILED'


def test_partial_sell_common_fill_and_idempotency(tmp_path):
    from repositories.application import RepositoryRegistry
    from services.strategy_registry_service import StrategyRegistryService
    from services.strategy_account_service import StrategyAccountService
    from services.simulated_execution_service import SimulatedExecutionService
    repos=RepositoryRegistry(StorageService(tmp_path,mode='local',database_url=''))
    accounts=StrategyAccountService(repos,StrategyRegistryService(repos))
    accounts.ensure_defaults()
    execution=SimulatedExecutionService(repos,accounts)
    before=deepcopy(accounts.get('autonomy_main'))
    trade={'trade_id':'PARTIAL-1','action':'SELL_PARTIAL','ticker':'DNO.OL','quantity':5,'price':100,'timestamp':NOW.isoformat()}
    first=execution.mirror_legacy_trade(account_id='autonomy_main',trade=trade)
    second=execution.mirror_legacy_trade(account_id='autonomy_main',trade=trade)
    assert first['mirrored'] and not second['mirrored']
    assert first['fill']['side']=='SELL' and first['order']['metadata']['action']=='SELL_PARTIAL'
    assert accounts.get('autonomy_main')==before
    assert len(execution.recent_fills())==1


def test_report_hour_hold_matches_engine_and_last_add():
    from report_portfolio_intelligence import build_portfolio_report
    position={'ticker':'DNO.OL','quantity':10,'average_price':100,'last_price':100,'highest_price':100,
              'opened_at':'2026-10-01T23:30:00Z','last_added_at':'2026-10-22T23:30:00Z','entry_score':80}
    result=build_portfolio_report({'positions':{'DNO.OL':position}},
        [{'ticker':'DNO.OL','investment_score':50,'raw':{'last_price':100}}],
        now=datetime(2026,10,23,0,30,tzinfo=timezone.utc))
    assert result['positions'][0]['exit_reason_code']=='MINIMUM_HOLD'


def test_missing_historical_evidence_is_never_passed(monkeypatch):
    import investment_pipeline as ip
    import advanced_investment_intelligence as ai
    monkeypatch.setattr(ai,'load_candidate_trend',lambda *a:{'trend':'FLAT','previous_score':None,'score_delta':0})
    result=ip.score_candidate({'ticker':'DNO.OL','price':100,'validation_score':90},ip.PipelineConfig())
    assert result.quality_gates['Historisk validering']=='IKKE VERIFISERT'


def test_fx_base_nav_and_cost_evidence_never_invented():
    from services.economic_accounting_audit import audit
    portfolio={'cash':1000,'base_currency':'NOK','initial_cash':3400,'history_complete':True,
               'positions':{'NO':{'quantity':10,'last_price':100,'currency':'NOK','quantity_unit':'ACTUAL_SHARES','price_observed_at':NOW.isoformat()},
                  'US':{'quantity':2,'last_price':50,'currency':'USD','quantity_unit':'ACTUAL_SHARES','price_observed_at':NOW.isoformat(),
                     'fx_quote':{'currency':'USD','base_currency':'NOK','rate':10,'observed_at':NOW.isoformat(),'source':'fixture'}},
                  'EU':{'quantity':1,'last_price':100,'currency':'EUR','quantity_unit':'ACTUAL_SHARES','price_observed_at':NOW.isoformat(),
                     'fx_quote':{'currency':'EUR','base_currency':'NOK','rate':11,'observed_at':NOW.isoformat(),'source':'fixture'}}}}
    original=deepcopy(portfolio)
    result=audit(portfolio,[{'trade_id':'T1','fee':5,'cost_currency':'NOK'}],at=NOW)
    assert result['verified_nav']==4100 and result['verified_net_return_pct']==pytest.approx(20.588235)
    assert portfolio==original
    for change in ['missing','stale','future','mismatch','model']:
        row=deepcopy(portfolio)
        fx=row['positions']['US']['fx_quote']
        if change=='missing':fx.clear()
        if change=='stale':fx['observed_at']=(NOW-timedelta(days=6)).isoformat()
        if change=='future':fx['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
        if change=='mismatch':fx['base_currency']='EUR'
        if change=='model':row['positions']['US']['quantity_unit']='MODEL_PRICE_RATIO_UNITS'
        assert audit(row,at=NOW)['verified_nav'] is None
    missing_fee=audit(portfolio,[{'trade_id':'T2'}],at=NOW)
    assert missing_fee['verified_nav']==4100 and missing_fee['verified_net_return_pct'] is None


def test_old_optimizer_results_hidden_until_recomputed():
    from research_findings_dashboard import collect
    from hashlib import sha256
    class Store:
        def read_json(self,key,default):
            if key.endswith('optimization_progress.json'):return {'completed_tickers':['AAA']}
            return {'status':'COMPLETE_RESEARCH','finalists':[{'holdout':{'total_pct':9999,'trades':100}}]}
    result=collect(Store(),'AUTONOMY')
    assert result['invalid_method']==1 and not result['holdout']


def test_unverified_alpha_is_not_a_zero_or_a_comparable_return():
    result=sp.benchmark_summary({'benchmark':{'index':{'return_pct':2}}},portfolio_return_pct=5)
    assert result['index']['alpha_pct'] is None


def test_interrupted_partial_mirror_repairs_original_fill(tmp_path,monkeypatch):
    from repositories.application import RepositoryRegistry
    from services.strategy_registry_service import StrategyRegistryService
    from services.strategy_account_service import StrategyAccountService
    from services.simulated_execution_service import SimulatedExecutionService
    repos=RepositoryRegistry(StorageService(tmp_path,mode='local',database_url=''))
    accounts=StrategyAccountService(repos,StrategyRegistryService(repos));accounts.ensure_defaults()
    execution=SimulatedExecutionService(repos,accounts)
    write=execution.fills.upsert
    def fail(*a):raise RuntimeError('crash after order write')
    monkeypatch.setattr(execution.fills,'upsert',fail)
    trade={'trade_id':'PARTIAL-RETRY','action':'SELL_PARTIAL','ticker':'DNO.OL','quantity':5,'price':100,
           'timestamp':NOW.isoformat(),'strategy_version_id':'autonomy_main@original'}
    with pytest.raises(RuntimeError,match='crash'):
        execution.mirror_legacy_trade(account_id='autonomy_main',trade=trade)
    monkeypatch.setattr(execution.fills,'upsert',write)
    result=execution.mirror_legacy_trade(account_id='autonomy_main',trade={**trade,'price':999})
    assert result['fill']['fill_price']==100
    assert result['fill']['metadata']['strategy_version_id']=='autonomy_main@original'
    assert len(execution.recent_orders())==len(execution.recent_fills())==1


def test_held_report_uses_base_score_and_current_policy():
    from report_portfolio_intelligence import build_portfolio_report
    position={'ticker':'DNO.OL','quantity':10,'average_price':100,'last_price':100,'highest_price':100,
              'opened_at':'2026-10-20T12:00:00Z','entry_score':80}
    result=build_portfolio_report({'positions':{'DNO.OL':position},'parameters':{'minimum_hold_hours':72}},
        [{'ticker':'DNO.OL','investment_score':80,'effective_entry_score':10,'raw':{'last_price':100}}],now=NOW)
    row=result['positions'][0]
    assert row['exit_action']=='HOLD'
    assert row['execution_authorized'] is False


def test_explicit_report_destination_is_not_hidden_by_simple_mode():
    from autonomy_modes import apply_requested_workspace_mode, EXPERT, SIMPLE
    state={'autonomy_interface_mode_v1884':SIMPLE}
    apply_requested_workspace_mode(state,'reports')
    assert state['autonomy_interface_mode_v1884']==EXPERT
    state={'autonomy_interface_mode_v1884':SIMPLE}
    apply_requested_workspace_mode(state,'overview')
    assert state['autonomy_interface_mode_v1884']==SIMPLE
    apply_requested_workspace_mode(state,'unknown')
    assert state['autonomy_interface_mode_v1884']==SIMPLE


def test_background_navigation_does_not_reassign_existing_widget():
    from navigation_state import restore_navigation_checkpoint_v19144
    class WidgetState(dict):
        def __setitem__(self,key,value):
            if key=='widget':raise RuntimeError('Widget is already instantiated')
            super().__setitem__(key,value)
    class St:
        session_state=WidgetState(widget='Autonomi',navigation_user_revision_v19143=1)
    assert restore_navigation_checkpoint_v19144(St(),{'revision':1,'values':{'widget':'Autonomi'}})
    assert St.session_state['widget']=='Autonomi'
