from copy import deepcopy
from datetime import datetime, timezone
import pytest
from test_revision_trade_postgres import pg

AT = datetime(2026, 11, 10, 17, tzinfo=timezone.utc)


def signal(ticker='VEI.OL', code='KJØPSKANDIDAT'):
    return {'ticker':ticker, 'market':'NORGE','investment_score':80,
            'autonomy_outcome_code':code,'raw':{'last_price':218.,'currency':'NOK',
            'latest_trade_timestamp':'2026-11-09T15:20:00+00:00'}}


def run(report='R1', **kw):
    return {'run_id':report,'created_at':'2026-11-09T13:07:50+00:00',
            'signal_available_at':'2026-11-09T13:07:50+00:00',
            'candidates':[signal()],**kw}


def test_active_control_does_not_hide_a_later_buy_signal(monkeypatch):
    import learning_observation_engine as engine
    old={'ticker':'VEI.OL','observation_id':'old','group':'NEAR_THRESHOLD',
         'status':'ACTIVE','entry_price':200.,'horizon_measurements':{}}
    monkeypatch.setattr(engine,'load_observations',lambda:[deepcopy(old)])
    result=engine.register_report_observations(run(),commit=False)
    assert result['signal_coverage']['strict_count']==1
    assert result['created_by_group']['STRICT']==1


def test_legacy_same_group_cannot_block_the_corrected_method(monkeypatch):
    import learning_observation_engine as engine
    old={'ticker':'VEI.OL','observation_id':'legacy','group':'STRICT','status':'ACTIVE'}
    monkeypatch.setattr(engine,'load_observations',lambda:[old])
    result=engine.register_report_observations(run(),commit=False)
    assert result['created_by_group']['STRICT']==1


def test_replaying_legacy_report_cannot_duplicate_observation_identity(monkeypatch):
    import learning_observation_engine as engine
    old={'ticker':'VEI.OL','observation_id':'LOW-R1-VEI.OL-STRICT','group':'STRICT','status':'ACTIVE'}
    saved=[]
    monkeypatch.setattr(engine,'load_observations',lambda:[deepcopy(old)])
    monkeypatch.setattr(engine,'save_observations',lambda rows:saved.extend(rows))
    monkeypatch.setattr(engine,'record_signal_coverage',lambda *a,**k:{'state':'RECORDED'})
    monkeypatch.setattr(engine,'_audit',lambda *a,**k:None)
    engine.register_report_observations(run())
    assert len({r['observation_id'] for r in saved})==len(saved)


def test_coverage_survives_full_sampling_quota(pg):
    from services.learning_signal_coverage import capture
    report=run(candidates=[signal(f'S{i}.OL') for i in range(40)])
    result=capture(report,commit=True,storage=pg)
    assert result['state']=='RECORDED' and result['strict_count']==40
    receipt=pg.read_json(result['key'])
    assert len(receipt['signals'])==40
    assert receipt['signals'][0]['reference_currency']=='NOK'
    assert receipt['signals'][0]['is_executed_trade'] is False
    assert capture(report,commit=True,storage=pg)==result
    changed=deepcopy(report); changed['candidates'][0]['raw']['last_price']=999.
    with pytest.raises(ValueError,match='identity'):
        capture(changed,commit=True,storage=pg)


def test_preview_has_no_storage_side_effect(pg):
    from services.learning_signal_coverage import capture
    result=capture(run(),commit=False,storage=pg)
    assert result['state']=='PLANNED' and pg.read_json(result['key']) is None


def test_coverage_requires_documented_signal_availability_for_commits(pg):
    from services.learning_signal_coverage import capture
    report=run();report.pop('signal_available_at')
    assert capture(report,commit=False,storage=pg)['state']=='PLANNED'
    with pytest.raises(ValueError,match='availability'):
        capture(report,commit=True,storage=pg)


def test_sample_uses_availability_after_finalization_not_report_creation(monkeypatch):
    import learning_observation_engine as engine
    saved=[]
    monkeypatch.setattr(engine,'load_observations',lambda:[])
    monkeypatch.setattr(engine,'save_observations',lambda rows:saved.extend(rows))
    monkeypatch.setattr(engine,'record_signal_coverage',lambda *a,**k:{'state':'RECORDED'})
    monkeypatch.setattr(engine,'_audit',lambda *a,**k:None)
    engine.register_report_observations(run(created_at='2026-11-09T07:50:00+00:00',signal_available_at='2026-11-09T08:10:00+00:00'))
    assert saved[0]['entry_at']=='2026-11-09T08:10:00+00:00'


def test_inconsistent_reference_does_not_erase_the_buy_recommendation(pg):
    from services.learning_signal_coverage import capture
    report=run();report['candidates'][0]['raw']['ticker']='OTHER.OL'
    result=capture(report,commit=True,storage=pg)
    receipt=pg.read_json(result['key'])
    assert receipt['signals'][0]['ticker']=='VEI.OL'
    assert receipt['signals'][0]['reference_status']=='UNVERIFIED_IDENTITY_OR_CURRENCY'
    assert 'reference_price' not in receipt['signals'][0]


