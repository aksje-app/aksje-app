"""Synthetic unit/integration cases; NOT a production transition trial."""
from copy import deepcopy
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_portfolio_accounting import local, activate, fill, quote, AT, NOW
from test_revision_trade_postgres import pg
from services import portfolio_accounting as ledger
from services.economic_ledger import reconcile


def event(kind='DEPOSIT',identity='E1',**extra):
    return dict(event_id=identity,type=kind,at=AT,source_ref='TEST ONLY documented model event',
        cost_currency='NOK',cost_source_ref='TEST ONLY explicit zero costs',
        cost_components=dict(brokerage_nok=0,fx_cost_nok=0,other_nok=0),**extra)


def mark(price=100,rate=10):
    return dict(price=price,observed_at=AT,source='TEST ONLY raw market price',fx_quote=quote(rate))


def period(storage):return ledger.report('paper',storage=storage,at=NOW)['new_period']


def test_capital_flows_do_not_manufacture_profit_and_twr_tracks_market(local):
    activate(local);ledger.settle('paper',fill(),storage=local)
    ledger.record_event('paper',event(amount_nok=99990,valuation_marks={'TEST':mark()}),storage=local)
    result=period(local)
    assert result['verification']['status']=='BESTÅTT'
    assert result['verification']['verified_nav']==199980
    assert result['period_net_pnl_nok']==-10
    assert result['verification']['verified_net_return_pct']==pytest.approx(-.01)
    assert result['return_method']=='UNITIZED_TWR_V1'
    ledger.record_event('paper',event('WITHDRAWAL','W1',amount_nok=99990,valuation_marks={'TEST':mark()}),storage=local)
    assert period(local)['verification']['verified_net_return_pct']==pytest.approx(-.01)
    ledger.mark('paper',{'TEST':mark(rate=11)},at=AT,storage=local)
    assert period(local)['verification']['verified_nav']==100990
    assert period(local)['verification']['verified_net_return_pct']==pytest.approx(.99)
    assert period(local)['period_net_pnl_nok']==990


def test_deposit_withdrawal_costs_are_expenses_not_capital(local):
    activate(local)
    deposit=event(amount_nok=10000,valuation_marks={});deposit['cost_components']['other_nok']=10
    ledger.record_event('paper',deposit,storage=local)
    assert period(local)['cash_nok']==109990
    assert period(local)['period_net_pnl_nok']==-10
    assert period(local)['verification']['verified_net_return_pct']==pytest.approx(-10/110000*100,abs=1e-6)


def test_dividend_uses_documented_entitlement_after_position_sold(local):
    activate(local);ledger.settle('paper',fill(),storage=local)
    ledger.settle('paper',fill('EXIT','SELL'),storage=local)
    dividend=event('DIVIDEND',ticker='TEST',entitlement_source_ref='TEST ONLY ex-date record',
        entitlement_at=AT,entitled_quantity=10,per_share_local=2,currency='USD',fx_quote=quote(11),withholding_nok=33)
    dividend['cost_components']['other_nok']=2
    ledger.record_event('paper',dividend,storage=local)
    result=period(local)
    assert result['cash_nok']==100165  # 100000 - 20 trading costs + 220 - 33 - 2
    assert result['dividend_income_nok']==185
    assert result['withholding_nok']==33
    assert result['realized_pnl_nok']==-20
    assert result['period_net_pnl_nok']==165
    assert result['verification']['status']=='BESTÅTT'
    assert result['verification']['documented_costs']==22


@pytest.mark.parametrize('numerator,denominator,price,quantity',[(2,1,50,20),(1,2,200,5)])
def test_split_preserves_cost_basis_then_partial_sale(local,numerator,denominator,price,quantity):
    activate(local);ledger.settle('paper',fill(),storage=local)
    action=event('SPLIT',ticker='TEST',quantity_before=10,numerator=numerator,denominator=denominator,
        cash_in_lieu=False,post_action_mark=mark(price))
    ledger.record_event('paper',action,storage=local)
    result=period(local)
    assert result['positions']['TEST']['quantity']==quantity
    assert result['positions']['TEST']['cost_basis_base']==10010
    assert result['verification']['verified_nav']==99990
    ledger.settle('paper',fill('PARTIAL','SELL',quantity/2,price,10,5),storage=local)
    result=period(local)
    assert result['positions']['TEST']['cost_basis_base']==5005
    assert result['realized_pnl_nok']==-10
    assert result['verification']['status']=='BESTÅTT'


