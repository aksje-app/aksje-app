"""Explicit base-currency simulated ledger; legacy balances are never relabelled.

Quotes are supplied by the caller, never fetched or inferred from a ticker.
Fees include brokerage and FX conversion; slippage belongs in the fill price.
All functions return new state so rejected orders cannot partly mutate cash.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import isfinite

SCHEMA = 'BASE_CURRENCY_SHARES_V1'


def number(value, *, positive=False):
    if isinstance(value, bool):
        raise ValueError('Boolean is not an economic amount')
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError('Missing economic amount') from None
    if not isfinite(result) or (result <= 0 if positive else result < 0):
        raise ValueError('Invalid economic amount')
    return result


def stamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise ValueError('Economic evidence requires an aware timestamp') from None


def fx_rate(currency, base_currency, quote, *, at, max_age=timedelta(minutes=15)):
    if not currency or not base_currency:
        raise ValueError('Missing currency')
    if currency == base_currency:
        return 1.0
    quote = quote or {}
    if (quote.get('currency') != currency or quote.get('base_currency') != base_currency
            or not quote.get('source')):
        raise ValueError('Missing or mismatched FX evidence')
    if not timedelta(0) <= stamp(at) - stamp(quote.get('observed_at')) <= max_age:
        raise ValueError('Stale or future FX evidence')
    return number(quote.get('rate'), positive=True)


def new_account(initial_cash, *, base_currency, at):
    """Start a new accounting period, never overwrite an existing portfolio."""
    initial = number(initial_cash, positive=True)
    if not isinstance(base_currency, str) or len(base_currency) != 3 or not base_currency.isalpha():
        raise ValueError('Explicit ISO currency required')
    stamp(at)
    return dict(accounting_schema=SCHEMA, base_currency=base_currency.upper(),
                initial_cash=initial, cash=initial, positions={}, trades=[],
                history_complete=True, fees_paid=0.0, realized_pnl=0.0, created_at=at)


def execute(portfolio, *, trade_id, ticker, side, quantity, price, currency,
            observed_at, source, at, fee, cost_currency, fx_quote=None):
    """Book a documented simulated fill, including proportional cost on partial exits."""
    if portfolio.get('accounting_schema') != SCHEMA:
        raise ValueError('Explicit reconciled base-currency opening balance required')
    if not trade_id or not ticker or side not in ('BUY', 'SELL'):
        raise ValueError('Trade identity, ticker and side required')
    q = number(quantity, positive=True)
    p = number(price, positive=True)
    costs = number(fee)
    if not source or not timedelta(0) <= stamp(at)-stamp(observed_at) <= timedelta(minutes=15):
        raise ValueError('Fresh documented execution price required')
    base = portfolio['base_currency']
    if cost_currency != base:
        raise ValueError('Costs must be documented in the base currency')
    rate = fx_rate(currency, base, fx_quote, at=at)
    gross = number(q*p*rate, positive=True)
    request = dict(trade_id=trade_id, ticker=ticker, action=side, quantity=q, price=p,
                   currency=currency, price_observed_at=observed_at, price_source=source,
                   timestamp=at, fx_quote=deepcopy(fx_quote), fx_rate=rate,
                   gross_value=gross, fee=costs, transaction_cost=costs,
                   cost_currency=base, accounting_schema=SCHEMA)
    for old in portfolio.get('trades', []):
        if old.get('trade_id') == trade_id:
            if any(old.get(key) != value for key, value in request.items()):
                raise ValueError('Trade ID reused with different economic input')
            return deepcopy(portfolio), deepcopy(old)
    if stamp(at) < stamp(portfolio['created_at']):
        raise ValueError('Trade predates the opening balance')
    if portfolio.get('trades') and stamp(at) < stamp(portfolio['trades'][-1]['timestamp']):
        raise ValueError('Out-of-order economic trade')
    result = deepcopy(portfolio)
    old = result['positions'].get(ticker)
    if old and (old.get('currency') != currency or old.get('quantity_unit') != 'ACTUAL_SHARES'):
        raise ValueError('Cannot mix currencies or model units in an existing position')
    cash = number(result['cash'])
    pnl = 0.0
    if side == 'BUY':
        if gross + costs > cash:
            raise ValueError('Insufficient base-currency cash including costs')
        held = number((old or {}).get('quantity', 0))
        total = held + q
        cost = number((old or {}).get('cost_basis_base', 0)) + gross + costs
        result['positions'][ticker] = {
            **(old or {}), 'quantity': total, 'quantity_unit': 'ACTUAL_SHARES',
            'currency': currency, 'last_price': p, 'price_observed_at': observed_at,
            'fx_quote': deepcopy(fx_quote), 'cost_basis_base': cost,
            'average_price': (held*float((old or {}).get('average_price', p))+q*p)/total,
            'average_cost_base': cost/total,
        }
        result['cash'] = cash-gross-costs
        request['cash_delta'] = -gross-costs
    else:
        if not old or q > number(old['quantity'], positive=True):
            raise ValueError('Insufficient shares')
        if costs > gross + cash:
            raise ValueError('Insufficient cash for selling costs')
        allocated_cost = number(old['cost_basis_base'])*q/old['quantity']
        pnl = gross-costs-allocated_cost
        result['cash'] = cash+gross-costs
        request['cash_delta'] = gross-costs
        remaining = old['quantity']-q
        if remaining <= 1e-10:
            del result['positions'][ticker]
        else:
            old.update(quantity=remaining, cost_basis_base=old['cost_basis_base']-allocated_cost,
                       last_price=p, price_observed_at=observed_at, fx_quote=deepcopy(fx_quote))
    result['fees_paid'] = number(result.get('fees_paid', 0))+costs
    result['realized_pnl'] = float(result.get('realized_pnl', 0))+pnl
    request['pnl'] = pnl
    result.setdefault('trades', []).append(request)
    return result, deepcopy(request)


def reconcile(portfolio):
    """Prove cash and remaining shares from the complete, recorded opening balance."""
    if portfolio.get('accounting_schema') != SCHEMA:
        return ['UNVERIFIED_OPENING_BALANCE']
    cash = number(portfolio['initial_cash'], positive=True)
    quantities = {}
    bases = {}
    realized = 0.0
    fees = 0.0
    ids = set()
    issues = []
    for trade in portfolio.get('trades', []):
        identity = trade.get('trade_id')
        if not identity or identity in ids:
            issues.append('DUPLICATE_OR_MISSING_TRADE_ID')
        ids.add(identity)
        q = number(trade.get('quantity'), positive=True)
        if trade.get('action') not in ('BUY', 'SELL'):
            issues.append('INVALID_TRADE_SIDE')
        direction = 1 if trade.get('action') == 'BUY' else -1
        ticker = trade['ticker']
        held = quantities.get(ticker, 0)
        gross = q*number(trade.get('price'), positive=True)*number(trade.get('fx_rate'), positive=True)
        rate = fx_rate(trade.get('currency'), portfolio['base_currency'],
                       trade.get('fx_quote'), at=trade.get('timestamp'))
        if abs(rate-number(trade.get('fx_rate'), positive=True)) > 1e-10:
            issues.append('TRADE_FX_DOES_NOT_RECONCILE')
        if not trade.get('price_source') or not timedelta(0) <= stamp(trade['timestamp'])-stamp(trade.get('price_observed_at')) <= timedelta(minutes=15):
            issues.append('UNVERIFIED_HISTORICAL_EXECUTION_PRICE')
        if abs(gross-number(trade.get('gross_value'))) > .00001:
            issues.append('TRADE_VALUE_DOES_NOT_RECONCILE')
        fee = number(trade.get('fee'))
        fees += fee
        if direction == 1:
            bases[ticker] = bases.get(ticker, 0)+gross+fee
        elif held <= 0 or q > held:
            issues.append('HISTORICAL_OVERSALE')
        else:
            allocated = bases.get(ticker, 0)*q/held
            expected_pnl = gross-fee-allocated
            if not isfinite(float(trade.get('pnl', float('nan')))) or abs(expected_pnl-float(trade['pnl'])) > .00001:
                issues.append('REALIZED_PNL_DOES_NOT_RECONCILE')
            realized += expected_pnl
            bases[ticker] -= allocated
        quantities[ticker] = held+direction*q
        cash -= direction*gross+fee
        if trade.get('cost_currency') != portfolio.get('base_currency'):
            issues.append('MISMATCHED_COST_CURRENCY')
    if abs(cash-number(portfolio['cash'])) > .00001:
        issues.append('CASH_DOES_NOT_RECONCILE')
    actual = {t:number(p['quantity']) for t,p in portfolio.get('positions', {}).items()}
    if any(abs(actual.get(t, 0)-quantities.get(t, 0)) > 1e-8 for t in set(actual)|set(quantities)):
        issues.append('SHARES_DO_NOT_RECONCILE')
    if any(abs(number(p.get('cost_basis_base'))-bases.get(t, 0)) > .00001 for t,p in portfolio.get('positions', {}).items()):
        issues.append('COST_BASIS_DOES_NOT_RECONCILE')
    if abs(number(portfolio.get('fees_paid'))-fees) > .00001:
        issues.append('FEES_DO_NOT_RECONCILE')
    if abs(float(portfolio.get('realized_pnl', 0))-realized) > .00001:
        issues.append('REALIZED_PNL_DOES_NOT_RECONCILE')
    return issues
