from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

try:
    from nbim_radar import apply_nbim_overlay, load_nbim_overlay
except Exception:  # pragma: no cover - optional module
    apply_nbim_overlay = None
    load_nbim_overlay = None


DECISION_QUEUE_KEY = "decision_support_queue_v1863ba"
DECISION_CASES_KEY = "decision_support_cases_v1863ba"


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _score(value: Any, default: float = 0.0) -> float:
    number = _float(value, None)
    if number is None:
        return float(default)
    if number <= 1.0:
        number *= 100.0
    return max(0.0, min(100.0, number))


def _score_from(row: Mapping[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
    values = [_score(row.get(key), default=-1.0) for key in keys if row.get(key) not in {None, ""}]
    values = [value for value in values if value >= 0.0]
    return max(values) if values else float(default)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _text_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item or "").strip()]


def _evidence_count(row: Mapping[str, Any], key: str) -> int:
    value = row.get(key)
    return len(value) if isinstance(value, list) else 0


def _source_name(row: Mapping[str, Any]) -> str:
    source = str(row.get("decision_source") or row.get("source") or row.get("mode") or "Radar").strip()
    if "Early Warning" in source:
        return "Early Warning"
    if "Alpha Radar" in source:
        return "Alpha Radar"
    return source or "Radar"


