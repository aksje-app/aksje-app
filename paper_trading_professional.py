from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def holding_days(position: Mapping[str, Any] | None) -> float:
    raw = (position or {}).get("opened_at") or (position or {}).get("entry_time")
    try:
        dt = datetime.fromisoformat(str(raw))
        return max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)
    except Exception:
        return 0.0


def position_professional_metrics(position: Mapping[str, Any] | None, total_value: float = 0.0) -> dict:
    pos = dict(position or {})
    shares = _f(pos.get("shares", pos.get("units", 0)))
    entry = _f(pos.get("entry_price", pos.get("avg_price", 0)))
    last = _f(pos.get("last_price", entry), entry)
    value = shares * last
    target = _f(pos.get("target_price"))
    stop = _f(pos.get("stop_loss"))
    initial_risk = _f(pos.get("initial_risk_amount"))
    if initial_risk <= 0 and entry > stop > 0:
        initial_risk = max(0.0, (entry - stop) * shares)
    pnl = (last - entry) * shares
    r_multiple = pnl / initial_risk if initial_risk > 0 else 0.0
    target_distance_pct = ((target - last) / last * 100.0) if target > 0 and last > 0 else 0.0
    target_progress_pct = ((last - entry) / (target - entry) * 100.0) if target > entry and last > 0 else 0.0
    binding_pct = value / total_value * 100.0 if total_value > 0 else 0.0
    return {
        "value": round(value, 2),
        "target_price": round(target, 4),
        "target_distance_pct": round(target_distance_pct, 2),
        "target_progress_pct": round(target_progress_pct, 2),
        "initial_risk_amount": round(initial_risk, 2),
        "r_multiple": round(r_multiple, 2),
        "capital_binding_pct": round(binding_pct, 2),
        "holding_days": round(holding_days(pos), 1),
    }


def portfolio_professional_summary(portfolio: Mapping[str, Any] | None) -> dict:
    portfolio = portfolio or {}
    cash = _f(portfolio.get("cash"))
    positions = portfolio.get("positions", {}) or {}
    invested = sum(_f(p.get("shares", p.get("units", 0))) * _f(p.get("last_price", p.get("entry_price", 0))) for p in positions.values())
    total = cash + invested
    return {
        "cash": round(cash, 2),
        "invested": round(invested, 2),
        "total": round(total, 2),
        "capital_binding_pct": round(invested / total * 100.0, 2) if total > 0 else 0.0,
        "free_capital_pct": round(cash / total * 100.0, 2) if total > 0 else 0.0,
    }


def exit_priority_decision(position: Mapping[str, Any] | None, price: float, *, hard_sell: bool = False, timeout_days: float | None = None) -> dict:
    pos = dict(position or {})
    price = _f(price)
    entry = _f(pos.get("entry_price", pos.get("avg_price", price)), price)
    stop_loss = _f(pos.get("stop_loss"))
    trailing = _f(pos.get("trailing_stop_level", pos.get("trailing_stop")))
    take_profit = _f(pos.get("take_profit"))
    target = _f(pos.get("target_price"))
    age = holding_days(pos)
    checks = [
        ("HARD_STOP", stop_loss > 0 and price <= stop_loss, 1),
        ("TRAILING_STOP", trailing > 0 and price <= trailing and _f(pos.get("highest_price"), entry) > entry, 2),
        ("TAKE_PROFIT", take_profit > 0 and price >= take_profit, 3),
        ("TARGET_PRICE", target > 0 and price >= target, 4),
        ("HARD_SELL", bool(hard_sell), 5),
        ("TIME_EXIT", timeout_days is not None and age >= float(timeout_days), 6),
    ]
    for reason, triggered, priority in checks:
        if triggered:
            return {"triggered": True, "reason": reason, "priority": priority, "holding_days": round(age, 1)}
    return {"triggered": False, "reason": "HOLD", "priority": 99, "holding_days": round(age, 1)}


def exit_simulation(position: Mapping[str, Any] | None) -> list[dict]:
    pos = dict(position or {})
    entry = _f(pos.get("entry_price", pos.get("avg_price", 0)))
    highest = _f(pos.get("highest_price", pos.get("last_price", entry)), entry)
    target = _f(pos.get("target_price"))
    rows = []
    for pct in (5.0, 8.0, 10.0, 15.0):
        exit_price = highest * (1.0 - pct / 100.0)
        pnl_pct = ((exit_price - entry) / entry * 100.0) if entry > 0 else 0.0
        rows.append({"Scenario": f"Trailing {pct:.0f}%", "Exit price": round(exit_price, 2), "P/L %": round(pnl_pct, 2)})
    if target > 0:
        rows.append({"Scenario": "Target price", "Exit price": round(target, 2), "P/L %": round(((target-entry)/entry*100.0) if entry else 0.0, 2)})
    return rows
