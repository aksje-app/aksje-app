"""Canonical source-search status contract for evidence collection.

This module deliberately separates *source-search execution* from the existing
canonical evidence states used by decision gates.  The legacy ``status`` and
``coverage`` fields remain untouched for backward compatibility and trading
rule stability.  New consumers should use ``search_status`` and
``reason_code`` to distinguish searched/no findings, failures, and deliberate
skips.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

SEARCHED_RESULTS_FOUND = "SEARCHED_RESULTS_FOUND"
SEARCHED_NO_RESULTS = "SEARCHED_NO_RESULTS"
SEARCH_FAILED = "SEARCH_FAILED"
NOT_SEARCHED_BUDGET = "NOT_SEARCHED_BUDGET"
NOT_SEARCHED_DISABLED = "NOT_SEARCHED_DISABLED"
NOT_SEARCHED_UNSUPPORTED = "NOT_SEARCHED_UNSUPPORTED"
NOT_SEARCHED_POLICY = "NOT_SEARCHED_POLICY"
NOT_APPLICABLE = "NOT_APPLICABLE"

CANONICAL_SEARCH_STATUSES = {
    SEARCHED_RESULTS_FOUND,
    SEARCHED_NO_RESULTS,
    SEARCH_FAILED,
    NOT_SEARCHED_BUDGET,
    NOT_SEARCHED_DISABLED,
    NOT_SEARCHED_UNSUPPORTED,
    NOT_SEARCHED_POLICY,
    NOT_APPLICABLE,
}

_SUCCESS_WITH_RESULTS = {
    "SUCCESS_WITH_RESULTS", "AVAILABLE", "VERIFIED_FACTS_FOUND",
    "SECONDARY_FACTS_FOUND", "DISCOVERY_ONLY",
}
_SUCCESS_NO_RESULTS = {
    "SUCCESS_NO_RESULTS", "CHECKED_NO_EVENTS", "VERIFIED_FACTS_NONE",
}
_FAILURE = {
    "ERROR", "SOURCE_ERROR", "PARTIAL_SOURCE_FAILURE", "RATE_LIMITED",
    "STALE", "UNAVAILABLE",
}
_BUDGET = {"SKIPPED_BUDGET_POLICY", "NOT_SEARCHED_BUDGET", "DAILY_QUOTA_EXCEEDED"}
_DISABLED = {"NOT_CONFIGURED", "DISABLED", "NOT_SEARCHED_DISABLED"}
_UNSUPPORTED = {"NOT_SUPPORTED", "UNSUPPORTED", "NOT_SEARCHED_UNSUPPORTED"}
_NOT_APPLICABLE = {"NOT_APPLICABLE", "N/A", "NA"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _upper(value: Any) -> str:
    return _text(value).upper()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def infer_reason_code(
    legacy_status: str,
    *,
    attempted: bool,
    error: str = "",
    reason: str = "",
    default_reason_code: str = "",
) -> str:
    """Return a stable machine-readable reason code."""
    if default_reason_code:
        return _upper(default_reason_code)
    status = _upper(legacy_status)
    text = f"{error} {reason}".casefold()
    if status in _SUCCESS_WITH_RESULTS:
        return "RESULTS_FOUND"
    if status in _SUCCESS_NO_RESULTS:
        return "NO_RELEVANT_RESULTS"
    if status == "RATE_LIMITED" or "429" in text or "rate" in text:
        return "RATE_LIMITED"
    if status == "DAILY_QUOTA_EXCEEDED" or "quota exceeded" in text:
        return "DAILY_QUOTA_EXCEEDED"
    if status in _BUDGET:
        return "BUDGET_POLICY"
    if "budsjett" in text:
        return "BUDGET_POLICY"
    if status in _UNSUPPORTED or "ikke støttet" in text or "unsupported" in text:
        return "SOURCE_UNSUPPORTED"
    if status in _DISABLED:
        return "MISSING_CONFIGURATION" if status == "NOT_CONFIGURED" else "MODULE_DISABLED"
    if status in _NOT_APPLICABLE:
        return "NOT_APPLICABLE"
    if "karantene" in text or "quarantine" in text:
        return "DATA_QUARANTINE"
    if "ikke prioritert" in text or "rangering" in text or "rank" in text:
        return "RANK_LIMIT"
    if "deaktiv" in text or "disabled" in text:
        return "MODULE_DISABLED"
    if "ikke relevant" in text or "not applicable" in text:
        return "NOT_APPLICABLE"
    if status in _FAILURE or attempted:
        return "SOURCE_ERROR" if error or status in _FAILURE else "NO_RELEVANT_RESULTS"
    return "UNKNOWN_REASON"


def normalize_search_attempt(
    attempt: Mapping[str, Any],
    *,
    default_reason_code: str = "",
    default_reason: str = "",
) -> dict[str, Any]:
    """Add canonical search fields without replacing legacy fields."""
    row = dict(attempt or {})
    legacy_status = _upper(row.get("legacy_status") or row.get("status"))
    attempted = bool(row.get("attempted"))
    results = max(0, _int(row.get("results"), 0))
    error = _text(row.get("error"))
    reason = _text(row.get("reason") or default_reason)
    explicit = _upper(row.get("search_status"))

    if explicit in CANONICAL_SEARCH_STATUSES:
        search_status = explicit
    elif legacy_status in _SUCCESS_WITH_RESULTS or results > 0:
        search_status = SEARCHED_RESULTS_FOUND
    elif legacy_status in _SUCCESS_NO_RESULTS:
        search_status = SEARCHED_NO_RESULTS
    elif legacy_status in _FAILURE:
        search_status = SEARCH_FAILED
    elif legacy_status in _BUDGET:
        search_status = NOT_SEARCHED_BUDGET
    elif legacy_status in _DISABLED:
        search_status = NOT_SEARCHED_DISABLED
    elif legacy_status in _UNSUPPORTED:
        search_status = NOT_SEARCHED_UNSUPPORTED
    elif legacy_status in _NOT_APPLICABLE:
        search_status = NOT_APPLICABLE
    elif legacy_status == "NOT_SEARCHED":
        inferred = infer_reason_code(
            legacy_status, attempted=attempted, error=error, reason=reason,
            default_reason_code=default_reason_code,
        )
        if inferred == "BUDGET_POLICY":
            search_status = NOT_SEARCHED_BUDGET
        elif inferred in {"MODULE_DISABLED", "MISSING_CONFIGURATION"}:
            search_status = NOT_SEARCHED_DISABLED
        elif inferred == "SOURCE_UNSUPPORTED":
            search_status = NOT_SEARCHED_UNSUPPORTED
        elif inferred == "NOT_APPLICABLE":
            search_status = NOT_APPLICABLE
        else:
            search_status = NOT_SEARCHED_POLICY
    elif attempted:
        search_status = SEARCH_FAILED if error else SEARCHED_NO_RESULTS
    else:
        search_status = NOT_SEARCHED_POLICY

    # Search success/failure is itself proof that a source call was attempted.
    # Conversely a locally exhausted daily budget means no external attempt.
    # Canonicalise contradictory legacy flags instead of exporting a status
    # that says both "searched" and ``attempted=false``.
    if legacy_status == "DAILY_QUOTA_EXCEEDED":
        search_status = NOT_SEARCHED_BUDGET
        attempted = False
    elif search_status in {SEARCHED_RESULTS_FOUND, SEARCHED_NO_RESULTS, SEARCH_FAILED}:
        attempted = True

    reason_code = _upper(row.get("reason_code")) or infer_reason_code(
        legacy_status,
        attempted=attempted,
        error=error,
        reason=reason,
        default_reason_code=default_reason_code,
    )
    row["legacy_status"] = legacy_status or "UNSPECIFIED"
    row["search_status"] = search_status
    row["reason_code"] = reason_code
    if reason and not row.get("reason"):
        row["reason"] = reason
    row["attempted"] = attempted
    row["results"] = results
    return row


def summarize_search_log(log: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_search_attempt(row) for row in log if isinstance(row, Mapping)]
    counts = Counter(str(row.get("search_status") or "") for row in normalized)
    reason_counts = Counter(str(row.get("reason_code") or "UNKNOWN_REASON") for row in normalized)

    if counts[SEARCHED_RESULTS_FOUND]:
        status = SEARCHED_RESULTS_FOUND
    elif counts[SEARCHED_NO_RESULTS]:
        status = SEARCHED_NO_RESULTS
    elif counts[SEARCH_FAILED]:
        status = SEARCH_FAILED
    elif counts[NOT_SEARCHED_BUDGET]:
        status = NOT_SEARCHED_BUDGET
    elif counts[NOT_SEARCHED_POLICY]:
        status = NOT_SEARCHED_POLICY
    elif counts[NOT_SEARCHED_DISABLED]:
        status = NOT_SEARCHED_DISABLED
    elif counts[NOT_SEARCHED_UNSUPPORTED]:
        status = NOT_SEARCHED_UNSUPPORTED
    elif counts[NOT_APPLICABLE]:
        status = NOT_APPLICABLE
    else:
        status = NOT_SEARCHED_POLICY
        reason_counts["UNKNOWN_REASON"] += 1

    return {
        "search_status": status,
        "status_counts": dict(sorted(counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "unknown_reason_count": int(reason_counts.get("UNKNOWN_REASON", 0)),
        "planned": len(normalized),
        "attempted": sum(bool(row.get("attempted")) for row in normalized),
        "successful": counts[SEARCHED_RESULTS_FOUND] + counts[SEARCHED_NO_RESULTS],
        "with_results": counts[SEARCHED_RESULTS_FOUND],
        "no_results": counts[SEARCHED_NO_RESULTS],
        "failed": counts[SEARCH_FAILED],
        "not_searched": (
            counts[NOT_SEARCHED_BUDGET] + counts[NOT_SEARCHED_DISABLED]
            + counts[NOT_SEARCHED_UNSUPPORTED] + counts[NOT_SEARCHED_POLICY]
        ),
        "not_applicable": counts[NOT_APPLICABLE],
    }


def normalize_evidence_payload(
    payload: Mapping[str, Any] | None,
    *,
    area: str,
    enabled: bool = True,
    default_reason_code: str = "",
    default_reason: str = "",
) -> dict[str, Any]:
    """Return a payload with a complete canonical search contract."""
    result = dict(payload or {})
    log = [dict(row) for row in (result.get("search_log") or []) if isinstance(row, Mapping)]
    legacy_area_status = _upper(result.get("coverage") or result.get("status"))

    if not log:
        if not enabled:
            log = [{
                "source": f"{area} evidence module",
                "attempted": False,
                "status": "NOT_SEARCHED",
                "reason": default_reason or "Evidensområdet er deaktivert i kjøringskonfigurasjonen.",
                "reason_code": default_reason_code or "MODULE_DISABLED",
            }]
        elif legacy_area_status in _SUCCESS_WITH_RESULTS:
            log = [{"source": f"{area} area summary", "attempted": True, "status": "SUCCESS_WITH_RESULTS", "results": 1}]
        elif legacy_area_status in _SUCCESS_NO_RESULTS:
            log = [{"source": f"{area} area summary", "attempted": True, "status": "SUCCESS_NO_RESULTS", "results": 0}]
        elif legacy_area_status in _FAILURE:
            log = [{
                "source": f"{area} area summary", "attempted": True,
                "status": legacy_area_status, "results": 0,
                "error": _text(result.get("reason") or result.get("summary")),
            }]
        elif legacy_area_status in _DISABLED | _UNSUPPORTED | _NOT_APPLICABLE | {"NOT_SEARCHED"} or default_reason_code:
            log = [{
                "source": f"{area} evidence area",
                "attempted": False,
                "status": legacy_area_status or "NOT_SEARCHED",
                "reason": _text(result.get("reason") or default_reason),
                "reason_code": default_reason_code,
            }]

    normalized = [
        normalize_search_attempt(
            row,
            default_reason_code=default_reason_code,
            default_reason=default_reason,
        )
        for row in log
    ]
    summary = summarize_search_log(normalized)
    result["search_log"] = normalized
    result["search_status"] = summary["search_status"]
    result["search_status_counts"] = summary["status_counts"]
    result["search_reason_counts"] = summary["reason_counts"]
    result["search_unknown_reason_count"] = summary["unknown_reason_count"]
    result["search_contract_version"] = "1.0"
    result["source_budget"] = {
        "planned": summary["planned"],
        "attempted": summary["attempted"],
        "successful": summary["successful"],
        "with_facts": summary["with_results"],
        "no_events": summary["no_results"],
        "failed": summary["failed"],
        "not_searched": summary["not_searched"],
        "not_applicable": summary["not_applicable"],
        "unknown_reason": summary["unknown_reason_count"],
        # Legacy counters retained for existing consumers.
        "rate_limited": sum(row.get("reason_code") == "RATE_LIMITED" for row in normalized),
        "daily_quota_exceeded": sum(row.get("reason_code") == "DAILY_QUOTA_EXCEEDED" for row in normalized),
        "not_configured": sum(row.get("reason_code") == "MISSING_CONFIGURATION" for row in normalized),
        "errors": summary["failed"],
    }
    return result


def source_budget(payload: Mapping[str, Any]) -> dict[str, int]:
    """Compatibility wrapper returning normalized budget counters."""
    result = normalize_evidence_payload(payload, area="evidence")
    return {str(k): _int(v) for k, v in dict(result.get("source_budget") or {}).items()}


def build_candidate_search_summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else candidate
    ticker = _text(candidate.get("ticker") or raw.get("ticker"))
    market = _text(candidate.get("market") or raw.get("market"))
    areas: dict[str, Any] = {}
    for area in ("news", "insider"):
        key = f"{area}_intelligence"
        payload = normalize_evidence_payload(
            raw.get(key) if isinstance(raw.get(key), Mapping) else {},
            area=area,
        )
        areas[area] = {
            "search_status": payload.get("search_status"),
            "reason_counts": dict(payload.get("search_reason_counts") or {}),
            "unknown_reason_count": int(payload.get("search_unknown_reason_count") or 0),
            "source_budget": dict(payload.get("source_budget") or {}),
        }
    return {"ticker": ticker, "market": market, "areas": areas}


def build_run_search_summary(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    unknown = 0
    planned = attempted = successful = with_results = failed = not_searched = 0
    candidate_rows = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        summary = build_candidate_search_summary(candidate)
        candidate_rows.append(summary)
        for area in summary["areas"].values():
            status_counts[str(area.get("search_status") or NOT_SEARCHED_POLICY)] += 1
            reason_counts.update({str(k): _int(v) for k, v in dict(area.get("reason_counts") or {}).items()})
            unknown += _int(area.get("unknown_reason_count"))
            budget = dict(area.get("source_budget") or {})
            planned += _int(budget.get("planned"))
            attempted += _int(budget.get("attempted"))
            successful += _int(budget.get("successful"))
            with_results += _int(budget.get("with_facts"))
            failed += _int(budget.get("failed", budget.get("errors")))
            not_searched += _int(budget.get("not_searched"))
    return {
        "schema": "evidence-search-summary-v1",
        "candidate_count": len(candidate_rows),
        "area_count": len(candidate_rows) * 2,
        "status_counts": dict(sorted(status_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "unknown_reason_count": unknown,
        "source_budget": {
            "planned": planned,
            "attempted": attempted,
            "successful": successful,
            "with_results": with_results,
            "failed": failed,
            "not_searched": not_searched,
        },
        "candidates": candidate_rows,
        "plain_not_searched_allowed": False,
        "production_parameters_changed": False,
    }
