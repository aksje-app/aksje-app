"""Reconcile the existing fund model without introducing a second money ledger."""
from copy import deepcopy
from datetime import datetime, timezone
import csv
from io import StringIO

import pytest
from test_superfund_v1 import item, step
from services.superfund_accounting import audit_native
from superfund_data import nok_quote
import superfund_reports


def priced(day='2026-10-05',price=100,rate=10,currency='USD'):
    return item(day=day,price=price,currency=currency,nok_rate=rate if currency!='NOK' else 1,
        source='TEST ONLY public price',fx_quote=None if currency=='NOK' else dict(currency=currency,
        base_currency='NOK',rate=rate,source='TEST ONLY ECB',observed_at=day+'T00:00:00+00:00'))


def opened(currency='USD'):
    state,_=step(None,[priced(currency=currency)])
    state,_=step(state,[priced(day='2026-10-06',currency=currency)],'2026-10-06')
    return state


@pytest.mark.parametrize('currency',['NOK','USD','EUR'])
def test_native_buy_fx_partial_and_full_sell(currency):
    state=opened(currency)
    checked=audit_native(state,at='2026-10-06T15:00:00+00:00')
    assert checked['status']=='VERIFISERT NOK-MODELL',checked
    pos=next(iter(state['positions'].values()));q=pos['quantity'];basis=pos['cost_nok']
    assert checked['verified_nav_nok']==pytest.approx(state['cash']+q*pos['last_nok'])
    assert checked['unrealized_pnl_nok']==pytest.approx(q*pos['last_nok']-basis)
    assert sum(checked['costs_nok'].values())==pytest.approx(basis-q*pos['last_nok'])
    # Explicit queued partial fill exercises the native accounting path, without
    # changing the engine's strategy or its rules for generating sell decisions.
    state['orders']=[dict(id=pos['id'],isin=pos['isin'],side='SELL',fraction=.4,
        requested_at='2026-10-06T15:00:00+00:00',next_at='2026-10-07T09:00:00+00:00')]
    state,_=step(state,[priced(day='2026-10-07',price=105,rate=11,currency=currency)],'2026-10-07')
    checked=audit_native(state,at='2026-10-07T15:00:00+00:00')
    assert checked['status']=='VERIFISERT NOK-MODELL',checked
    pos=next(iter(state['positions'].values()))
    assert pos['quantity']==pytest.approx(q*.6)
    assert pos['cost_nok']==pytest.approx(basis*.6)
    assert state['trades'][-1]['quantity']==pytest.approx(q*.4)
    assert checked['realized_pnl_nok']==pytest.approx(state['trades'][-1]['pnl_nok'])
    state['orders']=[dict(id=pos['id'],isin=pos['isin'],side='SELL',fraction=1,
        requested_at='2026-10-07T15:00:00+00:00',next_at='2026-10-08T09:00:00+00:00')]
    state,_=step(state,[priced(day='2026-10-08',price=106,rate=11,currency=currency)],'2026-10-08')
    checked=audit_native(state,at='2026-10-08T15:00:00+00:00')
    assert checked['status']=='VERIFISERT NOK-MODELL',checked
    assert not state['positions']
    assert checked['verified_nav_nok']==state['cash']
    assert checked['realized_pnl_nok']==pytest.approx(state['cash']-state['initial_capital'])
    assert checked['actual_broker_account'] is False
    assert checked['separate_operational_ledger'] is False


@pytest.mark.parametrize('change',['opening','quantity','cash','cost','fx','price_source','duplicate','pnl'])
def test_native_inconsistency_is_never_presented_as_verified(change):
    state=opened()
    if change=='opening':state.pop('accounting_opening')
    if change=='quantity':next(iter(state['positions'].values()))['quantity']+=1
    if change=='cash':state['cash']+=1
    if change=='cost':state['trades'][0]['cost_components']['fx_cost_nok']+=10
    if change=='fx':state['trades'][0]['fx_quote']['rate']+=1
    if change=='price_source':state['trades'][0]['price_source']=None
    if change=='duplicate':state['trades'].append(deepcopy(state['trades'][0]))
    if change=='pnl':
        pos=next(iter(state['positions'].values()))
        state['orders']=[dict(id=pos['id'],side='SELL',fraction=1,requested_at='2026-10-06T15:00:00Z',next_at='2026-10-07T09:00:00Z')]
        state,_=step(state,[priced(day='2026-10-07')],'2026-10-07')
        state['trades'][-1]['pnl_nok']+=1
    result=audit_native(state,at='2026-10-07T15:00:00Z')
    assert result['status']=='IKKE VERIFISERT'
    assert result['verified_nav_nok'] is None
    assert result['net_return_pct'] is None


