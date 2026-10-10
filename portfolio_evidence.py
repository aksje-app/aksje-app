"""Pure presentation and exposure helpers; no trading or persistence."""
from __future__ import annotations
from typing import Any, Mapping

# Business exposure differs from a provider's broad sector. Source checked
# 2026-10-10: https://hafnia.com/about-hafnia/ (OSE HAFNI / NYSE HAFN).
BUSINESS_OVERRIDES = {
    "HAFNI.OL": ("Shipping – produkttank", "https://hafnia.com/about-hafnia/"),
    "HAFN": ("Shipping – produkttank", "https://hafnia.com/about-hafnia/"),
}

def classification(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
    override = BUSINESS_OVERRIDES.get(ticker)
    raw = row.get("raw_candidate") if isinstance(row.get("raw_candidate"), Mapping) else row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    nested = raw.get("raw") if isinstance(raw.get("raw"), Mapping) else {}
    industry = str(row.get("industry") or raw.get("industry") or nested.get("industry") or "").strip()
    sector = str(row.get("sector") or "Ukjent").strip()
    text = (industry + " " + sector).upper()
    tags = set()
    if override or any(x in text for x in ("SHIPPING", "MARITIME", "MARINE", "TANKER", "SJØTRANSPORT")):
        tags.add("SHIPPING")
    if not override and any(x in text for x in ("ENERGY", "OFFSHORE", "OIL", "GAS")):
        tags.add("ENERGY")
    if "TECH" in text:
        tags.add("TECHNOLOGY")
    known = bool(override or industry.upper() not in {"", "UKJENT", "UNKNOWN", "NONE", "BROAD EQUITY"})
    return {"industry": override[0] if override else industry or "Ukjent",
            "risk_tags": sorted(tags), "classification_source": override[1] if override else "PROVIDER",
            "classification_known": known}

def rank_text(position: Mapping[str, Any]) -> str:
    entry, current = position.get("entry_rank"), position.get("rank")
    left = f"#{entry}" if entry is not None else "ukjent"
    right = f"#{current}" if current is not None else "ukjent"
    if entry is None or current is None:
        return f"{left} → {right}"
    delta = int(entry) - int(current)
    label = f"forbedret {delta} plasser" if delta > 0 else f"svekket {-delta} plasser" if delta < 0 else "uendret"
    return f"{left} → {right} · {label}"

def score_text(position: Mapping[str, Any]) -> str:
    entry = position.get("entry_portfolio_score")
    current = position.get("portfolio_score_adjusted", position.get("portfolio_score"))
    def fmt(value):
        return "ukjent" if value is None else f"{float(value):.1f}"
    return f"{fmt(entry)} → {fmt(current)}"

def retention_explanation(ticker: str, state: Mapping[str, Any]) -> str:
    trace = ((state.get("decision_trace") or {}).get("by_ticker") or {}).get(ticker) or {}
    action = str(trace.get("action") or "HOLD")
    status = str(trace.get("action_execution_status") or "")
    if action == "SELL" and status in {"BLOCKED", "ADVISORY_ONLY"}:
        reason = "venter på ordinær omvekting" if status == "ADVISORY_ONLY" else "utskifting blokkert"
        return f"Beholdes: {reason}. Forslag: {trace.get('action_reason') or trace.get('exclusion_reason') or 'salg'}."
    if action in {"REDUCE", "ADD"} and status != "EXECUTABLE":
        return f"Beholdes med dagens vekt: {action} er {status or 'ikke utført'}."
    gate = (state.get("entry_gate") or {}).get(ticker) or {}
    if gate.get("retained_due_to_blocked_challenger"):
        return "Beholdes: utfordrerens kjøpskrav er ikke oppfylt."
    if trace.get("target_selected"):
        return "Beholdes: valgt i målporteføljen; ingen risikosalgsregel utløst."
    if trace:
        return f"Beholdes: ingen utført utskifting. Vurderingskode: {trace.get('exclusion_reason') or 'HOLD'}."
    return "Beholdningsgrunnlag ikke lagret for denne vurderingen."

def stop_alert_text(alerts) -> str:
    blocks = ["🛡️ SUPERPORTEFØLJE – STOPPKONTROLL"]
    for row in list(alerts)[:8]:
        current, stop = float(row.get("current_price") or 0), float(row.get("stop_price") or 0)
        entry = float(row.get("entry_price") or 0)
        stop_result = f"{100 * (stop / entry - 1):+.2f}%" if entry > 0 and stop > 0 else "ukjent"
        fall = 100 * (current - stop) / current if current > 0 else None
        action, transition = row.get("action"), row.get("transition")
        headline = "solgt av risikoregel" if action == "SHADOW SELL UTFØRT" else "risikoen har økt – følg med" if transition == "ESCALATION" else "stoppsituasjonen er forbedret – ingen handling"
        margin = "ukjent" if fall is None else f"{max(0, fall):.2f}%"
        if fall is not None and fall <= 0:
            margin = "salgsgrensen er nådd/passert"
        blocks.append("\n".join([
            f"{row.get('ticker') or '-'}: {headline}",
            f"Kjøpskurs {float(row.get('entry_price') or 0):.2f} · topp {float(row.get('peak_price') or 0):.2f}",
            f"Siste kurs {current:.2f} · gevinst/tap {float(row.get('pnl_pct') or 0):+.2f}%",
            f"Salgsgrense {stop:.2f} · status {row.get('to') or '-'}",
            f"Mulig kursfall før salgsgrensen nås: {margin}",
            f"Beregnet gevinst/tap ved salgsgrensen: {stop_result}",
        ]))
    blocks.append("Gevinstbeskyttelse aktiveres ved minst +2% registrert toppgevinst. En andel av toppgevinsten beholdes; ellers maks trailing stop 3%. Salgsgrensen er en utløser, ikke garantert salgskurs. Kostnader kommer i tillegg.")
    return "\n\n".join(blocks)
