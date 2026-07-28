"""Canonical report view and integrity validation for v19.13.2.

The analysis engines remain authoritative for ranking and portfolio decisions.
This module makes a completed result internally consistent before it is
serialized or rendered. It does not recalculate a production score or relax a
trading rule.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping, Sequence

REPORT_INTEGRITY_SCHEMA_VERSION = "1.1"

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

_ANALYSIS_WRAPPER_KEYS = {
    "candidate_id", "investment_score", "confidence_score", "risk_score",
    "quality_gates", "analysis_ranking", "strategy_scores", "portfolio_action",
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


def _looks_like_analysis_wrapper(value: Mapping[str, Any]) -> bool:
    return bool(value.get("raw") and any(key in value for key in _ANALYSIS_WRAPPER_KEYS))


def _collapse_nested_raw(raw: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Remove repeated CandidateAssessment wrappers from a report payload.

    A compact previous snapshot is kept, while the deepest source payload is
    merged into the current raw object only for fields that are otherwise
    missing. This prevents 20+ MB JSON files from carrying divergent raw chains.
    """
    current = _mapping(raw)
    snapshots: list[dict[str, Any]] = []
    depth = 0
    while depth < 8 and _looks_like_analysis_wrapper(current):
        nested = current.get("raw")
        if not isinstance(nested, Mapping):
            break
        snapshots.append({
            "authoritative": False,
            "candidate_id": current.get("candidate_id"),
            "investment_score": current.get("investment_score"),
            "confidence_score": current.get("confidence_score"),
            "risk_score": current.get("risk_score"),
            "score_trend": current.get("score_trend") or current.get("trend"),
            "score_delta": current.get("score_delta"),
            "status": current.get("status"),
            "portfolio_action": current.get("portfolio_action"),
            "rank": current.get("rank"),
            "data_source": current.get("data_source"),
            "latest_trade_date": current.get("latest_trade_date"),
            "fetch_completed_at": current.get("fetch_completed_at"),
        })
        nested_copy = _mapping(nested)
        current.pop("raw", None)
        for key, value in nested_copy.items():
            if key == "raw":
                continue
            current.setdefault(key, value)
        # Continue only when another wrapper remains after the merge.
        if isinstance(nested_copy.get("raw"), Mapping):
            current["raw"] = deepcopy(nested_copy.get("raw"))
        depth += 1
    current.pop("raw", None)
    if snapshots:
        current["previous_analysis_snapshot"] = snapshots[0]
        current["analysis_wrapper_depth_removed"] = len(snapshots)
    return current, snapshots


def _is_evidence_data_ready(candidate: Mapping[str, Any]) -> bool:
    return bool(candidate.get("valid_for_decision") and candidate.get("evidence_valid_for_decision"))


def _is_final_decision_ready(candidate: Mapping[str, Any]) -> bool:
    action = str(candidate.get("portfolio_action") or "").upper()
    return bool(_is_evidence_data_ready(candidate) and action in {"BUY", "KJØP"})


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


def _normalise_market_diagnostics(result: MutableMapping[str, Any]) -> dict[str, int]:
    event_count = 0
    skipped_tickers: set[str] = set()
    for item in result.get("market_diagnostics") or []:
        if not isinstance(item, MutableMapping):
            continue
        candidate_errors = [row for row in item.get("candidate_errors") or [] if isinstance(row, Mapping)]
        tickers = sorted({str(row.get("ticker") or "").strip().upper() for row in candidate_errors if row.get("ticker")})
        event_count += len(candidate_errors)
        skipped_tickers.update(tickers)
        item["candidate_error_events"] = len(candidate_errors)
        item["skipped_candidate_count"] = len(tickers)
        item["skipped_tickers"] = tickers
        item["errors"] = int(item.get("market_data_errors") or 0)
        base_status = str(item.get("status") or "OK").split(" · ", 1)[0]
        item["status"] = base_status + (f" · {len(tickers)} kandidat(er) hoppet over" if tickers else "")
    return {
        "candidate_error_events": event_count,
        "skipped_candidate_count": len(skipped_tickers),
        "skipped_tickers": sorted(skipped_tickers),
    }


