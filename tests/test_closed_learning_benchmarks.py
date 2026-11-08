from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
import pytest
from pypdf import PdfReader
from app_version import APP_VERSION
from services import learning_position_outcomes as outcomes

NOW=datetime(2026,11,8,1,tzinfo=timezone.utc)


def position(**kw):
    return dict(ticker='TEST.OL',opened_at='2026-11-03T10:00:00+00:00',
        closed_at='2026-11-06T17:00:00+00:00',average_price=100.,close_price=110.,
        pnl=1000.,pnl_pct=10.,quantity=100.,market='NORGE',benchmark_ticker='OSEBX.OL',
        learning_cohort=APP_VERSION,evidence_valid_at_entry=True,observation_days=4,**kw)


def series(symbol='OSEBX.OL'):
    return {symbol:[{'date':'2026-09-14','close':100.},
        {'date':'2026-11-02','close':100.},{'date':'2026-11-03','close':102.},
        {'date':'2026-11-06','close':105.}]}


class Store:
    def __init__(self,rows):self.data={outcomes.PORTFOLIO:{'positions':{'KEEP':{'quantity':2}},'closed_positions':deepcopy(rows)}};self.writes=[]
    def read_json(self,key,default=None):return deepcopy(self.data.get(key,default))
    def write_json(self,key,value):self.writes.append(key);self.data[key]=deepcopy(value)
    def write_json_immutable(self,key,value):
        self.writes.append(key)
        if key not in self.data:self.data[key]=deepcopy(value)
        return deepcopy(self.data[key])
    def mutate_json(self,key,fn):
        value=fn(deepcopy(self.data.get(key)));self.write_json(key,value);return deepcopy(value)


def test_realized_return_daily_asof_reference_and_gross_excess():
    row=position();original=deepcopy(row)
    result=outcomes.measure(row,series(),now=NOW)
    assert result['gross_return_pct']==pytest.approx(10)
    assert result['benchmark_return_pct']==pytest.approx(5)
    assert result['excess_return_pct']==pytest.approx(5)
    assert result['entry_reference']['date']=='2026-11-02'
    assert result['exit_reference']['date']=='2026-11-06'
    assert result['validation_eligible'] and not result['net_after_costs_measured']
    assert outcomes.verified_measurement(row,result)==result and row==original


def test_missing_original_index_uses_labelled_comparator_without_rewriting_choice():
    row=position();row['benchmark_ticker']='^OSEAX'
    result=outcomes.measure(row,series(),now=NOW)
    assert result['requested_benchmark']=='^OSEAX' and result['benchmark_symbol']=='OSEBX.OL'
    assert result['retrospective_comparator'] and not result['validation_eligible']
    assert result['original_benchmark_errors'] and row['benchmark_ticker']=='^OSEAX'


def test_missing_entry_reference_does_not_become_frozen_original_evidence():
    row=position();row.pop('benchmark_ticker');row.pop('market');row.pop('learning_cohort')
    result=outcomes.measure(row,series(),now=NOW)
    assert result['cohort']=='LEGACY_UNVERSIONED' and not result['validation_eligible']
    assert result['retrospective_comparator']


@pytest.mark.parametrize('changes',[{'average_price':0},{'close_price':float('nan')},
    {'close_price':float('inf')},{'opened_at':'2026-11-03T10:00:00'},
    {'opened_at':'2026-11-07T17:00:00Z'},{'closed_at':'2026-11-10T17:00:00Z'}])
def test_bad_prices_naive_dates_reversed_or_future_fills_are_not_measured(changes):
    row=position();row.update(changes)
    with pytest.raises((ValueError,KeyError,TypeError)):outcomes.measure(row,series(),now=NOW)


def test_future_price_or_stale_prior_session_cannot_fill_missing_exit():
    values=series();values['OSEBX.OL'][-1]={'date':'2026-11-09','close':105.}
    with pytest.raises(ValueError,match='Missing or conflicting'):outcomes.measure(position(),values,now=NOW)


