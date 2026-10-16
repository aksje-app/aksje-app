"""Read-only integrity audit of existing daily Shadow marks."""
from __future__ import annotations
from math import isfinite
from typing import Any, Mapping, Sequence


def audit_shadow_daily_marks(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = 0
    duplicates = 0
    invalid = 0
    missing = 0
    benchmark_return_mismatches = 0
    for obs in observations:
        seen = set()
        entry_benchmark = obs.get("benchmark_entry_price")
        try:
            entry_benchmark = float(entry_benchmark)
            if not isfinite(entry_benchmark) or entry_benchmark <= 0:
                entry_benchmark = None
        except (TypeError, ValueError):
            entry_benchmark = None
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
            if entry_benchmark is not None:
                try:
                    benchmark_price = float(mark["benchmark_price"])
                    stored = float(mark["benchmark_return_pct"])
                    if isfinite(benchmark_price) and isfinite(stored) and abs((benchmark_price / entry_benchmark - 1) * 100 - stored) > 0.10:
                        benchmark_return_mismatches += 1
                except (KeyError, ValueError, TypeError):
                    pass
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
    status = ("DATA_INTEGRITY_FAILED" if not observations or not total or duplicates or invalid or missing
              else "BENCHMARK_RECONCILIATION_REQUIRED" if benchmark_return_mismatches
              else "DATA_INTEGRITY_OK")
    return {"status": status, "observation_count": len(observations),
            "mark_count": total, "duplicate_observation_dates": duplicates,
            "invalid_marks": invalid, "missing_market_dates": missing,
            "benchmark_return_mismatches": benchmark_return_mismatches,
            "note": "Structural validation only; NOT independent historical provider verification",
            "can_authorize_buy": False}
