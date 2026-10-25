"""New policies are synthetic approvals in isolated accounts, never production defaults."""
from copy import deepcopy
from datetime import datetime, timedelta
import math
import pytest
from services import trading_costs as costs, economic_ledger as engine
from services import portfolio_accounting as ledger, restart_trading as trading, simulation_restart as restart
from test_restart_trading import active, at, evidence, candidate, execute
from test_simulation_restart import storage, sealed, sources, certificate, dump_program


def rule(**terms): return dict(source_ref='SYNTHETIC explicit test assumption', **terms)


def policy(slippage=None):
    result=dict(schema=costs.SCHEMA,source_ref='SYNTHETIC signed test policy',components={
        'brokerage_nok':rule(rate_pct=.05,fixed_nok=2),
        'fx_cost_nok':rule(rate_bps=25), 'other_nok':rule(rate_bps=3,fixed_nok=1)})
    if slippage is not None: result['slippage']=rule(rate_bps=slippage)
    return result


def row(at, *, price=100, rate=10, currency='USD', assumption=None):
    result=evidence(at,price=price,rate=rate,currency=currency)['TEST']
    result.pop('cost_components')
    result['cost_policy']=assumption or policy()
    result['cost_source_ref']=result['cost_policy']['source_ref']
    return {'TEST':result}


@pytest.mark.parametrize('side,price',[('BUY',100.1),('SELL',99.9)])
def test_rates_percent_bps_fixed_and_slippage_have_distinct_cash_effects(side,price):
    result=costs.calculate(policy(10),quantity=10,reference_price=100,side=side,currency='USD',nok_rate=10)
    gross=10*price*10
    assert result['price']==pytest.approx(price)
    assert result['gross_nok']==pytest.approx(gross)
    assert result['cost_components']==pytest.approx({'brokerage_nok':gross*.0005+2,'fx_cost_nok':gross*.0025,'other_nok':gross*.0003+1})
    # Slippage moves gross; it is not added as another fee component.
    assert result['fee_nok']==pytest.approx(gross*.0033+3)


@pytest.mark.parametrize('gross',[10000,20000,144146.144])
def test_existing_superportfolio_cost_scales_once_and_keeps_aggregate_label(gross):
    p=costs.super_portfolio_proposal({'transaction_cost_bps':10},source_ref='SYNTHETIC archived 10bp',fx_component=rule(rate_bps=25))
    costs.validate_family(p,'super_portfolio',{'transaction_cost_bps':10})
    result=costs.calculate(p,quantity=gross/100,reference_price=100,side='BUY',currency='NOK',nok_rate=1)
    assert result['fee_nok']==pytest.approx(gross*.001)
    assert set(result['cost_components'])=={'model_transaction_cost_nok','fx_cost_nok'}
    assert result['cost_components']['fx_cost_nok']==0
    assert result['cost_calculation']['fx_treatment']=='NO_CURRENCY_CONVERSION'


@pytest.mark.parametrize('bad',[None,{}, {'schema':'unknown'}, {'source_ref':'x','components_per_fill':None}])
def test_missing_or_unknown_policy_never_becomes_zero(bad):
    with pytest.raises(ValueError):costs.validate(bad)


@pytest.mark.parametrize('failure',['unknown-fx','negative','nan','boolean','infinite','two-units','missing-source','unknown-field','double-cost','slip100'])
def test_policy_rejects_undocumented_or_ambiguous_assumptions(failure):
    p=policy()
    if failure=='unknown-fx':p['components']['fx_cost_nok']=None
    if failure in ('negative','nan','boolean','infinite'):
        p['components']['fx_cost_nok']['rate_bps']={'negative':-1,'nan':float('nan'),'boolean':True,'infinite':float('inf')}[failure]
    if failure=='two-units':p['components']['fx_cost_nok']['rate_pct']=.1
    if failure=='missing-source':p['components']['other_nok'].pop('source_ref')
    if failure=='unknown-field':p['components']['other_nok']['rate_percent']=3
    if failure=='double-cost':p['components']['model_transaction_cost_nok']=rule(rate_bps=10)
    if failure=='slip100':p['slippage']=rule(rate_pct=100)
    with pytest.raises(ValueError):costs.validate(p)


