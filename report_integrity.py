"""Canonical report view and integrity validation for v19.13.1.

The analysis engines remain authoritative for ranking and portfolio decisions.
This module only makes the completed result internally consistent before it is
serialized or rendered.  It never recalculates a production score or changes a
portfolio action.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping, Sequence

REPORT_INTEGRITY_SCHEMA_VERSION = "1.0"

_VERIFIED_EVIDENCE = {
    "AVAILABLE", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS",
}
_COMPANY_ALIASES = {
    "GOOG": "ALPHABET", "GOOGL": "ALPHABET",
    "BRK-A": "BERKSHIRE_HATHAWAY", "BRK-B": "BERKSHIRE_HATHAWAY",
    "BRK.A": "BERKSHIRE_HATHAWAY", "BRK.B": "BERKSHIRE_HATHAWAY",
    "FOX": "FOX_CORP", "FOXA": "FOX_CORP",
    "NWS": "NEWS_CORP", "NWSA": "NEWS_CORP",
}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [deepcopy(dict(row)) for row in value if isinstance(row, Mapping)]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else default
    except (TypeError, ValueError):
        return default


def _company_key(candidate: Mapping[str, Any]) -> str:
    ticker = str(candidate.get("ticker") or "").upper().strip()
    if ticker in _COMPANY_ALIASES:
        return _COMPANY_ALIASES[ticker]
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    name = str(candidate.get("name") or raw.get("longName") or raw.get("shortName") or ticker).upper()
    for suffix in (
        " CLASS A", " CLASS B", " CLASS C", " A-SHARE", " B-SHARE", " ADR",
        " PLC", " INC.", " INC", " CORP.", " CORP", " LTD.", " LTD",
    ):
        name = name.replace(suffix, "")
    compact = "".join(ch for ch in name if ch.isalnum())
    return compact or ticker


def executive_intelligence_from_candidates(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(candidates or [])
    scores = [_float(row.get("investment_score")) for row in rows]
    markets = {str(row.get("market") or "Ukjent") for row in rows[:10]}
    companies = {_company_key(row) for row in rows}
    return {
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "highest_score": round(max(scores), 2) if scores else 0.0,
        "lowest_score": round(min(scores), 2) if scores else 0.0,
        "unique_companies": len(companies),
        "markets_in_top10": len(markets),
    }


def _evidence_status(candidate: Mapping[str, Any], area: str) -> str:
    readiness = candidate.get("decision_readiness") if isinstance(candidate.get("decision_readiness"), Mapping) else {}
    status = str(readiness.get(area) or "").upper()
    if status:
        return status
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    payload = raw.get(f"{area}_intelligence") if isinstance(raw.get(f"{area}_intelligence"), Mapping) else {}
    return str(payload.get("coverage") or payload.get("status") or "NOT_SEARCHED").upper()


def canonical_report_view(run: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-copied report view with one declared field precedence.

    Candidate top-level fields are the final analysis result.  Nested ``raw``
    fields are supporting detail and are synchronized for rendering.  Any
    repair is recorded so the report remains auditable.
    """
    result = deepcopy(dict(run or {}))
    corrections: list[dict[str, Any]] = []
    canonical_candidates: list[dict[str, Any]] = []

    for position, source_candidate in enumerate(_rows(result.get("candidates")), 1):
        candidate = source_candidate
        ticker = str(candidate.get("ticker") or f"#{position}")
        raw = _mapping(candidate.get("raw"))

        for field in (
            "trend", "status", "portfolio_action", "investment_score",
            "confidence_score", "risk_score", "rank", "raw_rank",
        ):
            if candidate.get(field) is None:
                continue
            old = raw.get(field)
            if old is not None and old != candidate.get(field):
                corrections.append({
                    "ticker": ticker, "field": f"raw.{field}",
                    "from": old, "to": candidate.get(field),
                    "reason": "Toppnivå er kanonisk sluttresultat",
                })
            raw[field] = deepcopy(candidate.get(field))

        technical = _mapping(raw.get("technical"))
        if candidate.get("trend") is not None:
            old = technical.get("trend")
            if old is not None and old != candidate.get("trend"):
                corrections.append({
                    "ticker": ticker, "field": "raw.technical.trend",
                    "from": old, "to": candidate.get("trend"),
                    "reason": "Teknisk tabell må bruke slutttrend",
                })
            technical["trend"] = candidate.get("trend")
        if technical:
            raw["technical"] = technical

        readiness = _mapping(candidate.get("decision_readiness"))
        evidence_gate_action = str(readiness.get("allowed_action") or "REVIEW")
        final_action = str(candidate.get("portfolio_action") or "REVIEW")
        candidate["portfolio_action"] = final_action
        readiness["evidence_gate_action"] = evidence_gate_action
        readiness["final_action"] = final_action
        candidate["decision_readiness"] = readiness

        formula = _mapping(raw.get("score_formula"))
        if formula:
            if candidate.get("investment_score") is not None:
                formula["investment_score"] = candidate.get("investment_score")
            contributions = _mapping(formula.get("weighted_contributions"))
            semantics = _mapping(formula.get("contribution_semantics"))
            for area in ("insider", "news"):
                status = _evidence_status(candidate, area)
                backed = status in _VERIFIED_EVIDENCE
                semantics[area] = {
                    "status": status,
                    "evidence_backed": backed,
                    "display_label": (
                        "Dokumentert evidensbidrag" if backed
                        else "Nøytral modellbaseline - ikke dokumentert evidens"
                    ),
                    "contribution": contributions.get(area),
                }
            formula["contribution_semantics"] = semantics
            raw["score_formula"] = formula

        candidate["raw"] = raw
        canonical_candidates.append(candidate)

    result["candidates"] = canonical_candidates
    result["executive_intelligence"] = executive_intelligence_from_candidates(canonical_candidates)

    def _diverse(rows: Sequence[Mapping[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen_companies: set[str] = set()
        for row in rows:
            company = _company_key(row)
            if company in seen_companies:
                continue
            seen_companies.add(company)
            selected.append(deepcopy(dict(row)))
            if len(selected) >= limit:
                break
        return selected

    # Renderer input is derived from the same canonical candidate list.  This
    # also upgrades older rows that did not persist decision_ready_top3.
    raw_top3 = _diverse(canonical_candidates, 3)
    ready_rows = [
        row for row in canonical_candidates
        if bool(row.get("valid_for_decision")) and bool(row.get("evidence_valid_for_decision"))
    ]
    decision_ready_top3 = _diverse(ready_rows, 3)
    result["raw_top3"] = raw_top3
    result["diverse_top3"] = raw_top3
    result["decision_ready_top3"] = decision_ready_top3
    result["top3_status"] = {
        "decision_ready_count": len(decision_ready_top3),
        "raw_count": len(raw_top3),
        "uses_raw_fallback": not bool(decision_ready_top3),
    }

    actions = _mapping(_mapping(result.get("portfolio_decisions")).get("actions"))
    manual_review = int(actions.get("REVIEW") or sum(
        1 for row in canonical_candidates if str(row.get("portfolio_action") or "").upper() == "REVIEW"
    ))
    result["report_summary"] = {
        "scanned": int(_mapping(result.get("summary")).get("scanned") or 0),
        "deep_analyzed": len(canonical_candidates),
        "manual_review": manual_review,
        "decision_ready": sum(1 for row in canonical_candidates if row.get("valid_for_decision") and row.get("evidence_valid_for_decision")),
        **result["executive_intelligence"],
    }
    result["report_integrity"] = {
        "schema_version": REPORT_INTEGRITY_SCHEMA_VERSION,
        "canonical_candidate_count": len(canonical_candidates),
        "correction_count": len(corrections),
        "corrections": corrections,
        "field_precedence": "candidate top-level > raw supporting detail",
    }
    validation = validate_report_integrity(result)
    result["report_integrity"].update(validation)
    return result


def validate_report_integrity(run: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    candidates = list(run.get("candidates") or [])
    seen: set[str] = set()

    for index, candidate in enumerate(candidates, 1):
        if not isinstance(candidate, Mapping):
            errors.append(f"Kandidat {index} er ikke et objekt")
            continue
        ticker = str(candidate.get("ticker") or f"#{index}").upper()
        if ticker in seen:
            errors.append(f"Duplikat kandidat i kanonisk rapportmodell: {ticker}")
        seen.add(ticker)
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
        technical = raw.get("technical") if isinstance(raw.get("technical"), Mapping) else {}
        for field in ("trend", "status", "portfolio_action", "investment_score", "confidence_score"):
            top = candidate.get(field)
            nested = raw.get(field)
            if top is not None and nested is not None and top != nested:
                errors.append(f"{ticker}: {field} motsier raw.{field}")
        if candidate.get("trend") is not None and technical.get("trend") is not None and candidate.get("trend") != technical.get("trend"):
            errors.append(f"{ticker}: slutttrend motsier teknisk trend")
        readiness = candidate.get("decision_readiness") if isinstance(candidate.get("decision_readiness"), Mapping) else {}
        if str(readiness.get("final_action") or candidate.get("portfolio_action") or "REVIEW") != str(candidate.get("portfolio_action") or "REVIEW"):
            errors.append(f"{ticker}: endelig handling er ikke entydig")
        formula = raw.get("score_formula") if isinstance(raw.get("score_formula"), Mapping) else {}
        if formula and candidate.get("investment_score") is not None:
            if abs(_float(formula.get("investment_score")) - _float(candidate.get("investment_score"))) > 0.01:
                errors.append(f"{ticker}: scoreformel og sluttscore avviker")
        semantics = formula.get("contribution_semantics") if isinstance(formula.get("contribution_semantics"), Mapping) else {}
        for area in ("insider", "news"):
            status = _evidence_status(candidate, area)
            contribution = _float(_mapping(formula.get("weighted_contributions")).get(area), 0.0)
            item = semantics.get(area) if isinstance(semantics.get(area), Mapping) else {}
            if contribution > 0 and status not in _VERIFIED_EVIDENCE and item.get("evidence_backed") is not False:
                errors.append(f"{ticker}: {area}-bidrag uten evidens er ikke merket som modellbaseline")

    expected = executive_intelligence_from_candidates([row for row in candidates if isinstance(row, Mapping)])
    actual = run.get("executive_intelligence") if isinstance(run.get("executive_intelligence"), Mapping) else {}
    for key, value in expected.items():
        if actual.get(key) != value:
            errors.append(f"Sammendraget {key} er ikke beregnet fra kanonisk kandidatliste")

    if not candidates:
        warnings.append("Rapporten har ingen kandidater")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def apply_report_integrity(run: MutableMapping[str, Any]) -> dict[str, Any]:
    """Canonicalize a completed run in place before hashing and persistence."""
    canonical = canonical_report_view(run)
    run.clear()
    run.update(canonical)
    if not canonical["report_integrity"]["ok"]:
        raise ValueError("Rapportintegritet feilet: " + "; ".join(canonical["report_integrity"]["errors"]))
    return canonical["report_integrity"]


__all__ = [
    "REPORT_INTEGRITY_SCHEMA_VERSION", "apply_report_integrity",
    "canonical_report_view", "executive_intelligence_from_candidates",
    "validate_report_integrity",
]
