from copy import deepcopy
from datetime import datetime, timezone
import pytest
from test_revision_trade_postgres import pg

ENTRY='2026-11-10T08:00:00+00:00'
EXIT='2026-11-10T15:20:00+00:00'


def contract():
    from services.learning_cost_reference import make_contract
    return make_contract(at='2026-11-10T07:00:00+00:00',commit='a'*40)


def fx(currency,rate,at):
    return {'currency':currency,'base_currency':'NOK','rate':rate,'observed_at':at,
            'source':'documented-test-spot','quote_kind':'TIMESTAMPED_FX_SPOT_REFERENCE'}


def reference(**kw):
    from services.learning_cost_reference import cost_reference
    args=dict(gross_factor=1.1,currency='NOK',entry_at=ENTRY,exit_at=EXIT,contract=contract())
    args.update(kw)
    return cost_reference(**args)


def test_nok_reference_charges_both_sides_and_includes_entry_cost_in_denominator():
    result=reference()
    assert result['status']=='COSTED_REFERENCE_AVAILABLE'
    assert result['entry_gross_nok']==100.
    assert result['entry_cost_nok']==pytest.approx(.2)
    assert result['exit_gross_nok']==pytest.approx(110.)
    assert result['exit_cost_nok']==pytest.approx(.22)
    assert result['model_return_after_costs_pct']==pytest.approx(9.5609)
    assert result['actual_portfolio_result_verified'] is False


def test_flat_nok_price_loses_money_and_break_even_is_not_zero():
    result=reference(gross_factor=1.)
    assert result['model_return_after_costs_pct']==pytest.approx(-.3992)
    result=reference(gross_factor=1.002/.998)
    assert result['model_return_after_costs_pct']==0.


def test_foreign_reference_uses_both_fx_rates_and_only_one_combined_cost_per_side():
    result=reference(currency='USD',fx_entry=fx('USD',10.,'2026-11-10T07:59:00+00:00'),
                     fx_exit=fx('USD',11.,'2026-11-10T15:19:00+00:00'))
    assert result['status']=='COSTED_REFERENCE_AVAILABLE'
    assert result['entry_gross_nok']==1000.
    assert result['entry_cost_nok']==4.5
    assert result['exit_gross_nok']==pytest.approx(1210.)
    assert result['exit_cost_nok']==pytest.approx(5.445)
    assert result['model_return_after_costs_pct']==pytest.approx(round(100*(1204.555/1004.5-1),4))


@pytest.mark.parametrize('quote',[
    None,fx('SEK',10.,'2026-11-10T07:59:00+00:00'),
    fx('USD',10.,'2026-11-10T08:00:01+00:00'),
    fx('USD',10.,'2026-11-10T07:44:00+00:00'),
    fx('USD',True,'2026-11-10T07:59:00+00:00'),
    {**fx('USD',10.,'2026-11-10T07:59:00+00:00'),'quote_kind':'INDICATIVE_DAILY_RATE'},
])
def test_foreign_missing_wrong_future_stale_boolean_or_daily_fx_never_becomes_zero_cost(quote):
    result=reference(currency='USD',fx_entry=quote,fx_exit=fx('USD',11.,'2026-11-10T15:19:00+00:00'))
    assert result['status']=='UNQUALIFIED_FX'
    assert result['model_return_after_costs_pct'] is None


@pytest.mark.parametrize('currency',[None,'nok','US','',True])
def test_currency_is_documented_not_inferred_from_market(currency):
    assert reference(currency=currency)['status']=='UNQUALIFIED_CURRENCY'


def test_nok_cannot_silently_ignore_contradictory_fx():
    assert reference(fx_entry=fx('USD',10.,ENTRY))['status']=='UNQUALIFIED_FX'


def test_contract_after_entry_or_changed_policy_cannot_qualify_past_results():
    from services.learning_cost_reference import make_contract
    late=make_contract(at='2026-11-10T09:00:00+00:00',commit='a'*40)
    assert reference(contract=late)['status']=='UNQUALIFIED_COST_CONTRACT'
    changed=contract();changed['cost_policy']['components']['model_transaction_cost_nok']['rate_bps']=0
    assert reference(contract=changed)['status']=='UNQUALIFIED_COST_CONTRACT'
    assert reference(contract=None)['model_return_after_costs_pct'] is None


def test_contract_is_authoritative_immutable_and_keeps_original_publication_time(pg):
    from services.learning_cost_reference import ensure_contract, KEY
    first=ensure_contract(pg,clock=lambda:datetime(2026,11,10,7,tzinfo=timezone.utc),commit='a'*40)
    second=ensure_contract(pg,clock=lambda:datetime(2026,11,10,7,30,tzinfo=timezone.utc),commit='b'*40)
    assert first==second==pg.read_json(KEY)
    assert first['recorded_at']=='2026-11-10T07:00:00+00:00'
    assert first['commit']=='a'*40


