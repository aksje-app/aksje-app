"""Decision-report enrichment for AI Aksje Analyzer v19.0.21.

This module is deliberately read-only with respect to ranking and trading logic.
It derives explanation, reliability, validity, event and follow-up metadata from
an already completed market-intelligence run. It never changes candidate scores,
actions, portfolio weights, thresholds or autonomous execution rules.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Mapping, MutableMapping, Sequence

from local_time import DEFAULT_TIMEZONE, as_local, valid_timezone

DECISION_REPORT_SCHEMA_VERSION = "1.4"
TASK_STATUSES = ("VENTER", "PÅGÅR", "UTFØRT", "FORTSATT_PROBLEM", "IKKE_LENGER_RELEVANT")
CONSENSUS_LEVELS = ("STERK", "MODERAT", "SVAK", "MOTSTRIDENDE", "IKKE_VERIFISERT")

ACTION_LABELS_NO = {
    "BUY": "Kjøp", "HOLD": "Behold", "SELL": "Selg",
    "SKIP": "Ikke aktuell", "REVIEW": "Undersøk manuelt",
    "KJØP": "Kjøp",
}

def _action_label(value: Any) -> str:
    text = str(value or "Undersøk manuelt")
    return ACTION_LABELS_NO.get(text.upper(), text)

REPORT_FOCUS: dict[str, list[str]] = {
    "MORGENRAPPORT": [
        "Hendelser siden forrige markedsslutt",
        "USA- og Asia-utvikling før åpning",
        "Dagens resultater, makrotall og kandidatrisiko",
        "Kandidater som bør overvåkes ved børsåpning",
    ],
    "DAGSRAPPORT": [
        "Markedsbevegelser siden åpning",
        "Nye nyheter, volum- og kursutslag",
        "Kandidater som nærmer seg beslutningsterskler",
        "Endringer i risiko, likviditet og datakvalitet",
    ],
    "KVELDSRAPPORT": [
        "Hva som skjedde gjennom handelsdagen",
        "Om morgenens hypoteser ble bekreftet eller svekket",
        "Nye, forbedrede, svekkede og utgåtte kandidater",
        "Oppgaver og hendelser før neste handelsdag",
    ],
    "NATTRAPPORT": [
        "USA-avslutning og etterbørshendelser",
        "Overnight-risiko og Asia-relevante signaler",
        "Hendelser som kan påvirke neste morgenrapport",
        "Datakilder som må være klare før neste kjøring",
    ],
    "MANUELL_RAPPORT": [
        "Brukerens eksplisitte analyseoppdrag",
        "Vesentlige endringer og beslutningshindringer",
        "Datadekning og kildegrunnlag",
        "Konkrete oppfølgingspunkter",
    ],
    "UTKAST": [
        "Foreløpige funn innenfor periodeoppdraget",
        "Manglende data og kilder som må fullføres",
        "Kandidater som ikke er klare for beslutning",
        "Oppgaver før rapporten kan ferdigstilles",
    ],
}

TTL_HOURS = {
    "MORGENRAPPORT": 6,
    "DAGSRAPPORT": 4,
    "KVELDSRAPPORT": 16,
    "NATTRAPPORT": 10,
    "MANUELL_RAPPORT": 6,
    "UTKAST": 3,
    "SHADOW_VALIDATION": 3,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else default
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(text[:10], "%Y-%m-%d")
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _created_at(run: Mapping[str, Any]) -> datetime:
    return _parse_datetime(run.get("created_at")) or datetime.now(timezone.utc)


def _decision_threshold(run: Mapping[str, Any]) -> float:
    funnel = _mapping(run.get("decision_funnel"))
    portfolio = _mapping(run.get("portfolio_decisions"))
    for value in (funnel.get("production_threshold"), portfolio.get("production_threshold")):
        if value is not None:
            return _safe_float(value, 78.0)
    return 78.0


def _risk_limit(run: Mapping[str, Any]) -> float:
    funnel = _mapping(run.get("decision_funnel"))
    params = _mapping(funnel.get("parameters"))
    for value in (params.get("max_risk"), funnel.get("max_risk"), 65.0):
        if value is not None:
            return _safe_float(value, 65.0)
    return 65.0


def _canonical_source_name(row: Mapping[str, Any]) -> str:
    """Return the root publisher in a publication chain, not its aggregator."""
    for key in ("original_publisher", "publisher", "source", "provider"):
        value = str(row.get(key) or "").strip()
        if value and value.casefold() not in {
            "unavailable", "ikke oppgitt", "none", "kontrollerte offentlige kilder"
        }:
            return value
    return ""


def _source_names(payload: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, Any]]) -> set[str]:
    """Count independent supporting roots only.

    Attempted sources, sources without results, configured-but-unchecked primary
    sources and aggregator hops are not independent evidence.
    """
    names: set[str] = set()
    evidence_has_root = False
    for row in evidence_rows:
        value = _canonical_source_name(row)
        if value:
            names.add(value)
            evidence_has_root = True
    for row in _rows(payload.get("search_log")):
        status = str(row.get("status") or "").upper()
        if not row.get("attempted") or _safe_int(row.get("results"), 0) <= 0:
            continue
        if not status.startswith("SUCCESS"):
            continue
        source_type = str(row.get("source_type") or "").upper()
        # Aggregators distribute evidence; they are not an additional source
        # when the published item already identifies its root publisher.
        if evidence_has_root and any(token in source_type for token in ("AGGREGATOR", "DISCOVERY")):
            continue
        value = _canonical_source_name(row)
        if value:
            names.add(value)
    return names


def _primary_source_present(payload: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, Any]]) -> bool:
    primary_tokens = {"OFFICIAL", "EXCHANGE", "REGULATOR", "COMPANY_IR", "PRIMARY_SOURCE", "SEC_FILING", "BØRSMELDING", "PRIMARY_OR_DIRECT"}
    for row in evidence_rows:
        source_type = str(row.get("source_type") or row.get("type") or "").upper()
        role = str(row.get("source_role") or "").upper()
        if any(token in source_type or token in role for token in primary_tokens):
            return True
    for row in _rows(payload.get("search_log")):
        status = str(row.get("status") or "").upper()
        if not row.get("attempted") or _safe_int(row.get("results"), 0) <= 0 or not status.startswith("SUCCESS"):
            continue
        source_type = str(row.get("source_type") or row.get("type") or "").upper()
        role = str(row.get("source_role") or "").upper()
        if any(token in source_type or token in role for token in primary_tokens):
            return True
    return False


def _sponsored_count(payload: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    tokens = ("SPONSORED", "BRANDED", "PROMOTED", "PUBLieditorial".upper(), "CONTEÚDO DE MARCA")
    for row in evidence_rows:
        text = " ".join(str(row.get(k) or "") for k in ("article_type", "classification", "title", "source_role")).upper()
        if any(token in text for token in tokens):
            count += 1
    return count


def candidate_source_consensus(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Describe source agreement without changing evidence or candidate status."""
    raw = _mapping(candidate.get("raw"))
    readiness = _mapping(candidate.get("decision_readiness"))
    all_sources: set[str] = set()
    verified_facts = 0
    primary = False
    sponsored = 0
    attempted = 0
    successful = 0
    areas: dict[str, Any] = {}
    conflicts = _safe_int(readiness.get("conflicts"), 0)

    from evidence_contract import normalize_search_payload

    for area, key, evidence_key in (
        ("news", "news_intelligence", "events"),
        ("insider", "insider_intelligence", "evidence"),
    ):
        payload = normalize_search_payload(_mapping(raw.get(key)), area=area)
        evidence = _rows(payload.get(evidence_key))
        search_log = _rows(payload.get("search_log"))
        names = _source_names(payload, evidence)
        all_sources.update(names)
        verified_facts += len(evidence)
        primary = primary or _primary_source_present(payload, evidence)
        sponsored += _sponsored_count(payload, evidence)
        attempted += sum(1 for row in search_log if row.get("attempted"))
        successful += sum(1 for row in search_log if str(row.get("status") or "").upper().startswith("SUCCESS"))
        area_status = str(readiness.get(area) or payload.get("coverage") or payload.get("status") or "NOT_SEARCHED").upper()
        area_conflicts = _safe_int(_mapping(readiness.get("records")).get(area, {}).get("conflicts"), 0) if isinstance(_mapping(readiness.get("records")).get(area), Mapping) else 0
        conflicts += area_conflicts
        areas[area] = {
            "status": area_status,
            "search_status": payload.get("search_status") or "NOT_SEARCHED_POLICY",
            "search_reason_counts": dict(payload.get("search_reason_counts") or {}),
            "search_unknown_reason_count": int(payload.get("search_unknown_reason_count") or 0),
            "verified_facts": len(evidence),
            "sources": sorted(names),
            "attempted": sum(1 for row in search_log if row.get("attempted")),
        }

    # RC8: the claim ledger is the canonical source-count contract.  It counts
    # original publishers behind verified claims, not distribution domains or
    # merely attempted search endpoints.  Prefer it whenever available so the
    # overview and detailed transparency table cannot disagree.
    transparency = _mapping(candidate.get("analysis_transparency"))
    claim_ledger = _mapping(transparency.get("claim_ledger"))
    ledger_independent_count: int | None = None
    if claim_ledger:
        ledger_sources = {
            str(value).strip()
            for value in (claim_ledger.get("independent_sources") or [])
            if str(value).strip()
        }
        ledger_independent_count = _safe_int(
            claim_ledger.get("independent_source_count"),
            len(ledger_sources),
        )
        all_sources = ledger_sources
        verified_facts = _safe_int(
            claim_ledger.get("claim_count", claim_ledger.get("verified_claim_count")),
            verified_facts,
        )
        primary = bool(claim_ledger.get("primary_source_fact_areas"))

    independent = ledger_independent_count if ledger_independent_count is not None else len(all_sources)
    if conflicts > 0:
        level = "MOTSTRIDENDE"
    elif independent >= 3 and (primary or verified_facts >= 3):
        level = "STERK"
    elif independent >= 2 and verified_facts >= 1:
        level = "MODERAT"
    elif independent >= 1 or verified_facts >= 1 or successful >= 1:
        level = "SVAK"
    else:
        level = "IKKE_VERIFISERT"

    score_map = {"STERK": 90, "MODERAT": 75, "SVAK": 55, "MOTSTRIDENDE": 30, "IKKE_VERIFISERT": 20}
    explanation_parts = [f"{independent} uavhengig(e) kilde(r)", f"{verified_facts} verifisert(e) fakta"]
    explanation_parts.append("primærkilde funnet" if primary else "ingen tydelig primærkilde")
    if conflicts:
        explanation_parts.append(f"{conflicts} konflikt(er)")
    if sponsored:
        explanation_parts.append(f"{sponsored} kommersiell(e) sak(er) er ikke brukt som ordinært bevis")
    return {
        "level": level,
        "score": score_map[level],
        "independent_sources": independent,
        "sources": sorted(all_sources),
        "verified_facts": verified_facts,
        "primary_source_present": primary,
        "conflicts": conflicts,
        "sponsored_items": sponsored,
        "sources_attempted": attempted,
        "successful_source_attempts": successful,
        "areas": areas,
        "source_count_basis": "original_publisher_verified_claims" if claim_ledger else "available_source_names",
        "source_count_consistent": True,
        "explanation": "; ".join(explanation_parts),
    }


