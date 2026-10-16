"""Read-only integrity audit of existing daily Shadow marks."""
from __future__ import annotations
from math import isfinite
from typing import Any, Mapping, Sequence


def audit_shadow_daily_marks(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = 0
    duplicates = 0
    invalid = 0
    missing = 0
    for obs in observations:
        seen = set()
        for mark in obs.get("daily_marks") or []:
            total += 1
            if not isinstance(mark, Mapping):
                invalid += 1
                continue
            day = str(mark.get("market_date") or "")
            if not day:
                missing += 1
            elif day in seen:
                duplicates += 1
            seen.add(day)
            for field in ("price", "benchmark_price", "return_pct",
                          "benchmark_return_pct", "excess_return_pct"):
                try:
                    raw = mark[field]
                    if isinstance(raw, bool) or not isfinite(float(raw)):
                        invalid += 1
                        break
                except (KeyError, ValueError, TypeError):
                    invalid += 1
                    break
    status = "DATA_INTEGRITY_OK" if observations and total and not (duplicates or invalid or missing) else "DATA_INTEGRITY_FAILED"
    return {"status": status, "observation_count": len(observations),
            "mark_count": total, "duplicate_observation_dates": duplicates,
            "invalid_marks": invalid, "missing_market_dates": missing,
            "note": "Structural validation only; NOT independent historical provider verification",
            "can_authorize_buy": False}