def test_untraceable_contract_cannot_be_published(pg):
    from services.learning_cost_reference import ensure_contract,KEY
    with pytest.raises(ValueError,match='commit'):
        ensure_contract(pg,clock=lambda:datetime(2026,11,10,7,tzinfo=timezone.utc),commit='unknown')
    assert pg.read_json(KEY) is None


def bar(day,opened=100.,closed=110.,**kw):
    return {'date':day,'open':opened,'close':closed,'raw_open':opened,
            'return_basis':'PROVIDER_ADJUSTED_TOTAL_RETURN_PROXY_V1',**kw}


def measure_pair(currency='NOK',**kw):
    from services.learning_signal_measurement import measure,POLICY
    row={'ticker':'A.OL','market':'NORGE','entry_at':'2026-11-10T07:00:00+00:00',
         'measurement_policy':POLICY,'signal_reference':{'reference_currency':currency}}
    stock=kw.pop('stock',[bar('2026-11-10')])
    return measure(row,stock,[bar('2026-11-10',200.,204.)],
                   now=datetime(2026,11,10,18,tzinfo=timezone.utc),cost_contract=contract(),**kw)


def test_measurement_exposes_separate_cost_reference_without_claiming_actual_net():
    result=measure_pair()
    one=result['horizon_measurements']['1']
    assert one['cost_reference']['model_return_after_costs_pct']==pytest.approx(9.5609)
    assert one['net_return_pct'] is None
    assert result['entry_reference']['market_open_at']==ENTRY


def test_revised_fx_cannot_rewrite_a_frozen_costed_reference():
    entry_fx=fx('USD',10.,'2026-11-10T07:59:00+00:00')
    exit_fx=fx('USD',11.,'2026-11-10T15:19:00+00:00')
    stock=[bar('2026-11-10',fx_open_quote=entry_fx,fx_close_quote=exit_fx)]
    first=measure_pair('USD',stock=stock)
    changed=[bar('2026-11-10',fx_open_quote=entry_fx,fx_close_quote={**exit_fx,'rate':12.})]
    revised=measure_pair('USD',stock=changed,previous=first)
    assert revised['state']=='NORMALIZED_HISTORY_REVISION'
    assert revised['horizon_measurements']==first['horizon_measurements']


def test_later_missing_fx_preserves_exact_original_costed_reference():
    stock=[bar('2026-11-10',fx_open_quote=fx('USD',10.,'2026-11-10T07:59:00+00:00'),
               fx_close_quote=fx('USD',11.,'2026-11-10T15:19:00+00:00'))]
    first=measure_pair('USD',stock=stock)
    later=measure_pair('USD',previous=first)
    assert later['state']=='MEASURED'
    assert later['horizon_measurements']==first['horizon_measurements']


def test_cost_summary_replays_inputs_and_excludes_controls_legacy_and_tampering():
    from services.learning_signal_measurement import measure,POLICY,sessions
    from services.learning_cost_reference import summarize
    row={'ticker':'A.OL','group':'STRICT','status':'ACTIVE','market':'NORGE',
         'entry_at':'2026-11-10T07:00:00+00:00','measurement_policy':POLICY,
         'signal_reference':{'reference_currency':'NOK'}}
    days=[d for d,*_ in sessions('NORGE','2026-11-10','2026-12-10')]
    stock=[bar(d,100.,102.) for d in days]
    measured=measure(row,stock,stock,now=datetime(2026,12,10,18,tzinfo=timezone.utc),cost_contract=contract())
    good={**row,**measured}
    control={**good,'group':'MATCHED_CONTROL'}
    old={**good,'measurement_policy':'LEGACY'}
    corrupt=deepcopy(good);corrupt['horizon_measurements']['20']['cost_reference']['model_return_after_costs_pct']=999.
    loss={**row,**measure(row,[bar(d,100.,95.) for d in days],stock,
                        now=datetime(2026,12,10,18,tzinfo=timezone.utc),cost_contract=contract())}
    malformed=deepcopy(good);malformed['horizon_measurements']['20']['cost_reference']=None
    result=summarize([good,loss,control,old,corrupt,malformed],contract())
    assert result['count']==2 and result['unqualified_measured']==2
    assert result['mean_model_return_after_costs_pct']==pytest.approx(-1.8932)
    assert result['actual_portfolio_result_verified'] is False


