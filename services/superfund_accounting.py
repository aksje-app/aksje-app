"""Read-only reconciliation of Superfond's existing native NOK cost model.

No second operational ledger. Costs are simulated bps/spread, not broker fees.
Fund TER is embedded in NAV and must not be deducted a second time.
"""
from datetime import timedelta
from math import isfinite
from services.economic_ledger import number, stamp, fx_rate


def _value(item, at):
    if not item.get('source') or not timedelta(0) <= stamp(at)-stamp(item['price_at']) <= timedelta(days=5):
        raise ValueError('Missing or stale native fund price evidence')
    rate = fx_rate(item['currency'], 'NOK', item.get('fx_quote'), at=item['price_at'], max_age=timedelta(days=5))
    if abs(rate-number(item['nok_rate'], positive=True)) > 1e-10:
        raise ValueError('Native fund FX does not reconcile')
    return number(item['local_price'], positive=True)*rate


def audit_native(model, *, at):
    issues = []
    costs = dict(brokerage_nok=0., fx_cost_nok=0., other_nok=0.)
    realized = 0.
    nav = None
    try:
        opening = model.get('accounting_opening')
        if not opening or opening.get('positions') != {} or opening.get('source') != 'CONFIGURED_SIMULATION_CAPITAL':
            raise ValueError('Undocumented native opening; historical fills are not reconstructed')
        if stamp(opening['at']) > stamp(at):
            raise ValueError('Native opening is after report time')
        cash = number(opening['cash_nok'], positive=True)
        if cash != model['initial_capital']:
            raise ValueError('Initial capital differs from native opening')
        held, basis, ids = {}, {}, set()
        last = stamp(opening['at'])
        for trade in model.get('trades', []):
            identity = (trade['id'],trade['side'],trade['requested_at'],trade['executed_at'])
            if identity in ids:
                raise ValueError('Duplicate native fund execution')
            ids.add(identity)
            when = stamp(trade['executed_at'])
            if when > stamp(at) or when < last or stamp(trade['price_at']).date() <= stamp(trade['requested_at']).date():
                raise ValueError('Out-of-order native fund execution')
            last = when
            price = _value({'source':trade['price_source'], 'price_at':trade['price_at'],
                            'currency':trade['currency'], 'fx_quote':trade.get('fx_quote'),
                            'local_price':trade['local_price'], 'nok_rate':trade['nok_rate']}, trade['executed_at'])
            q = number(trade['quantity'], positive=True)
            gross = q*price
            if abs(gross-number(trade['gross_nok'])) > 1e-6 or abs(price-number(trade['price_nok'])) > 1e-8:
                raise ValueError('Native trade gross does not reconcile')
            if trade['cost_currency'] != 'NOK' or not trade.get('cost_source') or set(trade['cost_components']) != set(costs):
                raise ValueError('Native cost evidence missing')
            policy = trade['cost_policy']
            if policy['kind']=='etf' and policy.get('spread_pct') is None:
                raise ValueError('Native ETF spread was not documented')
            expected_costs = dict(brokerage_nok=gross*number(policy['fee_bps'])/10000,
                fx_cost_nok=gross*(number(policy['fx_bps']) if trade['currency']!='NOK' else 0)/10000,
                other_nok=gross*((number(policy.get('spread_pct') or 0))/200 if policy['kind']=='etf' else 0))
            if any(abs(number(trade['cost_components'][k])-v)>1e-6 for k,v in expected_costs.items()):
                raise ValueError('Native configured costs do not reconcile')
            fee = sum(number(v) for v in trade['cost_components'].values())
            for k in costs: costs[k] += trade['cost_components'][k]
            ticker = trade['id']
            if trade['side'] == 'BUY':
                cash -= gross+fee
                held[ticker] = held.get(ticker,0)+q
                basis[ticker] = basis.get(ticker,0)+gross+fee
                pnl = 0.
            elif trade['side'] == 'SELL':
                if q > held.get(ticker,0) or held.get(ticker,0) <= 0:
                    raise ValueError('Native oversale')
                allocated = basis[ticker]*q/held[ticker]
                pnl = gross-fee-allocated
                cash += gross-fee
                held[ticker] -= q
                basis[ticker] -= allocated
                actual = float(trade['pnl_nok'])
                if not isfinite(actual) or abs(actual-pnl) > 1e-6:
                    raise ValueError('Native realized PnL differs')
                realized += pnl
            else:
                raise ValueError('Unknown native execution side')
            if abs(cash-float(trade['cash_after_nok'])) > 1e-6 or cash < -1e-6:
                raise ValueError('Native cash does not reconcile')
        if abs(cash-number(model['cash'])) > 1e-6:
            raise ValueError('Native ending cash differs')
        positions = model.get('positions',{})
        for ticker in set(held)|set(positions):
            pos = positions.get(ticker,{})
            if abs(held.get(ticker,0)-number(pos.get('quantity',0))) > 1e-8:
                raise ValueError('Native ending shares differ')
            if abs(basis.get(ticker,0)-number(pos.get('cost_nok',0))) > 1e-6:
                raise ValueError('Native ending cost basis differs')
        values = []
        for pos in positions.values():
            price = _value(pos['valuation_evidence'],at)
            if abs(price-number(pos['last_nok'])) > 1e-8:
                raise ValueError('Native mark differs from evidence')
            values.append(number(pos['quantity'])*price)
        nav = cash+sum(values)
    except (ValueError, KeyError, TypeError) as exc:
        issues.append(str(exc))
    verified = nav is not None and not issues
    return dict(status='VERIFISERT NOK-MODELL' if verified else 'IKKE VERIFISERT',
        verified_nav_nok=nav if verified else None, issues=issues,
        realized_pnl_nok=realized if verified else None,
        unrealized_pnl_nok=nav-model['cash']-sum(p['cost_nok'] for p in model['positions'].values()) if verified else None,
        net_return_pct=(nav/model['initial_capital']-1)*100 if verified else None,
        costs_nok=costs if verified else None,
        cost_basis='Simulerte gebyrer og valutapåslag; halv ETF-spread. Fondskostnader inngår i NAV.',
        actual_broker_account=False, separate_operational_ledger=False)
