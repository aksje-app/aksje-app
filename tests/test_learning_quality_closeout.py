from copy import deepcopy
from datetime import datetime, timezone

import learning_observation_engine as engine
from services.learning_signal_measurement import POLICY


def isolated(monkeypatch, rows):
    saved = []
    monkeypatch.setattr(engine, 'load_observations', lambda: deepcopy(rows))
    monkeypatch.setattr(engine, 'save_observations', lambda value: saved.extend(deepcopy(value)))
    monkeypatch.setattr(engine, 'load_engine_state', lambda: {})
    monkeypatch.setattr(engine, 'write_json', lambda *a: None)
    monkeypatch.setattr(engine, '_audit', lambda *a, **k: None)
    return saved


def legacy(**kw):
    return {'observation_id':'old','ticker':'OLD.OL','market':'NORGE','group':'STRICT',
            'status':'ACTIVE','entry_at':'2026-11-09T07:00:00+00:00',
            'entry_market_date':'2026-11-09','entry_price':100.,'benchmark_ticker':'OSEBX.OL',
            'horizon_measurements':{},'daily_marks':[],**kw}


def test_legacy_only_evaluation_preserves_source_without_price_requests(monkeypatch):
    saved = isolated(monkeypatch, [legacy()])
    requested = []
    result = engine.evaluate_observations(lambda *a: requested.append(a) or {},
                                        now=datetime(2026,11,10,18,tzinfo=timezone.utc))
    assert requested == []
    assert saved == []
    assert result['active'] == 0
    assert result['legacy_frozen'] == 1


def test_mixed_evaluation_fetches_only_current_method_and_preserves_legacy(monkeypatch):
    old = legacy()
    current = legacy(observation_id='new',ticker='NEW.OL',measurement_policy=POLICY,
                     entry_at='2026-11-10T20:00:00+00:00',entry_market_date='2026-11-10')
    saved = isolated(monkeypatch,[old,current])
    requested = []
    engine.evaluate_observations(lambda symbols,start: requested.extend(symbols) or {},
                                 now=datetime(2026,11,10,21,tzinfo=timezone.utc))
    assert 'OLD.OL' not in requested
    assert 'NEW.OL' in requested
    assert next(r for r in saved if r['observation_id']=='old') == old


def test_frozen_legacy_does_not_consume_current_sampling_capacity(monkeypatch):
    isolated(monkeypatch,[legacy(observation_id=f'old-{i}',ticker=f'OLD{i}.OL') for i in range(120)])
    monkeypatch.setattr(engine,'record_signal_coverage',lambda *a,**k:{'state':'PLANNED'})
    report={'run_id':'R','created_at':'2026-11-10T07:00:00+00:00','candidates':[
        {'ticker':'NEW.OL','market':'NORGE','autonomy_outcome_code':'KJØPSKANDIDAT',
         'raw':{'current_price':100.}}]}
    result = engine.register_report_observations(report,commit=False)
    assert result['created_by_group']['STRICT'] == 1
    assert result['active_after'] == 1
    assert result['legacy_frozen'] == 120


def test_legacy_only_analysis_cannot_generate_active_statistics_or_proposals():
    rows = [legacy(ticker=f'OLD{i}.OL',group='MODERATE' if i<12 else 'NEAR_THRESHOLD',
                   horizon_measurements={'20':{'return_pct':50.,'benchmark_return_pct':0.,
                                             'excess_return_pct':50.}}) for i in range(24)]
    result = engine.build_weekly_analysis(rows)
    assert all(r['return']['count']==0 for r in result['horizons'])
    assert result['active_count'] == 0
    assert result['data_quality']['legacy_reference_observations'] == 24
    assert all(r['count']==0 and r['correlation_with_20d_excess'] is None
               for r in result['selection_quality']['factor_attribution'])
    assert all(p['status']=='OBSERVE' for p in result['shadow_proposals'])


def test_unknown_method_is_frozen_rather_than_assumed_current(monkeypatch):
    isolated(monkeypatch,[legacy(measurement_policy='UNKNOWN_FUTURE_V9')])
    requested=[]
    result=engine.evaluate_observations(lambda *a:requested.append(a) or {},
                                        now=datetime(2026,11,10,18,tzinfo=timezone.utc))
    assert not requested
    assert result['active']==0


def test_progress_summary_also_excludes_legacy_without_a_current_cohort():
    from services.learning_evidence_report import summarize_measured_observation_horizons
    row=legacy(horizon_measurements={'20':{'return_pct':90.,'excess_return_pct':90.}})
    assert summarize_measured_observation_horizons([row]) == []


def test_legacy_baseline_cannot_restart_an_unqualified_historical_scan(monkeypatch):
    requested=[]
    monkeypatch.setattr(engine,'read_json',lambda *a:{})
    monkeypatch.setattr(engine,'_load_compact_baseline_runs',lambda **k:requested.append('archive') or [])
    result=engine.generate_historical_baseline(notify=False)
    assert requested == []
    assert result['status']=='ON_HOLD_DATA_QUALITY'
    assert result['production_parameters_changed'] is False


def test_old_baseline_verified_label_does_not_qualify_return_figures():
    from services.learning_evidence_report import summarize_learning_evidence
    old={'status':'VERIFISERT','analysis':{'horizons':[
        {'horizon_days':1,'return':{'count':10,'average':99.},'excess_return':{'count':10,'average':99.}}]}}
    result=summarize_learning_evidence(old,{},[])
    assert result['historical_horizons']==[]
    assert result['historical_original_status_label']=='VERIFISERT'
    assert result['historical_qualified_for_strategy'] is False