def decision_source_rows_from_radar_result(
    result: Mapping[str, Any],
    selected_tickers: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    selected = {str(ticker or "").strip().upper() for ticker in selected_tickers or [] if str(ticker or "").strip()}
    source = "Early Warning" if "Early Warning" in str(result.get("analysis_engine") or result.get("mode") or "") else "Alpha Radar"
    nbim_overlay = load_nbim_overlay() if load_nbim_overlay is not None else {}
    rows: list[dict[str, Any]] = []
    for candidate in result.get("candidates") or []:
        if not isinstance(candidate, Mapping):
            continue
        ticker = str(candidate.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        if selected and ticker not in selected:
            continue
        row = dict(candidate)
        row["ticker"] = ticker
        row["decision_source"] = source
        row["source_result_created_at"] = result.get("created_at")
        row["source_scope"] = result.get("scope")
        row["source_horizon"] = result.get("horizon") or candidate.get("horizon")
        row["source_precision"] = result.get("precision_level")
        row["queued_at"] = datetime.now().isoformat(timespec="seconds")
        if nbim_overlay and apply_nbim_overlay is not None:
            row = apply_nbim_overlay(row, nbim_overlay)
        rows.append(row)
    return rows


def add_decision_rows(existing: Sequence[Mapping[str, Any]] | None, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in list(existing or []) + list(rows or []):
        if not isinstance(item, Mapping):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        source = _source_name(item)
        merged[(ticker, source)] = dict(item)
    return list(merged.values())


def remove_decision_rows(existing: Sequence[Mapping[str, Any]] | None, tickers: Sequence[str]) -> list[dict[str, Any]]:
    selected = {str(ticker or "").strip().upper() for ticker in tickers if str(ticker or "").strip()}
    if not selected:
        return [dict(item) for item in existing or [] if isinstance(item, Mapping)]
    return [
        dict(item)
        for item in existing or []
        if isinstance(item, Mapping) and str(item.get("ticker") or "").strip().upper() not in selected
    ]


def build_decision_case(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").strip().upper()
    alpha_score = _score_from(row, ("hidden_potential_score", "early_warning_score", "alpha_score", "score"), default=0.0)
    evidence_score = _score(row.get("evidence_score"), default=0.0)
    catalyst_score = _score(row.get("catalyst_score"), default=0.0)
    insider_score = _score(row.get("insider_score"), default=0.0)
    bjellesau_score = _score(row.get("bjellesau_score"), default=0.0)
    volume_score = _score(row.get("volume_score"), default=0.0)
    macro_score = _score(row.get("macro_score"), default=0.0)
    nbim_score = _score(row.get("nbim_signal_score"), default=0.0)
    risk_score = _score(row.get("risk_score"), default=45.0)
    liquidity_penalty = _score(row.get("liquidity_penalty"), default=0.0)

    insider_count = _evidence_count(row, "insider_evidence")
    bjellesau_count = _evidence_count(row, "bjellesau_evidence")
    news_count = _evidence_count(row, "news_evidence")
    nbim_count = _evidence_count(row, "nbim_evidence")
    source_count = _evidence_count(row, "evidence_items")
    source_count_total = max(source_count, nbim_count)
    concrete_bonus = min(20.0, insider_count * 5.0 + bjellesau_count * 5.0 + news_count * 3.0 + nbim_count * 4.0)

    ownership_strength = max(insider_score, bjellesau_score, nbim_score * 0.88)
    timing_strength = max(volume_score, catalyst_score, macro_score)
    evidence_strength = max(evidence_score, catalyst_score, ownership_strength, nbim_score * 0.85) + concrete_bonus
    evidence_strength = max(0.0, min(100.0, evidence_strength))
    risk_pressure = max(risk_score, liquidity_penalty * 2.2)
    decision_score = (
        alpha_score * 0.32
        + evidence_strength * 0.29
        + timing_strength * 0.17
        + ownership_strength * 0.10
        + nbim_score * 0.04
        + max(0.0, 100.0 - risk_pressure) * 0.08
    )

    rejects = _text_list(row.get("reject_reasons"))
    warnings = _text_list(row.get("warning_reasons"))
    missing = []
    if source_count_total == 0:
        missing.append("mangler direkte kildespor")
    if not insider_count and not bjellesau_count and ownership_strength >= 55:
        missing.append("eierskapsscore uten konkret insider-/bjellesauliste")
    if catalyst_score >= 55 and not news_count:
        missing.append("katalysator maa kobles til nyhets-/borsmeldingskilde")
    if row.get("market_cap_display") in {None, "", "-"}:
        missing.append("borsverdi/valuta maa bekreftes")

    hard_risk = risk_pressure >= 72 or liquidity_penalty >= 16 or bool(rejects)
    weak_evidence = evidence_strength < 48 or source_count_total == 0
    if hard_risk and decision_score < 78:
        decision = "Unnga"
    elif decision_score >= 76 and evidence_strength >= 58 and risk_pressure < 62 and not rejects:
        decision = "Kjop naa"
    elif decision_score < 42 and weak_evidence:
        decision = "Unnga"
    else:
        decision = "Vent"

    confidence = max(20.0, min(92.0, evidence_strength * 0.55 + max(0.0, 100.0 - risk_pressure) * 0.25 + source_count * 2.0))
    positives: list[str] = []
    if alpha_score >= 70:
        positives.append(f"radarscore {alpha_score:.0f}")
    if insider_count:
        positives.append(f"{insider_count} insider-spor")
    if bjellesau_count:
        positives.append(f"{bjellesau_count} bjellesau-spor")
    if news_count:
        positives.append(f"{news_count} nyhets-/katalysatorspor")
    if nbim_count and nbim_score >= 55:
        positives.append(f"Oljefond/NBIM-spor {nbim_score:.0f}")
    if timing_strength >= 65:
        positives.append(f"timing/bekreftelse {timing_strength:.0f}")
    if ownership_strength >= 65:
        positives.append(f"eierskapssignal {ownership_strength:.0f}")
    if not positives:
        positives.append("radarfunn krever mer bekreftelse")

    cautions = list(rejects[:4])
    cautions.extend(warnings[:4])
    cautions.extend(missing[:4])
    if risk_pressure >= 62:
        cautions.append(f"risikopress {risk_pressure:.0f}")
    if not cautions:
        cautions.append("sjekk pris, likviditet og kilde manuelt")

    triggers = [
        "bekreft siste kilde/URL og dato",
        "sjekk at kurs/volum bekrefter hypotesen",
        "kontroller borsverdi i lokal valuta og NOK",
    ]
    if insider_count or bjellesau_count:
        triggers.insert(0, "verifiser hvem som er insider og hvem som er bjellesau")
    if nbim_count:
        triggers.insert(0, "sjekk NBIM-endringen mot siste offentlige beholdningsfil")
    if decision == "Kjop naa":
        position_hint = "liten startposisjon hvis manuell sjekk bekrefter kildene"
    elif decision == "Vent":
        position_hint = "observasjon; krev ny bekreftelse foer kapital brukes"
    else:
        position_hint = "ingen ny posisjon foer avslag/datamangler er ryddet"

    return {
        "ticker": ticker,
        "name": row.get("name") or row.get("company") or ticker,
        "market": row.get("market"),
        "source": _source_name(row),
        "decision": decision,
        "decision_score": round(decision_score, 1),
        "confidence": round(confidence, 1),
        "evidence_strength": round(evidence_strength, 1),
        "risk_pressure": round(risk_pressure, 1),
        "positive_reasons": positives,
        "cautions": cautions,
        "missing": missing,
        "buy_triggers": triggers,
        "position_hint": position_hint,
        "why": row.get("why_now") or row.get("thesis") or "",
        "insider_count": insider_count,
        "bjellesau_count": bjellesau_count,
        "news_count": news_count,
        "nbim_count": nbim_count,
        "source_count": source_count_total,
        "source_row": dict(row),
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "disclaimer": "Beslutningsstotte for manuell vurdering, ikke investeringsraad og ikke automatisk handel.",
    }


def build_decision_cases(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cases = [build_decision_case(row) for row in rows if isinstance(row, Mapping)]
    order = {"Kjop naa": 0, "Vent": 1, "Unnga": 2}
    return sorted(cases, key=lambda item: (order.get(str(item.get("decision")), 9), -float(item.get("decision_score") or 0.0)))


__all__ = [
    "DECISION_CASES_KEY",
    "DECISION_QUEUE_KEY",
    "add_decision_rows",
    "build_decision_case",
    "build_decision_cases",
    "decision_source_rows_from_radar_result",
    "remove_decision_rows",
]