def test_unresolved_proposal_is_not_signable_and_sp_cannot_replace_rate_with_fixed_fee():
    proposal=costs.super_portfolio_proposal({'transaction_cost_bps':10},source_ref='documented existing model')
    assert proposal['components']['fx_cost_nok'] is None
    with pytest.raises(ValueError):costs.validate(proposal)
    p=costs.super_portfolio_proposal({'transaction_cost_bps':10},source_ref='fixture',fx_component=rule(rate_bps=25))
    p['components']['model_transaction_cost_nok']['rate_bps']=20
    with pytest.raises(ValueError):costs.validate_family(p,'super_portfolio',{'transaction_cost_bps':10})
    p['components']['model_transaction_cost_nok']=rule(fixed_nok=10)
    with pytest.raises(ValueError):costs.validate_family(p,'super_portfolio',{'transaction_cost_bps':10})


def test_affordability_includes_all_fees_fx_slippage_and_fractional_rounding():
    p=policy(10);budget=10000
    q=costs.affordable_quantity(p,budget_nok=budget,reference_price=100,currency='USD',nok_rate=10)
    fill=costs.calculate(p,quantity=q,reference_price=100,side='BUY',currency='USD',nok_rate=10)
    next_fill=costs.calculate(p,quantity=q+.0001,reference_price=100,side='BUY',currency='USD',nok_rate=10)
    assert fill['gross_nok']+fill['fee_nok']<=budget
    assert next_fill['gross_nok']+next_fill['fee_nok']>budget
    assert costs.affordable_quantity(p,budget_nok=2,reference_price=100,currency='USD',nok_rate=10)==0


@pytest.mark.parametrize('family',list(restart.CAPITALS))
def test_atomic_round_trip_partial_sale_nav_and_original_stores_preserved(active,family):
    backend,bundle,scoped=active;time=at(active)
    # These are synthetic new model approvals in tests, never account defaults.
    p=policy(10) if family!='super_portfolio' else costs.super_portfolio_proposal(
        {'transaction_cost_bps':10},source_ref='SYNTHETIC existing model',fx_component=rule(rate_bps=25))
    old={'loss':-25000,'history':[{'old':True}],'learning':{'weights':[.3,.7]}}
    for key in ['paper_trading/portfolio.json','autonomous_portfolio/portfolio.json','super_portfolio/state.json','superfund/models/original.json','learning/original.json']:
        backend.write_json(key,old)
    old_bundle=backend.read_json(restart._key(bundle['period_id']))
    common=dict(period_id=bundle['period_id'],family=family,at=time,settings={},strategy_input={},
        account_ref=trading.account_reference(bundle['period_id'],family,storage=backend),storage=backend)
    ev=row(time,assumption=p)
    def buy(session):
        q=session.size_buy('TEST',10000)
        session.fill('TEST','BUY',q,100,'SYNTHETIC decision')
        return {'quantity':q,'nav':session.nav()}
    result=trading.run(**common,run_id='buy',evidence=ev,operation=buy)
    doc=scoped.read_json(ledger.key(family));trade=doc['account']['trades'][0];q=result['quantity']
    expected=costs.calculate(p,quantity=q,reference_price=100,side='BUY',currency='USD',nok_rate=10)
    assert doc['account']['cash']==pytest.approx(restart.CAPITALS[family]-expected['gross_nok']-expected['fee_nok'])
    assert result['nav']==pytest.approx(doc['account']['cash']+q*100*10)
    assert doc['account']['positions']['TEST']['cost_basis_base']==pytest.approx(expected['gross_nok']+expected['fee_nok'])
    before=deepcopy(doc)
    assert trading.run(**common,run_id='buy',evidence=ev,operation=buy)==result
    assert scoped.read_json(ledger.key(family))==before
    # A quarter sale uses changed market/FX and exactly one new set of costs.
    ev2=row(time,price=110,rate=11,assumption=p)
    def sell(session):session.fill('TEST','SELL',q/4,110,'partial');return {'ok':True}
    trading.run(**common,run_id='partial',evidence=ev2,operation=sell)
    doc=scoped.read_json(ledger.key(family));sale=doc['account']['trades'][-1]
    assert sale['gross_value']==pytest.approx(q/4*costs.fill_price(p,110,'SELL')*11)
    assert sale['pnl']==pytest.approx(sale['gross_value']-sale['fee']-(expected['gross_nok']+expected['fee_nok'])/4)
    report=ledger.report(family,storage=scoped,at=datetime.fromisoformat(time))['new_period']
    assert report['verification']['status']=='BESTÅTT'
    assert report['period_net_pnl_nok']==pytest.approx(report['realized_pnl_nok']+report['unrealized_pnl_nok'])
    assert sum(report['costs_nok'].values())==pytest.approx(doc['account']['fees_paid'])
    if family=='super_portfolio':assert 'brokerage_nok' not in report['costs_nok'] and not report['cost_breakdown_complete']
    for key in ['paper_trading/portfolio.json','autonomous_portfolio/portfolio.json','super_portfolio/state.json','superfund/models/original.json','learning/original.json']:assert backend.read_json(key)==old
    updated=backend.read_json(restart._key(bundle['period_id']))
    for other in set(restart.CAPITALS)-{family}:assert updated['accounts'][other]==old_bundle['accounts'][other]