def candidate_confidence_profile(candidate: Mapping[str, Any], consensus: Mapping[str, Any]) -> dict[str, Any]:
    contract = _mapping(candidate.get("data_contract"))
    readiness = _mapping(candidate.get("decision_readiness"))
    validity = str(contract.get("validity") or "").upper()
    source = str(contract.get("source") or "").upper()

    completeness = _safe_float(candidate.get("data_completeness"), -1.0)
    if completeness < 0:
        completeness = _safe_float(contract.get("completeness"), -1.0)
    if 0 <= completeness <= 1:
        completeness *= 100
    if completeness < 0:
        completeness = 100.0 if validity in {"VALID", "GYLDIG"} else 65.0 if validity else 50.0
    documentation_coverage = max(0, min(100, round(completeness)))
    if validity and validity not in {"VALID", "GYLDIG"}:
        documentation_coverage = min(documentation_coverage, 60)
    if source in {"CACHE", "FALLBACK"}:
        documentation_coverage = min(documentation_coverage, 75)

    market_data_coverage = _safe_float(candidate.get("data_quality"), -1.0)
    if market_data_coverage < 0:
        market_data_coverage = _safe_float(contract.get("quality_score"), -1.0)
    if market_data_coverage < 0:
        market_data_coverage = 100.0 if validity in {"VALID", "GYLDIG"} else 0.0
    market_data_coverage = max(0, min(100, round(market_data_coverage)))

    source_confidence = _safe_int(consensus.get("score"), 20)
    legacy_profile = _mapping(candidate.get("confidence_profile"))
    raw_model_confidence = max(0, min(100, round(_safe_float(
        legacy_profile.get("model_confidence"), candidate.get("confidence_before_evidence_policy", candidate.get("confidence_score", 0.0))
    ))))
    evidence_adjusted_confidence = max(0, min(100, round(_safe_float(
        legacy_profile.get("evidence_adjusted_model_confidence", legacy_profile.get("calibrated_confidence")),
        candidate.get("evidence_adjusted_model_confidence", candidate.get("confidence_score", raw_model_confidence)),
    ))))
    evidence_coverage = max(0, min(100, round(_safe_float(
        legacy_profile.get("evidence_coverage", legacy_profile.get("data_coverage")),
        100.0 if candidate.get("evidence_valid_for_decision") else 0.0,
    ))))
    evidence_data_ready = bool(candidate.get("valid_for_decision") and candidate.get("evidence_valid_for_decision", True))
    final_action = str(candidate.get("portfolio_action") or readiness.get("final_action") or "").upper()
    final_decision_ready = bool(evidence_data_ready and final_action in {"BUY", "KJØP"})
    allowed = str(readiness.get("allowed_action") or final_action).upper()
    combined_coverage = round((documentation_coverage + market_data_coverage) / 2)
    if evidence_data_ready:
        decision_confidence = min(100, round((evidence_adjusted_confidence * 0.50) + (combined_coverage * 0.30) + (source_confidence * 0.20)))
    else:
        decision_confidence = min(69, round((evidence_adjusted_confidence * 0.42) + (combined_coverage * 0.33) + (source_confidence * 0.25)))
    if allowed in {"SKIP", "SELL"}:
        decision_confidence = min(decision_confidence, 65)
    return {
        # Legacy alias kept for report-schema compatibility. It means analysis/
        # documentation coverage, not market-price coverage.
        "data_coverage": documentation_coverage,
        "documentation_coverage": documentation_coverage,
        "market_data_coverage": market_data_coverage,
        "source_confidence": source_confidence,
        "decision_confidence": max(0, min(100, decision_confidence)),
        "model_confidence": raw_model_confidence,
        "evidence_adjusted_model_confidence": evidence_adjusted_confidence,
        "evidence_coverage": evidence_coverage,
        "evidence_data_ready": evidence_data_ready,
        "final_decision_ready": final_decision_ready,
        "decision_ready": final_decision_ready,
        "note": "Målene beskriver markedsdata, dokumentasjon og beslutningsporter – ikke sannsynlighet for gevinst.",
    }


