"""Advanced decision intelligence for AI Aksje Analyzer v19.3.0.

The functions in this module are read-only. They compare already calculated
candidate results, explain model and rule changes, formulate data-supported
counter-hypotheses, and evaluate expired historical decisions. They never
change ranking scores, portfolio actions, thresholds, risk limits or orders.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

DECISION_INTELLIGENCE_SCHEMA_VERSION = "1.0"

MODEL_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("investment_score", "Samlet investeringsscore"),
    ("discovery_score", "AI-funn"),
    ("fundamental_score", "Fundamentalt"),
    ("research_score", "Analyse"),
    ("validation_score", "Historisk test"),
    ("portfolio_fit_score", "Porteføljetilpasning"),
    ("confidence_score", "Modellkonfidens"),
    ("risk_score", "Risiko"),
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else default
    except (TypeError, ValueError):
        return default


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
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _candidate_map(run: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("ticker") or "").upper(): row
        for row in _rows(_mapping(run).get("candidates"))
        if row.get("ticker")
    }


def _contract_map(run: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    decision_report = _mapping(_mapping(run).get("decision_report"))
    return {
        str(row.get("ticker") or "").upper(): row
        for row in _rows(decision_report.get("candidate_contracts"))
        if row.get("ticker")
    }


def _raw(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(candidate.get("raw"))


def candidate_price(candidate: Mapping[str, Any] | None) -> float | None:
    row = _mapping(candidate)
    raw = _raw(row)
    for value in (
        row.get("current_price"), row.get("price"), row.get("last_price"),
        raw.get("current_price"), raw.get("price"), raw.get("last_price"),
        raw.get("market_price"), raw.get("close"),
    ):
        number = _float(value, 0.0)
        if number > 0:
            return number
    return None


def _nested_number(candidate: Mapping[str, Any], *names: str) -> float | None:
    raw = _raw(candidate)
    sources = [candidate, raw, _mapping(raw.get("technical")), _mapping(raw.get("indicators")), _mapping(raw.get("metrics"))]
    for source in sources:
        for name in names:
            if name not in source:
                continue
            value = source.get(name)
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number == number:
                return number
    return None


def _action(candidate: Mapping[str, Any] | None) -> str:
    row = _mapping(candidate)
    readiness = _mapping(row.get("decision_readiness"))
    return str(readiness.get("allowed_action") or row.get("portfolio_action") or row.get("status") or "REVIEW").upper()


def _decision_ready(candidate: Mapping[str, Any] | None, contract: Mapping[str, Any] | None = None) -> bool:
    profile = _mapping(_mapping(contract).get("confidence"))
    if "decision_ready" in profile:
        return bool(profile.get("decision_ready"))
    row = _mapping(candidate)
    return bool(row.get("valid_for_decision") and row.get("evidence_valid_for_decision", True))


def _data_validity(candidate: Mapping[str, Any] | None) -> str:
    return str(_mapping(_mapping(candidate).get("data_contract")).get("validity") or "UKJENT").upper()


def _consensus_level(contract: Mapping[str, Any] | None) -> str:
    return str(_mapping(_mapping(contract).get("source_consensus")).get("level") or "IKKE_VERIFISERT").upper()


def _value_change(field: str, label: str, before: Any, after: Any, *, unit: str = "") -> dict[str, Any] | None:
    if before == after:
        return None
    result: dict[str, Any] = {"field": field, "label": label, "before": before, "after": after}
    try:
        result["delta"] = round(float(after) - float(before), 4)
        result["unit"] = unit
    except (TypeError, ValueError):
        result["delta"] = None
        result["unit"] = unit
    return result


def build_candidate_decision_diff(
    current: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    current_contract: Mapping[str, Any],
    previous_contract: Mapping[str, Any] | None,
    *,
    threshold: float,
    risk_limit: float,
) -> dict[str, Any]:
    """Explain data, model and rule differences for one candidate."""
    ticker = str(current.get("ticker") or "").upper()
    if not previous:
        return {
            "ticker": ticker,
            "has_previous": False,
            "data_diff": [],
            "model_diff": [],
            "decision_diff": [],
            "net_score_delta": None,
            "summary": "Ny kandidat uten sammenlignbar tidligere vurdering.",
        }

    data_diff: list[dict[str, Any]] = []
    before_price, after_price = candidate_price(previous), candidate_price(current)
    if before_price is not None and after_price is not None:
        row = _value_change("price", "Kurs", round(before_price, 4), round(after_price, 4))
        if row:
            row["pct_change"] = round((after_price / before_price - 1.0) * 100.0, 3) if before_price else None
            data_diff.append(row)
    for field, label, before, after in (
        ("data_validity", "Datagyldighet", _data_validity(previous), _data_validity(current)),
        ("source_consensus", "Kildekonsensus", _consensus_level(previous_contract), _consensus_level(current_contract)),
        ("data_coverage", "Datadekning", _mapping(_mapping(previous_contract).get("confidence")).get("data_coverage"), _mapping(_mapping(current_contract).get("confidence")).get("data_coverage")),
        ("source_confidence", "Kildesikkerhet", _mapping(_mapping(previous_contract).get("confidence")).get("source_confidence"), _mapping(_mapping(current_contract).get("confidence")).get("source_confidence")),
    ):
        row = _value_change(field, label, before, after)
        if row:
            data_diff.append(row)

    model_diff: list[dict[str, Any]] = []
    for field, label in MODEL_COMPONENTS:
        before = previous.get(field)
        after = current.get(field)
        if before is None and after is None:
            before = _raw(previous).get(field)
            after = _raw(current).get(field)
        if before is None or after is None:
            continue
        row = _value_change(field, label, round(_float(before), 4), round(_float(after), 4), unit="poeng")
        if row:
            model_diff.append(row)
    model_diff.sort(key=lambda row: abs(_float(row.get("delta"))), reverse=True)

    old_score = _float(previous.get("investment_score"), 0.0)
    new_score = _float(current.get("investment_score"), 0.0)
    old_risk = _float(previous.get("risk_score"), 0.0)
    new_risk = _float(current.get("risk_score"), 0.0)
    old_action, new_action = _action(previous), _action(current)
    old_ready = _decision_ready(previous, previous_contract)
    new_ready = _decision_ready(current, current_contract)
    decision_diff: list[dict[str, Any]] = []
    if old_action != new_action:
        decision_diff.append({"rule": "ACTION", "label": "Handling", "before": old_action, "after": new_action, "effect": "ENDRET_HANDLING"})
    if old_ready != new_ready:
        decision_diff.append({"rule": "DECISION_READY", "label": "Beslutningsklar", "before": old_ready, "after": new_ready, "effect": "BLE_KLAR" if new_ready else "IKKE_LENGER_KLAR"})
    if (old_score < threshold) != (new_score < threshold):
        decision_diff.append({
            "rule": "SCORE_THRESHOLD", "label": f"Scoreterskel {threshold:.1f}",
            "before": old_score, "after": new_score,
            "effect": "TERSKELOPPFYLT" if new_score >= threshold else "FALT_UNDER_TERSKEL",
        })
    if (old_risk > risk_limit) != (new_risk > risk_limit):
        decision_diff.append({
            "rule": "RISK_LIMIT", "label": f"Risikogrense {risk_limit:.1f}",
            "before": old_risk, "after": new_risk,
            "effect": "RISIKO_INNENFOR" if new_risk <= risk_limit else "RISIKO_OVER_GRENSE",
        })
    old_conflicts = int(_float(_mapping(previous.get("decision_readiness")).get("conflicts"), 0))
    new_conflicts = int(_float(_mapping(current.get("decision_readiness")).get("conflicts"), 0))
    if old_conflicts != new_conflicts:
        decision_diff.append({"rule": "SOURCE_CONFLICTS", "label": "Kildekonflikter", "before": old_conflicts, "after": new_conflicts, "effect": "ENDRET_KILDEBILDE"})

    net_delta = round(new_score - old_score, 4)
    strongest = model_diff[0] if model_diff else None
    summary_parts = [f"Score {net_delta:+.2f} poeng"]
    if old_action != new_action:
        summary_parts.append(f"handling {old_action} -> {new_action}")
    if strongest:
        summary_parts.append(f"største modellbidrag: {strongest['label']} {strongest.get('delta', 0):+.2f}")
    if not data_diff and not model_diff and not decision_diff:
        summary_parts = ["Ingen vesentlig strukturert endring registrert"]
    return {
        "ticker": ticker,
        "has_previous": True,
        "data_diff": data_diff,
        "model_diff": model_diff,
        "decision_diff": decision_diff,
        "net_score_delta": net_delta,
        "summary": "; ".join(summary_parts) + ".",
    }


def build_decision_diffs(
    run: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    candidate_contracts: Sequence[Mapping[str, Any]],
    *,
    threshold: float,
    risk_limit: float,
) -> dict[str, Any]:
    current_map = _candidate_map(run)
    previous_map = _candidate_map(previous)
    current_contracts = {str(row.get("ticker") or "").upper(): row for row in candidate_contracts}
    previous_contracts = _contract_map(previous)
    rows: list[dict[str, Any]] = []
    for ticker, current in current_map.items():
        rows.append(build_candidate_decision_diff(
            current,
            previous_map.get(ticker),
            current_contracts.get(ticker, {}),
            previous_contracts.get(ticker),
            threshold=threshold,
            risk_limit=risk_limit,
        ))
    changed = [row for row in rows if row.get("has_previous") and (row.get("data_diff") or row.get("model_diff") or row.get("decision_diff"))]
    return {
        "schema_version": DECISION_INTELLIGENCE_SCHEMA_VERSION,
        "has_previous": bool(previous),
        "candidates": rows,
        "by_ticker": {row["ticker"]: deepcopy(row) for row in rows if row.get("ticker")},
        "changed_count": len(changed),
        "action_change_count": sum(1 for row in rows if any(item.get("rule") == "ACTION" for item in row.get("decision_diff") or [])),
    }


def _counter_evidence(candidate: Mapping[str, Any], contract: Mapping[str, Any], *, threshold: float, risk_limit: float) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    score = _float(candidate.get("investment_score"), 0.0)
    risk = _float(candidate.get("risk_score"), 0.0)
    if score < threshold:
        evidence.append({"severity": min(100, 45 + (threshold - score) * 7), "code": "SCORE_GAP", "fact": f"Score {score:.1f} er under terskel {threshold:.1f}", "source": "Rangeringsmodell"})
    if risk > risk_limit:
        evidence.append({"severity": min(100, 55 + (risk - risk_limit) * 5), "code": "HIGH_RISK", "fact": f"Risiko {risk:.1f} er over grense {risk_limit:.1f}", "source": "Risikomodell"})
    consensus = _mapping(contract.get("source_consensus"))
    consensus_level = str(consensus.get("level") or "IKKE_VERIFISERT").upper()
    if consensus_level in {"SVAK", "MOTSTRIDENDE", "IKKE_VERIFISERT"}:
        severity = {"MOTSTRIDENDE": 92, "IKKE_VERIFISERT": 82, "SVAK": 70}[consensus_level]
        evidence.append({"severity": severity, "code": "SOURCE_WEAKNESS", "fact": f"Kildekonsensus er {consensus_level.lower().replace('_', ' ')}", "source": "Evidenskontrakt"})
    confidence = _mapping(contract.get("confidence"))
    data_coverage = _float(confidence.get("data_coverage"), 0.0)
    if data_coverage < 70:
        evidence.append({"severity": 70 + min(25, (70 - data_coverage) / 2), "code": "DATA_GAP", "fact": f"Datadekning er bare {data_coverage:.0f}/100", "source": "Datakontrakt"})
    rsi = _nested_number(candidate, "rsi", "RSI")
    if rsi is not None and rsi >= 70:
        evidence.append({"severity": min(92, 62 + (rsi - 70) * 2), "code": "OVERBOUGHT", "fact": f"RSI er {rsi:.1f}, som kan indikere strukket kortsiktig prising", "source": "Teknisk analyse"})
    distance_50 = _nested_number(candidate, "distance_50d_pct", "distance_to_sma50_pct", "above_50d_pct")
    if distance_50 is not None and distance_50 >= 10:
        evidence.append({"severity": min(90, 60 + distance_50), "code": "PRICE_STRETCH", "fact": f"Kursen ligger {distance_50:.1f}% over 50-dagers referanse", "source": "Markedsdata"})
    pe = _nested_number(candidate, "pe", "pe_ratio", "forward_pe")
    if pe is not None and pe >= 35:
        evidence.append({"severity": min(85, 55 + (pe - 35) / 2), "code": "VALUATION", "fact": f"P/E er {pe:.1f}, som gir liten feilmargin", "source": "Fundamentale data"})
    raw = _raw(candidate)
    insider = _mapping(raw.get("insider_intelligence"))
    net_value = _float(insider.get("net_value"), 0.0)
    if net_value < 0:
        evidence.append({"severity": 68, "code": "INSIDER_SELLING", "fact": f"Netto insiderverdi er negativ ({net_value:,.0f})", "source": "Insideranalyse"})
    news = _mapping(raw.get("news_intelligence"))
    news_score = _float(news.get("sentiment_score", news.get("score", raw.get("news_score", 50))), 50.0)
    if news_score < 40:
        evidence.append({"severity": 72, "code": "NEGATIVE_NEWS", "fact": f"Nyhetsscore er svak ({news_score:.0f}/100)", "source": "Nyhetsanalyse"})
    if not evidence:
        evidence.append({"severity": 35, "code": "EXECUTION_RISK", "fact": "Ingen sterk negativ datapåstand er funnet; hovedrisikoen er at markedet allerede har priset inn den positive hypotesen", "source": "Forsiktighetsregel"})
    return sorted(evidence, key=lambda row: _float(row.get("severity")), reverse=True)


def build_counter_hypothesis(
    candidate: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    threshold: float,
    risk_limit: float,
) -> dict[str, Any]:
    evidence = _counter_evidence(candidate, contract, threshold=threshold, risk_limit=risk_limit)
    strongest = evidence[0]
    ticker = str(candidate.get("ticker") or "Kandidaten")
    code = str(strongest.get("code") or "EXECUTION_RISK")
    arguments = {
        "SCORE_GAP": f"{ticker} kan være en svakere kandidat enn totalfortellingen antyder fordi den fortsatt ikke oppfyller modellens beslutningsterskel.",
        "HIGH_RISK": f"{ticker} kan gi et ugunstig risikojustert utfall fordi den målte risikoen allerede overstiger gjeldende grense.",
        "SOURCE_WEAKNESS": f"Investeringshypotesen for {ticker} kan bygge på et utilstrekkelig eller motstridende kildegrunnlag.",
        "DATA_GAP": f"Vurderingen av {ticker} kan endres vesentlig når manglende eller eldre data blir oppdatert.",
        "OVERBOUGHT": f"{ticker} kan være kortsiktig overstrukket, slik at selv gode selskapsnyheter ikke gir attraktiv inngang nå.",
        "PRICE_STRETCH": f"Markedet kan allerede ha priset inn mye av oppsiden i {ticker}.",
        "VALUATION": f"Verdsettelsen av {ticker} gir liten feilmargin dersom vekst eller guiding skuffer.",
        "INSIDER_SELLING": f"Negativ netto insideraktivitet kan være et motargument mot den positive investeringshypotesen for {ticker}.",
        "NEGATIVE_NEWS": f"Nyhetsbildet kan varsle svakere utvikling enn den samlede modellen fanger opp for {ticker}.",
        "EXECUTION_RISK": f"Den sterkeste forsiktige hypotesen er at oppsiden i {ticker} allerede er priset inn og at forholdet mellom oppside og risiko derfor er svakere enn det ser ut.",
    }
    confirmation = {
        "SCORE_GAP": [f"Score forblir under {threshold:.1f}", "Kandidaten faller videre relativt til Top 3"],
        "HIGH_RISK": [f"Risiko forblir over {risk_limit:.1f}", "Volatilitet eller drawdown øker"],
        "SOURCE_WEAKNESS": ["Primærkilde uteblir", "Nye kilder bekrefter konflikten"],
        "DATA_GAP": ["Ny data svekker score eller beslutningsklarhet", "Datakontrakten forblir ugyldig"],
        "OVERBOUGHT": ["RSI forblir høy samtidig som momentum svekkes", "Kursen reverserer uten ny fundamental støtte"],
        "PRICE_STRETCH": ["Kursen faller tilbake mot normal trend", "Positive nyheter gir liten ny kursrespons"],
        "VALUATION": ["Guiding eller estimater kuttes", "Multipler forblir høye uten tilsvarende resultatvekst"],
        "INSIDER_SELLING": ["Flere verifiserte innsidersalg", "Ingen kompenserende kjøp fra ledelsen"],
        "NEGATIVE_NEWS": ["Flere uavhengige kilder bekrefter negativ utvikling", "Selskapet bekrefter hendelsen"],
        "EXECUTION_RISK": ["Kursen reagerer svakt på positive nyheter", "Forventet katalysator uteblir"],
    }
    weakening = {
        "SCORE_GAP": [f"Score stiger over {threshold:.1f}", "Alle beslutningsporter blir godkjent"],
        "HIGH_RISK": [f"Risiko faller til {risk_limit:.1f} eller lavere", "Likviditet og volatilitet normaliseres"],
        "SOURCE_WEAKNESS": ["En sterk primærkilde bekrefter hendelsen", "Kildekonflikten blir forklart og lukket"],
        "DATA_GAP": ["Ferske data bekrefter vurderingen", "Datadekning og beslutningssikkerhet blir høy"],
        "OVERBOUGHT": ["Kursen konsoliderer uten fundamentalt brudd", "Resultatvekst bekrefter prisingen"],
        "PRICE_STRETCH": ["Fundamentale estimater løftes mer enn kursen", "Ny katalysator gir dokumentert oppside"],
        "VALUATION": ["Resultatveksten akselererer", "Verdsettelsen faller uten svekket kvalitet"],
        "INSIDER_SELLING": ["Verifiserte innsiderkjøp oppstår", "Salgene dokumenteres som ikke-informasjonsdrevne"],
        "NEGATIVE_NEWS": ["Primærkilde avkrefter saken", "Resultater eller guiding motsier det negative bildet"],
        "EXECUTION_RISK": ["Ny, ikke-priset katalysator bekreftes", "Oppsideestimatet øker uten høyere risiko"],
    }
    priced_in = "UKJENT"
    if code in {"OVERBOUGHT", "PRICE_STRETCH", "VALUATION"}:
        priced_in = "SANNSYNLIGVIS_DELVIS"
    elif code in {"SCORE_GAP", "HIGH_RISK", "SOURCE_WEAKNESS", "DATA_GAP"}:
        priced_in = "KAN_IKKE_FASTSLÅS"
    return {
        "ticker": ticker,
        "status": "DATASTØTTET" if code != "EXECUTION_RISK" else "FORSIKTIGHETSHYPOTESE",
        "strongest_argument": arguments[code],
        "primary_risk_code": code,
        "evidence": evidence[:4],
        "confirmation_conditions": confirmation[code],
        "weakening_conditions": weakening[code],
        "priced_in_assessment": priced_in,
        "changes_production_decision": False,
        "warning": "Motargumentet er beslutningsstøtte og endrer ikke kandidatens score eller handling.",
    }


def build_critical_assumptions(candidate: Mapping[str, Any], contract: Mapping[str, Any], *, threshold: float, risk_limit: float) -> list[dict[str, Any]]:
    score = _float(candidate.get("investment_score"), 0.0)
    risk = _float(candidate.get("risk_score"), 0.0)
    consensus = _consensus_level(contract)
    validity = _data_validity(candidate)
    return [
        {"assumption": "Datagrunnlaget forblir gyldig og ferskt", "current_status": validity, "holds": validity in {"VALID", "GYLDIG"}},
        {"assumption": "Kildebildet er uten uløste vesentlige konflikter", "current_status": consensus, "holds": consensus != "MOTSTRIDENDE"},
        {"assumption": f"Risiko forblir innenfor {risk_limit:.1f}", "current_status": round(risk, 2), "holds": risk <= risk_limit},
        {"assumption": f"Score og beslutningsgrunnlag forblir konsistent med terskel {threshold:.1f}", "current_status": round(score, 2), "holds": score >= threshold},
    ]


def enrich_candidate_contracts(
    run: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    contracts: Sequence[Mapping[str, Any]],
    decision_diffs: Mapping[str, Any],
    *,
    threshold: float,
    risk_limit: float,
) -> list[dict[str, Any]]:
    candidate_map = _candidate_map(run)
    diff_map = _mapping(decision_diffs.get("by_ticker"))
    result: list[dict[str, Any]] = []
    for contract in contracts:
        row = deepcopy(dict(contract))
        ticker = str(row.get("ticker") or "").upper()
        candidate = candidate_map.get(ticker, {})
        counter = build_counter_hypothesis(candidate, row, threshold=threshold, risk_limit=risk_limit)
        assumptions = build_critical_assumptions(candidate, row, threshold=threshold, risk_limit=risk_limit)
        blockers = list(row.get("blockers") or [])
        rationale = [
            f"Handling: {_action(candidate)}",
            f"Score: {_float(candidate.get('investment_score'), 0.0):.1f}",
            f"Risiko: {_float(candidate.get('risk_score'), 0.0):.1f}",
            f"Kildekonsensus: {_consensus_level(row)}",
        ]
        row.update({
            "decision_diff": deepcopy(diff_map.get(ticker) or {}),
            "counter_hypothesis": counter,
            "critical_assumptions": assumptions,
            "rationale": rationale,
            "next_review": _mapping(row.get("validity")).get("valid_until"),
            "decision_contract": {
                "ticker": ticker,
                "decision": row.get("action"),
                "rationale": rationale,
                "validity": deepcopy(row.get("validity") or {}),
                "critical_assumptions": assumptions,
                "invalidators": list(_mapping(row.get("validity")).get("invalidated_by") or []),
                "invalidating_events": list(_mapping(row.get("validity")).get("invalidated_by") or []),
                "counter_hypothesis": counter,
                "confidence": deepcopy(row.get("confidence") or {}),
                "data_coverage": _mapping(row.get("confidence")).get("data_coverage"),
                "source_confidence": _mapping(row.get("confidence")).get("source_confidence"),
                "decision_confidence": _mapping(row.get("confidence")).get("decision_confidence"),
                "source_consensus": deepcopy(row.get("source_consensus") or {}),
                "next_review": _mapping(row.get("validity")).get("valid_until"),
                "blockers": blockers,
            },
        })
        result.append(row)
    return result


def build_historical_evaluations(
    run: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    current_contracts: Sequence[Mapping[str, Any]] = (),
    *,
    now: Any = None,
) -> list[dict[str, Any]]:
    if not previous:
        return []
    current_time = _parse_datetime(now) or _parse_datetime(run.get("created_at")) or datetime.now(timezone.utc)
    current_map = _candidate_map(run)
    previous_map = _candidate_map(previous)
    previous_contracts = _contract_map(previous)
    current_contract_map = {str(row.get("ticker") or "").upper(): row for row in current_contracts}
    evaluations: list[dict[str, Any]] = []
    for ticker, old in previous_map.items():
        old_contract = previous_contracts.get(ticker, {})
        valid_until = _parse_datetime(_mapping(old_contract.get("validity")).get("valid_until"))
        if valid_until and current_time < valid_until:
            continue
        new = current_map.get(ticker)
        old_price = candidate_price(old)
        new_price = candidate_price(new)
        return_pct = None
        if old_price and new_price:
            return_pct = round((new_price / old_price - 1.0) * 100.0, 3)
        old_score = _float(old.get("investment_score"), 0.0)
        new_score = _float(_mapping(new).get("investment_score"), old_score)
        old_action, new_action = _action(old), _action(new)
        if not new:
            outcome = "UTGÅTT_ELLER_MANGLER_DATA"
        elif new_action == old_action and abs(new_score - old_score) < 2:
            outcome = "STABIL"
        elif new_score > old_score or (old_action != "BUY" and new_action == "BUY"):
            outcome = "STYRKET"
        else:
            outcome = "SVEKKET"
        assumptions = list(_mapping(current_contract_map.get(ticker)).get("critical_assumptions") or [])
        evaluations.append({
            "ticker": ticker,
            "source_report_id": str(previous.get("run_id") or ""),
            "evaluated_in_report_id": str(run.get("run_id") or ""),
            "expired": bool(not valid_until or current_time >= valid_until),
            "expired_at": valid_until.isoformat(timespec="seconds") if valid_until else "",
            "old_action": old_action,
            "new_action": new_action if new else "IKKE_I_AKTUELT_UNIVERS",
            "action_changed": bool(new and old_action != new_action),
            "old_score": old_score,
            "new_score": new_score if new else None,
            "score_delta": round(new_score - old_score, 3) if new else None,
            "price_return_pct": return_pct,
            "outcome": outcome,
            "assumptions_held": sum(1 for item in assumptions if item.get("holds")),
            "assumptions_total": len(assumptions),
            "evaluation_note": "Evalueringen måler endring i grunnlag og beslutning, ikke bare kortsiktig avkastning.",
        })
    return evaluations


__all__ = [
    "DECISION_INTELLIGENCE_SCHEMA_VERSION",
    "build_candidate_decision_diff",
    "build_counter_hypothesis",
    "build_decision_diffs",
    "build_historical_evaluations",
    "candidate_price",
    "enrich_candidate_contracts",
]