def test_unknown_fx_or_failed_operation_rolls_back_everything(active):
    backend,bundle,scoped=active;time=at(active);ev=row(time)
    common=dict(period_id=bundle['period_id'],family='paper',run_id='bad',at=time,settings={},strategy_input={},
        account_ref=trading.account_reference(bundle['period_id'],'paper',storage=backend),storage=backend)
    before=backend.read_json(restart._key(bundle['period_id']))
    ev['TEST']['cost_policy']['components']['fx_cost_nok']=None
    with pytest.raises(ValueError):trading.run(**common,evidence=ev,operation=lambda s:{})
    ev=row(time)
    def fail(session):session.fill('TEST','BUY',1,100,'fixture');raise RuntimeError('before commit')
    with pytest.raises(RuntimeError):trading.run(**common,evidence=ev,operation=fail)
    assert backend.read_json(restart._key(bundle['period_id']))==before


def test_calculation_evidence_replay_rejects_changed_slippage_policy(active):
    backend,bundle,scoped=active;time=at(active)
    common=dict(period_id=bundle['period_id'],family='paper',run_id='proof',at=time,settings={},strategy_input={},
        account_ref=trading.account_reference(bundle['period_id'],'paper',storage=backend),storage=backend,evidence=row(time,assumption=policy(10)))
    trading.run(**common,operation=lambda s:(s.fill('TEST','BUY',1,100,'proof') and {'ok':True}))
    doc=scoped.read_json(ledger.key('paper'));ledger.verify(doc)
    # Recompute outer event hashes: arithmetic replay must still reject forgery.
    changed=deepcopy(doc)
    fill=next(e for e in changed['events'] if e['kind']=='FILL')
    fill['payload']['cost_calculation']['policy']['slippage']['rate_bps']=20
    from services.economic_opening import digest
    for i,event in enumerate(changed['events']):
        event['previous_hash']=changed['events'][i-1]['hash'] if i else None
        event['hash']=digest({k:v for k,v in event.items() if k!='hash'})
    with pytest.raises(ValueError):ledger.verify(changed)


@pytest.mark.parametrize('family',list(restart.CAPITALS))
def test_ordinary_strategies_execute_variable_fees_and_slippage(active,family):
    p=policy(10) if family!='super_portfolio' else costs.super_portfolio_proposal(
        {'transaction_cost_bps':10},source_ref='SYNTHETIC existing model',fx_component=rule(rate_bps=25))
    first=at(active);second=at(active,3)
    if family=='paper':
        execute(active,family,'ordinary-buy',first,[dict(ticker='TEST',operation='BUY',amount_nok=10000,confidence=90)],ev=row(first,assumption=p))
    else:
        execute(active,family,'search',first,[candidate(first)],ev=row(first,assumption=p))
        execute(active,family,'buy',second,[candidate(second)],ev=row(second,assumption=p))
    doc=active[2].read_json(ledger.key(family));trades=doc['account']['trades']
    assert trades
    for trade in trades:
        expected=costs.calculate(p,quantity=trade['quantity'],reference_price=100,side='BUY',currency='USD',nok_rate=10)
        assert trade['fee']==pytest.approx(expected['fee_nok'])
        assert trade['price']==pytest.approx(expected['price'])
    assert engine.reconcile(doc['account'])==[]


