"""Canonical report view and semantic integrity validation for v19.16.4.

The analysis engines remain authoritative for ranking and portfolio decisions.
This module makes a completed result internally consistent before it is
serialized or rendered. It does not recalculate a production score or relax a
trading rule.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping, Sequence
from urllib.parse import urlparse

from app_version import APP_VERSION, REPORT_SCHEMA_VERSION, get_version_contract

REPORT_INTEGRITY_SCHEMA_VERSION = "1.6"

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


def _compact_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "candidate_id", "ticker", "investment_score", "confidence_score", "risk_score",
        "score_trend", "trend", "score_delta", "status", "portfolio_action", "rank",
        "data_source", "source", "latest_trade_date", "fetch_completed_at", "analysis_stage",
    )
    return {key: deepcopy(value.get(key)) for key in fields if value.get(key) is not None}


def _collapse_nested_raw(raw: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Flatten every raw.raw chain and retain only compact non-authoritative history."""
    current = _mapping(raw)
    snapshots: list[dict[str, Any]] = []
    depth = 0
    while depth < 16 and isinstance(current.get("raw"), Mapping):
        nested = _mapping(current.pop("raw"))
        snapshot = _compact_snapshot(current)
        if snapshot:
            snapshot["authoritative"] = False
            snapshots.append(snapshot)
        # The outer layer is newer. Preserve its source/detail fields while the
        # nested object supplies only values absent from the outer layer.
        merged = nested
        for key, value in current.items():
            if key not in {"previous_analysis_snapshot", "raw_history"}:
                merged[key] = deepcopy(value)
        current = merged
        depth += 1
    current.pop("raw", None)
    if snapshots:
        current["raw_history"] = snapshots[:3]
        current["analysis_wrapper_depth_removed"] = len(snapshots)
    current.pop("previous_analysis_snapshot", None)
    return current, snapshots


def compact_candidate_reference(row: Mapping[str, Any]) -> dict[str, Any]:
    """Small canonical candidate reference for rankings, changes and archives."""
    fields = (
        "candidate_id", "ticker", "name", "market", "sector", "investment_score",
        "confidence_score", "model_confidence", "evidence_adjusted_model_confidence",
        "decision_confidence", "confidence_profile", "confidence_semantics",
        "risk_score", "data_quality", "liquidity_score", "status",
        "portfolio_action", "autonomy_outcome_code", "autonomy_outcome_label",
        "autonomy_outcome_reason", "automatic_next_action", "manual_review_required",
        "manual_tasks", "manual_task_summary", "analysis_stage", "valid_for_decision",
        "evidence_valid_for_decision", "evidence_data_ready", "final_decision_ready",
        "decision_readiness", "evidence_coverage", "portfolio_decision", "data_contract",
        "strategy_matches", "strategy_match", "score_trend", "trend", "score_delta",
        "rank", "raw_rank", "priority_rank", "evidence_ready_rank", "decision_ready_rank",
        "proposed_position_pct", "mission_eligible", "mission_fit", "proposal_stage", "proposal_label",
    )
    return {key: deepcopy(row.get(key)) for key in fields if key in row}


_OUTCOME_ACTION = {
    "KJØPSKANDIDAT": "BUY",
    "OVERVÅKES_AUTOMATISK": "HOLD",
    "AUTOMATISK_AVVIST": "SKIP",
    "UNDERSØK_MANUELT": "REVIEW",
}
_OUTCOME_LABEL = {
    "KJØPSKANDIDAT": "Kjøpskandidat",
    "OVERVÅKES_AUTOMATISK": "Overvåkes automatisk",
    "AUTOMATISK_AVVIST": "Automatisk avvist",
    "UNDERSØK_MANUELT": "Manuell vurdering kreves",
}


def _synchronise_final_outcome(candidate: MutableMapping[str, Any]) -> None:
    """Make outcome, action, evidence gate and manual-work fields one truth."""
    code = str(candidate.get("autonomy_outcome_code") or "AUTOMATISK_AVVIST").upper()
    label = _OUTCOME_LABEL.get(code, str(candidate.get("autonomy_outcome_label") or code))
    manual = code == "UNDERSØK_MANUELT"
    evidence_ready = bool(candidate.get("valid_for_decision") and candidate.get("evidence_valid_for_decision"))
    candidate["autonomy_outcome_label"] = label
    candidate["status"] = label
    candidate["portfolio_action"] = _OUTCOME_ACTION.get(code, "SKIP")
    candidate["manual_review_required"] = manual
    candidate["evidence_review_required"] = manual
    candidate["manual_task_summary"] = (
        str(candidate.get("manual_task_summary") or "Konkret manuell vurdering kreves")
        if manual else "Ingen manuell handling nødvendig"
    )
    candidate["evidence_gate_status"] = (
        "MANUAL_REVIEW" if manual else ("PASS" if evidence_ready else "AUTO_CLOSED")
    )
    readiness = _mapping(candidate.get("decision_readiness"))
    readiness.update({
        "allowed_action": candidate["portfolio_action"],
        "evidence_gate_action": "MANUAL_REVIEW" if manual else candidate["portfolio_action"],
        "final_action": candidate["portfolio_action"],
        "evidence_data_ready": evidence_ready,
        "final_decision_ready": code == "KJØPSKANDIDAT" and evidence_ready,
        "status": {
            "KJØPSKANDIDAT": "KJØPSKLAR",
            "OVERVÅKES_AUTOMATISK": "OVERVÅKES_AUTOMATISK",
            "AUTOMATISK_AVVIST": "AVSLUTTET_AUTOMATISK",
            "UNDERSØK_MANUELT": "MANUELL_VURDERING_KREVES",
        }.get(code, "AVSLUTTET_AUTOMATISK"),
    })
    candidate["evidence_data_ready"] = evidence_ready
    candidate["final_decision_ready"] = bool(readiness["final_decision_ready"])
    candidate["decision_readiness"] = readiness
    raw = _mapping(candidate.get("raw"))
    # Evidence display fields are derived from the complete source payload.
    insider = _mapping(raw.get("insider_intelligence"))
    news = _mapping(raw.get("news_intelligence"))
    insider_facts = int(insider.get("verified_fact_count") or len(insider.get("evidence") or []))
    news_facts = int(news.get("verified_fact_count") or news.get("article_count") or len(news.get("events") or []))
    if insider_facts and str(raw.get("insider_signal") or "").upper() in {"", "INGEN DATA", "MISSING", "NOT_SEARCHED"}:
        raw["insider_signal"] = str(insider.get("signal") or "DOKUMENTERT")
    if news_facts and str(raw.get("news_sentiment") or "").upper() in {"", "INGEN DATA", "MISSING", "NOT_SEARCHED"}:
        raw["news_sentiment"] = str(news.get("sentiment") or "DOKUMENTERT")
    raw.update({
        "status": candidate["status"],
        "portfolio_action": candidate["portfolio_action"],
        "evidence_gate_status": candidate["evidence_gate_status"],
        "evidence_review_required": manual,
    })
    candidate["raw"] = raw


