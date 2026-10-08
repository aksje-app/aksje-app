from __future__ import annotations

from typing import Any, Mapping

MAX_TRAILING_STOP_PCT = 3.0
PROFIT_PROTECT_TRIGGER_PCT = 2.0
PROFIT_RETENTION_2_3_PCT = 40.0
PROFIT_RETENTION_3_5_PCT = 55.0
PROFIT_RETENTION_5_6_PCT = 65.0
PROFIT_RETENTION_5_8_PCT = PROFIT_RETENTION_5_6_PCT  # persisted-key compatibility
PROFIT_RETENTION_6_PLUS_PCT = 70.0
PROFIT_RETENTION_8_PLUS_PCT = PROFIT_RETENTION_6_PLUS_PCT  # persisted-key compatibility
PROFIT_EXIT_WATCH_BUFFER_PCT = 0.50


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def profit_retention_pct(peak_gain_pct: float, *, trigger: float = PROFIT_PROTECT_TRIGGER_PCT, retentions: tuple = (40.0, 55.0, 65.0, 70.0)) -> float:
    peak_gain = max(0.0, _f(peak_gain_pct))
    if peak_gain + 1e-9 < trigger:
        return 0.0
    if peak_gain + 1e-9 < 3.0:
        return retentions[0]
    if peak_gain + 1e-9 < 5.0:
        return retentions[1]
    if peak_gain + 1e-9 < 6.0:
        return retentions[2]
    return retentions[3]


def strict_profit_protection_levels(position: Mapping[str, Any], *, trailing_stop_pct: float = MAX_TRAILING_STOP_PCT) -> dict[str, Any]:
    entry = _f(position.get("entry_price") or position.get("avg_price"))
    current = _f(position.get("last_price"))
    peak = max(_f(position.get("highest_price") or position.get("peak_price")), current, entry)
    hard = min(MAX_TRAILING_STOP_PCT, max(0.1, _f(trailing_stop_pct, MAX_TRAILING_STOP_PCT)))
    peak_gain = ((peak / entry) - 1.0) * 100.0 if entry > 0 and peak > 0 else 0.0
    pnl = ((current / entry) - 1.0) * 100.0 if entry > 0 and current > 0 else 0.0
    retention = profit_retention_pct(peak_gain)
    protected_gain = max(0.0, peak_gain * retention / 100.0)
    trailing_stop_price = peak * (1.0 - hard / 100.0) if peak > 0 else 0.0
    profit_floor_price = entry * (1.0 + protected_gain / 100.0) if retention > 0 and entry > 0 else 0.0
    effective_stop_price = max(trailing_stop_price, profit_floor_price)
    distance = ((current / effective_stop_price) - 1.0) * 100.0 if current > 0 and effective_stop_price > 0 else 999.0
    giveback = max(0.0, peak_gain - pnl)
    retained = (max(0.0, pnl) / peak_gain * 100.0) if peak_gain > 0 else 0.0
    active = retention > 0
    if active and current <= profit_floor_price:
        status = "STOP TRIGGERED"
        mode = "PROFIT_PROTECT"
    elif current <= trailing_stop_price:
        status = "STOP TRIGGERED"
        mode = "TRAILING_STOP"
    elif active and distance <= PROFIT_EXIT_WATCH_BUFFER_PCT:
        status = "EXIT WATCH"
        mode = "PROFIT_PROTECT"
    elif active:
        status = "PROFIT PROTECT"
        mode = "PROFIT_PROTECT"
    else:
        status = "SAFE"
        mode = "TRAILING_STOP"
    return {
        "stop_status": status,
        "stop_mode": mode,
        "hard_stop_drawdown_pct": round(hard, 2),
        "peak_gain_pct": round(peak_gain, 2),
        "pnl_pct": round(pnl, 2),
        "profit_protection_active": active,
        "profit_retention_pct": round(retention, 2),
        "protected_gain_pct": round(protected_gain, 2),
        "trailing_stop_price": round(trailing_stop_price, 4),
        "profit_floor_price": round(profit_floor_price, 4),
        "effective_stop_price": round(effective_stop_price, 4),
        "distance_to_effective_stop_pct": round(max(0.0, distance), 2),
        "profit_giveback_pct": round(giveback, 2),
        "mfe_retained_pct": round(retained, 1),
    }
