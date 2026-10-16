"""Strict audit of historical backtest rows before empirical publication.

The existing comparator accepts diagnostic fixtures. This publication gate
requires evidence of first-publication dates and historical universe sources.
"""
from __future__ import annotations
from datetime import date
from typing import Any, Mapping, Sequence
from services.value_historical_validation import validate_point_in_time_samples, _day


def audit_empirical_backtest_dataset(rows: Sequence[Mapping[str, Any]], *, as_of: str | None = None) -> dict[str, Any]:
    basic = validate_point_in_time_samples(rows)
    problems: dict[str, int] = dict(basic["rejection_counts"])
    cutoff = _day(as_of) if as_of is not None else date.today()
    for row in rows:
        reasons = set()
        if not str(row.get("fundamentals_source") or "").strip():
            reasons.add("MISSING_FUNDAMENTALS_SOURCE")
        if not str(row.get("filing_reference") or "").strip():
            reasons.add("MISSING_DISCLOSURE_REFERENCE")
        if not str(row.get("historical_universe_source") or "").strip():
            reasons.add("MISSING_UNIVERSE_SOURCE")
        if not str(row.get("price_source") or "").strip():
            reasons.add("MISSING_PRICE_SOURCE")
        when = _day(row.get("outcome_date"))
        if cutoff is None or when is None or when > cutoff:
            reasons.add("UNMATURED_OUTCOME")
        for reason in reasons:
            problems[reason] = problems.get(reason, 0) + 1
    return {
        "status": "READY_FOR_MANUAL_REVIEW" if rows and not problems else "BACKTEST_NOT_VERIFIABLE",
        "sample_count": len(rows), "rejection_counts": problems,
        "shadow_only": True, "can_authorize_buy": False,
        "note": "Even passing this metadata gate does not prove filing accuracy, unbiased selection or net returns.",
    }