def candidate_blockers_and_triggers(candidate: Mapping[str, Any], run: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    threshold = _decision_threshold(run)
    risk_limit = _risk_limit(run)
    score = _safe_float(candidate.get("investment_score"), 0.0)
    risk = _safe_float(candidate.get("risk_score"), 0.0)
    readiness = _mapping(candidate.get("decision_readiness"))
    contract = _mapping(candidate.get("data_contract"))
    action = str(readiness.get("allowed_action") or candidate.get("portfolio_action") or "REVIEW").upper()
    blockers: list[str] = []
    triggers: list[str] = []

    if score < threshold:
        blockers.append(f"Score {score:.1f} er {threshold - score:.1f} poeng under beslutningsterskel {threshold:.1f}")
        triggers.append(f"Samlet score må nå minst {threshold:.1f}")
    if risk > risk_limit:
        blockers.append(f"Risiko {risk:.1f} er over tillatt nivå {risk_limit:.1f}")
        triggers.append(f"Risiko må falle til {risk_limit:.1f} eller lavere")
    validity = str(contract.get("validity") or "").upper()
    if validity and validity not in {"VALID", "GYLDIG"}:
        blockers.append("Markedsdata oppfyller ikke full beslutningskvalitet")
        triggers.append("Datakontrakten må bli gyldig med ferske markedsdata")
    news_status = str(readiness.get("news") or "").upper()
    insider_status = str(readiness.get("insider") or "").upper()
    valid_evidence = {"VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "AVAILABLE", ""}
    if news_status not in valid_evidence:
        blockers.append("Nyhetsgrunnlaget er ikke ferdig verifisert")
        triggers.append("Nyhetsgrunnlaget må verifiseres eller dokumenteres uten vesentlige hendelser")
    if insider_status not in valid_evidence:
        blockers.append("Insidergrunnlaget er ikke ferdig verifisert")
        triggers.append("Insidergrunnlaget må verifiseres eller dokumenteres uten rapporterbare hendelser")
    conflicts = _safe_int(readiness.get("conflicts"), 0)
    if conflicts:
        blockers.append(f"{conflicts} kildekonflikt(er) må avklares")
        triggers.append("Motstridende kilder må avklares med en sterkere eller primær kilde")
    outcome = str(candidate.get("autonomy_outcome_code") or "").upper()
    if action not in {"BUY", "KJØP"} and not blockers:
        if outcome == "OVERVÅKES_AUTOMATISK":
            blockers.append("Kandidaten er satt til automatisk overvåking; ingen manuell handling er nødvendig nå")
            triggers.append(str(candidate.get("automatic_next_action") or "Programmet prøver på nytt når nye data eller hendelser foreligger"))
        elif outcome == "AUTOMATISK_AVVIST":
            blockers.append("Kandidaten er automatisk avvist etter gjeldende score-, risiko- og dokumentasjonsregler")
            triggers.append("Kandidaten vurderes på nytt automatisk dersom score, risiko eller dokumentasjon endres vesentlig")
        elif outcome == "UNDERSØK_MANUELT":
            blockers.append("Én konkret kritisk opplysning må undersøkes manuelt før kandidaten kan avklares")
            triggers.append("Den beskrevne manuelle oppgaven må avklares uten at produksjonsreglene endres")
        else:
            blockers.append("Porteføljelaget kjøpsgodkjenner ikke kandidaten")
            triggers.append("Alle produksjonsporter må godkjenne Kjøp uten at risikoreglene endres")
    if not blockers:
        blockers.append("Ingen eksplisitt blokkering; vurderingen er klar innenfor gjeldende regler")
    if not triggers:
        triggers.append("Ny vurdering kreves ved vesentlig kurs-, risiko-, kilde- eller hendelsesendring")
    return blockers[:5], triggers[:5]


def candidate_validity(candidate: Mapping[str, Any], run: Mapping[str, Any], report_type: str) -> dict[str, Any]:
    created = _created_at(run)
    ttl = TTL_HOURS.get(report_type, 6)
    valid_until = created + timedelta(hours=ttl)
    raw = _mapping(candidate.get("raw"))
    price = 0.0
    for value in (
        candidate.get("current_price"), candidate.get("price"), raw.get("current_price"),
        raw.get("price"), raw.get("last_price"), raw.get("market_price"),
    ):
        if _safe_float(value, 0.0) > 0:
            price = _safe_float(value)
            break
    price_range: dict[str, Any] = {}
    if price > 0:
        price_range = {
            "reference": round(price, 4),
            "minimum": round(price * 0.97, 4),
            "maximum": round(price * 1.03, 4),
            "basis": "Forklaringsområde ±3 % rundt analysekurs; dette er ikke en ordregrense.",
        }
    invalidators = [
        "Ny vesentlig selskaps-, regulatorisk eller makrohendelse",
        "Ny insidertransaksjon eller motstridende kildebevis",
        "Markedsdata som blir eldre enn datakontraktens grense",
    ]
    if price_range:
        invalidators.append("Kurs utenfor det oppgitte forklaringsområdet")
    return {
        "valid_from": created.isoformat(timespec="seconds"),
        "valid_until": valid_until.isoformat(timespec="seconds"),
        "ttl_hours": ttl,
        "price_range": price_range,
        "invalidated_by": invalidators,
        "status": "GYLDIG_VED_GENERERING",
    }


def build_candidate_decision_contract(candidate: Mapping[str, Any], run: Mapping[str, Any], report_type: str) -> dict[str, Any]:
    consensus = candidate_source_consensus(candidate)
    confidence = candidate_confidence_profile(candidate, consensus)
    blockers, triggers = candidate_blockers_and_triggers(candidate, run)
    outcome_code = str(candidate.get("autonomy_outcome_code") or candidate.get("portfolio_action") or candidate.get("status") or "REVIEW")
    return {
        "ticker": str(candidate.get("ticker") or ""),
        "action": outcome_code,
        "action_label": str(candidate.get("autonomy_outcome_label") or _action_label(outcome_code)),
        "score": candidate.get("investment_score"),
        "blockers": blockers,
        "change_conditions": triggers,
        "validity": candidate_validity(candidate, run, report_type),
        "source_consensus": consensus,
        "confidence": confidence,
        "manual_review_required": bool(candidate.get("manual_review_required")),
        "manual_tasks": deepcopy(list(candidate.get("manual_tasks") or [])),
        "automatic_next_action": str(candidate.get("automatic_next_action") or ""),
        "analysis_transparency": deepcopy(_mapping(candidate.get("analysis_transparency"))),
    }


def _candidate_by_ticker(run: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(row.get("ticker") or "").upper(): row for row in _rows(run.get("candidates")) if row.get("ticker")}


def build_change_summary(run: Mapping[str, Any], previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
    changes = _mapping(run.get("changes") or run.get("change_since_previous"))
    new_rows = _rows(changes.get("new"))
    improved = _rows(changes.get("improved"))
    weakened = _rows(changes.get("weakened"))
    dropped = _rows(changes.get("dropped"))
    has_previous = bool(
        previous
        or _mapping(run.get("report_revision")).get("supersedes_run_id")
        or _mapping(run.get("report_document")).get("metadata", {}).get("previous_report_id")
    )
    current_top = [str(row.get("ticker") or "") for row in _rows(run.get("candidates"))[:3]]
    previous_top = [str(row.get("ticker") or "") for row in _rows((previous or {}).get("candidates"))[:3]]
    top_added = [ticker for ticker in current_top if ticker and ticker not in previous_top] if has_previous else []
    top_removed = [ticker for ticker in previous_top if ticker and ticker not in current_top] if has_previous else []
    largest_improvement = max(improved, key=lambda row: _safe_float(row.get("score_delta")), default={})
    largest_weakening = min(weakened, key=lambda row: _safe_float(row.get("score_delta")), default={})
    action_changes: list[dict[str, Any]] = []
    previous_map = _candidate_by_ticker(previous or {})
    for row in _rows(run.get("candidates")):
        ticker = str(row.get("ticker") or "").upper()
        old = previous_map.get(ticker)
        if not old:
            continue
        old_action = str(old.get("portfolio_action") or old.get("status") or "")
        new_action = str(row.get("portfolio_action") or row.get("status") or "")
        if old_action != new_action:
            action_changes.append({"ticker": ticker, "from": old_action, "to": new_action})
    return {
        "has_previous": has_previous,
        "top3_added": top_added,
        "top3_removed": top_removed,
        "new": [{"ticker": row.get("ticker"), "score": row.get("investment_score")} for row in new_rows[:10]],
        "improved": [{"ticker": row.get("ticker"), "delta": row.get("score_delta")} for row in improved[:10]],
        "weakened": [{"ticker": row.get("ticker"), "delta": row.get("score_delta")} for row in weakened[:10]],
        "dropped": [{"ticker": row.get("ticker"), "score": row.get("investment_score")} for row in dropped[:10]],
        "largest_improvement": {
            "ticker": largest_improvement.get("ticker"), "delta": largest_improvement.get("score_delta"),
        } if largest_improvement else {},
        "largest_weakening": {
            "ticker": largest_weakening.get("ticker"), "delta": largest_weakening.get("score_delta"),
        } if largest_weakening else {},
        "action_changes": action_changes[:10],
        "unchanged_count": _safe_int(changes.get("unchanged_count"), 0),
        "top3_changed": bool(top_added or top_removed),
    }


def _event_date_and_title(candidate: Mapping[str, Any]) -> tuple[str, str, str]:
    raw = _mapping(candidate.get("raw"))
    ticker = str(candidate.get("ticker") or "")
    candidates = [
        (raw.get("earnings_date"), "Resultatpublisering", "BEKREFTET"),
        (raw.get("next_event"), "Kommende selskapshendelse", "ESTIMERT"),
        (raw.get("next_expected_event"), "Forventet selskapshendelse", "ESTIMERT"),
        (candidate.get("earnings_date"), "Resultatpublisering", "BEKREFTET"),
    ]
    for value, title, status in candidates:
        if not value:
            continue
        if isinstance(value, Mapping):
            date_value = value.get("date") or value.get("at") or value.get("event_date")
            title_value = value.get("title") or value.get("name") or title
            if date_value:
                return str(date_value), str(title_value), status
        text = str(value)
        if _parse_datetime(text):
            return text, title, status
    event_risk = _mapping(raw.get("event_risk"))
    diagnostics = _mapping(event_risk.get("diagnostics"))
    earnings = _mapping(diagnostics.get("earnings"))
    if earnings.get("date"):
        return str(earnings.get("date")), "Resultatpublisering", "BEKREFTET"
    return "", "", ""


def build_event_calendar(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    timezone_name = valid_timezone(run.get("timezone_name") or DEFAULT_TIMEZONE)
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in _rows(run.get("critical_events")):
        ticker = str(row.get("ticker") or "")
        event_at = str(row.get("event_at") or row.get("date") or row.get("at") or row.get("event_date") or "")
        title = str(row.get("title") or row.get("name") or row.get("message") or "Kritisk hendelse")
        key = (ticker, event_at, title)
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "ticker": ticker,
            "event_at": event_at,
            "event_at_local": str(row.get("event_at_local") or (as_local(_parse_datetime(event_at), timezone_name).isoformat(timespec="minutes") if _parse_datetime(event_at) else event_at)),
            "title": title,
            "importance": str(row.get("importance") or row.get("impact") or "HØY").upper(),
            "source": str(row.get("source") or "Rapportdata"),
            "verification": str(row.get("verification") or "BEKREFTET").upper(),
        })
    for candidate in _rows(run.get("candidates")):
        event_at, title, verification = _event_date_and_title(candidate)
        if not event_at:
            continue
        ticker = str(candidate.get("ticker") or "")
        key = (ticker, event_at, title)
        if key in seen:
            continue
        seen.add(key)
        dt = _parse_datetime(event_at)
        events.append({
            "ticker": ticker,
            "event_at": event_at,
            "event_at_local": as_local(dt, timezone_name).isoformat(timespec="minutes") if dt else event_at,
            "title": title,
            "importance": "HØY",
            "source": "Kandidatdata",
            "verification": verification,
        })
    def sort_key(row: Mapping[str, Any]) -> tuple[int, str]:
        dt = _parse_datetime(row.get("event_at"))
        return (0 if dt else 1, dt.isoformat() if dt else str(row.get("event_at") or "9999"))
    return sorted(events, key=sort_key)[:20]


def build_report_confidence(run: Mapping[str, Any], candidate_contracts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    profiles = [_mapping(row.get("confidence")) for row in candidate_contracts]
    if profiles:
        documentation = round(sum(_safe_float(row.get("documentation_coverage", row.get("data_coverage"))) for row in profiles) / len(profiles))
        market_data = round(sum(_safe_float(row.get("market_data_coverage")) for row in profiles) / len(profiles))
        sources = round(sum(_safe_float(row.get("source_confidence")) for row in profiles) / len(profiles))
        decision = round(sum(_safe_float(row.get("decision_confidence")) for row in profiles) / len(profiles))
    else:
        quality = _mapping(run.get("data_quality"))
        documentation = 0
        market_data = round(_safe_float(quality.get("score"), 0))
        sources = 0
        decision = 0
    return {
        # Legacy alias: documentation/analysis coverage, never price-data coverage.
        "data_coverage": max(0, min(100, documentation)),
        "documentation_coverage": max(0, min(100, documentation)),
        "market_data_coverage": max(0, min(100, market_data)),
        "source_confidence": max(0, min(100, sources)),
        "decision_confidence": max(0, min(100, decision)),
        "candidate_count": len(profiles),
        "interpretation": {
            "documentation_coverage": "Er analyse- og kildedokumentasjonen tilstrekkelig?",
            "market_data_coverage": "Er markedsdataene ferske og gyldige?",
            "source_confidence": "Er vesentlige påstander verifisert av gode og uavhengige kilder?",
            "decision_confidence": "Oppfyller kandidatene gjeldende handlings- og risikoregler?",
        },
        "warning": "Verdiene er ikke sannsynlighet for fremtidig avkastning.",
    }


def build_report_reliability(run: Mapping[str, Any], candidate_contracts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    score = 100
    deductions: list[dict[str, Any]] = []

    def deduct(points: int, code: str, reason: str) -> None:
        nonlocal score
        points = max(0, int(points))
        if not points:
            return
        score -= points
        deductions.append({"points": points, "code": code, "reason": reason})

    data_quality = _safe_float(_mapping(run.get("data_quality")).get("score"), 100.0)
    if data_quality < 95:
        deduct(min(20, round((95 - data_quality) * 0.35)), "DATA_QUALITY", f"Markedsdatakvalitet er {data_quality:.0f}/100")
    combined = _mapping(run.get("combined_data_quality") or run.get("combined_quality"))
    evaluated = _safe_int(combined.get("evaluated"), 0)
    valid = _safe_int(combined.get("overall_valid"), 0)
    if combined and evaluated and valid < evaluated:
        deduct(min(20, round(20 * (evaluated - valid) / evaluated)), "EVIDENCE_COVERAGE", f"Bare {valid} av {evaluated} kandidater har samlet gyldig evidens")
    conflicts = sum(_safe_int(_mapping(row.get("source_consensus")).get("conflicts"), 0) for row in candidate_contracts)
    if conflicts:
        deduct(min(12, conflicts * 4), "SOURCE_CONFLICTS", f"{conflicts} kildekonflikt(er) er ikke avklart")
    weak_sources = sum(1 for row in candidate_contracts if str(_mapping(row.get("source_consensus")).get("level")) in {"SVAK", "IKKE_VERIFISERT"})
    if weak_sources:
        deduct(min(12, weak_sources * 2), "WEAK_CONSENSUS", f"{weak_sources} kandidat(er) har svakt eller uverifisert kildegrunnlag")
    missing_insider = 0
    for candidate in _rows(run.get("candidates")):
        readiness = _mapping(candidate.get("decision_readiness"))
        if str(readiness.get("insider") or "").upper() not in {"", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "AVAILABLE"}:
            missing_insider += 1
    if missing_insider:
        deduct(min(12, missing_insider * 2), "INSIDER_GAPS", f"Insidergrunnlaget er ufullstendig for {missing_insider} kandidat(er)")
    source_health = _mapping(run.get("source_health"))
    fallback_count = 0
    source_errors = 0
    for row in _rows(source_health.get("sources")):
        fallback_count += _safe_int(row.get("fallback_used"), 0)
        source_errors += _safe_int(row.get("errors"), 0)
    # Raw search logs retain fallback metadata even when aggregated health does not.
    for candidate in _rows(run.get("candidates")):
        raw = _mapping(candidate.get("raw"))
        for key in ("news_intelligence", "insider_intelligence"):
            for item in _rows(_mapping(raw.get(key)).get("search_log")):
                fallback_count += 1 if item.get("fallback_used") else 0
    if fallback_count:
        deduct(min(8, fallback_count), "FALLBACK_SOURCE", f"Reserve-feed eller kontrollert fallback ble brukt {fallback_count} gang(er)")
    if source_errors:
        deduct(min(12, source_errors * 2), "SOURCE_ERRORS", f"Kildeinnhentingen registrerte {source_errors} feil")
    errors = len(list(run.get("errors") or []))
    warnings = len(list(run.get("warnings") or []))
    if errors:
        deduct(min(16, errors * 4), "RUN_ERRORS", f"Kjøringen registrerte {errors} feil")
    if warnings:
        deduct(min(5, warnings), "RUN_WARNINGS", f"Kjøringen registrerte {warnings} advarsel/advarsler")
    if run.get("analysis_aborted"):
        deduct(25, "ANALYSIS_ABORTED", "Analysen ble avbrutt før fullføring")
    if run.get("partial_market_failure"):
        deduct(10, "PARTIAL_MARKET_FAILURE", "Ett eller flere valgte markeder feilet")
    status = _mapping(run.get("report_status"))
    if str(status.get("state") or "").upper() == "PROVISIONAL":
        deduct(8, "PROVISIONAL", "Rapporten er foreløpig og krever revalidering")

    score = max(0, min(100, score))
    label = "HØY" if score >= 85 else "MIDDELS" if score >= 65 else "LAV"
    return {
        # Compatibility only.  New UI/PDF must use the separate quality
        # dimensions below and must not present this as one reliability score.
        "score": score,
        "legacy_score": score,
        "label": label,
        "deprecated": True,
        "display": False,
        "replacement_fields": [
            "market_data_quality", "technical_documentation_coverage",
            "candidate_evidence_coverage", "independent_source_coverage",
            "report_decision_strength",
        ],
        "deductions": sorted(deductions, key=lambda row: row["points"], reverse=True),
        "basis": "Utfaset kompatibilitetsberegning. Vis separate kvalitetsmål i stedet.",
        "not_investment_probability": True,
    }


def _task_id(kind: str, subject: str, reason: str) -> str:
    digest = sha256(f"{kind}|{subject}|{reason}".encode("utf-8")).hexdigest()[:10].upper()
    return f"TASK-{digest}"


def build_next_run_tasks(
    run: Mapping[str, Any],
    candidate_contracts: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    created = _created_at(run).isoformat(timespec="seconds")

    def add(kind: str, subject: str, reason: str, action: str, priority: str = "NORMAL") -> None:
        task = {
            "task_id": _task_id(kind, subject, reason),
            "kind": kind,
            "subject": subject,
            "reason": reason,
            "action": action,
            "priority": priority,
            "status": "VENTER",
            "created_at": created,
            "source_report_id": str(run.get("run_id") or ""),
            "result": "",
        }
        if not any(row["task_id"] == task["task_id"] for row in tasks):
            tasks.append(task)

    for error in list(run.get("errors") or [])[:5]:
        add("RUN_ERROR", "Rapportkjøring", str(error), "Kjør berørt trinn på nytt og bekreft at feilen er borte", "KRITISK")
    explicit_manual_tickers: set[str] = set()
    for manual in list(run.get("manual_tasks") or [])[:2]:
        if not isinstance(manual, Mapping):
            continue
        ticker = str(manual.get("ticker") or "Ukjent")
        explicit_manual_tickers.add(ticker.upper())
        reason = f"{manual.get('why') or ''} Programmet stoppet fordi: {manual.get('failure_reason') or '-'}"
        action = (
            f"{manual.get('title') or 'Undersøk konkret opplysning'}. "
            f"Bruk foreslått kilde: {manual.get('suggested_source') or 'primærkilde'}. "
            f"Beslutningseffekt: {manual.get('decision_impact') or '-'}"
        )
        add("MANUAL_INVESTIGATION", ticker, reason, action, "HØY")
    for row in candidate_contracts[:10]:
        ticker = str(row.get("ticker") or "Ukjent")
        confidence = _mapping(row.get("confidence"))
        consensus = _mapping(row.get("source_consensus"))
        blockers = list(row.get("blockers") or [])
        score = _safe_float(row.get("score"), 0)
        gap = max(0.0, _decision_threshold(run) - score)
        if 0 < gap <= 3:
            add("NEAR_THRESHOLD", ticker, f"Kandidaten er {gap:.1f} poeng under beslutningsterskelen", "Reevaluer kandidaten med ferske data ved neste kjøring", "HØY")
        if _safe_int(confidence.get("market_data_coverage"), 0) < 70 and ticker.upper() not in explicit_manual_tickers:
            add("AUTO_REFRESH_MARKET_DATA", ticker, f"Markedsdatakvalitet er {confidence.get('market_data_coverage', 0)}/100", "Programmet henter ferske markedsdata automatisk ved neste kjøring", "NORMAL")
        # Weak documentation is not automatically a user task.  It becomes
        # manual only when decision reduction emitted a concrete task above.
        if str(consensus.get("level")) in {"SVAK", "MOTSTRIDENDE", "IKKE_VERIFISERT"} and ticker.upper() not in explicit_manual_tickers:
            add("AUTO_RETRY_SOURCES", ticker, consensus.get("explanation") or "Svakt kildegrunnlag", "Programmet prøver primær- og reservekilder på nytt automatisk", "NORMAL")
    source_health = _mapping(run.get("source_health"))
    for row in _rows(source_health.get("sources")):
        if _safe_int(row.get("errors"), 0) > 0 or row.get("fallback_used"):
            source = str(row.get("source") or "Ukjent kilde")
            reason = f"Feil: {row.get('errors', 0)}; reserve-feed: {'ja' if row.get('fallback_used') else 'nei'}"
            add("SOURCE_HEALTH", source, reason, "Kontroller primærfeed og parser før neste rapport", "HØY")
    handoff = _mapping(run.get("autonomy_candidate_handoff"))
    if handoff.get("mismatch"):
        add("AUTONOMY_HANDOFF", "Autonomi", str(handoff.get("warning") or "Kandidatantall avviker"), "Sammenlign rapportkandidater med kandidater mottatt av Autonomi", "KRITISK")
    evidence_ready_count = sum(1 for row in candidate_contracts if _mapping(row.get("confidence")).get("evidence_data_ready"))
    final_ready_count = sum(1 for row in candidate_contracts if _mapping(row.get("confidence")).get("final_decision_ready"))
    if evidence_ready_count < 3:
        add("AUTO_EVIDENCE_COVERAGE", "Evidensdekning", f"Bare {evidence_ready_count} kandidat(er) bestod data- og evidensporten", "Programmet prioriterer nye kildeforsøk for de høyest rangerte kandidatene ved neste kjøring", "NORMAL")
    if evidence_ready_count and final_ready_count == 0:
        add("AUTO_FINAL_GATE", "Endelig beslutningsport", "Ingen evidens- og dataklar kandidat er kjøpsgodkjent", "Programmet overvåker portefølje- og risikokapasitet automatisk", "NORMAL")
    now = _created_at(run)
    for event in events[:5]:
        dt = _parse_datetime(event.get("event_at"))
        if dt and now <= dt <= now + timedelta(days=3):
            ticker = str(event.get("ticker") or "Marked")
            add("UPCOMING_EVENT", ticker, str(event.get("title") or "Kommende hendelse"), "Reevaluer kandidaten etter hendelsen eller når nye fakta foreligger", "HØY")
    return sorted(tasks, key=lambda row: ({"KRITISK": 0, "HØY": 1, "NORMAL": 2}.get(str(row.get("priority")), 3), str(row.get("subject"))))[:25]


def build_decision_overview(
    run: Mapping[str, Any],
    identity: Mapping[str, Any],
    candidate_contracts: Sequence[Mapping[str, Any]],
    change_summary: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    confidence: Mapping[str, Any],
    reliability: Mapping[str, Any],
) -> dict[str, Any]:
    actions: dict[str, int] = {}
    for row in candidate_contracts:
        action = str(row.get("action") or "REVIEW").upper()
        actions[action] = actions.get(action, 0) + 1
    urgent_tasks = sum(1 for row in tasks if str(row.get("priority")) in {"KRITISK", "HØY"})
    summary = _mapping(run.get("report_summary"))
    strict_buys = int(_mapping(run.get("autonomous_decision_reduction")).get("buy_candidates") or 0)
    moderate_buys = int(summary.get("moderate_buy_recommendations") or 0)
    return {
        "report_type": identity.get("type"),
        "mission_label": identity.get("mission_label"),
        "mission_objective": identity.get("mission_objective"),
        "focus": REPORT_FOCUS.get(str(identity.get("type") or ""), REPORT_FOCUS["MANUELL_RAPPORT"]),
        "actions": actions,
        "candidate_count": len(candidate_contracts),
        "evidence_data_ready_count": sum(1 for row in candidate_contracts if _mapping(row.get("confidence")).get("evidence_data_ready")),
        "decision_ready_count": sum(1 for row in candidate_contracts if _mapping(row.get("confidence")).get("final_decision_ready")),
        "top3_changed": bool(change_summary.get("top3_changed")),
        "urgent_task_count": urgent_tasks,
        "upcoming_event_count": len(events),
        "confidence": dict(confidence),
        "reliability": dict(reliability),
        "conclusion": (
            f"{strict_buys} strengt kjøpsgodkjent(e), {moderate_buys} moderat kjøpsanbefalt(e), "
            f"{int(_mapping(run.get('autonomous_decision_reduction')).get('automatic_watch') or 0)} overvåkes automatisk, "
            f"{int(_mapping(run.get('autonomous_decision_reduction')).get('automatic_rejected') or 0)} er automatisk avvist, "
            f"og {int(_mapping(run.get('autonomous_decision_reduction')).get('manual_task_count') or 0)} konkret(e) manuell(e) oppgave(r) er opprettet."
        ),
    }


def build_decision_report(
    run: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    report_type = str(identity.get("type") or "MANUELL_RAPPORT").upper()
    candidate_contracts = [build_candidate_decision_contract(row, run, report_type) for row in _rows(run.get("candidates"))]
    existing = _mapping(run.get("decision_report"))
    existing_changes = _mapping(existing.get("changes"))
    changes = deepcopy(existing_changes) if previous is None and existing_changes else build_change_summary(run, previous)

    # v19.3.0: derive read-only decision intelligence from already calculated
    # results. No score, action, threshold, risk limit or portfolio field is changed.
    from decision_intelligence import (
        build_decision_diffs,
        build_historical_evaluations,
        enrich_candidate_contracts,
    )
    threshold = _decision_threshold(run)
    risk_limit = _risk_limit(run)
    existing_decision_diffs = _mapping(existing.get("decision_diffs"))
    decision_diffs = (
        deepcopy(existing_decision_diffs)
        if previous is None and existing_decision_diffs
        else build_decision_diffs(
            run, previous, candidate_contracts,
            threshold=threshold, risk_limit=risk_limit,
        )
    )
    candidate_contracts = enrich_candidate_contracts(
        run, previous, candidate_contracts, decision_diffs,
        threshold=threshold, risk_limit=risk_limit,
    )
    existing_historical = existing.get("historical_evaluations")
    historical_evaluations = (
        deepcopy(list(existing_historical))
        if previous is None and isinstance(existing_historical, Sequence) and not isinstance(existing_historical, (str, bytes, bytearray))
        else build_historical_evaluations(run, previous, candidate_contracts)
    )

    events = build_event_calendar(run)
    confidence = build_report_confidence(run, candidate_contracts)
    reliability = build_report_reliability(run, candidate_contracts)
    combined_quality = _mapping(run.get("combined_data_quality") or run.get("combined_quality"))
    # The public report population can also contain already-owned positions
    # appended for portfolio control.  All channels must use that same
    # denominator instead of silently switching back to the smaller analysis
    # provider population.
    report_summary = _mapping(run.get("report_summary"))
    evaluated_count = _safe_int(
        report_summary.get("coverage_candidate_total"),
        _safe_int(combined_quality.get("evaluated"), len(candidate_contracts)),
    )
    evaluated_count = max(evaluated_count, len(candidate_contracts))
    evidence_ready_count = _safe_int(combined_quality.get("overall_valid"), sum(
        1 for row in candidate_contracts if _mapping(row.get("confidence")).get("evidence_data_ready")
    ))
    quality_dimensions = {
        "market_data_quality": _safe_int(confidence.get("market_data_coverage"), 0),
        "technical_documentation_coverage": _safe_int(confidence.get("documentation_coverage") or confidence.get("data_coverage"), 0),
        "candidate_evidence_coverage": round((100.0 * evidence_ready_count / evaluated_count), 1) if evaluated_count else 0.0,
        "candidate_evidence_ready_count": evidence_ready_count,
        "candidate_count": evaluated_count,
        "independent_source_coverage": _safe_int(confidence.get("source_confidence"), 0),
        "report_decision_strength": _safe_int(confidence.get("decision_confidence"), 0),
        "labels": {
            "market_data_quality": "Markedsdatakvalitet",
            "technical_documentation_coverage": "Rapportens tekniske dokumentasjonsgrad",
            "candidate_evidence_coverage": "Kandidatenes evidensdekning",
            "independent_source_coverage": "Uavhengig kildedekning",
            "report_decision_strength": "Beslutningsstyrke på rapportnivå",
        },
    }
    tasks = build_next_run_tasks(run, candidate_contracts, events)
    overview = build_decision_overview(run, identity, candidate_contracts, changes, tasks, events, confidence, reliability)
    overview["decision_diff_count"] = int(decision_diffs.get("changed_count") or 0)
    overview["historical_evaluation_count"] = len(historical_evaluations)
    source_consensus = {
        "candidates": {str(row.get("ticker") or ""): deepcopy(row.get("source_consensus") or {}) for row in candidate_contracts},
        "strong": sum(1 for row in candidate_contracts if _mapping(row.get("source_consensus")).get("level") == "STERK"),
        "moderate": sum(1 for row in candidate_contracts if _mapping(row.get("source_consensus")).get("level") == "MODERAT"),
        "weak_or_unverified": sum(1 for row in candidate_contracts if _mapping(row.get("source_consensus")).get("level") in {"SVAK", "IKKE_VERIFISERT"}),
        "conflicting": sum(1 for row in candidate_contracts if _mapping(row.get("source_consensus")).get("level") == "MOTSTRIDENDE"),
    }
    from report_portfolio_intelligence import build_candidate_watch_queue, build_portfolio_report, build_system_anomaly_watch
    from candidate_data_governance import build_candidate_data_audit
    from short_intelligence import build_short_report
    portfolio = _mapping(run.get("autonomous_portfolio_snapshot") or run.get("portfolio_snapshot") or run.get("portfolio_context"))
    portfolio_intelligence = build_portfolio_report(portfolio, _rows(run.get("candidates")), now=_created_at(run))
    system_anomaly_watch = build_system_anomaly_watch(_rows(run.get("candidates")))
    candidate_watch_queue = build_candidate_watch_queue(
        _rows(run.get("candidates")),
        available_position_slots=int(portfolio_intelligence.get("remaining_position_slots") or 0),
    )
    candidate_data_audit = build_candidate_data_audit(_rows(run.get("candidates")))
    short_intelligence = build_short_report(_rows(run.get("candidates")))
    return {
        "schema_version": DECISION_REPORT_SCHEMA_VERSION,
        "overview": overview,
        "candidate_contracts": candidate_contracts,
        "changes": changes,
        "events": events,
        "next_run_tasks": tasks,
        "confidence": confidence,
        "quality_dimensions": quality_dimensions,
        "reliability": reliability,
        "source_consensus": source_consensus,
        "decision_diffs": decision_diffs,
        "historical_evaluations": historical_evaluations,
        "portfolio_intelligence": portfolio_intelligence,
        "system_anomaly_watch": system_anomaly_watch,
        "candidate_watch_queue": candidate_watch_queue,
        "candidate_data_audit": candidate_data_audit,
        "short_intelligence": short_intelligence,
        "counter_hypotheses": {
            str(row.get("ticker") or ""): deepcopy(row.get("counter_hypothesis") or {})
            for row in candidate_contracts[:3]
        },
        "analysis_transparency": deepcopy(_mapping(run.get("analysis_transparency"))),
        "controlled_learning_guard": {
            "production_rules_auto_change_allowed": False,
            "protected_rules": [
                "maximum_position_pct", "stop_loss_pct", "maximum_risk_score",
                "minimum_investment_score", "approval_requirements", "autonomy_mode",
            ],
            "require_explicit_user_approval": True,
        },
    }


def enrich_decision_report(
    run: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and attach decision-report metadata when the run is mutable."""
    payload = build_decision_report(run, previous, identity)
    if isinstance(run, MutableMapping):
        run["decision_report"] = deepcopy(payload)
        run["critical_events"] = deepcopy(payload["events"])
        run["next_run_tasks"] = deepcopy(payload["next_run_tasks"])
        run["report_confidence"] = deepcopy(payload["confidence"])
        run["report_quality_dimensions"] = deepcopy(payload["quality_dimensions"])
        run["report_reliability"] = deepcopy(payload["reliability"])
        run["source_consensus"] = deepcopy(payload["source_consensus"])
        run["decision_diffs"] = deepcopy(payload["decision_diffs"])
        run["historical_decision_evaluations"] = deepcopy(payload["historical_evaluations"])
        run["counter_hypotheses"] = deepcopy(payload["counter_hypotheses"])
        run["controlled_learning_guard"] = deepcopy(payload["controlled_learning_guard"])
        run["candidate_data_audit"] = deepcopy(payload["candidate_data_audit"])
        run["short_intelligence"] = deepcopy(payload["short_intelligence"])
    return payload


__all__ = [
    "CONSENSUS_LEVELS", "DECISION_REPORT_SCHEMA_VERSION", "REPORT_FOCUS", "TASK_STATUSES",
    "build_change_summary", "build_decision_report", "build_event_calendar", "build_next_run_tasks",
    "build_report_confidence", "build_report_reliability", "candidate_source_consensus",
    "enrich_decision_report",
]