def _canonical_decisions(candidates: Sequence[Mapping[str, Any]], created_at: Any = "") -> list[dict[str, Any]]:
    return [{
        "timestamp": str(created_at or ""),
        "ticker": str(row.get("ticker") or ""),
        "market": str(row.get("market") or ""),
        "decision": str(row.get("autonomy_outcome_label") or row.get("status") or ""),
        "decision_code": str(row.get("autonomy_outcome_code") or ""),
        "action": str(row.get("portfolio_action") or ""),
        "score": _float(row.get("investment_score")),
        "reason": str(row.get("autonomy_outcome_reason") or ""),
        "manual_review_required": bool(row.get("manual_review_required")),
    } for row in candidates]

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
        selected.append(compact_candidate_reference(row))
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



def _synchronise_candidate_confidence(candidate: MutableMapping[str, Any]) -> dict[str, Any]:
    """Create one explicit confidence contract for every consumer.

    ``confidence_score`` is retained as a legacy evidence-adjusted model value.
    It must never be displayed as decision confidence. The final decision value
    is calculated by the decision-report contract and copied back to the
    canonical candidate before rankings, JSON and PDF are rebuilt.
    """
    from decision_report import candidate_confidence_profile, candidate_source_consensus

    consensus = candidate_source_consensus(candidate)
    profile = candidate_confidence_profile(candidate, consensus)
    candidate["model_confidence"] = _float(profile.get("model_confidence"))
    candidate["evidence_adjusted_model_confidence"] = _float(
        profile.get("evidence_adjusted_model_confidence"), candidate.get("confidence_score")
    )
    candidate["decision_confidence"] = _float(profile.get("decision_confidence"))
    evidence_coverage = max(0.0, min(100.0, _float(profile.get("evidence_coverage"), 0.0)))
    documentation_coverage = max(0.0, min(100.0, _float(profile.get("documentation_coverage", profile.get("data_coverage")), 0.0)))
    # Documentation cannot be more complete than the verified evidence behind it.
    # This prevents NOT_SEARCHED source areas from being displayed as 100% documented.
    profile["documentation_coverage"] = min(documentation_coverage, evidence_coverage)
    profile["data_coverage"] = profile["documentation_coverage"]
    profile["documentation_coverage_label"] = "Verifisert kilde- og analysedokumentasjon"
    candidate["confidence_profile"] = profile
    candidate["confidence_semantics"] = {
        "confidence_score": "LEGACY_EVIDENCE_ADJUSTED_MODEL_CONFIDENCE",
        "model_confidence": "RAW_MODEL_CONFIDENCE",
        "evidence_adjusted_model_confidence": "MODEL_CONFIDENCE_AFTER_EVIDENCE_POLICY",
        "decision_confidence": "FINAL_SOURCE_AND_GATE_ADJUSTED_DECISION_CONFIDENCE",
    }
    return consensus


def _candidate_evidence_coverage(candidate: Mapping[str, Any]) -> float:
    profile = _mapping(candidate.get("confidence_profile"))
    if profile.get("evidence_coverage") is not None:
        return max(0.0, min(100.0, _float(profile.get("evidence_coverage"))))
    if profile.get("data_coverage") is not None:
        return max(0.0, min(100.0, _float(profile.get("data_coverage"))))
    coverage = _mapping(candidate.get("evidence_coverage"))
    weights = {
        "VERIFIED_FACTS_FOUND": 100.0,
        "CHECKED_NO_EVENTS": 90.0,
        "SECONDARY_FACTS_FOUND": 55.0,
        "DISCOVERY_ONLY": 40.0,
        "PARTIAL_SOURCE_FAILURE": 30.0,
        "NOT_CONFIGURED": 15.0,
        "RATE_LIMITED": 15.0,
        "DAILY_QUOTA_EXCEEDED": 15.0,
        "SOURCE_ERROR": 10.0,
        "NOT_SEARCHED": 0.0,
    }
    values = []
    for area in ("news", "insider"):
        detail = _mapping(coverage.get(area))
        values.append(weights.get(str(detail.get("status") or "NOT_SEARCHED").upper(), 0.0))
    return round(sum(values) / len(values), 2) if values else 0.0


def _canonical_market_profile(result: MutableMapping[str, Any]) -> dict[str, Any]:
    from market_universe import market_profile_contract

    stored = _mapping(result.get("market_profile"))
    profile_id = stored.get("profile_id") or stored.get("id") or ""
    markets = result.get("markets") or []
    name = result.get("job_name") or ""
    named_profile = any(token in str(name).casefold() for token in (
        "kjernemarked", "utvidet norden", "alle markeder", "full skanning", "brasil",
    ))
    if not profile_id and not markets and not named_profile:
        return {}
    contract = market_profile_contract(profile_id, markets, name=name)
    result["market_profile"] = contract
    return contract


