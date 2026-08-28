"""Norwegian report language helpers for AI Aksje Analyzer Pro.

v19.0.16 centralizes user-facing Norwegian labels for reports, exports and
status badges. Technical identifiers (tickers, IDs, currency codes and source
URLs) remain unchanged; raw model/status values should only be shown in
technical-reference sections.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# Keep keys uppercase for case-insensitive exact lookup.
DECISION_LABELS: dict[str, str] = {
    "BUY": "Kjøp",
    "STRONG_BUY": "Sterkt kjøp",
    "HOLD": "Behold",
    "SELL": "Selg",
    "AVOID": "Unngå",
    "SKIP": "Ikke aktuell",
    "REVIEW": "Undersøk manuelt",
    "MANUAL_REVIEW": "Undersøk manuelt",
    "REVIEW_ONLY": "Kun vurdering",
    "UNDERSØK_MANUELT": "Undersøk manuelt",
    "OVERVÅKES_AUTOMATISK": "Overvåkes automatisk",
    "AUTOMATISK_AVVIST": "Automatisk avvist",
    "KJØPSKANDIDAT": "Kjøpskandidat",
    "APPROVE": "Godkjenn",
    "REJECT": "Avvis",
}

STATUS_LABELS: dict[str, str] = {
    "PASS": "OK",
    "OK": "OK",
    "ERROR": "Feil",
    "FAILED": "Feilet",
    "FAIL": "Feilet",
    "IDLE": "Venter",
    "ACTIVE": "Aktiv",
    "INACTIVE": "Inaktiv",
    "PENDING": "Venter",
    "PENDING_APPROVAL": "Venter på godkjenning",
    "APPROVED": "Godkjent",
    "REJECTED": "Avvist",
    "VERIFIED": "Verifisert",
    "UNVERIFIED": "Ikke verifisert",
    "PARTIAL": "Delvis verifisert",
    "STALE": "Utdatert",
    "NOT_SEARCHED": "Ikke søkt",
    "SEARCHED_RESULTS_FOUND": "Søkt - resultater funnet",
    "SEARCHED_NO_RESULTS": "Søkt - ingen relevante resultater",
    "SEARCH_FAILED": "Søk feilet",
    "NOT_SEARCHED_BUDGET": "Ikke søkt - budsjettregel",
    "NOT_SEARCHED_DISABLED": "Ikke søkt - deaktivert eller ikke konfigurert",
    "NOT_SEARCHED_UNSUPPORTED": "Ikke søkt - kilde ikke støttet",
    "NOT_SEARCHED_POLICY": "Ikke søkt - prioriteringsregel",
    "NOT_APPLICABLE": "Ikke relevant",
    "CHECKED_NO_EVENTS": "Kontrollert – ingen hendelser",
    "VERIFIED_FACTS_FOUND": "Primærverifiserte fakta funnet",
    "SECONDARY_FACTS_FOUND": "Sekundære strukturerte fakta – primærkilde ikke verifisert",
    "VERIFIED_FACTS_NONE": "Kontrollert – ingen faktafunn",
    "PARTIAL_SOURCE_FAILURE": "Delvis kildefeil",
    "RATE_LIMITED": "Midlertidig begrenset",
    "DAILY_QUOTA_EXCEEDED": "Døgnbudsjett brukt",
    "SOURCE_ERROR": "Kildefeil",
    "SKIPPED": "Hoppet over",
    "SKIPPED_BUDGET_POLICY": "Hoppet over av budsjettregel",
    "SKIPPED_BUDGET_RESERVE": "Hoppet over av budsjettreserve",
    "WARNING": "Advarsel",
    "DISABLED": "Deaktivert",
    "THEORETICAL_ONLY": "Kun teoretisk",
    "SENT": "Sendt",
    "SUCCESS": "Vellykket",
    "COMPLETED_WITH_ERRORS": "Fullført med feil",
    "RUNNING": "Kjører",
    "COMPLETED": "Fullført",
    "AVAILABLE": "Tilgjengelig",
    "MISSING": "Mangler",
    "VALID": "Gyldig",
    "INVALID": "Ugyldig",
    "SUCCESS_NO_RESULTS": "Vellykket – ingen resultater",
    "SUCCESS_WITH_RESULTS": "Vellykket – resultater funnet",
    "STRUCTURED_PROVIDER": "Strukturert dataleverandør",
    "PUBLISHED_SOURCE": "Publisert kilde",
    "SECONDARY_AGGREGATOR": "Sekundær aggregator",
    "SECONDARY_SOURCE_DISCOVERY": "Sekundær kildeoppdagelse",
    "PRIMARY_OR_DIRECT": "Primær eller direkte kilde",
    "NOT_ATTEMPTED": "Ikke forsøkt",
    "OFFICIAL_PRIMARY": "Offisiell primærkilde",
    "DIRECT_PRIMARY": "Direkte primærkilde",
    "OFFICIAL_EXCHANGE_FEED": "Offisiell børsmeldingskilde",
    "DISCOVERY_ONLY": "Kun kildeoppdagelse",
    "INSIDER PARTIAL SOURCE FAILURE": "Delvis kildefeil for innsiderdata",
    "INSIDER NOT SEARCHED": "Innsiderdata ikke søkt",
    "NEWS NOT SEARCHED": "Nyheter ikke søkt",
    "SOURCE CHECK PARTIAL": "Kildekontroll delvis",
    "EVIDENCE_DATA_READY": "Evidens- og dataklar",
    "FINAL_DECISION_READY": "Endelig beslutningsklar",
    "AUTONOMY_THEORETICAL_BUY": "Teoretisk autonomt kjøp",
    "AUTONOMY_LEARNING_BUY": "Autonomt læringskjøp",
    "KREVER MANUELL VURDERING": "Undersøk manuelt",
    "KREVER MANUELL VURDERING – DOKUMENTASJON": "Undersøk manuelt – manglende dokumentasjon",
    "MANUELL VURDERING": "Undersøk manuelt",
    "DELVIS – MANUELL VURDERING": "Delvis – undersøk manuelt",
}

MODEL_ROLE_LABELS: dict[str, str] = {
    "PRODUCTION": "Produksjon",
    "CHALLENGER": "Utfordrer",
    "SHADOW": "Skyggemodell",
    "CANDIDATE": "Kandidat",
    "BASELINE": "Referansemodell",
}

COMPONENT_LABELS: dict[str, str] = {
    "AI DISCOVERY": "AI-funn",
    "DISCOVERY": "AI-funn",
    "AI RESEARCH ASSISTANT": "AI-analyseassistent",
    "RESEARCH": "Analyse",
    "BACKTEST": "Historisk test",
    "BACKTESTING": "Historisk test",
    "BACKTESTING VALIDATION": "Historisk test",
    "PORTFOLIO": "Portefølje",
    "PORTFOLIO FIT": "Porteføljetilpasning",
    "PORTFOLIO OPTIMIZER": "Porteføljeoptimalisering",
    "FUNDAMENTAL": "Fundamentalt",
    "VALIDATION": "Historisk test",
    "FUNDAMENTALS": "Fundamentalt",
    "MARKET SCANNER": "Markedsskanner",
    "STRATEGY MATCH": "Strategisjekk",
    "LEARNING ADVISOR": "Læringsrådgiver",
    "INSIDER INTELLIGENCE": "Innsideranalyse",
    "NEWS & SENTIMENT INTELLIGENCE": "Nyhets- og sentimentanalyse",
    "NEWS & SENTIMENT": "Nyheter og sentiment",
    "CONFIDENCE": "Sikkerhet",
    "QUALITY": "Kvalitet",
}

STRATEGY_LABELS: dict[str, str] = {
    "GROWTH": "Vekst",
    "MOMENTUM": "Momentum",
    "VALUE": "Verdi",
    "INCOME": "Inntekt/utbytte",
    "QUALITY": "Kvalitet",
    "EVENT RECOVERY": "Hendelsesdrevet gjeninnhenting",
    "INSIDER": "Innsider",
    "DEFENSIVE": "Defensiv",
    "SWING": "Swing",
    "AI GROWTH": "AI-vekst",
    "VALUE TREND": "Verditrend",
}

SECTOR_LABELS: dict[str, str] = {
    "INDUSTRIALS": "Industri",
    "CONSUMER": "Forbruk",
    "CONSUMER CYCLICAL": "Syklisk forbruk",
    "CONSUMER DEFENSIVE": "Stabilt forbruk",
    "CONSUMER STAPLES": "Stabilt forbruk",
    "CONSUMER DISCRETIONARY": "Syklisk forbruk",
    "MATERIALS": "Materialer",
    "BASIC MATERIALS": "Materialer",
    "ENERGY": "Energi",
    "FINANCIALS": "Finans",
    "FINANCIAL SERVICES": "Finans",
    "HEALTHCARE": "Helse",
    "HEALTH CARE": "Helse",
    "TECHNOLOGY": "Teknologi",
    "INFORMATION TECHNOLOGY": "Teknologi",
    "UTILITIES": "Forsyning",
    "REAL ESTATE": "Eiendom",
    "COMMUNICATION SERVICES": "Kommunikasjon",
    "COMMUNICATIONS": "Kommunikasjon",
}

WORD_LABELS: dict[str, str] = {
    **DECISION_LABELS,
    **STATUS_LABELS,
    **MODEL_ROLE_LABELS,
    **COMPONENT_LABELS,
    **STRATEGY_LABELS,
    **SECTOR_LABELS,
    "DASHBOARD": "Oversikt",
    "SCHEDULER": "Planlegger",
    "LEARNING PORTFOLIO": "Læringsportefølje",
    "PENDING APPROVALS": "Ventende godkjenninger",
    "EXPECTED IMPACT": "Forventet effekt",
    "RISK": "Risiko",
    "RISKS": "Risiko",
    "EVIDENCE": "Bevis",
    "SOURCE": "Kilde",
    "SOURCES": "Kilder",
    "NEWS": "Nyheter",
    "INSIDER": "Innsider",
    "POSITIVE": "Positiv",
    "NEGATIVE": "Negativ",
    "NEUTRAL": "Nøytral",
    "HIGH": "Høy",
    "MEDIUM": "Middels",
    "LOW": "Lav",
    "NORMAL": "Normal",
    "YFINANCE / PUBLIC FILINGS": "yfinance / offentlige innsidermeldinger",
    "YFINANCE COMPANY NEWS": "yfinance selskapsnyheter",
    "SEC / PUBLIC FILINGS": "SEC / offentlige innsidermeldinger",
    "SENT": "Sendt",
    "PUSHOVER SENT": "Pushover sendt",
    "AND": "og",
    "FOUND": "fant",
    "IMPROVED": "forbedret",
    "SIGNALS": "signaler",
    "REQUIRED": "kreves",
    "REQUIRES": "krever",
    "MODEL": "Modell",
    "GAVE": "ga",
    "PROOF": "Bevis",
    "INSIDER MISSING": "Innsiderinformasjon mangler",
    "PARTIAL SOURCE FAILURE": "Delvis kildefeil",
    "SOURCE FAILURE": "Kildeinnhenting feilet",
    "KILDE FAILURE": "Kildeinnhenting feilet",
    "EARNINGS": "Resultater",
    "DOCUMENT": "Dokumentasjon",
    "DECISION READY": "Endelig beslutningsklar",
    "EVIDENCE READY": "Evidens- og dataklar",
    "MISSION_INELIGIBLE": "Utenfor investeringsoppdraget",
    "SCORE_BELOW_THRESHOLD": "Score under streng kjøpsgrense",
    "RISK_ABOVE_THRESHOLD": "Risiko over tillatt grense",
    "MAX_OPEN_POSITIONS": "Ingen ledig posisjonsplass",
    "EVIDENCE_NOT_READY": "Evidensgrunnlaget er ikke beslutningsklart",
    "DATA_CONTRACT_INVALID": "Datagrunnlaget oppfyller ikke beslutningskravene",
    "STRATEGY_NOT_MATCHED": "Ingen godkjent strategi passer",
    "TECHNICAL_ENTRY_WAIT": "Teknisk inngangssignal står på vent",
}

# Longer phrases first so "Event Recovery" is handled before "Recovery" etc.
_PHRASE_ITEMS = sorted(WORD_LABELS.items(), key=lambda item: len(item[0]), reverse=True)
_TECHNICAL_PREFIXES = ("HTTP", "URL", "API", "SEC", "CVM")


def _key(value: Any) -> str:
    return str(value or "").strip().replace("-", "_").replace(" ", "_").upper()


def label_for(value: Any, fallback: str | None = None) -> str:
    """Return a Norwegian label for a raw status/role/term when known."""
    text = str(value or "").strip()
    if not text:
        return fallback or "-"
    exact = text.upper()
    normalized = _key(text)
    spaced = normalized.replace("_", " ")
    for mapping in (DECISION_LABELS, STATUS_LABELS, MODEL_ROLE_LABELS, COMPONENT_LABELS, STRATEGY_LABELS, SECTOR_LABELS, WORD_LABELS):
        if exact in mapping:
            return mapping[exact]
        if normalized in mapping:
            return mapping[normalized]
        if spaced in mapping:
            return mapping[spaced]
    return fallback if fallback is not None else text


def decision_label(value: Any) -> str:
    return label_for(value)


def component_label(value: Any) -> str:
    return label_for(value)


def sector_label(value: Any) -> str:
    return label_for(value)


def model_role_label(value: Any) -> str:
    return label_for(value)


def translate_list(values: Iterable[Any] | Any, sep: str = ", ") -> str:
    """Translate a comma-separated string or sequence into Norwegian labels."""
    if values is None:
        return "-"
    if isinstance(values, str):
        parts = [p.strip() for p in values.split(",") if p.strip()]
    else:
        parts = [str(v).strip() for v in values if str(v).strip()]
    if not parts:
        return "-"
    return sep.join(label_for(part) for part in parts)


def translate_report_text(value: Any) -> str:
    """Translate common user-facing English tokens inside report text.

    The function intentionally avoids guessing technical identifiers. It only
    replaces known complete phrases/words used by the app's reporting layer.
    """
    text = str(value if value is not None else "-")
    if not text or text == "-":
        return text
    # Fast exact lookup first.
    exact = label_for(text, fallback="")
    if exact:
        return exact

    out = text
    # Common underscore identifiers should be readable in ordinary report text.
    for raw, label in _PHRASE_ITEMS:
        # Match words/phrases, including values embedded in punctuation.
        pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(raw) + r"(?![A-Za-z0-9_])", re.IGNORECASE)
        out = pattern.sub(label, out)
        underscore = raw.replace(" ", "_")
        if underscore != raw:
            pattern_u = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(underscore) + r"(?![A-Za-z0-9_])", re.IGNORECASE)
            out = pattern_u.sub(label, out)
    return out


def decision_color(value: Any) -> str:
    raw = _key(value)
    if raw in {"BUY", "STRONG_BUY", "KJØPSKANDIDAT", "APPROVED", "PASS", "OK", "VERIFIED", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "VALID"}:
        return "#D9FBE5"  # green tint
    if raw in {"REVIEW", "MANUAL_REVIEW", "UNDERSØK_MANUELT", "OVERVÅKES_AUTOMATISK", "PENDING", "PENDING_APPROVAL", "PARTIAL", "SECONDARY_FACTS_FOUND", "PARTIAL_SOURCE_FAILURE", "RATE_LIMITED", "DAILY_QUOTA_EXCEEDED", "STALE"}:
        return "#FFF5CC"  # yellow tint
    if raw in {"SKIP", "AUTOMATISK_AVVIST", "SELL", "AVOID", "ERROR", "FAILED", "FAIL", "SOURCE_ERROR", "INVALID", "MISSING"}:
        return "#FFE1E1"  # red tint
    return "#F5F8FA"


def decision_text_color(value: Any) -> str:
    raw = _key(value)
    if raw in {"BUY", "STRONG_BUY", "KJØPSKANDIDAT", "APPROVED", "PASS", "OK", "VERIFIED", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "VALID"}:
        return "#166534"
    if raw in {"REVIEW", "MANUAL_REVIEW", "UNDERSØK_MANUELT", "OVERVÅKES_AUTOMATISK", "PENDING", "PENDING_APPROVAL", "PARTIAL", "SECONDARY_FACTS_FOUND", "PARTIAL_SOURCE_FAILURE", "RATE_LIMITED", "DAILY_QUOTA_EXCEEDED", "STALE"}:
        return "#92400E"
    if raw in {"SKIP", "AUTOMATISK_AVVIST", "SELL", "AVOID", "ERROR", "FAILED", "FAIL", "SOURCE_ERROR", "INVALID", "MISSING"}:
        return "#991B1B"
    return "#102A43"


def score_status(score: Any, *, buy_threshold: float = 73.0, review_margin: float = 5.0) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "REVIEW"
    if value >= buy_threshold:
        return "BUY"
    if value >= buy_threshold - review_margin:
        return "REVIEW"
    return "SKIP"


def quality_status(score: Any) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "REVIEW"
    if value >= 85:
        return "PASS"
    if value >= 65:
        return "REVIEW"
    return "ERROR"


def status_dot(value: Any) -> str:
    """Readable colored-dot status indicator for reports and exports."""
    raw = _key(value)
    if raw in {"BUY", "STRONG_BUY", "APPROVED", "PASS", "OK", "VERIFIED", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "VALID", "SENT", "SUCCESS"}:
        return "●"
    if raw in {"REVIEW", "MANUAL_REVIEW", "PENDING", "PENDING_APPROVAL", "PARTIAL", "SECONDARY_FACTS_FOUND", "PARTIAL_SOURCE_FAILURE", "RATE_LIMITED", "DAILY_QUOTA_EXCEEDED", "STALE", "WARNING", "NOT_SEARCHED"}:
        return "●"
    if raw in {"SKIP", "AUTOMATISK_AVVIST", "SELL", "AVOID", "ERROR", "FAILED", "FAIL", "SOURCE_ERROR", "INVALID", "MISSING"}:
        return "●"
    return "●"


USER_FACING_ENGLISH_BLOCKLIST = {
    "BUY", "SELL", "REVIEW", "SKIP", "VERIFIED", "CHALLENGER", "PRODUCTION",
    "Backtesting", "Growth", "Value", "Income", "Quality", "Event Recovery",
    "Research", "Confidence", "Portfolio & Decision Layer", "Shadow Mode",
}
