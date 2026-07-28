"""Canonical report view and integrity validation for v19.14.1.

The analysis engines remain authoritative for ranking and portfolio decisions.
This module makes a completed result internally consistent before it is
serialized or rendered. It does not recalculate a production score or relax a
trading rule.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping, Sequence

REPORT_INTEGRITY_SCHEMA_VERSION = "1.4"

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
        "confidence_score", "risk_score", "data_quality", "liquidity_score", "status",
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
    result["candidates"] = canonical_candidates
    result["autonomous_decision_reduction"] = reduction
    result["manual_tasks"] = list(reduction.get("manual_tasks") or [])
    result["priority_top3"] = list(reduction.get("priority_top3") or [])
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
    "canonical_report_view", "compact_candidate_reference", "executive_intelligence_from_candidates",
    "validate_report_integrity",
]