def test_variable_cost_trades_and_dividend_replay_in_same_journal(active):
    from services import economic_events
    backend,bundle,scoped=active;time=at(active)
    trading.run(period_id=bundle['period_id'],family='paper',run_id='event-buy',at=time,evidence=row(time,assumption=policy(10)),settings={},strategy_input={},
        account_ref=trading.account_reference(bundle['period_id'],'paper',storage=backend),storage=backend,
        operation=lambda s:(s.fill('TEST','BUY',1,100,'fixture') and {'ok':True}))
    event=dict(event_id='synthetic-dividend',type='DIVIDEND',at=time,source_ref='SYNTHETIC entitlement',
        ticker='TEST',entitlement_source_ref='SYNTHETIC independent entitlement',entitled_quantity=1,entitlement_at=time,currency='NOK',cost_currency='NOK',per_share_local=10,withholding_nok=1,
        cost_components=dict(brokerage_nok=0,fx_cost_nok=0,other_nok=1),cost_source_ref='SYNTHETIC documented event fee')
    ledger.record_event('paper',event,storage=scoped)
    doc=scoped.read_json(ledger.key('paper'));ledger.verify(doc)
    assert economic_events.reconcile_events(doc['account'])==[]


def test_strategy_cannot_change_cost_terms_after_authorization(active):
    backend,bundle,scoped=active;time=at(active)
    before=backend.read_json(restart._key(bundle['period_id']))
    def operation(session):
        session.evidence['TEST']['cost_policy']['components']['brokerage_nok']['rate_pct']=1
        session.fill('TEST','BUY',1,100,'changed assumption')
        return {'ok':True}
    with pytest.raises(ValueError,match='cannot change'):
        trading.run(period_id=bundle['period_id'],family='paper',run_id='changed-policy',at=time,evidence=row(time),settings={},strategy_input={},
            account_ref=trading.account_reference(bundle['period_id'],'paper',storage=backend),storage=backend,operation=operation)
    assert backend.read_json(restart._key(bundle['period_id']))==before


def test_cost_overflow_and_noncanonical_currency_are_rejected():
    p=policy();p['components']['brokerage_nok']['rate_pct']=1e308
    with pytest.raises(ValueError):costs.calculate(p,quantity=100,reference_price=100,side='BUY',currency='USD',nok_rate=10)
    with pytest.raises(ValueError):costs.calculate(policy(),quantity=1,reference_price=100,side='BUY',currency='ÄBC',nok_rate=10)


def test_direct_account_audit_rejects_missing_aggregate_calculation(active):
    backend,bundle,scoped=active;time=at(active)
    p=costs.super_portfolio_proposal({'transaction_cost_bps':10},source_ref='SYNTHETIC archived model',fx_component=rule(rate_bps=25))
    trading.run(period_id=bundle['period_id'],family='super_portfolio',run_id='aggregate-proof',at=time,evidence=row(time,assumption=p),settings={},strategy_input={},
        account_ref=trading.account_reference(bundle['period_id'],'super_portfolio',storage=backend),storage=backend,
        operation=lambda s:(s.fill('TEST','BUY',1,100,'fixture') and {'ok':True}))
    account=scoped.read_json(ledger.key('super_portfolio'))['account']
    assert engine.reconcile(account)==[]
    account['trades'][0].pop('cost_calculation')
    assert 'MISSING_MODEL_COST_CALCULATION' in engine.reconcile(account)


def test_nok_policy_cannot_be_booked_as_another_base_currency():
    at='2026-10-25T00:00:00+00:00'
    account=engine.new_account(10000,base_currency='USD',at=at)
    result=costs.calculate(policy(),quantity=1,reference_price=100,side='BUY',currency='USD',nok_rate=1)
    before=deepcopy(account)
    with pytest.raises(ValueError,match='NOK ledger'):
        engine.execute(account,trade_id='wrong-base',ticker='TEST',side='BUY',quantity=1,price=100,
            currency='USD',observed_at=at,source='SYNTHETIC quote',at=at,fee=result['fee_nok'],cost_currency='USD',
            cost_components=result['cost_components'],cost_source_ref=result['cost_source_ref'],cost_calculation=result['cost_calculation'])
    assert account==before
