"""Point-in-time guard for accelerated, read-only value-shadow backtests."""
from __future__ import annotations
from datetime import date, datetime
from typing import Any, Mapping, Sequence


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def validate_point_in_time_samples(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Refuse backtests without contemporaneous financials and matured outcomes.

    Input rows must contain snapshot_date, fundamentals_known_at, price_date,
    outcome_date, and forward_return_pct. Never substitute current metrics.
    """
    reasons: dict[str, int] = {}
    valid_count = 0
    for row in samples:
        snapshot = _day(row.get("snapshot_date"))
        fundamentals = _day(row.get("fundamentals_known_at"))
        price = _day(row.get("price_date"))
        outcome = _day(row.get("outcome_date"))
        failures = []
        if None in (snapshot, fundamentals, price, outcome):
            failures.append("MISSING_DATES")
        else:
            if fundamentals > snapshot:
                failures.append("LOOKAHEAD_FUNDAMENTALS")
            if price > snapshot:
                failures.append("LOOKAHEAD_PRICE")
            if outcome <= snapshot:
                failures.append("INVALID_OUTCOME_DATE")
        if row.get("forward_return_pct") is None:
            failures.append("MISSING_OUTCOME")
        if not row.get("ticker") or row.get("historical_universe_member") is not True:
            failures.append("UNVERIFIED_HISTORICAL_UNIVERSE")
        if failures:
            for reason in set(failures):
                reasons[reason] = reasons.get(reason, 0) + 1
        else:
            valid_count += 1
    status = "READY_FOR_FURTHER_AUDIT" if samples and valid_count == len(samples) else "BACKTEST_NOT_VERIFIABLE"
    return {"status": status, "sample_count": len(samples), "valid_count": valid_count,
            "rejection_counts": reasons, "shadow_only": True, "can_authorize_buy": False}