def test_full_outcome_sample_still_records_every_recommendation(pg,monkeypatch):
    import learning_observation_engine as engine
    from services.learning_signal_coverage import capture
    old=[{'ticker':f'OLD{i}.OL','group':'STRICT','status':'ACTIVE'} for i in range(120)]
    monkeypatch.setattr(engine,'load_observations',lambda:deepcopy(old))
    monkeypatch.setattr(engine,'save_observations',lambda rows:pytest.fail('Full sample should not be rewritten'))
    monkeypatch.setattr(engine,'record_signal_coverage',lambda report,commit=False:capture(report,commit=commit,storage=pg))
    monkeypatch.setattr(engine,'_audit',lambda *a,**k:None)
    result=engine.register_report_observations(run())
    assert result['created']==0
    assert len(pg.read_json(result['signal_coverage']['key'])['signals'])==1


def bar(day, opened, closed):
    return {'date':day,'open':opened,'close':closed,'raw_open':opened,
            'raw_close':closed,'return_basis':'PROVIDER_ADJUSTED_TOTAL_RETURN_PROXY_V1'}


def test_midday_signal_uses_the_next_open_for_both_stock_and_index():
    from services.learning_signal_measurement import measure
    row={'ticker':'A.OL','market':'NORGE','entry_at':'2026-11-09T13:00:00+00:00'}
    stock=[bar('2026-11-09',50,100),bar('2026-11-10',100,110)]
    bench=[bar('2026-11-09',100,105),bar('2026-11-10',200,204)]
    result=measure(row,stock,bench,now=AT)
    assert result['entry_reference']['market_date']=='2026-11-10'
    assert result['horizon_measurements']['1']['return_pct']==10.
    assert result['horizon_measurements']['1']['benchmark_return_pct']==2.
    assert result['horizon_measurements']['1']['excess_return_pct']==8.
    assert result['horizon_measurements']['1']['net_return_pct'] is None


def test_before_open_signal_can_use_same_day_open_but_never_future_close():
    from services.learning_signal_measurement import measure
    row={'ticker':'A.OL','market':'NORGE','entry_at':'2026-11-09T07:00:00+00:00'}
    stock=[bar('2026-11-09',100,110)]
    bench=[bar('2026-11-09',200,204)]
    result=measure(row,stock,bench,now=datetime(2026,11,9,12,tzinfo=timezone.utc))
    assert not result.get('horizon_measurements')


def test_after_close_friday_signal_waits_for_monday_open():
    from services.learning_signal_measurement import measure
    row={'ticker':'A.OL','market':'NORGE','entry_at':'2026-11-06T20:00:00+00:00'}
    stock=[bar('2026-11-06',50,100),bar('2026-11-09',100,110),bar('2026-11-10',110,112)]
    bench=[bar('2026-11-06',100,105),bar('2026-11-09',200,204),bar('2026-11-10',204,206)]
    result=measure(row,stock,bench,now=AT)
    assert result['entry_reference']['market_date']=='2026-11-09'
    assert result['horizon_measurements']['1']['benchmark_return_pct']==2.


def test_reporting_does_not_average_old_price_references_with_new_total_return_proxy():
    from services.learning_signal_measurement import POLICY
    from learning_observation_engine import build_weekly_analysis
    legacy={'ticker':'OLD','status':'ACTIVE','horizon_measurements':{'1':{'return_pct':90.,'benchmark_return_pct':0.,'excess_return_pct':90.}}}
    fresh={'ticker':'NEW','status':'ACTIVE','measurement_policy':POLICY,
           'horizon_measurements':{'1':{'return_pct':10.,'benchmark_return_pct':2.,'excess_return_pct':8.}}}
    result=build_weekly_analysis([legacy,fresh])
    first=result['horizons'][0]
    assert first['return']['count']==1 and first['return']['average']==10.
    assert result['data_quality']['legacy_reference_observations']==1
    assert result['net_result_verified'] is False


def test_future_dividend_rescaling_cannot_mix_raw_and_adjusted_bases():
    from services.learning_signal_measurement import measure
    row={'ticker':'A.OL','market':'NORGE','entry_at':'2026-11-09T07:00:00+00:00'}
    stock=[bar('2026-11-09',100,110),bar('2026-11-10',110,112)]
    bench=[bar('2026-11-09',200,204),bar('2026-11-10',204,206)]
    first=measure(row,stock,bench,now=AT)
    revised=[{**b,'open':b['open']*.8,'close':b['close']*.8} for b in stock]
    second=measure(row,revised,bench,now=AT,previous=first)
    assert second['horizon_measurements']==first['horizon_measurements']
    assert first['entry_price']==100.


