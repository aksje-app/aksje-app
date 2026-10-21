"""Pure settlement of simulated SP trades in its existing portfolio currency.

Legacy portfolios acquire a labelled opening balance from the last recorded NAV
and weights. This does not reconstruct missing historical trades or prices.
"""
from copy import deepcopy
import hashlib
import math


def _price(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def settle(before, positions, changes, *, operation_id, decision_at, cost_bps):
    nav = float(before.get("portfolio_value", before.get("initial_cash", 1_000_000)))
    old = before.get("positions") or {}
    values = {t: float(p["market_value"]) if p.get("market_value") is not None
              else nav * float(p.get("target_weight_pct", 0)) / 100 for t, p in old.items()}
    cash = float(before["cash"]) if before.get("accounting_schema") else nav - sum(values.values())
    output = deepcopy(positions)
    quantities = {}
    # Mark every previously held position before any sale removes its exposure.
    for ticker, pos in old.items():
        previous = _price(pos.get("last_price"))
        mark = _price((output.get(ticker) or {}).get("last_price"))
        sale = next((r for r in changes if r.get("ticker") == ticker and r.get("action") == "SELL"), {})
        mark = _price(sale.get("exit_price")) or mark or previous
        if previous is None and values[ticker]:
            raise ValueError(f"Mangler tidligere verdsettingskurs: {ticker}")
        quantity = float(pos.get("quantity")) if pos.get("quantity") is not None else (values[ticker] / previous if previous else 0)
        quantities[ticker] = quantity
        values[ticker] = quantity * mark if mark else values[ticker]

    fee_rate = max(0.0, float(cost_bps)) / 10000
    trades = []
    total_cost = 0.0
    for index, change in enumerate(changes):
        ticker, action = change["ticker"], change["action"]
        pos = output.get(ticker) or old.get(ticker) or {}
        price = _price(change.get("exit_price") if action == "SELL" else change.get("execution_price"))
        price = price or _price(pos.get("entry_price") if action == "BUY" else pos.get("last_price"))
        if price is None:
            raise ValueError(f"Ingen dokumentert utførelseskurs: {ticker}")
        delta = abs(float(change.get("to_pct", 0)) - float(change.get("from_pct", 0)))
        if action in {"SELL", "REDUCE"}:
            fraction = 1.0 if action == "SELL" else min(1.0, delta / max(float(change.get("from_pct", 0)), 1e-12))
            quantity = quantities.get(ticker, 0) * fraction
            gross = quantity * price
            fee = gross * fee_rate
            cash += gross - fee
            values[ticker] = max(0.0, values.get(ticker, 0) - gross)
            quantities[ticker] = max(0.0, quantities.get(ticker, 0) - quantity)
        elif action in {"BUY", "ADD"}:
            gross = min(nav * delta / 100, max(0.0, cash) / (1 + fee_rate))
            if gross <= 0:
                raise ValueError("Ikke nok kontanter til godkjent kjøp og handelskostnad")
            quantity = gross / price
            fee = gross * fee_rate
            cash -= gross + fee
            quantities[ticker] = quantities.get(ticker, 0) + quantity
            # A known next-session open and a later mark are different prices.
            mark = _price(pos.get("last_price")) or price
            values[ticker] = quantities[ticker] * mark
        else:
            raise ValueError(f"Ukjent transaksjonstype: {action}")
        total_cost += fee
        evidence = deepcopy(change.get("execution_evidence") or pos.get("execution_evidence") or {})
        trade = {**change, "trade_id": hashlib.sha256(f"{operation_id}:{index}:{ticker}:{action}".encode()).hexdigest(),
                 "position_id": pos.get("position_id") or f"{ticker}:{pos.get('entry_date', '')}",
                 "entry_at": pos.get("entry_date"), "entry_price": pos.get("entry_price"),
                 "decision_at": decision_at, "simulated_execution_at": decision_at,
                 "price_observed_at": evidence.get("market_data_at"), "execution_evidence": evidence,
                 "execution_price": price, "quantity": quantity, "gross_amount": round(gross, 6),
                 "quote_currency": pos.get("currency"), "portfolio_currency": (before.get("config") or {}).get("base_currency"),
                 "quantity_unit": "MODEL_PRICE_RATIO_UNITS",
                 "transaction_cost": round(fee, 6), "cost_bps": cost_bps,
                 "stop_price": change.get("stop_price") or pos.get("effective_stop_price"),
                 "cash_after": round(cash, 6), "portfolio_value_after": round(cash + sum(values.values()), 2),
                 "operation_id": operation_id, "execution_kind": "SIMULATED"}
        trades.append(trade)

    for ticker, pos in output.items():
        pos["quantity"] = quantities.get(ticker, 0)
        pos["market_value"] = round(values.get(ticker, 0), 6)
    cash = round(cash, 6)
    after_nav = round(cash + sum(p["market_value"] for p in output.values()), 2)
    if cash < -0.00001:
        raise ValueError("Negativ kontantbeholdning etter oppgjør")
    gross_traded = sum(t["gross_amount"] for t in trades)
    gross_return = ((after_nav + total_cost) / nav - 1) * 100 if nav else 0
    return {"positions": output, "cash": cash, "portfolio_value": after_nav,
            "portfolio_value_before": nav, "transaction_cost": round(total_cost, 6),
            "portfolio_return_pct": (after_nav / float(before.get("initial_cash", nav)) - 1) * 100,
            "period_return_pct": gross_return,
            "turnover_costs": {"estimated_cost": round(total_cost, 6), "traded_value": gross_traded,
                               "cost_bps": cost_bps, "cost_pct": total_cost / nav * 100 if nav else 0,
                               "turnover_pct": gross_traded / nav * 100 if nav else 0,
                               "gross_return_pct": gross_return, "net_return_pct": (after_nav / nav - 1) * 100 if nav else 0},
            "accounting_schema": 1, "accounting_opening_balance": before.get("accounting_opening_balance") or {
                "at": decision_at, "nav": nav, "basis": "RECORDED_NAV_AND_WEIGHTS_NO_HISTORICAL_RECONSTRUCTION"},
            "transactions": trades}
