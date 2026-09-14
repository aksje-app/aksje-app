"""Streamlit renderer for Super Portfolio RC16.32g."""
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
        benchmark_summary,
        refresh_index_benchmark,
        resource_health,
        save_state,
        set_manual_aurora_benchmark,
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

    evaluation_running = bool(st.session_state.get("sp_evaluation_running", False))
    notice = st.session_state.pop("sp_evaluation_notice", None)
    error_notice = st.session_state.pop("sp_evaluation_error", None)
    if notice:
        st.success(notice)
    if error_notice:
        st.error(error_notice)

    a,b,c = st.columns(3)
    evaluate_clicked = a.button(
        "⏳ Jobber..." if evaluation_running else "🧠 Vurder porteføljen nå",
        type="primary",
        width="stretch",
        disabled=evaluation_running,
        key="sp_evaluate_portfolio_32g",
    )
    if evaluate_clicked and not evaluation_running:
        st.session_state["sp_evaluation_running"] = True
        st.session_state["sp_evaluation_requested"] = True
        st.rerun()

    if evaluation_running and st.session_state.get("sp_evaluation_requested", False):
        progress = st.progress(5, text="Starter Super Portfolio-vurdering...")
        try:
            progress.progress(20, text="Henter kandidat- og markedsgrunnlag...")
            progress.progress(40, text="Analyserer rangering, risiko og portefølje...")
            result = evaluate(persist=True, rebalance_policy="ANALYZE_ONLY")
            progress.progress(85, text="Oppdaterer challengers, stop-pressure og historikk...")
            st.session_state["sp_last_changes"] = result["changes"]
            progress.progress(100, text="Ferdig")
            st.session_state["sp_evaluation_notice"] = (
                f"Vurdering ferdig: {len(result['changes'])} faktisk(e) Shadow-endring(er). "
                f"Ordinær rebalansering: {'JA' if result.get('rebalance_due') else 'NEI'}."
            )
        except Exception as exc:
            st.session_state["sp_evaluation_error"] = f"Super Portfolio-vurdering feilet: {exc}"
        finally:
            st.session_state["sp_evaluation_running"] = False
            st.session_state["sp_evaluation_requested"] = False
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

    st.markdown("### 📊 Benchmark")
    bench = benchmark_summary(state, portfolio_return_pct=weighted_return)
    b1,b2,b3 = st.columns(3)
    idx = bench.get("index") or {}
    aur = bench.get("aurora") or {}
    b1.metric(str(idx.get("label") or "Indeks"), f"{float(idx.get('return_pct') or 0):+.2f}%", delta=f"Alpha {float(idx.get('alpha_pct') or 0):+.2f} pp" if idx.get("return_pct") is not None else None)
    b2.metric(str(aur.get("label") or "Aurora"), f"{float(aur.get('return_pct') or 0):+.2f}%", delta=f"Alpha {float(aur.get('alpha_pct') or 0):+.2f} pp" if aur.get("return_pct") is not None else None)
    confidence = state.get("decision_confidence") or {}
    b3.metric("🧠 Decision Confidence", f"{confidence.get('icon','⚪')} {float(confidence.get('score') or 0):.1f}/100")
    with st.expander("⚙️ Benchmark-innstillinger", expanded=False):
        presets={"STOXX Europe 600":"^STOXX","S&P 500":"^GSPC","OMX Stockholm 30":"^OMX","Oslo All Share":"OSEAX.OL"}
        current_cfg=dict(state.get("config") or {})
        current_label=str(current_cfg.get("benchmark_label") or "STOXX Europe 600")
        choice=st.selectbox("Automatisk indeks",list(presets),index=list(presets).index(current_label) if current_label in presets else 0,key="sp_benchmark_choice_32d")
        cidx,caur=st.columns(2)
        if cidx.button("🔄 Oppdater indeksbenchmark",width="stretch",key="sp_refresh_benchmark_32d"):
            current_cfg["benchmark_ticker"]=presets[choice]; current_cfg["benchmark_label"]=choice
            state["config"]=current_cfg; save_state(state); refresh_index_benchmark(state); st.rerun()
        aurora_return=caur.number_input("Aurora siden start (%)",value=float(aur.get("return_pct") or 0.0),step=0.1,key="sp_aurora_return_32d")
        if caur.button("💾 Lagre Aurora-benchmark",width="stretch",key="sp_save_aurora_32d"):
            set_manual_aurora_benchmark(aurora_return,label="Aurora"); st.rerun()

    st.markdown("### 🧯 Stress Radar")
    stress=state.get("stress_radar") or []
    if stress:
        st.dataframe(pd.DataFrame([{"Scenario":f"{r.get('icon','')} {r.get('label','')}","Eksponering %":r.get("exposure_pct"),"Sjokk %":r.get("shock_pct"),"Estimert porteføljeeffekt %":r.get("estimated_portfolio_impact_pct")} for r in stress]),width="stretch",hide_index=True)
    else:
        st.caption("Stress Radar fylles når startporteføljen er opprettet.")

    tc=state.get("turnover_costs") or {}
    st.markdown("### 💸 Turnover & kostnader")
    t1,t2,t3,t4=st.columns(4)
    t1.metric("Turnover",f"{float(tc.get('turnover_pct') or 0):.2f}%")
    t2.metric("Estimert kostnad",f"{float(tc.get('estimated_cost') or 0):,.0f}")
    t3.metric("Brutto",f"{float(tc.get('gross_return_pct') or weighted_return):+.2f}%")
    t4.metric("Etter kostnader",f"{float(tc.get('net_return_pct') or weighted_return):+.2f}%")

    st.markdown("### 🖥️ Ressurser")
    rh=state.get("resource_health") or {}
    if not rh:
        rh=resource_health()
    r1,r2,r3=st.columns(3)
    r1.metric("Status",f"{rh.get('icon','⚪')} {rh.get('status','-')}")
    r2.metric("Memory / cgroup",f"{float(rh.get('memory_used_pct') or 0):.1f}%")
    r3.metric("DB",f"{float(rh.get('db_used_pct') or 0):.1f}%")
    if st.button("🔄 Oppdater ressursstatus",key="sp_resource_refresh_32d"):
        state["resource_health"]=resource_health(); save_state(state); st.rerun()

    advisory = state.get("ai_would_do_today") or []

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
                "Sektorstraff":p.get("sector_penalty"),"Korr.straff":p.get("correlation_penalty"),"Risiko":p.get("risk_score"),
                "🕒 Data Freshness":f"{(p.get('data_freshness') or {}).get('icon','⚪')} {(p.get('data_freshness') or {}).get('status','-')}",
                "📅 Event Risk":f"{(p.get('event_risk') or {}).get('icon','⚪')} {(p.get('event_risk') or {}).get('date','-')}"
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        info_row_1 = st.columns(3)
        with info_row_1[0]:
            with st.expander("🧠 Hvorfor er aksjene med?", expanded=False):
                why_rows=[]
                for p in sorted(positions, key=lambda x: int(x.get("rank") or 999)):
                    reasons=p.get("why_here") or []
                    why_rows.append({
                        "Aksje":p.get("ticker"),
                        "AI":round(float(p.get("portfolio_score_adjusted") or p.get("portfolio_score") or 0),1),
                        "Risiko":round(float(p.get("risk_score") or 0),0),
                        "Rank":f"#{p.get('rank','-')} {p.get('rank_arrow','→')}",
                        "Forklaring":" · ".join(str(x) for x in reasons),
                    })
                st.dataframe(pd.DataFrame(why_rows), width="stretch", hide_index=True, height=280)

        with info_row_1[1]:
            with st.expander("🕒 Data Freshness", expanded=False):
                freshness_rows=[]
                for p in sorted(positions,key=lambda x: float((x.get("data_freshness") or {}).get("age_hours") or 9999)):
                    fr=p.get("data_freshness") or {}
                    freshness_rows.append({
                        "Aksje":p.get("ticker"),
                        "Status":f"{fr.get('icon','⚪')} {fr.get('status','-')}",
                        "Alder t":fr.get("age_hours","-"),
                    })
                st.dataframe(pd.DataFrame(freshness_rows), width="stretch", hide_index=True, height=280)

        with info_row_1[2]:
            with st.expander("📅 Event Risk", expanded=False):
                event_rows=[]
                upcoming=[p for p in positions if (p.get("event_risk") or {}).get("status")=="UPCOMING"]
                for p in sorted(upcoming,key=lambda x: int((x.get("event_risk") or {}).get("days_until") or 9999)):
                    ev=p.get("event_risk") or {}
                    event_rows.append({
                        "Aksje":p.get("ticker"),
                        "Dato":ev.get("date","-"),
                        "Dager":ev.get("days_until","-"),
                        "Status":f"{ev.get('icon','⚪')} {ev.get('status','-')}",
                    })
                if event_rows:
                    st.dataframe(pd.DataFrame(event_rows), width="stretch", hide_index=True, height=280)
                else:
                    st.caption("Ingen nærstående selskapsbegivenheter i tilgjengelige kandidatdata.")

        info_row_2 = st.columns(3)
        with info_row_2[0]:
            with st.expander("🛡️ Stop Pressure", expanded=False):
                stop_rows=[]
                for p in sorted(positions,key=lambda x: float(x.get("distance_to_hard_stop_pct") or 999)):
                    stop_rows.append({
                        "Aksje":p.get("ticker"),
                        "Press":f"{p.get('stop_pressure_icon','')} {p.get('stop_pressure','LOW')} {p.get('stop_direction_arrow','→')}",
                        "Til stop %":round(float(p.get("distance_to_hard_stop_pct") or 0),2),
                        "P/L %":round(float(p.get("pnl_pct") or 0),2),
                    })
                st.dataframe(pd.DataFrame(stop_rows), width="stretch", hide_index=True, height=280)

        with info_row_2[1]:
            with st.expander("🚀 Ranking Velocity", expanded=False):
                movers=sorted(positions, key=lambda p: float(p.get("rank_velocity") or 0), reverse=True)
                velocity_rows=[{
                    "Aksje":p.get("ticker"),
                    "Rank":f"#{p.get('rank','-')} {p.get('rank_arrow','→')}",
                    "Δ rank":float(p.get("rank_change") or 0),
                } for p in movers[:12]]
                st.dataframe(pd.DataFrame(velocity_rows), width="stretch", hide_index=True, height=280)

        with info_row_2[2]:
            with st.expander("💭 AI WOULD DO TODAY", expanded=False):
                st.caption("Kun rådgivende Shadow-visning. Ingen ordinær handel utføres her.")
                icons={"BUY":"🟢","ADD":"🔵","REDUCE":"🟠","SELL":"🔴"}
                advisory_rows=[{
                    "Handling":f"{icons.get(action.get('action'),'•')} {action.get('action')}",
                    "Aksje":action.get("ticker"),
                    "Fra %":round(float(action.get("from_pct") or 0),1),
                    "Til %":round(float(action.get("to_pct") or 0),1),
                } for action in advisory]
                if advisory_rows:
                    st.dataframe(pd.DataFrame(advisory_rows), width="stretch", hide_index=True, height=280)
                else:
                    st.caption("Ingen foreslåtte endringer akkurat nå.")

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