def test_legacy_fund_history_is_preserved_without_fabricated_opening():
    state=opened();state.pop('accounting_opening')
    old=deepcopy(state)
    after,_=step(state,[priced(day='2026-10-07')],'2026-10-07')
    assert state==old
    assert 'accounting_opening' not in after
    assert after['trades'][:len(old['trades'])]==old['trades']
    assert audit_native(after,at='2026-10-07T15:00:00Z')['status']=='IKKE VERIFISERT'


def test_no_truncation_of_preserved_fund_trades_and_losses():
    state=opened()
    state['trades']=[{'id':str(i),'pnl_nok':-i} for i in range(2005)]
    old=deepcopy(state['trades'])
    after,_=step(state,[priced(day='2026-10-07')],'2026-10-07')
    assert after['trades']==old


def test_ecb_quote_preserves_exact_fixing_day_and_source():
    fx=dict(source='TEST ONLY ECB XML',days={'2026-10-02':{'NOK':10,'USD':2},'2026-10-07':{'NOK':12,'USD':2}})
    q=nok_quote('USD','2026-10-05T00:00:00Z',fx)
    assert q['rate']==5
    assert q['observed_at']=='2026-10-02T00:00:00+00:00'
    assert q['source']==fx['source']
    assert nok_quote('USD','2026-10-20',fx) is None


def test_reports_explicitly_distinguish_unverified_native_history():
    state=opened()
    snapshot=dict(model=state,at='2026-10-06T15:00:00Z')
    rows=list(csv.reader(StringIO(superfund_reports.csv_bytes(snapshot).decode('utf-8-sig'))))
    assert rows[0][-2:] == ['Regnskapsstatus','Kostnadsgrunnlag']
    assert rows[1][-2]=='VERIFISERT NOK-MODELL'
    state.pop('accounting_opening')
    rows=list(csv.reader(StringIO(superfund_reports.csv_bytes(snapshot).decode('utf-8-sig'))))
    assert rows[1][-2]=='IKKE VERIFISERT'
    from openpyxl import load_workbook
    from io import BytesIO
    wb=load_workbook(BytesIO(superfund_reports.xlsx_bytes(snapshot)))
    assert list(wb.active.values)[1][-2]=='IKKE VERIFISERT'


def test_native_report_refuses_future_opening_or_execution():
    state=opened()
    assert audit_native(state,at='2026-10-04T15:00:00Z')['verified_nav_nok'] is None
    assert audit_native(state,at='2026-10-05T15:00:00Z')['verified_nav_nok'] is None


def test_native_etf_costs_include_half_spread_once():
    def etf(day='2026-10-05'):
        row=priced(day=day,currency='EUR')
        row.update(kind='etf',spread_pct=.2)
        row['detail']['ucits']=True
        return row
    state,_=step(None,[etf()])
    state,_=step(state,[etf('2026-10-06')],'2026-10-06')
    checked=audit_native(state,at='2026-10-06T15:00:00Z')
    assert checked['status']=='VERIFISERT NOK-MODELL',checked
    trade=state['trades'][0]
    assert checked['costs_nok']['other_nok']==pytest.approx(trade['gross_nok']*.001)
    assert checked['verified_nav_nok']==pytest.approx(state['initial_capital']-sum(checked['costs_nok'].values()))
    trade['cost_policy']['spread_pct']=None
    assert audit_native(state,at='2026-10-06T15:00:00Z')['verified_nav_nok'] is None


def test_native_value_history_is_not_truncated():
    state=opened()
    old=[{'at':'2026-10-01T00:00:00Z','equity':1000000-i,'cash':900000,'frame':str(i)} for i in range(1505)]
    state['history']=deepcopy(old)
    after,_=step(state,[priced(day='2026-10-07')],'2026-10-07')
    assert after['history'][:len(old)]==old
    assert len(after['history'])==1506
