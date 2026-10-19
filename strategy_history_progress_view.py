"""Live, read-only historical strategy test progress for both portfolio pages."""
from __future__ import annotations

def snapshot(storage):
    record = storage.read_json("strategy_history/progress.json", {}) or {}
    total = max(0, int(record.get("total") or 0))
    done = max(0, int(record.get("completed") or 0))
    rejected = max(0, int(record.get("rejected") or 0))
    return {
        "status": str(record.get("status") or "IKKE_STARTET"),
        "total": total, "done": done, "rejected": rejected,
        "pct": 100.0 * done / total if total else None,
        "processed_pct": 100.0 * min(total, done + rejected) / total if total else None,
        "updated_at": record.get("updated_at"),
        "reason": str(record.get("reason") or ""),
        "batch_completed": record.get("batch_completed"),
        "batch_total": record.get("batch_total"),
    }

def render(st):
    from services.storage_service import get_storage_service
    st.subheader("📈 Strategitesting – historisk fremdrift")
    try:
        progress = snapshot(get_storage_service())
    except Exception as exc:
        st.error(f"Fremdriftsdata utilgjengelige: {type(exc).__name__}")
        return
    status = progress["status"]
    st.caption(f"Jobbstatus: {status} · Sist oppdatert: {progress['updated_at'] or 'Ikke registrert'}")
    if progress["reason"]:
        st.warning(f"Årsak: {progress['reason']}")
    cols = st.columns(3)
    cols[0].metric("Aksjer analysert", f"{progress['done']:,} / {progress['total']:,}".replace(",", " "))
    cols[1].metric("Avvist / utilstrekkelige data", progress["rejected"])
    cols[2].metric("Datainnsamling", f"{progress['pct']:.1f} %" if progress["pct"] is not None else "Ikke målt")
    if progress["pct"] is not None:
        st.progress(min(1.0, progress["pct"] / 100))
        st.caption(f"Ferdig behandlet inkl. avviste: {progress['processed_pct']:.1f} %. Avviste regnes ikke som analyserte.")
    st.caption("Datakontroll, grovtesting, finjustering og historisk sluttvalidering: "
               "Ikke målt separat. Strategiforsøk og validerte finalister: Ikke målt. "
               "Gjenstående tid: Ikke beregnet uten pålitelig hastighetsmåling.")
    st.caption("Historiske OHLC og resultater lagres under strategy_history/prices/ og strategy_history/results/. "
               "Dette er utforskende simulering, ikke godkjente strategiresultater.")
