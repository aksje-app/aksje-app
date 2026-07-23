"""Canonical evidence states and decision-readiness helpers for v19.0.10."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

VERIFIED_FACTS_FOUND = "VERIFIED_FACTS_FOUND"
CHECKED_NO_EVENTS = "CHECKED_NO_EVENTS"
PARTIAL_SOURCE_FAILURE = "PARTIAL_SOURCE_FAILURE"
NOT_CONFIGURED = "NOT_CONFIGURED"
RATE_LIMITED = "RATE_LIMITED"
SOURCE_ERROR = "SOURCE_ERROR"
NOT_SEARCHED = "NOT_SEARCHED"
STALE = "STALE"

FAILURE_STATES = {PARTIAL_SOURCE_FAILURE, NOT_CONFIGURED, RATE_LIMITED, SOURCE_ERROR, NOT_SEARCHED, STALE}


def canonical_status(payload: Mapping[str, Any], facts: Sequence[Mapping[str, Any]]) -> str:
    logs = [row for row in payload.get("search_log") or [] if isinstance(row, Mapping)]
    statuses = {str(row.get("status") or "").upper() for row in logs}
    if facts:
        return VERIFIED_FACTS_FOUND
    if "RATE_LIMITED" in statuses:
        return RATE_LIMITED
    successes = statuses & {"SUCCESS_WITH_RESULTS", "SUCCESS_NO_RESULTS"}
    failures = statuses & {"ERROR", "SOURCE_ERROR", "PARTIAL_SOURCE_FAILURE"}
    if successes and failures:
        return PARTIAL_SOURCE_FAILURE
    if failures:
        return SOURCE_ERROR
    if "NOT_CONFIGURED" in statuses and not successes:
        return NOT_CONFIGURED
    if successes:
        return CHECKED_NO_EVENTS
    coverage = str(payload.get("coverage") or "").upper()
    if coverage == "STALE":
        return STALE
    return NOT_SEARCHED


def source_budget(payload: Mapping[str, Any]) -> dict[str, int]:
    logs = [row for row in payload.get("search_log") or [] if isinstance(row, Mapping)]
    statuses = [str(row.get("status") or "").upper() for row in logs]
    return {
        "planned": len(logs),
        "attempted": sum(bool(row.get("attempted")) for row in logs),
        "successful": sum(status in {"SUCCESS_WITH_RESULTS", "SUCCESS_NO_RESULTS"} for status in statuses),
        "with_facts": sum(status == "SUCCESS_WITH_RESULTS" for status in statuses),
        "no_events": sum(status == "SUCCESS_NO_RESULTS" for status in statuses),
        "rate_limited": sum(status == "RATE_LIMITED" for status in statuses),
        "not_configured": sum(status == "NOT_CONFIGURED" for status in statuses),
        "errors": sum(status in {"ERROR", "SOURCE_ERROR", "PARTIAL_SOURCE_FAILURE"} for status in statuses),
    }


def evidence_conflicts(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Flag contradictory transaction directions for the same person/date."""
    grouped: dict[tuple[str, str], set[str]] = {}
    for fact in facts:
        key = (str(fact.get("insider") or fact.get("subject") or "").casefold(),
               str(fact.get("date") or fact.get("published_at") or "")[:10])
        direction = str(fact.get("type") or fact.get("direction") or "").upper()
        if key[0] and key[1] and direction:
            grouped.setdefault(key, set()).add(direction)
    return [
        {"subject": key[0], "date": key[1], "directions": sorted(values)}
        for key, values in grouped.items() if "BUY" in values and "SELL" in values
    ]