def test_missing_expected_entry_bar_does_not_silently_move_the_entry():
    from services.learning_signal_measurement import measure
    row={'ticker':'A.OL','market':'NORGE','entry_at':'2026-11-09T07:00:00+00:00'}
    result=measure(row,[bar('2026-11-10',100,110)],[bar('2026-11-10',200,204)],now=AT)
    assert result['state']=='MISSING_EXPECTED_ENTRY_BAR'
    assert not result.get('horizon_measurements')


def test_missing_comparable_benchmark_is_explicit_not_a_zero_return():
    from services.learning_signal_measurement import measure
    row={'ticker':'A.ST','market':'SVERIGE','entry_at':'2026-11-09T07:00:00+00:00'}
    result=measure(row,[bar('2026-11-09',100,110),bar('2026-11-10',110,112)],[],now=AT)
    assert result['horizon_measurements']['1']['return_pct']==10.
    assert result['horizon_measurements']['1']['benchmark_return_pct'] is None
    assert result['horizon_measurements']['1']['excess_return_pct'] is None


def test_normalized_historical_revision_is_rejected_instead_of_rewriting_frozen_outcomes():
    from services.learning_signal_measurement import measure
    row={'ticker':'A.OL','market':'NORGE','entry_at':'2026-11-09T07:00:00+00:00'}
    stock=[bar('2026-11-09',100,110),bar('2026-11-10',110,112)]
    bench=[bar('2026-11-09',200,204),bar('2026-11-10',204,206)]
    first=measure(row,stock,bench,now=AT)
    changed=deepcopy(stock);changed[0]['close']=120.
    result=measure(row,changed,bench,now=AT,previous=first)
    assert result['state']=='NORMALIZED_HISTORY_REVISION'
    assert result['horizon_measurements']==first['horizon_measurements']


def test_daily_benchmark_revision_is_not_silently_rewritten():
    from services.learning_signal_measurement import measure
    row={'ticker':'A.OL','market':'NORGE','entry_at':'2026-11-09T07:00:00+00:00'}
    stock=[bar('2026-11-09',100,110),bar('2026-11-10',110,112)]
    bench=[bar('2026-11-09',200,204),bar('2026-11-10',204,206)]
    first=measure(row,stock,bench,now=AT)
    revised=deepcopy(bench);revised[1]['close']=250.
    result=measure(row,stock,revised,now=AT,previous=first)
    assert result['state']=='NORMALIZED_HISTORY_REVISION'
    assert result['daily_marks']==first['daily_marks']


def test_missing_new_benchmark_keeps_frozen_comparisons_and_stock_progress():
    from services.learning_signal_measurement import measure
    row={'ticker':'A.OL','market':'NORGE','entry_at':'2026-11-09T07:00:00+00:00'}
    stock=[bar('2026-11-09',100,110),bar('2026-11-10',110,112)]
    bench=[bar('2026-11-09',200,204),bar('2026-11-10',204,206)]
    first=measure(row,stock[:1],bench[:1],now=datetime(2026,11,9,17,tzinfo=timezone.utc))
    result=measure(row,stock,bench[:1],now=AT,previous=first)
    assert result['state']=='MEASURED_WITHOUT_COMPARABLE_BENCHMARK'
    assert result['horizon_measurements']['1']==first['horizon_measurements']['1']
    assert len(result['daily_marks'])==2 and result['daily_marks'][1]['benchmark_return_pct'] is None


def test_waiting_for_first_completed_session_is_healthy():
    from learning_observation_engine import build_weekly_analysis
    from services.learning_signal_measurement import POLICY
    row={'ticker':'A.OL','market':'NORGE','group':'STRICT','status':'ACTIVE','measurement_policy':POLICY,
         'benchmark_ticker':'OSEBX.OL','source_health':{'status':'AWAITING_COMPLETED_ENTRY_SESSION'},'horizon_measurements':{}}
    result=build_weekly_analysis([row])
    assert result['health']['status']=='OK' and result['health']['missing_or_stale']==0


def test_headline_buy_performance_does_not_include_controls_or_moderate_references(monkeypatch):
    import learning_observation_engine as engine
    from services.learning_signal_measurement import POLICY
    rows=[{'ticker':group,'group':group,'status':'ACTIVE','measurement_policy':POLICY,'benchmark_ticker':'OSEBX.OL',
           'horizon_measurements':{'20':{'return_pct':ret,'benchmark_return_pct':0.,'excess_return_pct':ret}}}
          for group,ret in [('STRICT',10.),('MODERATE',50.),('MATCHED_CONTROL',100.)]]
    monkeypatch.setattr(engine,'load_observations',lambda:rows)
    monkeypatch.setattr(engine,'read_json',lambda *a:{})
    result=engine.report_control_snapshot()
    assert result['separate_results']['signal_20d_excess_return_pct']==10.
    assert result['separate_results']['signal_20d_count']==1
    assert result['separate_results']['signal_scope']=='STRICT_ONLY'
