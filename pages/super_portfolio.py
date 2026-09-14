"""Streamlit renderer for Super Portfolio RC16.32a."""
from __future__ import annotations


def render_super_portfolio(_legacy_context) -> None:
    from ui.legacy_context import bind_legacy_context
    bind_legacy_context(globals(), _legacy_context, preserve={"render_super_portfolio"})
    import pandas as pd
    from super_portfolio import evaluate, load_state, manual_exit, notify_changes, publish_pdf_report

    st.markdown("## 🌍 AI Super Portfolio")
    st.caption("Isolert Shadow-portefølje. Bruker ferdige Analyzer-signaler; ingen ekte ordre sendes.")
    state = load_state(); positions = list((state.get("positions") or {}).values())
    c1,c2,c3,c4 = st.columns(4)
    avg = sum(float(p.get("pnl_pct") or 0) for p in positions)/len(positions) if positions else 0.0
    c1.metric("Posisjoner", len(positions)); c2.metric("Snitt siden inn", f"{avg:+.2f}%"); c3.metric("Modus", "SHADOW"); c4.metric("Kilde", state.get("source_run_id") or "-")

    a,b,c = st.columns(3)
    if a.button("🧠 Vurder porteføljen nå", type="primary", width="stretch"):
        with st.spinner("Rangerer kandidater og vurderer porteføljen..."):
            result=evaluate(persist=True)
        st.success(f"Vurdering ferdig: {len(result['changes'])} endring(er).")
        st.session_state["sp_last_changes"] = result["changes"]
        st.rerun()
    if b.button("📄 Lag delbar PDF", width="stretch"):
        report=publish_pdf_report(state)
        if report.get("report_url"): st.link_button("Åpne PDF", report["report_url"], width="stretch")
        else: st.info("PDF er lagret, men offentlig base-URL er ikke tilgjengelig i dette miljøet.")
    if c.button("📲 Varsle siste endringer", width="stretch"):
        ok,detail=notify_changes(st.session_state.get("sp_last_changes") or [], state)
        (st.success if ok else st.error)("Pushover sendt." if ok else f"Pushover feilet: {detail}")

    if positions:
        rows=[]
        for p in positions:
            rows.append({"Status":f"{p.get('stop_icon','')} {p.get('stop_status','')}","Aksje":p.get("ticker"),"Marked":p.get("market"),"Sektor":p.get("sector"),"Vekt %":p.get("target_weight_pct"),"Fra inn %":p.get("pnl_pct"),"Fra topp %":p.get("drawdown_from_peak_pct"),"Til hard stop %":p.get("distance_to_hard_stop_pct"),"AI-score":p.get("portfolio_score"),"Risiko":p.get("risk_score")})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.markdown("### 🛡️ Stop Watch")
        for p in sorted(positions,key=lambda x: float(x.get("distance_to_hard_stop_pct") or 999)):
            st.write(f"{p.get('stop_icon')} **{p.get('ticker')}** · {p.get('stop_status')} · {float(p.get('distance_to_hard_stop_pct') or 0):.2f}% til hard stop · P/L {float(p.get('pnl_pct') or 0):+.2f}%")
        with st.expander("👤 Manuell exit", expanded=False):
            ticker=st.selectbox("Aksje", [p.get("ticker") for p in positions], key="sp_manual_exit_ticker")
            note=st.text_input("Kommentar", key="sp_manual_exit_note")
            if st.button("Registrer manuell exit", key="sp_manual_exit_button"):
                result=manual_exit(ticker,note)
                if result.get("ok"): st.success(f"{ticker} registrert som manuell exit."); st.rerun()
                else: st.error(result.get("reason") or "Kunne ikke registrere exit")
    else:
        st.info("Ingen Super Portfolio ennå. Kjør vurderingen når Investment Pipeline har kandidater med prisdata.")

    challengers=state.get("challengers") or []
    st.markdown("### ⚔️ Challengers")
    if challengers:
        st.dataframe(pd.DataFrame([{"Aksje":r.get("ticker"),"Marked":r.get("market"),"Sektor":r.get("sector"),"Portfolio score":r.get("portfolio_score"),"Risiko":r.get("risk_score")} for r in challengers]),width="stretch",hide_index=True)
    else: st.caption("Ingen challengers lagret ennå.")
