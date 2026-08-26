"""One factual coverage ledger shared by JSON, PDF, UI and notifications.

This module is deliberately reporting-only.  It does not change scores,
thresholds, portfolio actions or trading eligibility.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


TERMINAL_SEARCH_STATES = {
    "SEARCHED_RESULTS_FOUND", "SEARCHED_NO_RESULTS", "SEARCH_FAILED",
    "NOT_SEARCHED_BUDGET", "NOT_SEARCHED_DISABLED",
    "NOT_SEARCHED_UNSUPPORTED", "NOT_SEARCHED_POLICY", "NOT_APPLICABLE",
}


def _rows(values: Any) -> list[Mapping[str, Any]]:
    return [row for row in (values or []) if isinstance(row, Mapping)]


def canonical_candidates(values: Sequence[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for row in _rows(values):
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        result.append(row)
    return result


def _evidence_state(candidate: Mapping[str, Any], area: str) -> tuple[str, str]:
    from evidence_search_status import normalize_evidence_payload

    if (
        area == "news"
        and str(candidate.get("coverage_role") or "").upper()
        == "PORTFOLIO_ONLY_EXISTING_POSITION"
    ):
        return "NOT_APPLICABLE", "PORTFOLIO_ONLY_EXISTING_POSITION"
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    key = f"{area}_intelligence"
    raw_payload = raw.get(key) if isinstance(raw.get(key), Mapping) else {}
    top_payload = candidate.get(key) if isinstance(candidate.get(key), Mapping) else {}
    # Portfolio-only rows are enriched at candidate level after the original
    # ranked row has been built.  A stale empty placeholder may still exist in
    # ``raw``; never let that overwrite a real, later search receipt.
    raw_log = [row for row in (raw_payload.get("search_log") or []) if isinstance(row, Mapping)]
    top_log = [row for row in (top_payload.get("search_log") or []) if isinstance(row, Mapping)]
    payload = top_payload if top_log and not raw_log else (raw_payload or top_payload)
    normalized = normalize_evidence_payload(payload, area=area)
    status = str(normalized.get("search_status") or "NOT_SEARCHED_POLICY").upper()
    reasons = normalized.get("search_reason_counts") if isinstance(normalized.get("search_reason_counts"), Mapping) else {}
    reason = next((str(key) for key, count in reasons.items() if int(count or 0) > 0), "UNKNOWN_REASON")
    return status, reason


def _short_state(candidate: Mapping[str, Any]) -> tuple[str, str]:
    from short_intelligence import normalize_short_snapshot

    snapshot = normalize_short_snapshot(candidate)
    coverage = str(snapshot.get("coverage") or "UNKNOWN").upper()
    if coverage == "VERIFIED":
        return "SEARCHED_RESULTS_FOUND", "VERIFIED_SHORT_DATA"
    if coverage == "CHECKED_NO_PUBLIC_POSITION":
        return "SEARCHED_NO_RESULTS", "NO_PUBLIC_POSITION"
    if coverage == "SOURCE_ERROR":
        return "SEARCH_FAILED", "SOURCE_ERROR"
    if coverage == "NOT_SUPPORTED":
        return "NOT_SEARCHED_UNSUPPORTED", "SOURCE_UNSUPPORTED"
    return "NOT_SEARCHED_POLICY", "UNKNOWN_REASON"


def _market_state(candidate: Mapping[str, Any]) -> tuple[str, str]:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    contract = candidate.get("data_contract") if isinstance(candidate.get("data_contract"), Mapping) else {}
    if not contract and isinstance(raw.get("data_contract"), Mapping):
        contract = raw.get("data_contract")
    validity = str(contract.get("validity") or contract.get("status") or "").upper()
    if candidate.get("valid_for_decision") or validity in {"VALID", "GYLDIG", "VERIFIED", "KOMPLETT"}:
        return "SEARCHED_RESULTS_FOUND", "VALID_MARKET_DATA"
    if validity in {"ERROR", "INVALID", "UGYLDIG", "STALE", "BLOCKED"}:
        return "SEARCH_FAILED", validity
    if any(
        source.get(key) not in (None, "", 0, 0.0)
        for source in (candidate, raw)
        for key in ("last_price", "current_price", "price")
    ):
        reason = (
            "PORTFOLIO_VALUATION_DATA"
            if str(candidate.get("coverage_role") or "").upper() == "PORTFOLIO_ONLY_EXISTING_POSITION"
            else "VALID_MARKET_PRICE"
        )
        return "SEARCHED_RESULTS_FOUND", reason
    return "NOT_SEARCHED_POLICY", "UNKNOWN_REASON"


def _area_summary(states: list[tuple[str, str]]) -> dict[str, Any]:
    counts = Counter(status for status, _ in states)
    reasons = Counter(reason for _, reason in states)
    required = len(states)
    completed = sum(counts[state] for state in TERMINAL_SEARCH_STATES)
    attempted = counts["SEARCHED_RESULTS_FOUND"] + counts["SEARCHED_NO_RESULTS"] + counts["SEARCH_FAILED"]
    return {
        "required": required,
        "attempted": attempted,
        "completed": completed,
        "with_results": counts["SEARCHED_RESULTS_FOUND"],
        "no_results": counts["SEARCHED_NO_RESULTS"],
        "source_error": counts["SEARCH_FAILED"],
        "not_searched_budget": counts["NOT_SEARCHED_BUDGET"],
        "not_searched_disabled": counts["NOT_SEARCHED_DISABLED"],
        "not_supported": counts["NOT_SEARCHED_UNSUPPORTED"],
        "not_applicable": counts["NOT_APPLICABLE"],
        "not_searched": counts["NOT_SEARCHED_POLICY"],
        "unknown_reason": reasons["UNKNOWN_REASON"],
        "completion_pct": round(completed * 100.0 / required, 1) if required else 0.0,
        "status_counts": dict(sorted(counts.items())),
        "reason_counts": dict(sorted(reasons.items())),
    }


def build_production_coverage_contract(
    values: Sequence[Mapping[str, Any]] | None,
    *,
    configured: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = canonical_candidates(values)
    ledger: list[dict[str, Any]] = []
    area_states: dict[str, list[tuple[str, str]]] = {area: [] for area in ("market", "news", "insider", "short")}
    for candidate in candidates:
        states = {
            "market": _market_state(candidate),
            "news": _evidence_state(candidate, "news"),
            "insider": _evidence_state(candidate, "insider"),
            "short": _short_state(candidate),
        }
        for area, state in states.items():
            area_states[area].append(state)
        ledger.append({
            "ticker": str(candidate.get("ticker") or ""),
            "market": str(candidate.get("market") or "Ukjent"),
            "areas": {area: {"status": state, "reason_code": reason} for area, (state, reason) in states.items()},
            "evidence_data_ready": bool(candidate.get("evidence_data_ready")),
            "final_decision_ready": bool(candidate.get("final_decision_ready")),
        })
    areas = {area: _area_summary(states) for area, states in area_states.items()}
    structural_gaps = [
        {"area": area, "not_searched": summary["not_searched"], "unknown_reason": summary["unknown_reason"]}
        for area, summary in areas.items()
        if summary["unknown_reason"]
    ]
    return {
        "schema_version": "1.0",
        "candidate_total": len(candidates),
        "unique_ticker_total": len(candidates),
        "evidence_data_ready": sum(bool(row["evidence_data_ready"]) for row in ledger),
        "decision_ready": sum(bool(row["final_decision_ready"]) for row in ledger),
        "areas": areas,
        "configured": dict(configured or {}),
        "structural_gaps": structural_gaps,
        "structurally_complete": not structural_gaps and all(summary["completed"] == len(candidates) for summary in areas.values()),
        "ledger": ledger,
        "changes_decision_rules": False,
    }


__all__ = ["TERMINAL_SEARCH_STATES", "build_production_coverage_contract", "canonical_candidates"]