@pytest.mark.parametrize('kind', ['DEPOSIT','WITHDRAWAL','DIVIDEND','SPLIT','MERGER','SPINOFF','RETURN_OF_CAPITAL'])
def test_incomplete_or_unsupported_events_never_change_account(local,kind):
    before=activate(local)
    with pytest.raises((ValueError,KeyError)):ledger.record_event('paper',event(kind),storage=local)
    assert local.read_json(ledger.key('paper'))==before


def test_missing_or_stale_preflow_marks_stop_cashflow(local):
    activate(local);ledger.settle('paper',fill(),storage=local)
    before=local.read_json(ledger.key('paper'))
    with pytest.raises(ValueError):ledger.record_event('paper',event(amount_nok=1000,valuation_marks={}),storage=local)
    stale={**mark(),'observed_at':(NOW-timedelta(hours=1)).isoformat()}
    with pytest.raises(ValueError):ledger.record_event('paper',event(amount_nok=1000,valuation_marks={'TEST':stale}),storage=local)
    assert local.read_json(ledger.key('paper'))==before


def test_event_retry_conflicts_tampering_and_lost_ack(local,monkeypatch):
    activate(local);request=event(amount_nok=1000,valuation_marks={})
    real=local.mutate_json
    def lost_ack(*a,**kw):real(*a,**kw);raise OSError('TEST ONLY lost acknowledgement')
    monkeypatch.setattr(local,'mutate_json',lost_ack)
    with pytest.raises(OSError):ledger.record_event('paper',request,storage=local)
    monkeypatch.setattr(local,'mutate_json',real)
    before=local.read_json(ledger.key('paper'))
    assert ledger.record_event('paper',request,storage=local)==before
    with pytest.raises(ValueError):ledger.record_event('paper',{**request,'amount_nok':2000},storage=local)
    bad=deepcopy(before);bad['account']['performance_units']+=100
    assert reconcile(bad['account'])
    local.write_json(ledger.key('paper'),bad)
    assert ledger.report('paper',storage=local,at=NOW)['status']=='INTEGRITY_ERROR'


def test_event_retries_are_atomic_under_concurrency(local):
    activate(local);request=event(amount_nok=1000,valuation_marks={})
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:ledger.record_event('paper',request,storage=local),range(4)))
    result=period(local)
    assert result['cash_nok']==101000
    assert result['external_net_flows_nok']==1000
    assert result['period_net_pnl_nok']==0
    assert len(result['economic_events'])==1
    assert result['verification']['verified_net_return_pct']==0


def test_pg_events_and_cashflow_concurrency(pg,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    test_event_retries_are_atomic_under_concurrency(pg)


def test_mixed_events_survive_serialization_and_buy_add_sell(local):
    activate(local);ledger.record_event('paper',event(amount_nok=1000,valuation_marks={}),storage=local)
    ledger.settle('paper',fill(),storage=local)
    ledger.settle('paper',fill('ADD',quantity=5,fee=5),storage=local)
    ledger.settle('paper',fill('PARTIAL','SELL',3,110,11,3),storage=local)
    assert period(local)['verification']['status']=='BESTÅTT'
    assert period(local)['period_net_pnl_nok']==3132
    ledger.settle('paper',fill('FINAL','SELL',12,110,11,12),storage=local)
    assert period(local)['cash_nok']==104120
    assert period(local)['period_net_pnl_nok']==3120
    assert period(local)['verification']['verified_net_return_pct']==pytest.approx(3120/101000*100,abs=1e-6)