def test_conflicting_expected_session_prices_are_not_silently_selected():
    values=series();values['OSEBX.OL'].append({'date':'2026-11-06','close':106.})
    with pytest.raises(ValueError,match='Missing or conflicting'):outcomes.measure(position(),values,now=NOW)


def test_us_holiday_early_close_and_publication_buffer():
    at=datetime(2025,11,28,18,20,tzinfo=timezone.utc)
    data=[{'date':'2025-11-26','close':100},{'date':'2025-11-28','close':101}]
    assert outcomes.reference_point(data,at,'USA')['date']=='2025-11-28'
    assert outcomes.reference_point(data,at-timedelta(minutes=10),'USA')['date']=='2025-11-26'


def test_changed_source_or_self_consistent_forged_flags_do_not_validate():
    row=position();row['benchmark_ticker']='^OSEAX'
    measured=outcomes.measure(row,series(),now=NOW)
    other=deepcopy(row);other['close_price']=120
    assert outcomes.verified_measurement(other,measured) is None
    forged=deepcopy(measured);forged['validation_eligible']=True;forged['retrospective_comparator']=False
    forged['sha256']=outcomes.digest({k:v for k,v in forged.items() if k!='sha256'})
    assert outcomes.verified_measurement(row,forged) is None


def test_batch_resume_idempotency_and_no_portfolio_writes():
    rows=[position(),position()];rows[1]['ticker']='SECOND.OL'
    store=Store(rows);before=deepcopy(store.data[outcomes.PORTFOLIO]);calls=[]
    loader=lambda *a:(calls.append(1) or series())
    first=outcomes.run_maintenance(service=store,now=NOW,series_loader=loader,limit=1)
    assert first['measured']==1 and first['pending_after_batch']==1
    second=outcomes.run_maintenance(service=store,now=NOW,series_loader=loader,limit=1)
    assert second['measured']==2 and second['unmeasured']==0
    snapshots=deepcopy({k:v for k,v in store.data.items() if '/measurements/' in k})
    assert outcomes.run_maintenance(service=store,now=NOW,series_loader=loader)['processed_in_batch']==0
    assert len(calls)==2 and snapshots=={k:v for k,v in store.data.items() if '/measurements/' in k}
    assert store.data[outcomes.PORTFOLIO]==before and all(k.startswith(outcomes.PREFIX) for k in store.writes)


def test_interrupted_index_commit_resumes_existing_immutable_receipt(monkeypatch):
    store=Store([position()]);original=store.mutate_json
    monkeypatch.setattr(store,'mutate_json',lambda *a:(_ for _ in ()).throw(RuntimeError('connection interrupted')))
    with pytest.raises(RuntimeError):outcomes.run_maintenance(service=store,now=NOW,series_loader=lambda *a:series())
    receipt=deepcopy(next(v for k,v in store.data.items() if '/measurements/' in k))
    monkeypatch.setattr(store,'mutate_json',original)
    assert outcomes.run_maintenance(service=store,now=NOW+timedelta(seconds=2),series_loader=lambda *a:series())['measured']==1
    assert next(iter(store.data[outcomes.INDEX]['records'].values()))==receipt


def test_missing_provider_data_retries_after_cooldown_without_inventing_zero_return():
    store=Store([position()]);calls=[]
    loader=lambda *a:(calls.append(1) or {})
    first=outcomes.run_maintenance(service=store,now=NOW,series_loader=loader)
    assert first['unmeasured']==1 and first['mean_excess_return_pct'] is None
    outcomes.run_maintenance(service=store,now=NOW+timedelta(minutes=10),series_loader=loader)
    assert len(calls)==1
    later=outcomes.run_maintenance(service=store,now=NOW+timedelta(hours=1),series_loader=lambda *a:series())
    assert later['measured']==1


