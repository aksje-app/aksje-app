"""Deterministic, read-only 7/30-session shadow backtest.

Inputs must be point-in-time snapshots with already-matured returns.
No data fetch, side effects, live decisions or fabricated returns.
"""
from __future__ import annotations
from collections import defaultdict
from math import isfinite
from typing import Any, Mapping, Sequence
from services.value_historical_validation import validate_point_in_time_samples


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def compare_value_shadow_history(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare same-date value-shadow vs legacy-finalist observations.

    Only 7/30-session horizons. A cohort must have both arms on the same
    snapshot date and horizon; otherwise that cohort is not comparable.
    """
    gate = validate_point_in_time_samples(samples)
    if gate["status"] != "READY_FOR_FURTHER_AUDIT":
        return {"status": "BACKTEST_NOT_VERIFIABLE", "eligibility": gate,
                "comparisons": [], "shadow_only": True, "can_authorize_buy": False}
    buckets: dict[tuple[str, int], dict[str, list[float]]] = defaultdict(
        lambda: {"value_shadow": [], "legacy_finalist": []})
    invalid = 0
    for row in samples:
        horizon = row.get("horizon_sessions")
        cohort = row.get("cohort")
        ret = _number(row.get("forward_return_pct"))
        if horizon not in (7, 30) or cohort not in ("value_shadow", "legacy_finalist") or ret is None:
            invalid += 1
            continue
        buckets[(str(row["snapshot_date"]), horizon)][cohort].append(ret)
    if invalid:
        return {"status": "BACKTEST_NOT_VERIFIABLE", "invalid_rows": invalid,
                "eligibility": gate, "comparisons": [],
                "shadow_only": True, "can_authorize_buy": False}
    comparisons = []
    for (as_of, horizon), arms in sorted(buckets.items()):
        if not all(arms.values()):
            continue
        value_avg = sum(arms["value_shadow"]) / len(arms["value_shadow"])
        legacy_avg = sum(arms["legacy_finalist"]) / len(arms["legacy_finalist"])
        comparisons.append({"snapshot_date": as_of, "horizon_sessions": horizon,
                            "value_count": len(arms["value_shadow"]),
                            "legacy_count": len(arms["legacy_finalist"]),
                            "value_mean_return_pct": round(value_avg, 4),
                            "legacy_mean_return_pct": round(legacy_avg, 4),
                            "difference_percentage_points": round(value_avg - legacy_avg, 4)})
    return {"status": "DESCRIPTIVE_COMPARISON_ONLY" if comparisons else "BACKTEST_NOT_VERIFIABLE",
            "eligibility": gate, "comparisons": comparisons,
            "caveats": ["No transaction-cost adjustment", "No liquidity or overlap adjustment",
                        "No statistical significance claim", "No production authorization"],
            "shadow_only": True, "can_authorize_buy": False}
