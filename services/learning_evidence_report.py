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