def _synchronise_decision_funnel(
    funnel: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Align the diagnostic funnel with the final canonical Autonomy outcome.

    Report canonicalisation can legitimately refine an outcome after the first
    funnel snapshot. The report must never retain stale reasons from an earlier
    outcome, so the hard gates are refreshed without relaxing any execution
    gate or recalculating model scores.
    """
    result = _mapping(funnel)
    if not result:
        return result
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in candidates if isinstance(row, Mapping)}
    production_threshold = _float(result.get("production_threshold"), 78.0)
    reason_labels = {
        "portfolio_active": "Porteføljen er ikke aktiv",
        "autonomy_outcome_buy": "Autonomiutfallet er {outcome}, ikke Kjøpskandidat",
        "portfolio_layer_buy": "Porteføljelaget ga {action}",
        "valid_for_decision": "Markedsdata er ikke beslutningsgyldige",
        "evidence_valid_for_decision": "Evidensgrunnlaget er ikke beslutningsgyldig",
        "final_decision_ready": "Kandidaten er ikke endelig kjøpsklar",
        "technical_timing": "Teknisk timing gir Vent",
        "score": "Score {score:.1f} er under {threshold:.1f}",
        "data_quality": "Datakvaliteten er under minimumskravet",
        "risk": "Risikoen er over maksimumsgrensen",
        "price": "Mangler gyldig markedspris",
        "position_capacity": "Maksimalt antall åpne posisjoner er nådd",
        "addition_policy": "Tilleggskjøp er deaktivert",
    }
    counts: dict[str, int] = {}
    refreshed: list[dict[str, Any]] = []
    for source_row in result.get("candidates") or []:
        if not isinstance(source_row, Mapping):
            continue
        row = _mapping(source_row)
        ticker = str(row.get("ticker") or "").upper()
        candidate = by_ticker.get(ticker, {})
        outcome = str(candidate.get("autonomy_outcome_code") or row.get("autonomy_outcome_code") or "").upper()
        outcome_display = str(candidate.get("autonomy_outcome_label") or {
            "KJØPSKANDIDAT": "Kjøpskandidat",
            "OVERVÅKES_AUTOMATISK": "Overvåkes automatisk",
            "AUTOMATISK_AVVIST": "Automatisk avvist",
            "UNDERSØK_MANUELT": "Undersøk manuelt",
        }.get(outcome, outcome or "ikke satt"))
        action = str(candidate.get("portfolio_action") or row.get("portfolio_action") or "UNASSESSED").upper()
        action_display = {"BUY": "Kjøp", "KJØP": "Kjøp", "HOLD": "Behold", "REVIEW": "Undersøk manuelt", "SKIP": "Ikke aktuell", "SELL": "Selg"}.get(action, action)
        gates = _mapping(row.get("gates"))
        gates.update({
            "autonomy_outcome_buy": outcome == "KJØPSKANDIDAT",
            "portfolio_layer_buy": action in {"BUY", "KJØP"},
            "valid_for_decision": candidate.get("valid_for_decision") is True,
            "evidence_valid_for_decision": candidate.get("evidence_valid_for_decision") is True,
            "final_decision_ready": candidate.get("final_decision_ready") is not False,
            "technical_timing": not bool(candidate.get("technical_entry_wait")),
            "score": _float(row.get("score"), _float(candidate.get("investment_score"))) >= production_threshold,
        })
        reasons: list[str] = []
        for gate, passed in gates.items():
            if passed:
                continue
            counts[gate] = counts.get(gate, 0) + 1
            template = reason_labels.get(gate, str(gate))
            reasons.append(template.format(
                outcome=outcome_display, action=action_display,
                score=_float(row.get("score"), _float(candidate.get("investment_score"))),
                threshold=production_threshold,
            ))
        eligible = bool(gates) and all(bool(value) for value in gates.values())
        row.update({
            "portfolio_action": action,
            "autonomy_outcome_code": outcome,
            "autonomy_outcome_label": candidate.get("autonomy_outcome_label"),
            "gates": gates,
            "eligible_for_theoretical_buy": eligible,
            "decision": "BUY_ELIGIBLE" if eligible else "REJECTED",
            "reasons": reasons,
        })
        refreshed.append(row)
    result["candidates"] = refreshed
    result["evaluated"] = len(refreshed)
    result["eligible"] = sum(bool(row.get("eligible_for_theoretical_buy")) for row in refreshed)
    result["rejected"] = len(refreshed) - int(result["eligible"])
    result["rejection_counts"] = counts
    result["near_threshold"] = [
        row for row in refreshed
        if not row.get("eligible_for_theoretical_buy")
        and _float(row.get("score")) >= production_threshold - 6.0
    ][:10]
    for shadow in result.get("shadow_thresholds") or []:
        if not isinstance(shadow, MutableMapping):
            continue
        threshold = _float(shadow.get("threshold"), production_threshold)
        score_qualified = [row["ticker"] for row in refreshed if _float(row.get("score")) >= threshold]
        eligible = [
            row["ticker"] for row in refreshed
            if all(bool(value) for key, value in _mapping(row.get("gates")).items() if key != "score")
            and _float(row.get("score")) >= threshold
        ]
        shadow.update({
            "score_qualified_count": len(score_qualified),
            "score_qualified_tickers": score_qualified,
            "eligible_count": len(eligible),
            "eligible_tickers": eligible,
        })
    return result


def _valid_web_url(value: Any) -> bool:
    text = str(value or "").strip()
    try:
        parsed = urlparse(text)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def _sync_reference_tree(value: Any, by_ticker: Mapping[str, Mapping[str, Any]]) -> Any:
    """Synchronise known candidate references without retaining stale decisions."""
    if isinstance(value, Mapping):
        source = dict(value)
        row = {key: _sync_reference_tree(item, by_ticker) for key, item in source.items()}
        ticker = str(source.get("ticker") or "").upper()
        canonical = by_ticker.get(ticker)
        if canonical:
            for field in (
                "status", "portfolio_action", "autonomy_outcome_code", "autonomy_outcome_label",
                "autonomy_outcome_reason", "automatic_next_action", "manual_review_required",
                "manual_tasks", "manual_task_summary", "decision_confidence", "confidence_profile",
                "evidence_gate_status", "evidence_valid_for_decision", "valid_for_decision",
                "final_decision_ready", "decision_readiness", "portfolio_decision",
            ):
                if field in canonical:
                    row[field] = deepcopy(canonical.get(field))
            decision = canonical.get("portfolio_decision") if isinstance(canonical.get("portfolio_decision"), Mapping) else {}
            if decision:
                row["portfolio_reason"] = str(decision.get("reason") or "")
                if "reason" in source:
                    row["reason"] = str(decision.get("reason") or source.get("reason") or "")
        return row
    if isinstance(value, list):
        return [_sync_reference_tree(item, by_ticker) for item in value]
    return deepcopy(value)


def _synchronise_derived_views(result: MutableMapping[str, Any], candidates: Sequence[Mapping[str, Any]]) -> None:
    """Rebuild every active candidate/portfolio view from canonical candidates."""
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in candidates if isinstance(row, Mapping)}
    action_counts = {
        action: sum(1 for row in candidates if str(row.get("portfolio_action") or "").upper() == action)
        for action in ("BUY", "HOLD", "SELL", "SKIP", "REVIEW")
    }

    proposal = _mapping(result.get("portfolio_proposal"))
    if proposal:
        proposal["actions"] = action_counts
        buy_tickers = {ticker for ticker, row in by_ticker.items() if str(row.get("portfolio_action") or "").upper() == "BUY"}
        proposal["allocations"] = [
            _sync_reference_tree(row, by_ticker) for row in _rows(proposal.get("allocations"))
            if str(row.get("ticker") or "").upper() in buy_tickers
        ]
        proposal["positions"] = [
            _sync_reference_tree(row, by_ticker) for row in _rows(proposal.get("positions"))
            if str(row.get("ticker") or "").upper() in buy_tickers
        ]
        if not buy_tickers:
            proposal["invested_pct"] = 0.0
            proposal["cash_pct"] = 100.0
            proposal["status"] = "INGEN_KJØPSGODKJENTE_KANDIDATER"
        result["portfolio_proposal"] = proposal

    for key in ("changes", "ranking_explanation"):
        if key in result:
            result[key] = _sync_reference_tree(result.get(key), by_ticker)
    if isinstance(result.get("market_runs"), list):
        result["market_runs"] = _sync_reference_tree(result.get("market_runs"), by_ticker)


def _iter_candidate_references(value: Any):
    if isinstance(value, Mapping):
        if value.get("ticker") and any(key in value for key in ("portfolio_action", "autonomy_outcome_code")):
            yield value
        for key, item in value.items():
            if key in {"raw", "raw_history", "previous_analysis_snapshot", "source_payload", "discovery_data"}:
                continue
            yield from _iter_candidate_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_candidate_references(item)


def canonical_report_view(run: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-copied report view with explicit semantic precedence."""
    result = deepcopy(dict(run or {}))
    corrections: list[dict[str, Any]] = []

    # A report rendered or persisted by this release must carry the current
    # renderer/schema contract in every format. Preserve the source contract as
    # provenance when an older run is reprocessed, but never let stale version
    # metadata survive as the authoritative JSON contract while the PDF shows
    # the current release.
    source_contract = _mapping(result.get("version_contract"))
    current_contract = get_version_contract(
        component_name="report_integrity",
        component_version=APP_VERSION,
    )
    if source_contract and (
        str(source_contract.get("app_version") or "") != APP_VERSION
        or str(source_contract.get("report_schema_version") or "") != REPORT_SCHEMA_VERSION
    ):
        result["source_version_contract"] = source_contract
        corrections.append({
            "ticker": "REPORT",
            "field": "version_contract",
            "from": {
                "app_version": source_contract.get("app_version"),
                "report_schema_version": source_contract.get("report_schema_version"),
            },
            "to": {
                "app_version": APP_VERSION,
                "report_schema_version": REPORT_SCHEMA_VERSION,
            },
            "reason": "JSON og PDF må bruke samme gjeldende rapportkontrakt",
        })
    result["version"] = APP_VERSION
    result["app_version"] = APP_VERSION
    result["report_schema_version"] = REPORT_SCHEMA_VERSION
    result["version_contract"] = current_contract
    # Existing report documents may contain stale metadata and sections. They
    # are rebuilt from the canonical result at the end of this function.
    result.pop("report_document", None)
    result.pop("report_contract_validation", None)
    # Resolve one stable market-profile contract, but retain the actual market
    # list for semantic validation. A historic six-market run must never be
    # silently relabelled as a three-market core run.
    _canonical_market_profile(result)

    # Report type and completion state are different concepts. A draft can be a
    # completed run, but it must never be labelled FINAL/ENDELIG in the report.
    identity = _mapping(result.get("report_identity"))
    identity_type = str(identity.get("type") or "").upper()
    identity_label = str(identity.get("label") or "")
    draft_job = str(result.get("job_id") or "").upper() == "MI-DRAFT-AUTOSAVE"
    is_draft = draft_job or identity_type == "UTKAST" or identity_label.casefold().startswith("utkast")
    if draft_job and identity_type != "UTKAST":
        base_label = identity_label or "Rapport"
        if not base_label.casefold().startswith("utkast"):
            base_label = f"Utkast – {base_label}"
        identity.update({"type": "UTKAST", "label": base_label, "slug": "UTKAST_" + str(identity.get("slug") or "Rapport")})
    if identity:
        result["report_identity"] = identity
    if is_draft:
        old_status = _mapping(result.get("report_status"))
        result["report_status"] = {
            **old_status,
            "state": "DRAFT",
            "label": "UTKAST – IKKE ENDELIG",
            "revalidation_required": bool(old_status.get("revalidation_required")),
            "completion_state": "COMPLETED_DRAFT",
        }
        corrections.append({
            "ticker": "REPORT",
            "field": "report_status",
            "from": old_status.get("label") or old_status.get("state") or "",
            "to": "UTKAST – IKKE ENDELIG",
            "reason": "Rapporttype UTKAST kan ikke merkes ENDELIG",
        })
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
        if candidate.get("valid_for_decision") is None:
            candidate["valid_for_decision"] = str(readiness.get("market_data") or "").upper() in {
                "VALID", "GYLDIG", "VERIFIED", "KOMPLETT",
            }
        if candidate.get("evidence_valid_for_decision") is None:
            valid_evidence_states = {"VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "AVAILABLE", "VERIFIED"}
            statuses = [str(readiness.get(area) or "").upper() for area in ("news", "insider")]
            candidate["evidence_valid_for_decision"] = bool(statuses) and all(
                status in valid_evidence_states for status in statuses
            )
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

    from autonomous_decision_reduction import apply_decision_reduction
    portfolio_meta = _mapping(result.get("portfolio_decisions"))
    previous_reduction = _mapping(result.get("autonomous_decision_reduction"))
    funnel = _mapping(result.get("decision_funnel"))
    threshold = _float(
        funnel.get("production_threshold")
        if funnel.get("production_threshold") is not None
        else previous_reduction.get("production_buy_threshold", previous_reduction.get("threshold", portfolio_meta.get("production_threshold"))),
        78.0,
    )
    maximum_risk = _float(
        previous_reduction.get("maximum_risk", portfolio_meta.get("maximum_risk_score")), 65.0
    )
    canonical_candidates, reduction = apply_decision_reduction(
        canonical_candidates, threshold=threshold, maximum_risk=maximum_risk,
        near_threshold_gap=6.0, max_manual_tasks=2,
    )
    for candidate in canonical_candidates:
        _synchronise_final_outcome(candidate)
        _synchronise_candidate_confidence(candidate)
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), MutableMapping) else {}
        if isinstance(raw, MutableMapping):
            for field in (
                "model_confidence", "evidence_adjusted_model_confidence",
                "decision_confidence", "confidence_profile", "confidence_semantics",
            ):
                raw[field] = deepcopy(candidate.get(field))
    # Rebuild reduction counts after canonical outcome/action synchronisation.
    counts = {code: sum(1 for row in canonical_candidates if row.get("autonomy_outcome_code") == code)
              for code in _OUTCOME_ACTION}
    reduction.update({
        "counts": counts,
        "buy_candidates": counts["KJØPSKANDIDAT"],
        "automatic_watch": counts["OVERVÅKES_AUTOMATISK"],
        "automatic_rejected": counts["AUTOMATISK_AVVIST"],
        "manual_candidates": counts["UNDERSØK_MANUELT"],
    })
    # Priority rows are rebuilt from canonical candidates. This prevents a
    # stale pre-policy confidence value from surviving in the front page while
    # candidate detail pages display the final decision confidence.
    priority_tickers = [
        str(row.get("ticker") or "").upper()
        for row in (reduction.get("priority_top3") or []) if isinstance(row, Mapping)
    ]
    by_priority = {str(row.get("ticker") or "").upper(): row for row in canonical_candidates}
    canonical_priority = [compact_candidate_reference(by_priority[ticker]) for ticker in priority_tickers if ticker in by_priority]
    for priority_rank, priority_row in enumerate(canonical_priority, 1):
        priority_row["priority_rank"] = priority_rank
    reduction["priority_top3"] = canonical_priority
    result["candidates"] = canonical_candidates
    result["autonomous_decision_reduction"] = reduction
    result["manual_tasks"] = list(reduction.get("manual_tasks") or [])
    result["priority_top3"] = canonical_priority
    result["executive_intelligence"] = executive_intelligence_from_candidates(canonical_candidates)
    if isinstance(result.get("decision_funnel"), Mapping):
        result["decision_funnel"] = _synchronise_decision_funnel(result.get("decision_funnel") or {}, canonical_candidates)

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
    priority_top3 = list(reduction.get("priority_top3") or [])
    result["top3_status"] = {
        "priority_count": len(priority_top3),
        "raw_count": len(raw_top3),
        "evidence_data_ready_count": len(evidence_ready_top3),
        "decision_ready_count": len(final_decision_top3),
        "uses_raw_fallback": not bool(priority_top3),
        "display_mode": "PRIORITY_REVIEW" if priority_top3 else "NO_PRIORITY_CANDIDATES",
    }

    actions = _mapping(_mapping(result.get("portfolio_decisions")).get("actions"))
    manual_review = int(reduction.get("manual_candidates") or 0)
    evidence_ready_count = len(evidence_ready_rows)
    final_ready_count = len(final_ready_rows)
    preliminary_count = int(_mapping(result.get("summary")).get("proposals") or len(result.get("proposals") or []))
    candidate_by_ticker = {str(row.get("ticker") or "").upper(): row for row in canonical_candidates}
    for proposal in result.get("proposals") or []:
        if isinstance(proposal, MutableMapping):
            canonical = candidate_by_ticker.get(str(proposal.get("ticker") or "").upper(), {})
            for field in (
                "autonomy_outcome_code", "autonomy_outcome_label", "autonomy_outcome_reason",
                "automatic_next_action", "manual_review_required", "manual_tasks", "manual_task_summary",
                "analysis_stage",
            ):
                if field in canonical:
                    proposal[field] = deepcopy(canonical.get(field))
            proposal["proposal_stage"] = "PRELIMINARY_MODEL_OUTPUT"
            proposal["final_trade_proposal"] = False
            proposal["display_label"] = "Foreløpig modellkandidat før evidens- og beslutningsport"
    result["proposals"] = [compact_candidate_reference(row) for row in result.get("proposals") or [] if isinstance(row, Mapping)]
    # Nested market results are diagnostic references after the canonical top-level
    # candidate list has been created. Keeping full raw copies here caused repeated
    # raw.raw chains and multi-megabyte delivery files.
    for market_run in result.get("market_runs") or []:
        if not isinstance(market_run, MutableMapping):
            continue
        market_run["candidates"] = [
            compact_candidate_reference(candidate_by_ticker.get(str(row.get("ticker") or "").upper(), row))
            for row in market_run.get("candidates") or [] if isinstance(row, Mapping)
        ]
        market_run["proposals"] = [compact_candidate_reference(row) for row in market_run.get("proposals") or [] if isinstance(row, Mapping)]
        market_run["candidate_payload_mode"] = "COMPACT_CANONICAL_REFERENCES"
    result["proposal_summary"] = {
        "preliminary_model_candidates": preliminary_count,
        "evidence_data_ready_candidates": evidence_ready_count,
        "final_buy_candidates": final_ready_count,
        "label": "Foreløpige modellkandidater – ikke handelsforslag",
    }

    diagnostics_summary = _normalise_market_diagnostics(result)
    result["diagnostics_summary"] = diagnostics_summary
    result["learning_portfolio_summary"] = _learning_summary(result)
    # Canonical portfolio reason: do not claim capacity shortage when the
    # portfolio is inactive or has documented room/cash.
    portfolio_decisions = _mapping(result.get("portfolio_decisions"))
    portfolio_context = _mapping(portfolio_decisions.get("portfolio_context"))
    portfolio_status = str(portfolio_context.get("portfolio_status") or portfolio_context.get("status") or "").upper()
    portfolio_active = bool(
        portfolio_context.get("active") or portfolio_context.get("portfolio_active")
        or portfolio_status in {"ACTIVE", "AKTIV"}
    )
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in canonical_candidates}
    canonical_portfolio_rows = []
    for decision in _rows(portfolio_decisions.get("decisions")):
        ticker = str(decision.get("ticker") or "").upper()
        candidate = by_ticker.get(ticker, {})
        if not portfolio_active:
            reason = "Porteføljen er ikke aktiv; ingen handel kan gjennomføres."
        elif candidate.get("autonomy_outcome_code") != "KJØPSKANDIDAT":
            reason = str(candidate.get("autonomy_outcome_reason") or "Kandidaten er ikke kjøpsgodkjent.")
        else:
            reason = str(decision.get("reason") or "Porteføljeporten vurderte kandidaten.")
        decision["reason"] = reason
        decision["blockers"] = [reason]
        decision["action"] = str(candidate.get("portfolio_action") or decision.get("action") or "SKIP")
        canonical_portfolio_rows.append(decision)
    if portfolio_decisions:
        if not canonical_portfolio_rows:
            canonical_portfolio_rows = [{
                "ticker": str(candidate.get("ticker") or ""),
                "action": str(candidate.get("portfolio_action") or "SKIP"),
                "reason": (
                    "Porteføljen er ikke aktiv; ingen handel kan gjennomføres."
                    if not portfolio_active else str(candidate.get("autonomy_outcome_reason") or "Kandidaten er ikke kjøpsgodkjent.")
                ),
                "blockers": [
                    "Porteføljen er ikke aktiv; ingen handel kan gjennomføres."
                    if not portfolio_active else str(candidate.get("autonomy_outcome_reason") or "Kandidaten er ikke kjøpsgodkjent.")
                ],
            } for candidate in canonical_candidates]
        portfolio_decisions["decisions"] = canonical_portfolio_rows
        portfolio_decisions["actions"] = {
            action: sum(1 for row in canonical_portfolio_rows if str(row.get("action") or "").upper() == action)
            for action in ("BUY", "HOLD", "SELL", "SKIP", "REVIEW")
        }
        result["portfolio_decisions"] = portfolio_decisions
        canonical_by_ticker = {str(row.get("ticker") or "").upper(): row for row in canonical_portfolio_rows}
        for candidate in canonical_candidates:
            decision = canonical_by_ticker.get(str(candidate.get("ticker") or "").upper())
            if not decision:
                continue
            candidate["portfolio_decision"] = deepcopy(decision)
            raw = candidate.get("raw") if isinstance(candidate.get("raw"), MutableMapping) else None
            if isinstance(raw, MutableMapping):
                raw["portfolio_decision"] = deepcopy(decision)

    _synchronise_derived_views(result, canonical_candidates)
    # Ranking explanation is regenerated after evidence filtering and all final outcomes.
    try:
        from market_intelligence import build_ranking_explanation
        result["ranking_explanation"] = build_ranking_explanation(result)
    except Exception:
        result["ranking_explanation"] = _sync_reference_tree(result.get("ranking_explanation") or {}, by_ticker)

    result["autonomous_decisions"] = _canonical_decisions(canonical_candidates, result.get("created_at"))
    result["autonomous_decision_summary"] = {
        "registered": len(result["autonomous_decisions"]),
        "counts": dict(reduction.get("counts") or {}),
    }
    combined_quality = _mapping(result.get("combined_data_quality"))
    evaluated_quality = int(combined_quality.get("evaluated") or len(canonical_candidates) or 0)
    market_valid_quality = int(combined_quality.get("market_data_valid") or 0)
    if combined_quality.get("coverage_pct") is not None:
        data_coverage_pct = _float(combined_quality.get("coverage_pct"))
    elif evaluated_quality:
        data_coverage_pct = round(market_valid_quality / evaluated_quality * 100.0, 2)
    else:
        data_coverage_pct = _float(_mapping(result.get("data_quality")).get("score"))
    result["quality_metrics"] = {
        "overall_report_quality": _float(_mapping(result.get("data_quality")).get("score")),
        "data_coverage": data_coverage_pct,
        "candidate_evidence_coverage_average": round(
            sum(_candidate_evidence_coverage(row) for row in canonical_candidates) / len(canonical_candidates), 2
        ) if canonical_candidates else 0.0,
        "labels": {
            "overall_report_quality": "Teknisk rapportfullstendighet",
            "data_coverage": "Markedsdatadekning",
            "candidate_evidence_coverage_average": "Gjennomsnittlig evidensdekning per kandidat",
        },
    }
    result["report_summary"] = {
        "scanned": int(_mapping(result.get("summary")).get("scanned") or 0),
        "deep_analyzed": len(canonical_candidates),
        "manual_review": manual_review,
        "manual_task_count": int(reduction.get("manual_task_count") or 0),
        "automatic_watch": int(reduction.get("automatic_watch") or 0),
        "automatic_rejected": int(reduction.get("automatic_rejected") or 0),
        "buy_candidates": int(reduction.get("buy_candidates") or 0),
        "evidence_data_ready": evidence_ready_count,
        "decision_ready": final_ready_count,
        "preliminary_model_candidates": preliminary_count,
        "production_buy_threshold": threshold,
        "manual_review_window_points": float(reduction.get("manual_review_window_points") or 6.0),
        **result["executive_intelligence"],
        **diagnostics_summary,
    }
    result["summary"] = {
        "scanned": int(result["report_summary"].get("scanned") or 0),
        "deep_analyzed": int(result["report_summary"].get("deep_analyzed") or 0),
        "proposals": int(result["report_summary"].get("preliminary_model_candidates") or 0),
        "recommended": int(result["report_summary"].get("buy_candidates") or 0),
        "rejected": int(result["report_summary"].get("automatic_rejected") or 0),
        "automatic_watch": int(result["report_summary"].get("automatic_watch") or 0),
        "manual_review": int(result["report_summary"].get("manual_review") or 0),
    }
    # Rebuild the decision report from the same canonical candidates used by
    # JSON and PDF. Historic decision-report payloads are retained only as
    # provenance through their own history fields, never as an active truth.
    from decision_report import enrich_decision_report
    enrich_decision_report(result, None, identity)
    result["report_integrity"] = {
        "schema_version": REPORT_INTEGRITY_SCHEMA_VERSION,
        "canonical_candidate_count": len(canonical_candidates),
        "correction_count": len(corrections),
        "corrections": corrections,
        "field_precedence": "candidate top-level > raw supporting detail; score trend is not technical price trend",
    }
    validation = validate_report_integrity(result)
    result["report_integrity"].update(validation)

    # Rebuild the renderer-independent document after all canonical fields and
    # integrity results are final. This makes archived JSON and rendered PDF
    # share the same app/schema version and candidate sections.
    if result.get("run_id") or result.get("report_id"):
        from report_contracts import ensure_report_document
        ensure_report_document(result)
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

    # Market profile is a semantic contract, not a display label. A job called
    # Kjernemarkeder must have executed exactly Norway, Sweden and USA.
    profile = run.get("market_profile") if isinstance(run.get("market_profile"), Mapping) else {}
    actual_markets = [str(value) for value in (run.get("markets") or [])]
    expected_markets = [str(value) for value in (profile.get("expanded_markets") or [])]
    if expected_markets and actual_markets != expected_markets:
        errors.append(
            "Markedsprofilen %s forventer %s, men kjøringen brukte %s" % (
                profile.get("label") or profile.get("profile_id") or "-",
                ", ".join(expected_markets), ", ".join(actual_markets),
            )
        )
    for mission_key in ("investment_mission", "user_mission"):
        mission = run.get(mission_key) if isinstance(run.get(mission_key), Mapping) else {}
        mission_markets = [str(value) for value in (mission.get("markets") or [])]
        if mission_markets and actual_markets and mission_markets != actual_markets:
            errors.append(f"{mission_key}.markets samsvarer ikke med faktisk markedsutvalg")

    decision_report = run.get("decision_report") if isinstance(run.get("decision_report"), Mapping) else {}
    report_contracts = {
        str(row.get("ticker") or "").upper(): row
        for row in (decision_report.get("candidate_contracts") or []) if isinstance(row, Mapping)
    }
    portfolio_rows = {
        str(row.get("ticker") or "").upper(): row
        for row in (_mapping(run.get("portfolio_decisions")).get("decisions") or []) if isinstance(row, Mapping)
    }
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        ticker = str(candidate.get("ticker") or "").upper()
        profile_row = candidate.get("confidence_profile") if isinstance(candidate.get("confidence_profile"), Mapping) else {}
        decision_confidence = _float(candidate.get("decision_confidence"), -1.0)
        profile_decision = _float(profile_row.get("decision_confidence"), -1.0)
        if decision_confidence < 0 or abs(decision_confidence - profile_decision) > 0.01:
            errors.append(f"{ticker}: beslutningskonfidens har flere sannhetskilder")
        if profile_row.get("model_confidence") is None or profile_row.get("evidence_adjusted_model_confidence") is None:
            errors.append(f"{ticker}: modell- og evidensjustert konfidens er ikke eksplisitt adskilt")
        contract_row = report_contracts.get(ticker, {})
        contract_confidence = _mapping(contract_row.get("confidence"))
        if contract_confidence and abs(_float(contract_confidence.get("decision_confidence"), -1.0) - decision_confidence) > 0.01:
            errors.append(f"{ticker}: beslutningsrapporten bruker en annen beslutningskonfidens")
        portfolio = portfolio_rows.get(ticker)
        candidate_portfolio = candidate.get("portfolio_decision") if isinstance(candidate.get("portfolio_decision"), Mapping) else {}
        if portfolio and (
            str(candidate_portfolio.get("action") or "") != str(portfolio.get("action") or "")
            or str(candidate_portfolio.get("reason") or "") != str(portfolio.get("reason") or "")
        ):
            errors.append(f"{ticker}: kandidatens porteføljebegrunnelse er foreldet")

        raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
        news = raw.get("news_intelligence") if isinstance(raw.get("news_intelligence"), Mapping) else {}
        for event in news.get("events") or []:
            if not isinstance(event, Mapping):
                continue
            relevant = event.get("company_relevant")
            if relevant is None and event.get("title") and (event.get("url") or event.get("source_url") or event.get("summary")):
                from news_intelligence import article_company_relevance
                relevant = article_company_relevance(
                    event, ticker, str(candidate.get("name") or raw.get("longName") or raw.get("shortName") or "")
                ).get("company_relevant")
            if relevant is False:
                errors.append(f"{ticker}: nyhetsgrunnlaget inneholder en sak uten dokumentert selskapsrelevans")
                break
        insider = raw.get("insider_intelligence") if isinstance(raw.get("insider_intelligence"), Mapping) else {}
        insider_status = str(_mapping(candidate.get("evidence_coverage")).get("insider", {}).get("status") if isinstance(_mapping(candidate.get("evidence_coverage")).get("insider"), Mapping) else "").upper()
        facts = [row for row in (insider.get("evidence") or []) if isinstance(row, Mapping)]
        primary_facts = [row for row in facts if row.get("primary_source_verified") is True]
        if facts and not primary_facts and insider_status == "VERIFIED_FACTS_FOUND":
            errors.append(f"{ticker}: sekundære insiderdata er feilklassifisert som primærverifiserte fakta")

    expected = executive_intelligence_from_candidates([row for row in candidates if isinstance(row, Mapping)])
    actual = run.get("executive_intelligence") if isinstance(run.get("executive_intelligence"), Mapping) else {}
    for key, value in expected.items():
        if actual.get(key) != value:
            errors.append(f"Sammendraget {key} er ikke beregnet fra kanonisk kandidatliste")

    # One final outcome per candidate; manual status may not coexist with automatic closure.
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        ticker = str(candidate.get("ticker") or "-")
        code = str(candidate.get("autonomy_outcome_code") or "").upper()
        expected_action = _OUTCOME_ACTION.get(code)
        if expected_action and str(candidate.get("portfolio_action") or "").upper() != expected_action:
            errors.append(f"{ticker}: sluttutfall og slutthandling motsier hverandre")
        manual = code == "UNDERSØK_MANUELT"
        if bool(candidate.get("manual_review_required")) != manual or bool(candidate.get("evidence_review_required")) != manual:
            errors.append(f"{ticker}: manuell vurderingsstatus er ikke entydig")
        if not manual and str(candidate.get("evidence_gate_status") or "").upper() == "MANUAL_REVIEW":
            errors.append(f"{ticker}: automatisk utfall viser fortsatt manuell evidensport")
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
        for area in ("insider", "news"):
            payload = raw.get(f"{area}_intelligence") if isinstance(raw.get(f"{area}_intelligence"), Mapping) else {}
            facts = int(payload.get("verified_fact_count") or payload.get("article_count") or len(payload.get("evidence") or payload.get("events") or []))
            display = str(raw.get(f"{area}_signal") if area == "insider" else raw.get("news_sentiment") or "").upper()
            if facts > 0 and display in {"", "INGEN DATA", "NOT_SEARCHED", "MISSING"}:
                errors.append(f"{ticker}: {area} har verifiserte fakta, men vises som ingen data")

    summary = run.get("summary") if isinstance(run.get("summary"), Mapping) else {}
    report_summary = run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
    final_count = sum(1 for row in candidates if isinstance(row, Mapping) and _is_final_decision_ready(row))
    evidence_count = sum(1 for row in candidates if isinstance(row, Mapping) and _is_evidence_data_ready(row))
    if int(report_summary.get("decision_ready") or 0) != final_count:
        errors.append("Sammendragets beslutningsklare antall er ikke endelig kjøpsklart antall")
    if int(report_summary.get("evidence_data_ready") or 0) != evidence_count:
        errors.append("Sammendragets evidens- og dataklare antall er feil")
    reduction = run.get("autonomous_decision_reduction") if isinstance(run.get("autonomous_decision_reduction"), Mapping) else {}
    if int(summary.get("rejected") or 0) != int(report_summary.get("automatic_rejected") or 0):
        errors.append("summary.rejected og report_summary.automatic_rejected er ulike")
    if int(report_summary.get("automatic_rejected") or 0) != int(reduction.get("automatic_rejected") or 0):
        errors.append("Avvisningstall er ikke kanoniske på tvers av rapporten")
    autonomous_decisions = list(run.get("autonomous_decisions") or [])
    if candidates and len(autonomous_decisions) != len(candidates):
        errors.append("Alle kandidatutfall er ikke registrert som autonome beslutninger")

    manual_candidates = [row for row in candidates if isinstance(row, Mapping) and row.get("manual_review_required")]
    manual_tasks = list(run.get("manual_tasks") or [])
    if len(manual_candidates) > 2:
        errors.append("Flere enn to kandidater er sendt til manuell undersøkelse")
    if len(manual_tasks) > 2:
        errors.append("Flere enn to konkrete manuelle oppgaver er opprettet")
    for row in manual_candidates:
        tasks = list(row.get("manual_tasks") or [])
        if not tasks:
            errors.append(f"{row.get('ticker')}: manuell undersøkelse mangler konkret oppgave")
        for task in tasks:
            if not isinstance(task, Mapping) or not all(task.get(key) for key in ("title", "why", "program_attempts", "failure_reason", "suggested_source", "decision_impact")):
                errors.append(f"{row.get('ticker')}: manuell oppgave er ufullstendig")
    if len(manual_tasks) != sum(len(row.get("manual_tasks") or []) for row in manual_candidates):
        errors.append("Sammendraget for manuelle oppgaver samsvarer ikke med kandidatene")

    funnel = run.get("decision_funnel") if isinstance(run.get("decision_funnel"), Mapping) else {}
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in candidates if isinstance(row, Mapping)}
    for row in funnel.get("candidates") or []:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").upper()
        candidate = by_ticker.get(ticker, {})
        if str(row.get("autonomy_outcome_code") or "").upper() != str(candidate.get("autonomy_outcome_code") or "").upper():
            errors.append(f"{ticker}: beslutningstrakten bruker et foreldet Autonomiutfall")

    chain = run.get("autonomous_chain") if isinstance(run.get("autonomous_chain"), Mapping) else {}
    portfolio_stage: Mapping[str, Any] = {}
    for stage in chain.get("stages") or []:
        if isinstance(stage, Mapping) and str(stage.get("name") or "").upper() == "AUTONOMOUS_PORTFOLIO":
            portfolio_stage = stage.get("detail") if isinstance(stage.get("detail"), Mapping) else {}
            break
    if portfolio_stage:
        buy_tickers = {str(value or "").upper() for value in portfolio_stage.get("buy_tickers") or [] if value}
        sell_tickers = {str(value or "").upper() for value in portfolio_stage.get("sell_tickers") or [] if value}
        if buy_tickers & sell_tickers:
            errors.append("Samme ticker er både kjøpt og solgt i én Autonomi-kjøring: " + ", ".join(sorted(buy_tickers & sell_tickers)))
        by_ticker = {str(row.get("ticker") or "").upper(): row for row in candidates if isinstance(row, Mapping)}
        for ticker in sorted(buy_tickers):
            row = by_ticker.get(ticker, {})
            if str(row.get("autonomy_outcome_code") or "").upper() != "KJØPSKANDIDAT":
                errors.append(f"{ticker}: produksjonskjøp uten Autonomiutfall Kjøpskandidat")
            if str(row.get("portfolio_action") or "").upper() not in {"BUY", "KJØP"}:
                errors.append(f"{ticker}: produksjonskjøp uten endelig kjøpshandling")
            if row.get("valid_for_decision") is not True or row.get("evidence_valid_for_decision") is not True:
                errors.append(f"{ticker}: produksjonskjøp uten gyldige data og evidens")
        production_buys = int(portfolio_stage.get("ordinary_buys") if portfolio_stage.get("ordinary_buys") is not None else portfolio_stage.get("buys") or 0)
        if production_buys != len(buy_tickers):
            errors.append("Antall produksjonskjøp samsvarer ikke med kjøpstickerne")
        if production_buys and int(report_summary.get("buy_candidates") or 0) == 0:
            errors.append("Autonomi registrerte produksjonskjøp, men rapporten har ingen kjøpskandidater")
        execution_integrity = portfolio_stage.get("execution_integrity") if isinstance(portfolio_stage.get("execution_integrity"), Mapping) else {}
        if execution_integrity and execution_integrity.get("ok") is False:
            errors.append("Autonom handel ble blokkert av ordrelagets integritetskontroll: " + "; ".join(execution_integrity.get("errors") or []))

    identity = run.get("report_identity") if isinstance(run.get("report_identity"), Mapping) else {}
    status = run.get("report_status") if isinstance(run.get("report_status"), Mapping) else {}
    is_draft = str(identity.get("type") or "").upper() == "UTKAST" or str(identity.get("label") or "").casefold().startswith("utkast")
    if is_draft and str(status.get("state") or "").upper() in {"FINAL", "ENDELIG"}:
        errors.append("Rapporttype UTKAST er feilaktig merket som endelig")
    if is_draft and "ENDELIG" in str(status.get("label") or "").upper() and "IKKE ENDELIG" not in str(status.get("label") or "").upper():
        errors.append("Utkastrapportens statusetikett motsier rapporttypen")
    version_contract = run.get("version_contract") if isinstance(run.get("version_contract"), Mapping) else {}
    if str(version_contract.get("app_version") or "") != APP_VERSION:
        errors.append("JSON-rapportens appversjon samsvarer ikke med gjeldende rapportgenerator")
    if str(version_contract.get("report_schema_version") or "") != REPORT_SCHEMA_VERSION:
        errors.append("JSON-rapportens skjemaversjon samsvarer ikke med gjeldende rapportgenerator")
    if str(run.get("version") or run.get("app_version") or "") != APP_VERSION:
        errors.append("Rapportens toppnivåversjon samsvarer ikke med versjonskontrakten")

    by_ticker = {str(row.get("ticker") or "").upper(): row for row in candidates if isinstance(row, Mapping)}
    expected_actions = {
        action: sum(1 for row in candidates if str(row.get("portfolio_action") or "").upper() == action)
        for action in ("BUY", "HOLD", "SELL", "SKIP", "REVIEW")
    }
    for container_key in ("portfolio_decisions", "portfolio_proposal"):
        container = run.get(container_key) if isinstance(run.get(container_key), Mapping) else {}
        actions = container.get("actions") if isinstance(container.get("actions"), Mapping) else {}
        if actions and any(int(actions.get(action) or 0) != count for action, count in expected_actions.items()):
            errors.append(f"{container_key}.actions motsier den kanoniske kandidatlisten")

    for container_key in ("market_runs", "changes", "ranking_explanation"):
        for ref in _iter_candidate_references(run.get(container_key)):
            ticker = str(ref.get("ticker") or "").upper()
            canonical = by_ticker.get(ticker)
            if not canonical:
                continue
            for field in ("status", "portfolio_action", "autonomy_outcome_code"):
                if ref.get(field) is not None and canonical.get(field) is not None and str(ref.get(field)) != str(canonical.get(field)):
                    errors.append(f"{ticker}: {container_key} bruker foreldet {field}")
                    break

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        ticker = str(candidate.get("ticker") or "").upper()
        profile = candidate.get("confidence_profile") if isinstance(candidate.get("confidence_profile"), Mapping) else {}
        if _float(profile.get("documentation_coverage"), 0.0) > _float(profile.get("evidence_coverage"), 0.0) + 0.01:
            errors.append(f"{ticker}: dokumentasjonsdekning overstiger verifisert evidensdekning")
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
        news = raw.get("news_intelligence") if isinstance(raw.get("news_intelligence"), Mapping) else {}
        for event in news.get("events") or []:
            if not isinstance(event, Mapping):
                continue
            source_url = event.get("original_url") or event.get("source_url") or event.get("url") or event.get("link")
            explicit_source_field = any(key in event for key in ("original_url", "source_url", "url", "link"))
            if event.get("company_relevant") is True and explicit_source_field and not _valid_web_url(source_url):
                warnings.append(
                    f"{ticker}: nyhet uten gyldig http/https-kilde ble ekskludert fra verifisert evidens"
                )
                # En mangelfull enkeltkilde skal redusere dokumentasjonen, ikke
                # stoppe hele rapportkjeden. Bevar hendelsen for sporbarhet,
                # men gjør det eksplisitt at den ikke kan brukes som verifisert
                # beslutningsevidens.
                if isinstance(event, dict):
                    event["source_validation_status"] = "INVALID_URL"
                    event["source_usable"] = False
                    event["evidence_verified"] = False
                break

    quality_metrics = run.get("quality_metrics") if isinstance(run.get("quality_metrics"), Mapping) else {}
    for key in ("overall_report_quality", "data_coverage", "candidate_evidence_coverage_average"):
        value = _float(quality_metrics.get(key), -1.0)
        if value < 0 or value > 100:
            errors.append(f"Kvalitetsmålet {key} er utenfor 0–100")
    expected_evidence_average = round(
        sum(_candidate_evidence_coverage(row) for row in candidates if isinstance(row, Mapping))
        / max(1, sum(isinstance(row, Mapping) for row in candidates)), 2
    ) if candidates else 0.0
    if abs(_float(quality_metrics.get("candidate_evidence_coverage_average"), -1.0) - expected_evidence_average) > 0.01:
        errors.append("Gjennomsnittlig evidensdekning er koblet til feil datakilde")

    if not candidates:
        warnings.append("Rapporten har ingen kandidater")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def validate_pdf_semantics(pdf_bytes: bytes, run: Mapping[str, Any]) -> dict[str, Any]:
    """Compare load-bearing PDF text with the canonical JSON report model.

    This is deliberately narrower than a visual layout test. It verifies the
    semantic stamp, complete ranking count, report state, priority outcomes and
    evidence labels that previously diverged between PDF sections and JSON.
    """
    errors: list[str] = []
    warnings: list[str] = []
    try:
        from io import BytesIO
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception as exc:
        return {"ok": False, "errors": [f"PDF kunne ikke leses for semantisk kontroll: {exc}"], "warnings": []}
    normalized = " ".join(text.split())
    candidates = [row for row in (run.get("candidates") or []) if isinstance(row, Mapping)]
    version_stamp = f"VERSION={APP_VERSION};SCHEMA={REPORT_SCHEMA_VERSION}"
    if candidates and version_stamp not in normalized:
        errors.append("PDF-versjon og rapportskjema samsvarer ikke med kanonisk JSON")
    summary = run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
    stamp = (
        f"INTEGRITY-CANDIDATES={len(candidates)};WATCH={int(summary.get('automatic_watch') or 0)};"
        f"REJECTED={int(summary.get('automatic_rejected') or 0)};BUY={int(summary.get('buy_candidates') or 0)}"
    )
    if candidates and stamp not in normalized:
        errors.append("PDF mangler eller motsier kanonisk integritetsstempel")
    ranking_stamp = f"Rangering omfatter {len(candidates)} av {len(candidates)} kandidater."
    if candidates and not bool(run.get("analysis_aborted")) and ranking_stamp not in normalized:
        errors.append("PDF dokumenterer ikke full kandidatrangering")
    identity = run.get("report_identity") if isinstance(run.get("report_identity"), Mapping) else {}
    if str(identity.get("type") or "").upper() == "UTKAST" or str(run.get("job_id") or "").upper() == "MI-DRAFT-AUTOSAVE":
        if "UTKAST – IKKE ENDELIG" not in normalized.upper():
            errors.append("PDF viser ikke at utkastet er ikke-endelig")
        if "RAPPORTSTATUS ENDELIG" in normalized.upper():
            errors.append("PDF merker utkast som ENDELIG")
    priorities = list(run.get("priority_top3") or [])[:3]
    proposal_tickers = {str(row.get("ticker") or "").upper() for row in (run.get("proposals") or []) if isinstance(row, Mapping)}
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in candidates}
    for item in priorities:
        ticker = str(item.get("ticker") or "").upper()
        row = by_ticker.get(ticker, {})
        if not ticker or not row:
            continue
        if ticker not in normalized:
            errors.append(f"PDF mangler kanonisk prioritet for {ticker}")
        # Detailed proposal sections were the source of the AIZ/SSAB mismatch.
        # Validate outcome and evidence there; decision-only shortlists need only
        # appear in the canonical decision table.
        if ticker not in proposal_tickers:
            continue
        label = str(row.get("autonomy_outcome_label") or "")
        if label and label not in normalized:
            errors.append(f"PDF mangler kanonisk status for {ticker}")
        raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
        for area, signal_key, info_key in (
            ("insider", "insider_signal", "insider_intelligence"),
            ("news", "news_sentiment", "news_intelligence"),
        ):
            info = raw.get(info_key) if isinstance(raw.get(info_key), Mapping) else {}
            facts = int(info.get("verified_fact_count") or info.get("article_count") or 0)
            signal = str(raw.get(signal_key) or "")
            if facts > 0 and signal and signal not in normalized:
                errors.append(f"PDF mangler dokumentert {area}-signal for {ticker}")
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
    "canonical_report_view", "compact_candidate_reference", "executive_intelligence_from_candidates",
    "validate_pdf_semantics", "validate_report_integrity",
]
