"""Offline evidence report for persisted learning baseline and outcome observations.

Read-only transformation: accepts exported JSON, does not contact production.
"""
from __future__ import annotations
from typing import Any, Mapping


def summarize_learning_evidence(baseline: Mapping[str, Any],
                                acceptance: Mapping[str, Any],
                                observations: list[Mapping[str, Any]]) -> dict[str, Any]:
    analysis = baseline.get("analysis") or {}
    horizons = []
    for item in analysis.get("horizons") or []:
        ret = item.get("return") or {}
        excess = item.get("excess_return") or {}
        horizons.append({
            "horizon_days": item.get("horizon_days"),
            "measured_count": ret.get("count", 0),
            "average_return_pct": ret.get("average") if ret.get("count", 0) else None,
            "average_excess_return_pct": excess.get("average") if excess.get("count", 0) else None,
            "maturity_label": ret.get("maturity"),
        })
    current = acceptance.get("strategy_quality_gate") or {}
    status_counts: dict[str, int] = {}
    for row in observations:
        name = str(row.get("status") or "UNKNOWN")
        status_counts[name] = status_counts.get(name, 0) + 1
    return {
        "historical_signal_count": baseline.get("signal_count"),
        "historical_horizons": horizons,
        "historical_matured_count": analysis.get("matured_count"),
        "historical_status_label": baseline.get("status"),
        "strategy_readiness": acceptance.get("strategy_readiness", "UNKNOWN"),
        "current_mature_positions": current.get("mature_closed_positions"),
        "benchmark_measured_positions": current.get("benchmark_measured_positions"),
        "observation_status_counts": status_counts,
        "warning": "VERIFISERT is a data-audit label, not proof of investment outperformance.",
        "can_authorize_buy": False,
        "shadow_only": True,
    }


def summarize_measured_observation_horizons(observations: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Report measured sub-horizons independently of lifecycle status ACTIVE."""
    from collections import defaultdict
    from math import isfinite
    buckets = defaultdict(list)
    for observation in observations:
        measurements = observation.get("horizon_measurements") or {}
        if not isinstance(measurements, Mapping):
            continue
        for horizon, reading in measurements.items():
            if not isinstance(reading, Mapping):
                continue
            try:
                ret = float(reading["return_pct"])
                excess = float(reading["excess_return_pct"])
                days = int(horizon)
            except (TypeError, ValueError, KeyError):
                continue
            if days not in (1, 5, 20, 60) or not isfinite(ret) or not isfinite(excess):
                continue
            buckets[days].append((ret, excess))
    return [{
        "horizon_days": days,
        "measured_count": len(values),
        "positive_count": sum(ret > 0 for ret, _ in values),
        "mean_return_pct": round(sum(ret for ret, _ in values) / len(values), 4),
        "mean_excess_return_pct": round(sum(excess for _, excess in values) / len(values), 4),
        "whole_observation_maturity_independent": True,
    } for days, values in sorted(buckets.items())]
