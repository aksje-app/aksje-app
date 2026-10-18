"""Read-only release gate for market-health composite calibration.

No risk scores, weights, trade orders, or synthetic history are produced here.
A complete latest snapshot is necessary, not sufficient, for calibration.
"""
from __future__ import annotations
from datetime import datetime, timezone
from market_health_ui import INDICATORS
from market_health_history import normalize

REQUIRED = frozenset(INDICATORS)
MIN_BACKTEST_YEARS = 10
REQUIRED_BACKTEST_CHECKS = (
    "point_in_time_sources",
    "walk_forward_validation",
    "out_of_sample_results",
    "regime_and_crisis_coverage",
    "overlap_and_weight_documentation",
    "missing_data_robustness",
    "transaction_independence",
)

def audit_snapshot(snapshot: dict, *, now=None) -> dict:
    """Report evidence gaps; always block activation absent reviewed backtest."""
    now = now or datetime.now(timezone.utc)
    rows = snapshot.get("indicators", {}) if isinstance(snapshot, dict) else {}
    rows = rows if isinstance(rows, dict) else {}
    good, stale, missing = [], [], []
    for key in sorted(REQUIRED):
        datum = normalize(key, rows.get(key), now=now)
        if datum is None:
            missing.append(key)
        elif datum["status"] == "STALE":
            stale.append(key)
        else:
            good.append(key)
    composite = snapshot.get("composite", {}) if isinstance(snapshot, dict) else {}
    source = snapshot.get("collection_status", {}) if isinstance(snapshot, dict) else {}
    return {
        "mode": "READ_ONLY",
        "current_count": len(good),
        "present_count": len(good) + len(stale),
        "total_count": len(REQUIRED),
        "missing": missing,
        "stale": stale,
        "source_schema": source.get("source_schema") if isinstance(source, dict) else None,
        "existing_composite_validated": composite.get("validated") is True if isinstance(composite, dict) else False,
        "calibration_ready": len(good) == len(REQUIRED),
        "validated": False,
        "risk_score": None,
        "trade_signals_enabled": False,
        "backtest_required": list(REQUIRED_BACKTEST_CHECKS),
        "minimum_target_history_years": MIN_BACKTEST_YEARS,
        "explanation": "Complete latest observations do not establish historical calibration or predictive performance.",
    }
