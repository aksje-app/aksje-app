"""Offline publication-quality provenance gate for value research.

This tool never fetches current fundamentals, writes portfolios, or executes trades.
The session count is supplied by a historical exchange calendar calculation, not
inferred from calendar-day differences.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from math import isfinite
from typing import Any, Mapping, Sequence

from services.value_research_batch import run_combined_value_research
from services.value_historical_validation import _day


def audit_historical_session_evidence(
    rows: Sequence[Mapping[str, Any]], *, as_of: str | None = None
) -> dict[str, Any]:
    reasons: Counter[str] = Counter()
    for row in rows:
        horizon = row.get("horizon_sessions")
        observed = row.get("observed_trading_sessions")
        if type(horizon) is not int or horizon not in (7, 30):
            reasons["INVALID_HORIZON"] += 1
        if type(observed) is not int or observed != horizon:
            reasons["UNVERIFIED_TRADING_SESSION_COUNT"] += 1
        if not str(row.get("exchange_calendar_source") or "").strip():
            reasons["MISSING_EXCHANGE_CALENDAR_SOURCE"] += 1
        if row.get("price_adjusted_for_corporate_actions") is not True:
            reasons["UNVERIFIED_ADJUSTED_RETURN"] += 1
        if not str(row.get("price_adjustment_source") or "").strip():
            reasons["MISSING_ADJUSTMENT_SOURCE"] += 1
        # The source's timestamp is an auditable first-publication date.
        publication = _day(row.get("fundamentals_first_published_at"))
        known = _day(row.get("fundamentals_known_at"))
        snapshot = _day(row.get("snapshot_date"))
        if publication is None or known is None or snapshot is None or publication > known or known > snapshot:
            reasons["UNVERIFIED_FIRST_PUBLICATION"] += 1
        value = row.get("forward_return_pct")
        try:
            if isinstance(value, bool) or not isfinite(float(value)):
                reasons["INVALID_RETURN"] += 1
        except (TypeError, ValueError):
            reasons["INVALID_RETURN"] += 1
    status = "READY_FOR_MANUAL_SOURCE_VERIFICATION" if rows and not reasons else "BACKTEST_NOT_VERIFIABLE"
    return {"status": status, "sample_count": len(rows), "rejection_counts": dict(reasons),
            "shadow_only": True, "can_authorize_buy": False}


def research_with_session_evidence(rows: Sequence[Mapping[str, Any]], *,
                                   as_of: str | None = None) -> dict[str, Any]:
    gate = audit_historical_session_evidence(rows, as_of=as_of)
    if gate["status"] != "READY_FOR_MANUAL_SOURCE_VERIFICATION":
        return {"status": "BACKTEST_NOT_VERIFIABLE", "session_evidence": gate,
                "comparisons": [], "risk_by_cohort": [],
                "shadow_only": True, "can_authorize_buy": False}
    result = run_combined_value_research(rows, as_of=as_of)
    return {**result, "session_evidence": gate}