def _learning_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    chain = result.get("autonomous_chain") if isinstance(result.get("autonomous_chain"), Mapping) else {}
    portfolio_stage: Mapping[str, Any] = {}
    for stage in chain.get("stages") or []:
        if isinstance(stage, Mapping) and str(stage.get("name") or "").upper() == "AUTONOMOUS_PORTFOLIO":
            portfolio_stage = stage.get("detail") if isinstance(stage.get("detail"), Mapping) else {}
            break
    ordinary_buys = portfolio_stage.get("ordinary_buys")
    production_buys = int(ordinary_buys if ordinary_buys is not None else (portfolio_stage.get("buys") or 0))
    learning_buys = int(portfolio_stage.get("learning_buys") or 0)
    return {
        "production_buys": production_buys,
        "learning_buys": learning_buys,
        "production_open_positions": int(portfolio_stage.get("open_positions") or 0),
        "learning_open_positions": int(portfolio_stage.get("learning_open_positions") or 0),
        "production_buy_tickers": list(portfolio_stage.get("buy_tickers") or []),
        "learning_buy_tickers": list(portfolio_stage.get("learning_buy_tickers") or []),
        "separate_accounts": bool(learning_buys or portfolio_stage.get("learning_open_positions")),
    }


def canonical_report_view(run: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-copied report view with explicit semantic precedence."""
    result = deepcopy(dict(run or {}))
    corrections: list[dict[str, Any]] = []
    canonical_candidates: list[dict[str, Any]] = []

    for position, source_candidate in enumerate(_rows(result.get("candidates")), 1):
        candidate = source_candidate
        ticker = str(candidate.get("ticker") or f"#{position}")
        raw, snapshots = _collapse_nested_raw(_mapping(candidate.get("raw")))
        if snapshots:
            corrections.append({
                "ticker": ticker,
                "field": "raw.raw",
                "from": f"{len(snapshots)} nestet(e) analysewrapper(e)",
                "to": "previous_analysis_snapshot",
                "reason": "Historiske analyseobjekter er ikke autoritative kildefelt",
            })

        # Top-level values are the completed assessment. Supporting raw values
        # are synchronised for fields that have the same meaning. ``trend`` is
        # explicitly a score trend, not a technical price trend.
        for field in (
            "status", "portfolio_action", "investment_score",
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

        score_trend = candidate.get("score_trend") or candidate.get("trend") or raw.get("score_trend") or "NY"
        candidate["score_trend"] = score_trend
        candidate["trend"] = score_trend  # compatibility alias
        candidate["trend_basis"] = "Kandidatscore sammenlignet med forrige analysekjøring"
        raw["score_trend"] = score_trend
        raw["score_trend_basis"] = candidate["trend_basis"]

        readiness = _mapping(candidate.get("decision_readiness"))
        evidence_gate_action = str(readiness.get("allowed_action") or "REVIEW")
        final_action = str(candidate.get("portfolio_action") or "REVIEW")
        evidence_data_ready = _is_evidence_data_ready(candidate)
        final_decision_ready = _is_final_decision_ready(candidate)
        candidate["portfolio_action"] = final_action
        candidate["evidence_data_ready"] = evidence_data_ready
        candidate["final_decision_ready"] = final_decision_ready
        readiness["evidence_gate_action"] = evidence_gate_action
        readiness["final_action"] = final_action
        readiness["evidence_data_ready"] = evidence_data_ready
        readiness["final_decision_ready"] = final_decision_ready
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
                        else "Nøytral modellbaseline – ikke dokumentert evidens"
                    ),
                    "contribution": contributions.get(area),
                }
            formula["contribution_semantics"] = semantics
            raw["score_formula"] = formula

        candidate["raw"] = raw
        canonical_candidates.append(candidate)

    result["candidates"] = canonical_candidates
    result["executive_intelligence"] = executive_intelligence_from_candidates(canonical_candidates)

    raw_top3 = _diverse(canonical_candidates, 3)
    evidence_ready_rows = [row for row in canonical_candidates if _is_evidence_data_ready(row)]
    final_ready_rows = [row for row in canonical_candidates if _is_final_decision_ready(row)]
    evidence_ready_top3 = _diverse(evidence_ready_rows, 3)
    final_decision_top3 = _diverse(final_ready_rows, 3)
    result["raw_top3"] = raw_top3
    result["diverse_top3"] = raw_top3
    result["evidence_ready_top3"] = evidence_ready_top3
    result["decision_ready_top3"] = final_decision_top3
    result["final_decision_top3"] = final_decision_top3
    result["top3_status"] = {
        "raw_count": len(raw_top3),
        "evidence_data_ready_count": len(evidence_ready_top3),
        "decision_ready_count": len(final_decision_top3),
        "uses_raw_fallback": not bool(evidence_ready_top3),
        "display_mode": "FINAL_DECISION" if final_decision_top3 else ("EVIDENCE_SHORTLIST" if evidence_ready_top3 else "RAW_RANKING"),
    }

    actions = _mapping(_mapping(result.get("portfolio_decisions")).get("actions"))
    manual_review = int(actions.get("REVIEW") or sum(
        1 for row in canonical_candidates if str(row.get("portfolio_action") or "").upper() == "REVIEW"
    ))
    evidence_ready_count = len(evidence_ready_rows)
    final_ready_count = len(final_ready_rows)
    preliminary_count = int(_mapping(result.get("summary")).get("proposals") or len(result.get("proposals") or []))
    for proposal in result.get("proposals") or []:
        if isinstance(proposal, MutableMapping):
            proposal["proposal_stage"] = "PRELIMINARY_MODEL_OUTPUT"
            proposal["final_trade_proposal"] = False
            proposal["display_label"] = "Foreløpig modellkandidat før evidens- og beslutningsport"
    result["proposal_summary"] = {
        "preliminary_model_candidates": preliminary_count,
        "evidence_data_ready_candidates": evidence_ready_count,
        "final_buy_candidates": final_ready_count,
        "label": "Foreløpige modellkandidater – ikke handelsforslag",
    }

    diagnostics_summary = _normalise_market_diagnostics(result)
    result["diagnostics_summary"] = diagnostics_summary
    result["learning_portfolio_summary"] = _learning_summary(result)
    result["report_summary"] = {
        "scanned": int(_mapping(result.get("summary")).get("scanned") or 0),
        "deep_analyzed": len(canonical_candidates),
        "manual_review": manual_review,
        "evidence_data_ready": evidence_ready_count,
        "decision_ready": final_ready_count,
        "preliminary_model_candidates": preliminary_count,
        **result["executive_intelligence"],
        **diagnostics_summary,
    }
    result["report_integrity"] = {
        "schema_version": REPORT_INTEGRITY_SCHEMA_VERSION,
        "canonical_candidate_count": len(canonical_candidates),
        "correction_count": len(corrections),
        "corrections": corrections,
        "field_precedence": "candidate top-level > raw supporting detail; score trend is not technical price trend",
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
        if isinstance(raw.get("raw"), Mapping):
            errors.append(f"{ticker}: nestet raw.raw finnes fortsatt i leveransemodellen")
        for field in ("status", "portfolio_action", "investment_score", "confidence_score", "risk_score"):
            top = candidate.get(field)
            nested = raw.get(field)
            if top is not None and nested is not None and top != nested:
                errors.append(f"{ticker}: {field} motsier raw.{field}")
        readiness = candidate.get("decision_readiness") if isinstance(candidate.get("decision_readiness"), Mapping) else {}
        if str(readiness.get("final_action") or candidate.get("portfolio_action") or "REVIEW") != str(candidate.get("portfolio_action") or "REVIEW"):
            errors.append(f"{ticker}: endelig handling er ikke entydig")
        if bool(candidate.get("final_decision_ready")) and str(candidate.get("portfolio_action") or "").upper() not in {"BUY", "KJØP"}:
            errors.append(f"{ticker}: endelig beslutningsklar uten kjøpshandling")
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

    report_summary = run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
    final_count = sum(1 for row in candidates if isinstance(row, Mapping) and _is_final_decision_ready(row))
    evidence_count = sum(1 for row in candidates if isinstance(row, Mapping) and _is_evidence_data_ready(row))
    if int(report_summary.get("decision_ready") or 0) != final_count:
        errors.append("Sammendragets beslutningsklare antall er ikke endelig kjøpsklart antall")
    if int(report_summary.get("evidence_data_ready") or 0) != evidence_count:
        errors.append("Sammendragets evidens- og dataklare antall er feil")

    if not candidates:
        warnings.append("Rapporten har ingen kandidater")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


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
