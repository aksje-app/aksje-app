"""Read-only Superfond portfolio overview, based only on persisted snapshots."""
from collections import defaultdict

from superfund_presentation import resolve_identity, investment_group


def portfolio_rows(snapshot):
    model = snapshot.get("model") or {}
    positions = model.get("positions") or {}
    equity = float(model.get("cash") or 0) + sum(
        float(p.get("quantity") or 0) * float(p.get("last_nok") or 0)
        for p in positions.values() if isinstance(p, dict))
    rows = []
    for key, position in positions.items():
        if not isinstance(position, dict):
            continue
        info = resolve_identity(snapshot, position)
        value = float(position.get("quantity") or 0) * float(position.get("last_nok") or 0)
        cost = float(position.get("cost_nok") or 0)
        pnl = value - cost
        rows.append(dict(id=str(position.get("id") or key), name=str(position.get("name") or info.get("name") or key),
                         country=investment_group(info), sector=str(info.get("category") or "Ukjent kategori"),
                         value_nok=value, weight_pct=value / equity * 100 if equity > 0 else 0,
                         pnl_nok=pnl, pnl_pct=pnl / cost * 100 if cost > 0 else None,
                         info=info, position=position))
    return equity, rows


def render_overview(st, snapshot):
    equity, rows = portfolio_rows(snapshot)
    st.subheader("Porteføljeoversikt")
    if not rows:
        st.info("Ingen fond er kjøpt i modellen ennå.")
        return
    st.caption("Andel er beregnet av total modellverdi inkludert kontanter. Land viser kildens investeringsområde, ikke fondets registreringsland.")
    sort = st.selectbox("Sorter porteføljen", ["Størst andel", "Beste utvikling", "Svakeste utvikling", "Fond", "Land", "Kategori"], key="sf_overview_sort")
    key = {"Størst andel":lambda r:-r["weight_pct"],"Beste utvikling":lambda r:-(r["pnl_pct"] if r["pnl_pct"] is not None else -1e10),
           "Svakeste utvikling":lambda r:r["pnl_pct"] if r["pnl_pct"] is not None else 1e10,
           "Fond":lambda r:r["name"].casefold(),"Land":lambda r:r["country"].casefold(),
           "Kategori":lambda r:r["sector"].casefold()}[sort]
    ordered = sorted(rows,key=key)
    import pandas as pd
    table = pd.DataFrame([{"Fond/ETF":r["name"],"Land/region":r["country"],"Sektor/kategori":r["sector"],
                           "Verdi NOK":round(r["value_nok"]),"Andel %":round(r["weight_pct"],2),
                           "Resultat NOK":round(r["pnl_nok"]),"Siden kjøp %":round(r["pnl_pct"],2) if r["pnl_pct"] is not None else None} for r in ordered])
    st.dataframe(table,hide_index=True,use_container_width=True)
    st.caption("Trykk på fondets detaljer nedenfor for kursgraf og kjøpsinformasjon.")
    # This widget is already rendered inside the parent Portefølje expander:
    # do not nest Streamlit expanders, which breaks the surrounding menu tree.
    for field,title in (("country","Land/region"),("sector","Sektor/kategori")):
        values=defaultdict(float)
        for row in rows:
            values[row[field]] += row["value_nok"]
        st.markdown("**Fordeling · "+title+"**")
        for label,value in sorted(values.items(),key=lambda x:-x[1]):
            st.caption(f"{label}: {value:,.0f} NOK · {value/equity*100:.2f} %")
    return ordered
