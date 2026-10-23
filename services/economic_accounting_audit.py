"""Read-only verification of economic NAV; never migrates legacy model units.

A historical local-price model cannot become a NOK/share ledger by relabelling
its quantities. Missing FX, unit provenance or fees remain explicit evidence
holes. Only supplied, dated rates can authorise a converted valuation.
"""
from datetime import datetime, timedelta, timezone
from math import isfinite


def _number(value):
    try:
        result=float(value)
        return result if isfinite(result) else None
    except (ValueError,TypeError):
        return None


def _time(value):
    try:
        result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo is not None else None
    except (ValueError,TypeError):
        return None


def audit(portfolio, trades=(), *, at=None):
    """Return verified base-currency value or None, with every missing input.

    FX quotes belong to positions: fx_quote {currency, base_currency, rate,
    observed_at, source}. Rate = base units per one quote-currency unit. A five
    calendar day valuation ceiling is not an execution freshness allowance.
    """
    at=at or datetime.now(timezone.utc)
    if at.tzinfo is None:raise ValueError('Audit time requires timezone')
    at=at.astimezone(timezone.utc)
    base=str(portfolio.get('base_currency') or (portfolio.get('config') or {}).get('base_currency') or '').upper()
    errors=[]
    if portfolio.get('accounting_schema') == 'BASE_CURRENCY_SHARES_V1':
        from services.economic_ledger import reconcile
        trades = portfolio.get('trades') or []
        created = _time(portfolio.get('created_at'))
        if created is None or created > at:
            errors.append('INVALID_OR_FUTURE_OPENING_TIME')
        if any(_time(t.get('timestamp')) is None or _time(t.get('timestamp')) > at for t in trades):
            errors.append('FUTURE_OR_UNDATED_TRADE_AT_VALUATION')
        if any(_time(e.get('input',{}).get('at')) is None or _time(e['input']['at']) > at for e in portfolio.get('economic_events',[])):
            errors.append('FUTURE_OR_UNDATED_ECONOMIC_EVENT')
        if portfolio.get('marked_at') and (_time(portfolio['marked_at']) is None or _time(portfolio['marked_at']) > at):
            errors.append('FUTURE_VALUATION_AT_REPORT_TIME')
        try:
            errors.extend(reconcile(portfolio))
        except (ValueError, KeyError, TypeError):
            errors.append('INVALID_ECONOMIC_JOURNAL')
    if not base:errors.append('MISSING_BASE_CURRENCY')
    cash=_number(portfolio.get('cash'))
    if cash is None:errors.append('MISSING_BASE_CASH')
    values={}
    for ticker,pos in (portfolio.get('positions') or {}).items():
        quantity=_number(pos.get('quantity',pos.get('shares',pos.get('units'))))
        price=_number(pos.get('last_price'))
        currency=str(pos.get('currency') or '').upper()
        mark_at=_time(pos.get('price_observed_at') or pos.get('market_data_at'))
        if mark_at is None or not timedelta(0)<=at-mark_at<=timedelta(days=5):
            errors.append(f'{ticker}:MISSING_STALE_OR_FUTURE_MARK_TIME')
        if pos.get('quantity_unit')!='ACTUAL_SHARES':
            errors.append(f'{ticker}:UNVERIFIED_OR_MODEL_QUANTITY')
        if quantity is None or quantity<0 or price is None or price<=0:
            errors.append(f'{ticker}:MISSING_QUANTITY_OR_MARK');continue
        rate=None
        if currency and currency==base:rate=1.0
        elif currency and base:
            fx=pos.get('fx_quote') or {}
            stamp=_time(fx.get('observed_at'))
            candidate=_number(fx.get('rate'))
            if (fx.get('currency')==currency and fx.get('base_currency')==base and fx.get('source')
                and stamp is not None and timedelta(0)<=at-stamp<=timedelta(days=5)
                and candidate is not None and candidate>0):rate=candidate
        if rate is None:
            errors.append(f'{ticker}:MISSING_STALE_OR_MISMATCHED_FX');continue
        values[ticker]=quantity*price*rate
    if not errors:
        recorded=_number(portfolio.get('portfolio_value',portfolio.get('last_equity')))
        if recorded is not None and abs(recorded-cash-sum(values.values()))>.02:
            errors.append('RECORDED_NAV_DOES_NOT_RECONCILE')
    nav=round(cash+sum(values.values()),6) if not errors else None
    cost_errors=[]
    total_cost=0.0
    for trade in trades:
        cost=_number(trade.get('transaction_cost',trade.get('fee')))
        if cost is None or cost<0 or trade.get('cost_currency')!=base:
            cost_errors.append(str(trade.get('trade_id') or 'UNKNOWN')+':UNVERIFIED_COST')
        else:total_cost+=cost
    for event in portfolio.get('economic_events',[]):
        fee=_number(event.get('fee'))
        if fee is None or fee<0:cost_errors.append('INVALID_EVENT_COST')
        else:total_cost+=fee
    complete=portfolio.get('history_complete') is True
    initial=_number(portfolio.get('initial_cash'))
    if initial is None or initial<=0:cost_errors.append('MISSING_INITIAL_CASH')
    unitized=portfolio.get('return_method')=='UNITIZED_TWR_V1' and portfolio.get('accounting_schema')=='BASE_CURRENCY_SHARES_V1' and bool(portfolio.get('economic_events'))
    units=_number(portfolio.get('performance_units')) if unitized else initial
    if unitized and (units is None or units<=0):cost_errors.append('INVALID_PERFORMANCE_UNITS')
    if portfolio.get('cash_flows') and not unitized:cost_errors.append('EXTERNAL_CASH_FLOWS_REQUIRE_TIME_WEIGHTED_RETURN')
    # External cash flows require a proper time-weighted return, not this
    # constant-capital formula. Do not quietly treat deposits as profits.
    returns_verified=nav is not None and complete and not cost_errors and initial is not None and initial>0 and (not portfolio.get('cash_flows') or unitized)
    return {'status':'BESTÅTT' if returns_verified else 'IKKE VERIFISERT',
            'base_currency':base or None,'verified_nav':nav,'converted_position_values':values,
            'verified_net_return_pct':round((nav/units-1)*100,6) if returns_verified else None,
            'documented_costs':round(total_cost,6),'history_complete':complete,
            'issues':errors+cost_errors+([] if complete else ['INCOMPLETE_TRANSACTION_HISTORY']),
            'legacy_state_changed':False}
