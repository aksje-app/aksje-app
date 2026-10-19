"""Read-only progress of actual stored learning evidence, never invented percentages."""
from __future__ import annotations
from datetime import datetime, timezone

PHASES = (
    ("Innsamling av historiske kurser", "price_collection"),
    ("Datakontroll og klargjøring", "data_validation"),
    ("Grovtesting av strategier", "coarse_search"),
    ("Finjustering av parametere", "fine_search"),
    ("Historisk sluttvalidering", "holdout_validation"),
)

def percent(done, total):
    try:
        done, total = int(done), int(total)
        return round(100 * done / total) if 0 <= done <= total and total > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None

def snapshot(storage, engine):
    if engine not in {"AUTONOMY", "SUPER_PORTFOLIO"}:
        raise ValueError("Unsupported engine")
    shadow = storage.read_json(f"controlled_learning/forward/{engine}.json", {}) or {}
    index = storage.read_json("controlled_learning/history/index.json", {}) or {}
    records = [x for x in index.get("records", []) if isinstance(x, dict) and x.get("engine") == engine]
    dates = shadow.get("observed_trading_dates")
    return {
        "engine": engine, "last_at": shadow.get("last_at"),
        "state": shadow.get("status") or "IKKE_STARTET",
        "error": shadow.get("error") or shadow.get("reason") or "",
        "history_frames": len(records),
        "complete_frames": sum(x.get("complete_universe") is True for x in records),
        "shadow_days": dates if isinstance(dates, int) else len(dates) if isinstance(dates, list) else None,
        "validated": shadow.get("validated") is True,
        "phases": {key: None for _, key in PHASES},
        "stocks": None, "trials": None, "finalists": None,
    }

def render(st, engine):
    from services.storage_service import get_storage_service
    with st.expander("📊 Strategitesting og læring – faktisk fremdrift", expanded=False):
        try:
            data = snapshot(get_storage_service(), engine)
        except Exception as exc:
            st.error(f"Fremdrift utilgjengelig: {type(exc).__name__}. Ingen fremdrift antas.")
            return
        st.caption("Kun dokumenterte målinger. «Ikke målt» betyr at jobben ikke rapporterer fullførte arbeidsenheter.")
        st.write(f"**Shadow-status:** {data['state']} · **Siste registrering:** {data['last_at'] or 'Ikke registrert'}")
        if data["error"]:
            st.warning(f"Årsak: {data['error']}")
        for title, key in PHASES:
            fraction = data["phases"][key]
            st.write(f"{title}: **{fraction} %**" if fraction is not None else f"{title}: **Ikke målt**")
            if fraction is not None:
                st.progress(fraction / 100)
        st.write(f"Historiske opptak: **{data['history_frames']}** (komplette: **{data['complete_frames']}**)")
        st.write(f"Observerte Shadow-handelsdager: **{data['shadow_days'] if data['shadow_days'] is not None else 'Ikke målt'}**")
        st.write("Aksjer analysert: **Ikke målt** · Strategiforsøk: **Ikke målt** · Validerte finalister: **Ikke målt**")
        st.caption("Estimert tid igjen: Ikke tilgjengelig uten faktisk gjennomstrømming og kjent arbeidsmengde.")
