"""Autonomous decision reduction for AI Aksje Analyzer Pro v19.14.2.

The module converts internal engine actions into a small set of user-facing
Norwegian outcomes.  It deliberately avoids turning every missing data point
into manual work.  Manual investigation is reserved for near-threshold
candidates where one concrete, decision-relevant fact could change the result.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping, Sequence

from app_version import APP_VERSION

VERSION = APP_VERSION

OUTCOME_BUY = "KJØPSKANDIDAT"
OUTCOME_WATCH = "OVERVÅKES_AUTOMATISK"
OUTCOME_REJECT = "AUTOMATISK_AVVIST"
OUTCOME_MANUAL = "UNDERSØK_MANUELT"

OUTCOME_LABELS = {
    OUTCOME_BUY: "Kjøpskandidat",
    OUTCOME_WATCH: "Overvåkes automatisk",
    OUTCOME_REJECT: "Automatisk avvist",
    OUTCOME_MANUAL: "Undersøk manuelt",
}

# Human-readable source plans.  The existing source engines remain responsible
# for network calls; this matrix makes fallback expectations and manual advice
# explicit and market-specific.
MARKET_SOURCE_MATRIX: dict[str, dict[str, tuple[str, ...]]] = {
    "Norge": {
        "news": ("Euronext Oslo Børs – offisielle selskapsmeldinger", "Selskapets investorrelasjoner", "E24/EFN", "Yahoo Finance"),
        "insider": ("Euronext Oslo Børs – offisielle primærinnsidermeldinger", "Finanstilsynet", "Selskapets investorrelasjoner"),
        "financials": ("Selskapets kvartalsrapport", "Euronext Oslo Børs – offisielle selskapsmeldinger", "Selskapets investorrelasjoner"),
    },
    "Sverige": {
        "news": ("Nasdaq Nordic selskapsmeldinger", "Selskapets investorrelasjoner", "EFN", "Yahoo Finance"),
        "insider": ("Finansinspektionens insynsregister", "Nasdaq Nordic", "Selskapets investorrelasjoner"),
        "financials": ("Selskapets kvartalsrapport", "Nasdaq Nordic", "Selskapets investorrelasjoner"),
    },
    "USA": {
        "news": ("SEC EDGAR", "Selskapets investorrelasjoner", "Yahoo Finance", "CNBC/Reuters"),
        "insider": ("SEC Form 4", "SEC EDGAR", "Selskapets investorrelasjoner", "Yahoo Finance"),
        "financials": ("SEC 10-Q/10-K", "Selskapets investorrelasjoner", "SEC EDGAR"),
    },
    "Danmark": {
        "news": ("Nasdaq Copenhagen – offisielle selskapsmeldinger", "Selskapets investorrelasjoner", "Yahoo Finance"),
        "insider": ("Nasdaq Copenhagen – offisielle ledertransaksjoner", "Finanstilsynet Danmark", "Selskapets investorrelasjoner"),
        "financials": ("Selskapets kvartalsrapport", "Nasdaq Copenhagen – offisielle selskapsmeldinger", "Selskapets investorrelasjoner"),
    },
    "Finland": {
        "news": ("Nasdaq Helsinki – offisielle selskapsmeldinger", "Selskapets investorrelasjoner", "Yahoo Finance"),
        "insider": ("Nasdaq Helsinki – offisielle ledertransaksjoner", "Finanssivalvonta", "Selskapets investorrelasjoner"),
        "financials": ("Selskapets kvartalsrapport", "Nasdaq Helsinki – offisielle selskapsmeldinger", "Selskapets investorrelasjoner"),
    },
    "Brasil": {
        "news": ("CVM", "B3 selskapsmeldinger", "Selskapets investorrelasjoner", "Yahoo Finance"),
        "insider": ("CVM VLMO", "B3", "Selskapets investorrelasjoner"),
        "financials": ("CVM ITR/DFP", "B3", "Selskapets investorrelasjoner"),
    },
}

TERMINAL_EVIDENCE = {"AVAILABLE", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "VERIFIED_FACTS_NONE"}
TEMPORARY_SOURCE_FAILURES = {"RATE_LIMITED", "DAILY_QUOTA_EXCEEDED", "SOURCE_ERROR", "ERROR", "PARTIAL_SOURCE_FAILURE"}
UNSUPPORTED_SOURCE_STATES = {"NOT_CONFIGURED", "UNAVAILABLE", "NOT_SUPPORTED"}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else default
    except (TypeError, ValueError):
        return default


def _status(candidate: Mapping[str, Any], area: str) -> str:
    readiness = candidate.get("decision_readiness") if isinstance(candidate.get("decision_readiness"), Mapping) else {}
    value = str(readiness.get(area) or "").upper()
    if value:
        return value
    coverage = candidate.get("evidence_coverage") if isinstance(candidate.get("evidence_coverage"), Mapping) else {}
    detail = coverage.get(area) if isinstance(coverage.get(area), Mapping) else {}
    if detail.get("status"):
        return str(detail.get("status")).upper()
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    payload = raw.get(f"{area}_intelligence") if isinstance(raw.get(f"{area}_intelligence"), Mapping) else {}
    return str(payload.get("coverage") or payload.get("status") or "NOT_SEARCHED").upper()


def _evidence_detail(candidate: Mapping[str, Any], area: str) -> dict[str, Any]:
    coverage = candidate.get("evidence_coverage") if isinstance(candidate.get("evidence_coverage"), Mapping) else {}
    detail = _mapping(coverage.get(area))
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    payload = raw.get(f"{area}_intelligence") if isinstance(raw.get(f"{area}_intelligence"), Mapping) else {}
    if not detail:
        detail = _mapping(payload)
    if not detail.get("search_log") and isinstance(payload.get("search_log"), list):
        detail["search_log"] = deepcopy(payload.get("search_log"))
    return detail


def _attempted_sources(detail: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for row in detail.get("search_log") or []:
        if not isinstance(row, Mapping) or not row.get("attempted"):
            continue
        name = str(row.get("source") or row.get("source_name") or row.get("source_type") or "").strip()
        if name and name not in names:
            names.append(name)
    source = str(detail.get("source") or "").strip()
    if source and source not in names and source.lower() not in {"ikke oppgitt", "kontrollerte offentlige kilder"}:
        names.append(source)
    return names


def source_plan(market: str, area: str) -> tuple[str, ...]:
    matrix = MARKET_SOURCE_MATRIX.get(str(market or ""), MARKET_SOURCE_MATRIX["USA"])
    return tuple(matrix.get(area) or matrix.get("financials") or ())


def _source_failure_reason(detail: Mapping[str, Any], status: str) -> str:
    reason = str(detail.get("reason") or detail.get("error") or "").strip()
    if reason:
        return reason
    if status == "RATE_LIMITED":
        return "Kilden begrenset antall forespørsler midlertidig."
    if status == "DAILY_QUOTA_EXCEEDED":
        return "Døgnbudsjettet for kilden var brukt opp."
    if status == "PARTIAL_SOURCE_FAILURE":
        return "Minst én kilde svarte, men en nødvendig reserve- eller primærkilde feilet."
    if status in UNSUPPORTED_SOURCE_STATES:
        return "Ingen støttet direktekilde var tilgjengelig for dette markedet."
    if status == "NOT_SEARCHED":
        return "Kandidaten ble ikke prioritert til full evidenskontroll i denne kjøringen."
    return "Programmet kunne ikke bekrefte opplysningen automatisk."


def _manual_task(candidate: Mapping[str, Any], area: str, *, threshold: float) -> dict[str, Any]:
    market = str(candidate.get("market") or "Ukjent")
    ticker = str(candidate.get("ticker") or "-")
    status = _status(candidate, area)
    detail = _evidence_detail(candidate, area)
    attempted = _attempted_sources(detail)
    fallback = [name for name in source_plan(market, area) if name not in attempted]
    if area == "insider":
        what = "Bekreft om det finnes relevante, ferske innsidetransaksjoner"
        why = "En bekreftet handel kan endre evidensstyrken og kandidatens prioritet."
    elif area == "news":
        what = "Bekreft siste vesentlige selskapsmelding eller nyhetshendelse"
        why = "En vesentlig hendelse kan endre risiko, score og beslutningsutfall."
    else:
        what = "Bekreft den manglende beslutningskritiske regnskapsopplysningen"
        why = "Opplysningen inngår i risiko- eller kvalitetsporten."
    sources_text = ", ".join(attempted) if attempted else "Ingen kilde ble forsøkt i denne kjøringen"
    suggestion = fallback[0] if fallback else (source_plan(market, area)[0] if source_plan(market, area) else "selskapets primærkilde")
    score = _float(candidate.get("investment_score"))
    return {
        "ticker": ticker,
        "area": area,
        "title": what,
        "why": why,
        "program_attempts": sources_text,
        "failure_reason": _source_failure_reason(detail, status),
        "suggested_source": suggestion,
        "decision_impact": (
            f"Bekreftet positiv informasjon kan løfte dokumentasjonsgrunnlaget. "
            f"Negativ eller fortsatt ubekreftet informasjon vil normalt gi overvåking eller avvisning. "
            f"Kandidatens score er {score:.1f} mot produksjonsterskel {threshold:.1f}."
        ),
        "status": status,
    }


def _candidate_blockers(candidate: Mapping[str, Any]) -> list[str]:
    decision = candidate.get("portfolio_decision") if isinstance(candidate.get("portfolio_decision"), Mapping) else {}
    blockers = [str(x) for x in decision.get("blockers") or [] if str(x).strip()]
    if not blockers and decision.get("reason"):
        blockers.append(str(decision.get("reason")))
    return blockers[:4]


def classify_candidate(candidate: Mapping[str, Any], *, threshold: float = 78.0,
                       near_threshold_gap: float = 6.0, maximum_risk: float = 65.0) -> dict[str, Any]:
    row = deepcopy(dict(candidate))
    score = _float(row.get("investment_score"))
    risk = _float(row.get("risk_score"), 100.0)
    action = str(row.get("portfolio_action") or "REVIEW").upper()
    valid_data = bool(row.get("valid_for_decision"))
    evidence_ready = bool(row.get("evidence_valid_for_decision"))
    stage = str(row.get("analysis_stage") or _mapping(row.get("raw")).get("analysis_stage") or "EXTENDED_ANALYSIS")
    conflicts = int(_mapping(row.get("decision_readiness")).get("conflicts") or 0)
    blockers = _candidate_blockers(row)
    manual_tasks: list[dict[str, Any]] = []

    if action in {"BUY", "KJØP"} and valid_data and evidence_ready:
        code = OUTCOME_BUY
        reason = "Kandidaten har bestått data-, evidens-, risiko- og porteføljeportene."
        automatic_next = "Beholdes i kjøpsklar beslutningsliste etter gjeldende handelsregler."
    elif (not valid_data) or risk > maximum_risk or score < threshold - near_threshold_gap:
        code = OUTCOME_REJECT
        if not valid_data:
            reason = "Markeds- eller grunnlagsdata oppfyller ikke beslutningskravene."
        elif risk > maximum_risk:
            reason = f"Risiko {risk:.1f} er over maksimalgrensen {maximum_risk:.1f}."
        else:
            reason = f"Score {score:.1f} er mer enn {near_threshold_gap:.1f} poeng under produksjonsterskelen {threshold:.1f}."
        automatic_next = "Avsluttes automatisk for denne kjøringen; ingen brukerhandling nødvendig."
    else:
        # Only near-threshold candidates can create manual work.  NOT_SEARCHED
        # from an earlier stage means automatic monitoring, not a user task.
        critical_areas: list[str] = []
        for area in ("news", "insider"):
            status = _status(row, area)
            detail = _evidence_detail(row, area)
            attempts = _attempted_sources(detail)
            if status in TERMINAL_EVIDENCE:
                continue
            if status == "NOT_SEARCHED" and stage != "EVIDENCE_CONTROLLED":
                continue
            if status in TEMPORARY_SOURCE_FAILURES | UNSUPPORTED_SOURCE_STATES or attempts:
                critical_areas.append(area)
        if conflicts:
            manual_tasks.append({
                "ticker": str(row.get("ticker") or "-"),
                "area": "source_conflict",
                "title": "Avklar motstridende kildeopplysninger",
                "why": "Motstridende tall kan endre både risiko og beslutningsstatus.",
                "program_attempts": "Programmet registrerte kildene, men kunne ikke avgjøre hvilken verdi som er autoritativ.",
                "failure_reason": f"{conflicts} kildekonflikt(er) står uløst.",
                "suggested_source": source_plan(str(row.get("market") or ""), "financials")[0],
                "decision_impact": "Bruk den nyeste daterte primærkilden. Avvik som svekker kvalitets- eller risikokravet gir automatisk avvisning.",
                "status": "CONFLICT",
            })
        for area in critical_areas:
            manual_tasks.append(_manual_task(row, area, threshold=threshold))

        if manual_tasks:
            code = OUTCOME_MANUAL
            reason = "Kandidaten er nær terskelen, men én eller flere beslutningskritiske opplysninger kunne ikke bekreftes automatisk."
            automatic_next = "Avventer den konkrete manuelle kontrollen nedenfor."
        else:
            code = OUTCOME_WATCH
            if evidence_ready and action == "REVIEW" and blockers:
                reason = "Datagrunnlaget er tilstrekkelig, men portefølje- eller risikokapasitet blokkerer kjøp nå."
            elif stage != "EVIDENCE_CONTROLLED":
                reason = "Kandidaten bestod den raske analysen, men ble ikke prioritert til full evidenskontroll i denne kjøringen."
            else:
                reason = "Kandidaten er ikke kjøpsgodkjent, men kan bli aktuell ved nye data eller endrede porteføljeforhold."
            automatic_next = "Programmet følger kandidaten og vurderer den på nytt automatisk ved neste relevante kjøring."

    row["autonomy_outcome_code"] = code
    row["autonomy_outcome_label"] = OUTCOME_LABELS[code]
    row["autonomy_outcome_reason"] = reason
    row["automatic_next_action"] = automatic_next
    row["manual_review_required"] = code == OUTCOME_MANUAL
    row["manual_tasks"] = manual_tasks
    row["manual_task_summary"] = manual_tasks[0]["title"] if manual_tasks else "Ingen manuell handling nødvendig"
    row["decision_priority_eligible"] = code != OUTCOME_REJECT
    row["analysis_stage"] = stage
    return row


def _priority_candidate_view(row: Mapping[str, Any]) -> dict[str, Any]:
    """Compact user-facing priority row without duplicated raw source payloads."""
    fields = (
        "ticker", "name", "market", "sector", "investment_score", "confidence_score",
        "risk_score", "data_quality", "portfolio_action", "autonomy_outcome_code",
        "autonomy_outcome_label", "autonomy_outcome_reason", "automatic_next_action",
        "manual_review_required", "manual_tasks", "manual_task_summary", "analysis_stage",
        "valid_for_decision", "evidence_valid_for_decision", "evidence_data_ready",
        "final_decision_ready", "decision_readiness", "evidence_coverage", "rank", "raw_rank",
        "strategy_matches", "score_trend", "trend",
    )
    return {key: deepcopy(row.get(key)) for key in fields if key in row}


def apply_decision_reduction(candidates: Sequence[Mapping[str, Any]], *, threshold: float = 78.0,
                             near_threshold_gap: float = 6.0, maximum_risk: float = 65.0,
                             max_manual_tasks: int = 2) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [classify_candidate(row, threshold=threshold, near_threshold_gap=near_threshold_gap,
                               maximum_risk=maximum_risk) for row in candidates]
    manual = sorted((row for row in rows if row.get("autonomy_outcome_code") == OUTCOME_MANUAL),
                    key=lambda row: _float(row.get("investment_score")), reverse=True)
    remaining = max(0, int(max_manual_tasks))
    for row in manual:
        tasks = list(row.get("manual_tasks") or [])
        allocated = tasks[:remaining] if remaining else []
        remaining -= len(allocated)
        if allocated:
            row["manual_tasks"] = allocated
            row["manual_task_summary"] = allocated[0].get("title") or "Konkret manuell undersøkelse"
            continue
        row["autonomy_outcome_code"] = OUTCOME_WATCH
        row["autonomy_outcome_label"] = OUTCOME_LABELS[OUTCOME_WATCH]
        row["autonomy_outcome_reason"] = (
            "Kandidaten har en mulig datamangel, men høyere rangerte oppgaver er prioritert. "
            "Programmet prøver igjen automatisk."
        )
        row["automatic_next_action"] = "Ny automatisk kildekontroll ved neste relevante kjøring."
        row["manual_review_required"] = False
        row["manual_tasks"] = []
        row["manual_task_summary"] = "Ingen manuell handling nødvendig nå"

    counts = {code: sum(1 for row in rows if row.get("autonomy_outcome_code") == code) for code in OUTCOME_LABELS}
    eligible_priority = [row for row in rows if row.get("autonomy_outcome_code") != OUTCOME_REJECT]
    eligible_priority.sort(key=lambda row: (
        {OUTCOME_BUY: 3, OUTCOME_MANUAL: 2, OUTCOME_WATCH: 1}.get(str(row.get("autonomy_outcome_code")), 0),
        _float(row.get("investment_score")),
    ), reverse=True)
    rejected_fallback = sorted(
        (row for row in rows if row.get("autonomy_outcome_code") == OUTCOME_REJECT),
        key=lambda row: _float(row.get("investment_score")), reverse=True,
    )
    # Keep the promised 1-3 overview even when fewer than three candidates remain
    # actionable. Rejected fallback rows are clearly labelled and do not create
    # manual work or become buy proposals.
    priority_pool = eligible_priority + rejected_fallback
    priority_top3 = [_priority_candidate_view(row) for row in priority_pool[:3]]
    for index, row in enumerate(priority_top3, 1):
        row["priority_rank"] = index
    manual_tasks = [deepcopy(task) for row in rows for task in row.get("manual_tasks") or [] if row.get("manual_review_required")]
    summary = {
        "version": VERSION,
        "counts": counts,
        "buy_candidates": counts[OUTCOME_BUY],
        "automatic_watch": counts[OUTCOME_WATCH],
        "automatic_rejected": counts[OUTCOME_REJECT],
        "manual_candidates": counts[OUTCOME_MANUAL],
        "manual_tasks": manual_tasks,
        "manual_task_count": len(manual_tasks),
        "priority_top3": priority_top3,
        "target": "Normalt 0-2 konkrete manuelle oppgaver; øvrige kandidater avsluttes eller overvåkes automatisk.",
        "production_buy_threshold": threshold,
        "manual_review_window_points": near_threshold_gap,
        "threshold": threshold,
        "near_threshold_gap": near_threshold_gap,
        "threshold_explanation": (
            f"Produksjonsterskel {threshold:.1f}. Bare kandidater innen {near_threshold_gap:.1f} poeng "
            "kan bli vurdert for en konkret manuell oppgave; dette er ikke en egen kjøpsterskel."
        ),
        "maximum_risk": maximum_risk,
    }
    return rows, summary


__all__ = [
    "VERSION", "OUTCOME_BUY", "OUTCOME_WATCH", "OUTCOME_REJECT", "OUTCOME_MANUAL",
    "OUTCOME_LABELS", "MARKET_SOURCE_MATRIX", "source_plan", "classify_candidate",
    "apply_decision_reduction",
]