def test_recovered_original_reference_upgrades_proxy_preserving_old_receipt():
    row=position();row['benchmark_ticker']='^OSEAX';store=Store([row])
    outcomes.run_maintenance(service=store,now=NOW,series_loader=lambda *a:series())
    previous=deepcopy(next(iter(store.data[outcomes.INDEX]['records'].values())))
    values={**series(),**series('OSEAX.OL')}
    def not_due(*a):raise AssertionError('Do not redownload old proxy inputs every day')
    assert outcomes.run_maintenance(service=store,now=NOW+timedelta(days=1),series_loader=not_due)['processed_in_batch']==0
    summary=outcomes.run_maintenance(service=store,now=NOW+timedelta(days=7),series_loader=lambda *a:values)
    assert summary['eligible_original_benchmarks']==1 and summary['retrospective_comparators']==0
    assert any(v==previous for k,v in store.data.items() if '/measurements/' in k)
    assert previous['sha256'] in store.data[outcomes.INDEX]['history'][outcomes.position_id(row)]


def test_duplicate_history_is_preserved_but_not_counted_twice_and_cohorts_stay_apart():
    a=position();b=position();b['learning_cohort']='OLDER';b['close_price']=90.
    records={outcomes.position_id(r):outcomes.measure(r,series(),now=NOW) for r in (a,b)}
    result=outcomes.summarize([a,deepcopy(a),b],{'records':records})
    assert result['stored_closed_rows']==3 and result['closed_positions']==result['measured']==2
    assert result['duplicate_rows_not_counted_twice']==1 and len(result['by_cohort'])==2
    assert result['mean_excess_return_pct']==pytest.approx(-5)
    assert result['current_cohort']['measured']==1
    assert result['current_cohort']['mean_excess_return_pct']==pytest.approx(5)


def test_readiness_requires_verified_original_benchmarks_and_keeps_30_position_gate(monkeypatch):
    import learning_acceptance as acceptance
    rows=[];records={}
    for i in range(30):
        row=position();row.update(ticker=f'T{i}.OL',opened_at='2026-09-15T10:00:00Z',observation_days=20,benchmark_ticker='^OSEAX')
        rows.append(row);records[outcomes.position_id(row)]=outcomes.measure(row,series(),now=NOW)
    monkeypatch.setattr(acceptance,'read_json',lambda *a:{'records':records})
    monkeypatch.setattr(acceptance,'write_json',lambda *a:None)
    run={'run_id':'R','candidates':[{'ticker':'T0.OL'}],'autonomous_chain':{'status':'OK',
         'learning_portfolio':{'positions':{},'closed_positions':rows,'last_run_id':'R'},
         'learning_performance':{'return_pct':10},
         'learning_decisions':[{'ticker':'T0.OL','action':'OBSERVE','reason':'Follow'}]}}
    result=acceptance.evaluate_learning_run(run)
    assert result['strategy_readiness']=='NOT_VALIDATED'
    assert result['closed_position_benchmarks']['measured']==30
    assert result['strategy_quality_gate']['benchmark_measured_positions']==0
    for row in rows:row['benchmark_ticker']='OSEBX.OL'
    records.clear();records.update({outcomes.position_id(r):outcomes.measure(r,series(),now=NOW) for r in rows})
    result=acceptance.evaluate_learning_run(run)
    assert result['strategy_readiness']=='VALIDATED_CANDIDATE'
    assert not result['strategy_quality_gate']['automatic_production_promotion_allowed']
    rows.pop()
    assert acceptance.evaluate_learning_run(run)['strategy_readiness']=='NOT_VALIDATED'


def test_legacy_brazil_position_does_not_get_a_us_comparator():
    row=position();row.update(ticker='GGBR4.SA',market=None,benchmark_ticker=None,
        opened_at='2026-11-03T22:00:00Z',closed_at='2026-11-06T22:00:00Z')
    data={'^BVSP':[{'date':'2026-11-03','close':100},{'date':'2026-11-06','close':105}]}
    measured=outcomes.measure(row,data,now=NOW)
    assert measured['market']=='BRASIL' and measured['benchmark_symbol']=='^BVSP'
    assert not measured['validation_eligible'] and measured['retrospective_comparator']


