"""Streamlit renderer for Super Portfolio RC16.32c."""
from __future__ import annotations


def render_super_portfolio(_legacy_context) -> None:
    from ui.legacy_context import bind_legacy_context
    bind_legacy_context(globals(), _legacy_context, preserve={"render_super_portfolio"})
    import pandas as pd
    from super_portfolio import (
        build_pdf,
        evaluate,
        load_state,
        manual_exit,
        master_checklist,
        notify_changes,
        publish_pdf_report,
    )

    st.markdown("## 🌍 AI Super Portfolio")
    st.caption(
        "Isolert Shadow-portefølje. Daglig analyse og stop-overvåking, ordinær ukentlig rebalansering, "
        "myke sektor-/korrelasjonsstraffer, Ranking Velocity og Stop Pressure. Ingen ekte ordre sendes."
    )
    state = load_state()
    positions = list((state.get("positions") or {}).values())
    health = state.get("portfolio_health") or {}

    c1,c2,c3,c4,c5 = st.columns(5)
    total_weight = sum(float(p.get("target_weight_pct") or 0) for p in positions)
    weighted_return = (
        sum(float(p.get("pnl_pct") or 0) * float(p.get("target_weight_pct") or 0) for p in positions) / total_weight
        if positions and total_weight > 0 else 0.0
    )
    c1.metric("Posisjoner", len(positions))
    c2.metric("📈 Siden start", f"{weighted_return:+.2f}%")
    c3.metric("🧬 Health", f"{health.get('icon','⚪')} {float(health.get('score') or 0):.1f}/100")
    c4.metric("Modus", "SHADOW")
    c5.metric("Kilde", state.get("source_run_id") or "-")

    if health.get("components"):
        hc = health["components"]
        st.caption(
            f"🧠 Quality {float(hc.get('quality') or 0):.1f} · 🛡️ Risk {float(hc.get('risk') or 0):.1f} · "
            f"🧬 Diversification {float(hc.get('diversification') or 0):.1f} · 🚦 Stop safety {float(hc.get('stop_safety') or 0):.1f} · "
            f"🔗 Correlation {float(hc.get('correlation') or 0):.1f}"
        )

    a,b,c = st.columns(3)
    if a.button("🧠 Vurder porteføljen nå", type="primary", width="stretch"):
        with st.spinner("Analyserer kandidater, korrelasjon, stop-pressure og challengers..."):
            result = evaluate(persist=True, rebalance_policy="ANALYZE_ONLY")
        st.success(
            f"Vurdering ferdig: {len(result['changes'])} faktisk(e) Shadow-endring(er). "
            f"Ordinær rebalansering: {'JA' if result.get('rebalance_due') else 'NEI'}."
        )
        st.session_state["sp_last_changes"] = result["changes"]
        st.rerun()
    if b.button("📄 Publiser delbar PDF", width="stretch"):
        report = publish_pdf_report(state)
        if report.get("report_url"):
            st.session_state["sp_last_report_url"] = report["report_url"]
            st.success("PDF publisert.")
        else:
            st.info("PDF er lagret, men offentlig base-URL er ikke tilgjengelig i dette miljøet.")
    if c.button("📲 Varsle siste endringer", width="stretch"):
        ok,detail = notify_changes(state.get("last_changes") or st.session_state.get("sp_last_changes") or [], state)
        (st.success if ok else st.error)("Pushover sendt." if ok else f"Pushover feilet: {detail}")

    report_url = st.session_state.get("sp_last_report_url")
    pdf_bytes = build_pdf(state)
    d1,d2 = st.columns(2)
    d1.download_button(
        "⬇️ Last ned gjeldende PDF",
        data=pdf_bytes,
        file_name=f"SuperPortfolio_{str(state.get('updated_at') or 'latest')[:10]}.pdf",
        mime="application/pdf",
        width="stretch",
        key="sp_download_pdf_rc1632c",
    )
    if report_url:
        d2.link_button("🔗 Åpne / del publisert PDF", report_url, width="stretch")
    else:
        d2.caption("Publiser PDF først for delbar lenke.")

    if positions:
        rows=[]
        for p in positions:
            score = float(p.get("portfolio_score_adjusted") or p.get("portfolio_score") or 0)
            rows.append({
                "Stop":f"{p.get('stop_icon','')} {p.get('stop_status','')}",
                "Press":f"{p.get('stop_pressure_icon','')} {p.get('stop_pressure','')} {p.get('stop_direction_arrow','→')}",
                "Aksje":p.get("ticker"),"Marked":p.get("market"),"Sektor":p.get("sector"),
                "Vekt %":p.get("target_weight_pct"),"Fra inn %":p.get("pnl_pct"),"Fra topp %":p.get("drawdown_from_peak_pct"),
                "Til stop %":p.get("distance_to_hard_stop_pct"),"Stopkurs":p.get("hard_stop_price"),
                "AI-score":score,"Rank":f"#{p.get('rank','-')} {p.get('rank_arrow','→')}","Δ rank":p.get("rank_change"),
                "Sektorstraff":p.get("sector_penalty"),"Korr.straff":p.get("correlation_penalty"),"Risiko":p.get("risk_score")
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        st.markdown("### 🧠 Hvorfor er aksjene med?")
        for p in sorted(positions, key=lambda x: int(x.get("rank") or 999)):
            reasons = p.get("why_here") or []
            if reasons:
                st.write(f"**{p.get('ticker')}** · " + " · ".join(str(x) for x in reasons))

        st.markdown("### 🛡️ Stop Pressure")
        for p in sorted(positions,key=lambda x: float(x.get("distance_to_hard_stop_pct") or 999)):
            st.write(
                f"{p.get('stop_pressure_icon','')} **{p.get('ticker')}** · {p.get('stop_pressure','LOW')} {p.get('stop_direction_arrow','→')} · "
                f"{float(p.get('distance_to_hard_stop_pct') or 0):.2f}% til hard stop · "
                f"hard stop {float(p.get('hard_stop_drawdown_pct') or 0):.1f}% fra topp · "
                f"Δ avstand {float(p.get('stop_distance_change_pct') or 0):+.2f} pp · P/L {float(p.get('pnl_pct') or 0):+.2f}%"
            )

        movers = sorted(positions, key=lambda p: float(p.get("rank_velocity") or 0), reverse=True)
        st.markdown("### 🚀 Ranking Velocity")
        st.write(" · ".join(f"**{p.get('ticker')}** #{p.get('rank','-')} {p.get('rank_arrow','→')} ({float(p.get('rank_change') or 0):+g})" for p in movers[:8]))

        with st.expander("👤 Manuell exit", expanded=False):
            ticker=st.selectbox("Aksje", [p.get("ticker") for p in positions], key="sp_manual_exit_ticker")
            note=st.text_input("Kommentar", key="sp_manual_exit_note")
            st.caption("Manuell exit gir 10 dagers cooldown som standard. Aksjen følges fortsatt i Shadow-listen under cooldown.")
            if st.button("Registrer manuell exit", key="sp_manual_exit_button"):
                result=manual_exit(ticker,note)
                if result.get("ok"):
                    st.success(f"{ticker} registrert som manuell exit til {result.get('cooldown_until')}.")
                    st.rerun()
                else:
                    st.error(result.get("reason") or "Kunne ikke registrere exit")
    else:
        st.info("Ingen Super Portfolio ennå. Første gyldige Investment Pipeline-kjøring med kandidater og prisdata oppretter startporteføljen.")

    manual_shadow = state.get("manual_exit_shadow") or []
    if manual_shadow:
        with st.expander("👤 Manuelle exits som fortsatt følges i Shadow", expanded=False):
            st.dataframe(pd.DataFrame(manual_shadow), width="stretch", hide_index=True)

    st.markdown("### 💭 AI WOULD DO TODAY")
    st.caption("Kun rådgivende Shadow-visning – utfører ingen ordinær handel eller rebalansering før planlagt rebalanseringsdag. Hard stop kan likevel utløses umiddelbart.")
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
    else:
        st.caption("Ingen challengers lagret ennå.")

    history = state.get("history") or []
    with st.expander("📜 Endringshistorikk", expanded=False):
        events=[]
        for snap in reversed(history):
            for change in snap.get("changes") or []:
                events.append({
                    "Dato":snap.get("at"),"Handling":change.get("action"),"Aksje":change.get("ticker"),
                    "Fra %":change.get("from_pct"),"Til %":change.get("to_pct"),"Årsak":change.get("reason"),"Kode":change.get("reason_code")
                })
        if events:
            st.dataframe(pd.DataFrame(events[:250]), width="stretch", hide_index=True)
        else:
            st.caption("Ingen faktiske Shadow-endringer registrert ennå.")

    with st.expander("✅ Super Portfolio – master-checkliste / release gate", expanded=False):
        checklist = master_checklist()
        icons = {"DONE":"✅", "PARTIAL":"🟡", "MISSING":"❌", "BLOCKED":"🚫"}
        done = sum(1 for row in checklist if row.get("status") == "DONE")
        st.caption(f"{done}/{len(checklist)} punkter er ferdige. Delvis/manglende punkter blir stående synlig til de faktisk er løst.")
        st.dataframe(pd.DataFrame([{
            "Status":f"{icons.get(row.get('status'),'•')} {row.get('status')}",
            "Punkt":row.get("label"),
            "Nøkkel":row.get("key"),
        } for row in checklist]), width="stretch", hide_index=True)
