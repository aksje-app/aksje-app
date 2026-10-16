"""Read-only combined value research report; never authorizes portfolio trades."""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any, Mapping, Sequence

from services.value_empirical_dataset_audit import audit_empirical_backtest_dataset
from services.value_historical_comparison import compare_value_shadow_history


def _risk_metrics(values: list[float]) -> dict[str, Any]:
    count = len(values)
    return {
        "count": count,
        "win_rate_pct": round(100 * sum(v > 0 for v in values) / count, 2),
        "loss_rate_pct": round(100 * sum(v < 0 for v in values) / count, 2),
        "mean_loss_pct": round(sum(v for v in values if v < 0) / max(1, sum(v < 0 for v in values)), 4),
        "worst_return_pct": round(min(values), 4),
    }


def run_combined_value_research(
    rows: Sequence[Mapping[str, Any]], *, as_of: str | None = None
) -> dict[str, Any]:
    """Require provenance and mature outcomes before reporting any return metrics.

    Report cohort-level risk only; do not mistake a 7/30-session forward
    return for a daily path or a maximum drawdown. Unmatched cohorts and
    duplicate records remain a fail-closed data problem.
    """
    audit = audit_empirical_backtest_dataset(rows, as_of=as_of)
    blocked = {"status": "BACKTEST_NOT_VERIFIABLE", "evidence": audit,
               "comparisons": [], "risk_by_cohort": [], "shadow_only": True,
               "can_authorize_buy": False}
    if audit["status"] != "READY_FOR_MANUAL_REVIEW":
        return blocked
    comparison = compare_value_shadow_history(rows)
    if comparison["status"] != "DESCRIPTIVE_COMPARISON_ONLY":
        return {**blocked, "comparison_gate": comparison}
    comparable = {(x["snapshot_date"], x["horizon_sessions"])
                  for x in comparison["comparisons"]}
    # Do not publish risk statistics for a cohort lacking a matched control.
    if len(comparable) != len({(str(r["snapshot_date"]), r["horizon_sessions"]) for r in rows}):
        return {**blocked, "reason": "UNMATCHED_COHORT"}
    grouped: dict[tuple[str, int, str], list[float]] = defaultdict(list)
    for row in rows:
        value = float(row["forward_return_pct"])
        if not isfinite(value):
            return {**blocked, "reason": "NONFINITE_RETURN"}
        key = (str(row["snapshot_date"]), row["horizon_sessions"], row["cohort"])
        grouped[key].append(value)
    risk = [{"snapshot_date": date, "horizon_sessions": horizon, "cohort": cohort,
             **_risk_metrics(values)}
            for (date, horizon, cohort), values in sorted(grouped.items())]
    return {"status": "DESCRIPTIVE_RESEARCH_ONLY", "evidence": audit,
            "comparisons": comparison["comparisons"], "risk_by_cohort": risk,
            "caveats": ["Not net of fees/slippage", "No significance estimate",
                        "Not a drawdown measure", "Source accuracy needs human verification"],
            "shadow_only": True, "can_authorize_buy": False}
