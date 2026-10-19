"""Superfond coverage and real historical-learning status, read only."""
from __future__ import annotations

def snapshot(data):
    coverage=data.get("coverage") or {}
    prior=data.get("prior_learning") or {}
    return {
        "at": data.get("at") or "",
        "listings": int(coverage.get("listings") or 0),
        "priced": int(coverage.get("fresh_prices") or 0),
        "funds": int((coverage.get("source_totals") or {}).get("fond") or 0),
        "etfs": int((coverage.get("source_totals") or {}).get("etf") or 0),
        "history_cap": int(coverage.get("history_points_cap_per_listing") or 0),
        "paired": int(prior.get("paired_dates") or 0),
        "required": int(prior.get("minimum_dates") or 80),
        "status": str(prior.get("status") or "UKJENT"),
        "history_status": str((data.get("archive_status") or {}).get("state") or "Ikke verifisert")
    }

def render(st, data):
    x=snapshot(data)
    st.subheader("📊 Superfond – datainnsamling og læring")
    cols=st.columns(3)
    cols[0].metric("Fond / ETF-noteringer", x["listings"])
    cols[1].metric("Ferske priser", x["priced"])
    cols[2].metric("Prisdekning", f"{100*x['priced']/x['listings']:.1f} %" if x["listings"] else "Ikke målt")
    if x["listings"]:
        st.progress(min(1.0,x["priced"]/x["listings"]))
    st.caption(f"Fond: {x['funds']} · ETF: {x['etfs']} · Snapshot: {x['at'] or 'Ukjent'}")
    st.markdown("**Historikk, bearbeiding og validering**")
    cols=st.columns(3)
    cols[0].metric("Historiske kursdager per produkt", f"Maks {x['history_cap']}" if x["history_cap"] else "Ikke målt")
    cols[1].metric("Bekreftede referansedatoer",f"{x['paired']} / {x['required']}")
    cols[2].metric("Massestrategitester", "Ikke startet")
    st.caption(f"Læringsstatus: {x['status']}. Historikk: {x['history_status']}.")
    st.caption("Katalogdekning er ikke flerårig historisk kursdekning. Fonds- og ETF-massetesting "
               "og validerte finalister er ikke registrert som gjennomført.")
