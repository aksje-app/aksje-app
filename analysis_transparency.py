"""Transparent analysis contracts for v19.18.0.

This module is report-only: it explains ranking, evidence and confidence without
changing trading thresholds, portfolio rules or execution decisions.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

PRIMARY_TYPES = {
    "PRIMARY_STRUCTURED", "PRIMARY_REGULATORY", "PRIMARY_OR_DIRECT_RSS",
    "OFFICIAL_PRIMARY", "OFFICIAL_EXCHANGE_FEED", "OFFICIAL_FILING",
}
GOOD_STATUSES = {"SUCCESS_WITH_RESULTS", "SUCCESS_NO_RESULTS", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "AVAILABLE"}
DEGRADED_STATUSES = {"PARTIAL_SOURCE_FAILURE", "STALE", "RATE_LIMITED", "DAILY_QUOTA_EXCEEDED"}
FAILED_STATUSES = {"SOURCE_ERROR", "ERROR", "NOT_CONFIGURED", "NOT_SEARCHED"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _m(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or [] if isinstance(row, Mapping)]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _domain(url: Any) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        return (urlparse(text).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _root_domain(domain: str) -> str:
    parts = [part for part in domain.split(".") if part]
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def _source_identity(row: Mapping[str, Any]) -> str:
    return _root_domain(_domain(row.get("url") or row.get("source_url"))) or str(row.get("source") or "Ukjent").strip().casefold()


def _is_primary(row: Mapping[str, Any]) -> bool:
    source_type = str(row.get("source_type") or row.get("source_role") or "").upper()
    return bool(row.get("direct_primary") or row.get("direct_primary_source_checked") or source_type in PRIMARY_TYPES or source_type.startswith("PRIMARY_"))


def _score_components(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _m(candidate.get("raw"))
    formula = _m(raw.get("score_formula") or candidate.get("score_formula"))
    weighted = _m(formula.get("weighted_contributions"))
    components: list[dict[str, Any]] = []
    if weighted:
        for key, value in weighted.items():
            components.append({"factor": str(key), "contribution": round(_f(value), 2), "documented": key not in {"news", "insider"}})
    else:
        mappings = (
            ("fundamental", "fundamental_score"), ("research", "research_score"),
            ("validation", "validation_score"), ("portfolio_fit", "portfolio_fit_score"),
            ("liquidity", "liquidity_score"), ("risk", "risk_score"),
            ("discovery", "discovery_score"), ("scanner", "scanner_score"),
        )
        for label, key in mappings:
            if candidate.get(key) is not None:
                value = _f(candidate.get(key))
                components.append({"factor": label, "contribution": round(value, 2), "documented": True, "raw_score": True})
    components.sort(key=lambda row: abs(_f(row.get("contribution"))), reverse=True)
    return components


def build_claim_ledger(candidate: Mapping[str, Any], passport: Mapping[str, Any] | None = None) -> dict[str, Any]:
    passport = _m(passport or candidate.get("evidence_passport"))
    areas = _m(passport.get("areas"))
    claims: list[dict[str, Any]] = []
    by_identity: dict[str, set[str]] = defaultdict(set)
    primary_areas: set[str] = set()
    attempts = 0
    successes = 0
    degraded = 0
    failures = 0

    for area, payload_any in areas.items():
        payload = _m(payload_any)
        source_rows = _rows(payload.get("sources"))
        fact_rows = _rows(payload.get("facts"))
        for source in source_rows:
            attempts += int(bool(source.get("attempted")))
            status = str(source.get("status") or "NOT_SEARCHED").upper()
            if status in GOOD_STATUSES:
                successes += 1
            elif status in DEGRADED_STATUSES:
                degraded += 1
            elif status in FAILED_STATUSES:
                failures += 1
            if _is_primary(source):
                primary_areas.add(str(area))
        for index, fact in enumerate(fact_rows, 1):
            identity = _source_identity(fact)
            if identity:
                by_identity[str(area)].add(identity)
            title = str(fact.get("title") or f"Dokumentert faktum {index}")
            verification = str(fact.get("verification") or "UKJENT").upper()
            claims.append({
                "claim_id": str(fact.get("fact_id") or f"{area}-{index}"),
                "area": str(area),
                "claim": title,
                "source": str(fact.get("source") or "Ukjent"),
                "source_url": str(fact.get("source_url") or ""),
                "published_at": str(fact.get("published_at") or ""),
                "retrieved_at": str(fact.get("retrieved_at") or payload.get("fetched_at") or ""),
                "verification": verification,
                "primary_source": _is_primary(fact),
                "ranking_contribution": payload.get("ranking_contribution"),
            })

    independent = sorted({item for values in by_identity.values() for item in values})
    return {
        "generated_at": _now_iso(),
        "claims": claims,
        "claim_count": len(claims),
        "independent_sources": independent,
        "independent_source_count": len(independent),
        "primary_source_areas": sorted(primary_areas),
        "source_attempts": attempts,
        "successful_attempts": successes,
        "degraded_attempts": degraded,
        "failed_attempts": failures,
    }


def build_confidence_breakdown(candidate: Mapping[str, Any], claim_ledger: Mapping[str, Any]) -> dict[str, Any]:
    profile = _m(candidate.get("confidence_profile"))
    model = _f(profile.get("model_confidence"), _f(candidate.get("confidence_before_evidence_policy"), _f(candidate.get("confidence_score"))))
    adjusted = _f(profile.get("evidence_adjusted_model_confidence"), _f(candidate.get("confidence_score"), model))
    market = _f(profile.get("market_data_coverage"), _f(candidate.get("data_quality")))
    evidence = _f(profile.get("evidence_coverage"), _f(profile.get("data_coverage")))
    source = _f(profile.get("source_confidence"), 20.0)
    readiness = _m(candidate.get("decision_readiness"))
    conflicts = int(_f(readiness.get("conflicts"), 0))
    deductions: list[dict[str, Any]] = []

    if claim_ledger.get("claim_count", 0) == 0:
        deductions.append({"reason": "Ingen verifiserte fakta lagret", "points": 20})
    if claim_ledger.get("independent_source_count", 0) < 2:
        deductions.append({"reason": "Færre enn to uavhengige kilder", "points": 12})
    if not claim_ledger.get("primary_source_areas"):
        deductions.append({"reason": "Ingen dokumentert primærkilde", "points": 10})
    if conflicts:
        deductions.append({"reason": f"{conflicts} kildekonflikt(er)", "points": min(25, conflicts * 10)})
    if market < 70:
        deductions.append({"reason": "Svak markedsdatadekning", "points": 10})
    if claim_ledger.get("failed_attempts", 0):
        deductions.append({"reason": "Ett eller flere kildeforsøk feilet", "points": min(12, int(claim_ledger.get("failed_attempts")) * 3)})

    formula = round(model * 0.35 + adjusted * 0.20 + market * 0.15 + evidence * 0.15 + source * 0.15, 2)
    deduction_total = sum(int(row["points"]) for row in deductions)
    final = max(0.0, min(100.0, formula - deduction_total))
    if not candidate.get("evidence_valid_for_decision", True):
        final = min(final, 69.0)
    return {
        "inputs": {
            "model_confidence": round(model, 2),
            "evidence_adjusted_model_confidence": round(adjusted, 2),
            "market_data_coverage": round(market, 2),
            "evidence_coverage": round(evidence, 2),
            "source_confidence": round(source, 2),
        },
        "weights": {"model": 0.35, "evidence_adjusted": 0.20, "market_data": 0.15, "evidence_coverage": 0.15, "source_quality": 0.15},
        "pre_deduction_score": formula,
        "deductions": deductions,
        "deduction_total": deduction_total,
        "transparent_decision_confidence": round(final, 2),
        "not_profit_probability": True,
        "explanation": "Konfidensen er en dokumentert beslutningsstyrke, ikke sannsynlighet for kursgevinst.",
    }


def build_candidate_transparency(candidate: Mapping[str, Any]) -> dict[str, Any]:
    passport = _m(candidate.get("evidence_passport"))
    ledger = build_claim_ledger(candidate, passport)
    confidence = build_confidence_breakdown(candidate, ledger)
    components = _score_components(candidate)
    blockers = [str(x) for x in candidate.get("manual_tasks") or [] if str(x).strip()]
    critical_gaps: list[dict[str, Any]] = []
    for area, payload_any in _m(passport.get("areas")).items():
        payload = _m(payload_any)
        status = str(payload.get("status") or "NOT_SEARCHED").upper()
        if status not in GOOD_STATUSES:
            critical_gaps.append({"area": str(area), "status": status, "reason": "Området er ikke fullt dokumentert"})
    return {
        "schema_version": "19.18.0-rc1",
        "ticker": str(candidate.get("ticker") or ""),
        "generated_at": _now_iso(),
        "claim_ledger": ledger,
        "confidence_breakdown": confidence,
        "ranking_explanation": {
            "total_score": round(_f(candidate.get("investment_score")), 2),
            "components": components,
            "top_positive_drivers": components[:3],
            "score_is_separate_from_evidence": True,
        },
        "critical_gaps": critical_gaps,
        "counter_arguments": [str(x) for x in candidate.get("risks") or [] if str(x).strip()][:6],
        "positive_arguments": [str(x) for x in candidate.get("positives") or [] if str(x).strip()][:6],
        "manual_tasks": blockers,
        "decision_trace": {
            "status": str(candidate.get("status") or ""),
            "portfolio_action": str(candidate.get("portfolio_action") or ""),
            "autonomy_outcome": str(candidate.get("autonomy_outcome_code") or ""),
            "evidence_ready": bool(candidate.get("evidence_data_ready") or candidate.get("evidence_valid_for_decision")),
            "final_decision_ready": bool(candidate.get("final_decision_ready")),
        },
    }


def attach_analysis_transparency(run: dict[str, Any]) -> dict[str, Any]:
    candidates = [row for row in run.get("candidates") or [] if isinstance(row, dict)]
    for candidate in candidates:
        candidate["analysis_transparency"] = build_candidate_transparency(candidate)
    by_ticker = {str(row.get("ticker") or ""): row for row in candidates}
    for key in ("raw_top3", "evidence_ready_top3", "decision_ready_top3", "diverse_top3"):
        if isinstance(run.get(key), list):
            run[key] = [by_ticker.get(str(row.get("ticker") or ""), dict(row)) for row in run.get(key) or [] if isinstance(row, Mapping)]
    top = list(run.get("raw_top3") or candidates[:3])
    run["analysis_transparency"] = {
        "schema_version": "19.18.0-rc1",
        "generated_at": _now_iso(),
        "top3": [row.get("analysis_transparency") or build_candidate_transparency(row) for row in top],
        "candidate_count": len(candidates),
        "transparent_candidate_count": sum(1 for row in candidates if row.get("analysis_transparency")),
        "principles": [
            "Score, evidens og konfidens vises separat",
            "Kildeuavhengighet beregnes fra faktisk kildeidentitet",
            "Manglende primærkilde og kildefeil gir synlige trekk",
            "Konfidens er ikke sannsynlighet for gevinst",
            "Ingen produksjons- eller handelsregel endres",
        ],
    }
    return run


__all__ = [
    "attach_analysis_transparency", "build_candidate_transparency",
    "build_claim_ledger", "build_confidence_breakdown",
]