def test_calendar_age_without_actual_observations_cannot_claim_maturity():
    import autonomous_portfolio as ap
    portfolio={'positions':{'OLD':{'quantity':1,'average_price':100,'opened_at':'2020-01-01T00:00:00Z'}},
               'closed_positions':[{'opened_at':'2020-01-01T00:00:00Z','observation_days':0}]}
    assert ap.learning_portfolio_performance(portfolio)['mature_observations_20d']==0
    portfolio['positions']['OLD']['observation_days']=20
    assert ap.learning_portfolio_performance(portfolio)['mature_observations_20d']==1


def test_pdf_explains_closed_sample_proxy_and_gross_comparison():
    import learning_observation_engine as engine
    analysis=engine.build_weekly_analysis([])
    analysis['closed_position_results']={'measured':129,'closed_positions':129,'mean_excess_return_pct':-4.5,'retrospective_comparators':129}
    pdf=engine.build_weekly_pdf(analysis)
    text=' '.join(' '.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages).split())
    assert '129 / 129' in text and '-4.50' in text and 'før kostnader' in text
    assert 'Ettervalgte referanser: 129' in text and 'ikke hele porteføljen' in text


def test_closed_result_collection_runs_when_weekday_observations_are_not_due(monkeypatch):
    import learning_observation_engine as engine
    store={engine.BASELINE_KEY:{'report_id':'KEEP'},engine.STATE_KEY:{}}
    monkeypatch.setattr(engine,'read_json',lambda k,p,d:deepcopy(store.get(k,d)))
    monkeypatch.setattr(engine,'write_json',lambda k,p,v:store.__setitem__(k,deepcopy(v)))
    monkeypatch.setattr(engine,'_daily_due',lambda now:False)
    monkeypatch.setattr(engine,'_weekly_due',lambda now:False)
    calls=[]
    monkeypatch.setattr(outcomes,'run_maintenance',lambda **kw:(calls.append(kw) or {'status':'COMPLETED','measured':129}))
    result=engine.run_learning_maintenance(now=NOW)
    assert len(calls)==1 and result['closed_positions']['measured']==129
    assert store[engine.STATE_KEY]['closed_positions']['status']=='COMPLETED'


def test_daily_message_shows_closed_results_without_losing_three_streams(monkeypatch):
    from test_shadow_guard_schedule import report
    from services import shadow_daily_guard as guard
    row=report(NOW)
    row['learning_progress']['closed_position_results']={'closed_positions':129,'measured':129,
        'retrospective_comparators':129,'mean_excess_return_pct':-.88}
    monkeypatch.setattr(guard,'evaluate',lambda *a:deepcopy(row))
    monkeypatch.setattr(guard,'read_json',lambda *a:{})
    monkeypatch.setattr(guard,'write_json',lambda *a:None)
    calls=[]
    monkeypatch.setattr('notifier.send_pushover_alert',lambda message,**kw:(calls.append(message) or (True,'HTTP 200')))
    assert guard.send_daily_if_due(now=NOW)['sent'] is True
    assert len(calls[0])<=1024
    assert '129/129' in calls[0] and '-0.88 pp før kostnader' in calls[0]
    assert all(name in calls[0] for name in ('Autonomi:','Superporteføljen:','Aksjeunivers:','NOT_VALIDATED'))


def test_provider_series_are_frozen_once_per_day_without_repeated_downloads(monkeypatch):
    import learning_observation_engine as engine
    store=Store([]);calls=[]
    monkeypatch.setattr(engine,'yfinance_series_loader',lambda *a:(calls.append(a) or series()))
    first=outcomes.cached_series(['OSEBX.OL'],store,NOW)
    second=outcomes.cached_series(['OSEBX.OL'],store,NOW+timedelta(minutes=15))
    assert first==second and len(calls)==1
    outcomes.cached_series(['OSEBX.OL'],store,NOW+timedelta(days=1))
    assert len(calls)==2 and len([k for k in store.data if '/series/' in k])==2
