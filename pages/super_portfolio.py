"""Streamlit renderer for Super Portfolio RC16.32b."""
from __future__ import annotations


def render_super_portfolio(_legacy_context) -> None:
    from ui.legacy_context import bind_legacy_context
    bind_legacy_context(globals(), _legacy_context, preserve={"render_super_portfolio"})
    import pandas as pd
    from super_portfolio import evaluate, load_state, manual_exit, notify_changes, publish_pdf_report

    st.markdown("## 🌍 AI Super Portfolio")
    st.caption("Isolert Shadow-portefølje. Myke sektor-/korrelasjonsstraffer, ranking velocity og stop pressure. Ingen ekte ordre sendes.")
    state = load_state(); positions = list((state.get("positions") or {}).values())
    health = state.get("portfolio_health") or {}
    c1,c2,c3,c4,c5 = st.columns(5)
    avg = sum(float(p.get("pnl_pct") or 0) for p in positions)/len(positions) if positions else 0.0
    c1.metric("Posisjoner", len(positions))
    c2.metric("Snitt siden inn", f"{avg:+.2f}%")
    c3.metric("🧬 Health", f"{health.get('icon','⚪')} {float(health.get('score') or 0):.1f}/100")
    c4.metric("Modus", "SHADOW")
    c5.metric("Kilde", state.get("source_run_id") or "-")

    if health.get("components"):
        hc = health["components"]
        st.caption(
            f"🧠 Quality {float(hc.get('quality') or 0):.1f} · 🛡️ Risk {float(hc.get('risk') or 0):.1f} · "
            f"🧬 Diversification {float(hc.get('diversification') or 0):.1f} · 🚦 Stop safety {float(hc.get('stop_safety') or 0):.1f}"
        )

    a,b,c = st.columns(3)
    if a.button("🧠 Vurder porteføljen nå", type="primary", width="stretch"):
        with st.spinner("Rangerer kandidater, måler konsentrasjon og vurderer porteføljen..."):
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
            score = float(p.get("portfolio_score_adjusted") or p.get("portfolio_score") or 0)
            rows.append({
                "Stop":f"{p.get('stop_icon','')} {p.get('stop_status','')}",
                "Press":f"{p.get('stop_pressure_icon','')} {p.get('stop_pressure','')} {p.get('stop_direction_arrow','→')}",
                "Aksje":p.get("ticker"),"Marked":p.get("market"),"Sektor":p.get("sector"),
                "Vekt %":p.get("target_weight_pct"),"Fra inn %":p.get("pnl_pct"),"Fra topp %":p.get("drawdown_from_peak_pct"),
                "Til stop %":p.get("distance_to_hard_stop_pct"),"AI-score":score,
                "Rank":f"#{p.get('rank','-')} {p.get('rank_arrow','→')}","Δ rank":p.get("rank_change"),
                "Sektorstraff":p.get("sector_penalty"),"Korr.straff":p.get("correlation_penalty"),"Risiko":p.get("risk_score")
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        st.markdown("### 🛡️ Stop Pressure")
        for p in sorted(positions,key=lambda x: float(x.get("distance_to_hard_stop_pct") or 999)):
            st.write(
                f"{p.get('stop_pressure_icon','')} **{p.get('ticker')}** · {p.get('stop_pressure','LOW')} {p.get('stop_direction_arrow','→')} · "
                f"{float(p.get('distance_to_hard_stop_pct') or 0):.2f}% til hard stop · "
                f"Δ avstand {float(p.get('stop_distance_change_pct') or 0):+.2f} pp · P/L {float(p.get('pnl_pct') or 0):+.2f}%"
            )

        movers = sorted(positions, key=lambda p: float(p.get("rank_velocity") or 0), reverse=True)
        st.markdown("### 🚀 Ranking Velocity")
        st.write(" · ".join(f"**{p.get('ticker')}** #{p.get('rank','-')} {p.get('rank_arrow','→')} ({float(p.get('rank_change') or 0):+g})" for p in movers[:8]))

        with st.expander("👤 Manuell exit", expanded=False):
            ticker=st.selectbox("Aksje", [p.get("ticker") for p in positions], key="sp_manual_exit_ticker")
            note=st.text_input("Kommentar", key="sp_manual_exit_note")
            if st.button("Registrer manuell exit", key="sp_manual_exit_button"):
                result=manual_exit(ticker,note)
                if result.get("ok"): st.success(f"{ticker} registrert som manuell exit."); st.rerun()
                else: st.error(result.get("reason") or "Kunne ikke registrere exit")
    else:
        st.info("Ingen Super Portfolio ennå. Kjør vurderingen når Investment Pipeline har kandidater med prisdata.")

    st.markdown("### 💭 AI WOULD DO TODAY")
    st.caption("Kun rådgivende Shadow-visning – dette utfører ingen handel eller rebalansering.")
    advisory = state.get("ai_would_do_today") or []
    if advisory:
        icons={"BUY":"🟢","ADD":"🔵","REDUCE":"🟠","SELL":"🔴"}
        for action in advisory:
            st.write(f"{icons.get(action.get('action'),'•')} **{action.get('action')} {action.get('ticker')}** · {float(action.get('from_pct') or 0):.1f}% → {float(action.get('to_pct') or 0):.1f}%")
    else:
        st.caption("Ingen foreslåtte endringer akkurat nå.")

    challengers=state.get("challengers") or []
    st.markdown("### ⚔️ Challengers")
    if challengers:
        st.dataframe(pd.DataFrame([{
            "Aksje":r.get("ticker"),"Marked":r.get("market"),"Sektor":r.get("sector"),
            "AI score":r.get("portfolio_score_adjusted",r.get("portfolio_score")),"Rank":f"#{r.get('rank','-')} {r.get('rank_arrow','→')}",
            "Δ rank":r.get("rank_change"),"Sektorstraff":r.get("sector_penalty"),"Korr.straff":r.get("correlation_penalty"),"Risiko":r.get("risk_score")
        } for r in challengers]),width="stretch",hide_index=True)
    else: st.caption("Ingen challengers lagret ennå.")