def test_scheduled_maintenance_binds_contract_before_evaluation(pg,monkeypatch):
    import learning_observation_engine as engine
    import services.storage_service as stores
    import services.learning_position_outcomes as positions
    import services.learning_outcome_integrity as integrity
    from services.learning_cost_reference import KEY
    monkeypatch.setenv('RENDER_GIT_COMMIT','a'*40)
    monkeypatch.setattr(stores,'get_storage_service',lambda:pg)
    monkeypatch.setattr(engine,'read_json',lambda key,*a:{'report_id':'original'} if key==engine.BASELINE_KEY else {})
    monkeypatch.setattr(engine,'write_json',lambda *a:None)
    monkeypatch.setattr(engine,'load_engine_state',lambda:{})
    monkeypatch.setattr(engine,'_daily_due',lambda *a:True)
    monkeypatch.setattr(engine,'_weekly_due',lambda *a:False)
    monkeypatch.setattr(integrity,'run_authorized_cleanup',lambda **k:{'state':'COMPLETED'})
    monkeypatch.setattr(positions,'run_maintenance',lambda **k:{})
    monkeypatch.setattr(positions,'report_view',lambda x:{'status':'COMPLETED'})
    called=[]
    def evaluate(*a,**kw):
        assert pg.read_json(KEY) is not None
        called.append(True)
        return {'status':'COMPLETED'}
    monkeypatch.setattr(engine,'evaluate_observations',evaluate)
    result=engine.run_learning_maintenance(now=datetime(2026,11,10,7,tzinfo=timezone.utc))
    assert called==[True]
    assert result['cost_reference_contract']['status']=='BOUND'


def test_definition_write_delay_cannot_backdate_cost_contract_before_entry(pg):
    from services.learning_cost_reference import ensure_contract
    now=[datetime(2026,11,10,7,59,tzinfo=timezone.utc)]
    class Delayed:
        allow_local_fallback=False
        def using_postgres(self):return True
        def write_json_immutable(self,key,value):
            saved=pg.write_json_immutable(key,value)
            now[0]=datetime(2026,11,10,8,1,tzinfo=timezone.utc)
            return saved
    result=ensure_contract(Delayed(),clock=lambda:now[0],commit='a'*40)
    assert reference(contract=result)['status']=='UNQUALIFIED_COST_CONTRACT'


def test_read_only_report_never_publishes_a_contract(monkeypatch):
    import learning_observation_engine as engine
    import services.learning_cost_reference as costs
    monkeypatch.setattr(engine,'load_observations',lambda:[])
    monkeypatch.setattr(engine,'load_engine_state',lambda:{})
    monkeypatch.setattr(engine,'read_json',lambda *a:{})
    monkeypatch.setattr(costs,'ensure_contract',lambda *a,**k:pytest.fail('A preview must not publish a contract'))
    result=engine.report_control_snapshot()
    assert result['cost_reference_model']['count']==0
    assert result['cost_reference_model']['mean_model_return_after_costs_pct'] is None
    assert result['cost_reference_model']['actual_portfolio_result_verified'] is False


def test_public_cost_reference_text_does_not_label_it_portfolio_profit():
    from services.learning_cost_reference import report_text
    text=report_text({'count':1,'mean_model_return_after_costs_pct':1.5928})
    assert '+1,59 %' in text and '1 aksje' in text
    assert 'ikke porteføljeresultat' in text
    empty=report_text({'count':0,'mean_model_return_after_costs_pct':None})
    assert 'ikke kvalifisert' in empty and '0,00 %' not in empty


def test_engine_loads_persisted_contract_for_new_measurements(pg,monkeypatch):
    import learning_observation_engine as engine
    from services.learning_cost_reference import ensure_contract
    from services.learning_signal_measurement import POLICY
    ensure_contract(pg,commit='a'*40,clock=lambda:datetime(2026,11,10,7,tzinfo=timezone.utc))
    row={'observation_id':'new','ticker':'A.OL','market':'NORGE','group':'STRICT','status':'ACTIVE',
         'entry_at':'2026-11-10T07:00:00+00:00','entry_market_date':'2026-11-10',
         'measurement_policy':POLICY,'benchmark_ticker':'OSEBX.OL',
         'signal_reference':{'reference_currency':'NOK'},'decision_snapshot':{'original':True},
         'horizon_measurements':{},'daily_marks':[]}
    saved=[]
    monkeypatch.setattr(engine,'load_observations',lambda:[deepcopy(row)])
    monkeypatch.setattr(engine,'save_observations',lambda rows:saved.extend(rows))
    monkeypatch.setattr(engine,'read_json',lambda key,*a:pg.read_json(key,default={}))
    monkeypatch.setattr(engine,'write_json',lambda *a:None)
    monkeypatch.setattr(engine,'_audit',lambda *a,**k:None)
    engine.evaluate_observations(lambda *a:{'A.OL':[bar('2026-11-10')],'OSEBX.OL':[bar('2026-11-10',200.,204.)]},
                                  now=datetime(2026,11,10,18,tzinfo=timezone.utc))
    assert saved[0]['horizon_measurements']['1']['cost_reference']['model_return_after_costs_pct']==pytest.approx(9.5609)
    assert saved[0]['decision_snapshot']==row['decision_snapshot']


def test_optional_cost_source_failure_does_not_claim_zero_performance():
    from services.learning_cost_reference import read_contract
    def unavailable(key):raise RuntimeError('injected storage failure')
    assert read_contract(unavailable) is None
