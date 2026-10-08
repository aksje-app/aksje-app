"""Streamlit renderer for Super Portfolio RC16.32l."""
from __future__ import annotations


def _terminal_job_needs_app_refresh(job, refreshed_run_id: str) -> bool:
    """Return true once when a verified background result is newer than the page."""
    state_name = str((job or {}).get("state") or "").upper()
    successful_run_id = str((job or {}).get("latest_successful_run_id") or "")
    return bool(
        state_name in {"COMPLETED", "DEGRADED"}
        and successful_run_id
        and successful_run_id != str(refreshed_run_id or "")
    )


def render_super_portfolio(_legacy_context) -> None:
    from ui.legacy_context import bind_legacy_context
    bind_legacy_context(globals(), _legacy_context, preserve={"render_super_portfolio"})
    import pandas as pd
    from super_portfolio import (
        build_pdf,
        build_diagnostic_zip,
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
    from super_portfolio_jobs import (
        ACTIVE_STATES, diagnostic_zip as job_diagnostic_zip, get_job,
        recover_stale_job, request_control, start_job,
    )

    st.markdown("## 🌍 AI Super Portfolio")
    st.caption(
        "Isolert Shadow-portefølje. Daglig analyse og stop-overvåking, ordinær ukentlig rebalansering, "
        "myke sektor-/korrelasjonsstraffer, Ranking Velocity og Stop Pressure. Ingen ekte ordre sendes."
    )
    state = load_state()
    with st.expander("Offisielle innside- og short-hendelser", expanded=False):
        from services.storage_service import get_storage_service
        from market_event_discovery import KEY, purchase_clusters
        from datetime import datetime, timezone
        event_state = get_storage_service().read_json(KEY, {}) or {}
        st.caption("Norske primærkilder kontrolleres før finalistutvelgelsen. Hendelser utløser analyse; ordinære kjøps- og risikokrav gjelder fortsatt. Øvrige markeder har foreløpig ikke denne oppdagelsen.")
        for source, source_health in event_state.get("sources", {}).items():
            st.write(f"{source}: {source_health.get('status', 'UKJENT')} · siste kontroll {source_health.get('checked_at', 'ukjent')}")
        st.caption("Offentlig short er ikke total short interest. Bortfall fra registeret betyr under publiseringsgrensen / ukjent, og beviser ikke full inndekning.")
        analysis = state.get("market_scan_summary", {}).get("official_event_discovery", {}).get("analysis", [])
        if analysis:
            st.dataframe(pd.DataFrame([{"Aksje": r["ticker"], "Analyse": r["status"], "Finalist": r.get("finalist", False), "Hendelser": ", ".join(sorted({e["kind"] for e in r["events"]}))} for r in analysis]), use_container_width=True, hide_index=True)
        recent = event_state.get("events", [])[:50]
        if recent:
            st.dataframe(pd.DataFrame([{"Selskap": e["issuer"], "Hendelse": e["kind"], "Aktør": e.get("actor", "Uklassifisert"), "Dato": e["occurred_at"], "Offentlig short %": e.get("current_pct"), "Kilde": e["source_url"]} for e in recent]), use_container_width=True, hide_index=True)
        else:
            st.info("Ingen hendelser lastet. Dette bekrefter ikke at det ikke finnes innsidehandel eller short.")
        clusters = purchase_clusters(event_state.get("events", []), datetime.now(timezone.utc))
        if clusters:
            st.caption("Gjentatte eksplisitt bekreftede kjøp, gruppert per selskap, kjøper og valuta. Historikken bygges fra oppstart; dette er ikke en komplett 90-dagers tilbakefylling.")
            st.dataframe(pd.DataFrame(clusters), use_container_width=True, hide_index=True)
    positions = list((state.get("positions") or {}).values())
    health = state.get("portfolio_health") or {}

    total_weight = sum(float(p.get("target_weight_pct") or 0) for p in positions)
    weighted_return = (
        sum(float(p.get("pnl_pct") or 0) * float(p.get("target_weight_pct") or 0) for p in positions) / total_weight
        if positions and total_weight > 0 else 0.0
    )
    initial_cash = float(state.get("initial_cash") or 1_000_000.0)
    portfolio_value = float(state.get("portfolio_value") or initial_cash)
    portfolio_return = float(
        state.get("portfolio_return_pct")
        if state.get("portfolio_return_pct") is not None
        else ((portfolio_value / max(1.0, initial_cash)) - 1.0) * 100.0
    )
    advisory = list(state.get("ai_would_do_today") or [])
    advisory_by_ticker = {str(a.get("ticker") or ""): a for a in advisory if a.get("ticker")}

    st.markdown(
        """<style>
        .sp-quick-note{border:1px solid rgba(56,189,248,.32);background:rgba(15,23,42,.54);
        border-radius:12px;padding:.65rem .8rem;margin:.25rem 0 .6rem 0}
        .sp-quick-note b{font-size:1.02rem}
        @media (max-width: 760px){
          div[data-testid="stDataFrame"]{font-size:.88rem!important}
          .sp-quick-note{padding:.55rem .65rem}
        }
        </style>""", unsafe_allow_html=True,
    )

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Porteføljeverdi", f"NOK {portfolio_value:,.0f}")
    c2.metric("📈 Siden NAV-start", f"{portfolio_return:+.2f}%")
    c3.metric("Posisjoner", len(positions))
    c4.metric("🧬 Health", f"{health.get('icon','⚪')} {float(health.get('score') or 0):.1f}/100")
    c5.metric("Modus", "SHADOW")
    st.caption(
        f"Startkapital NOK {initial_cash:,.0f} · NAV-sporing fra {state.get('portfolio_tracking_started_at') or '-'} · "
        f"Åpne posisjoner vektet fra inngang {weighted_return:+.2f}% · Kilde {state.get('source_run_id') or '-'}"
    )

    # Beslutningsoversikt først: ticker, alvorlighet og handling - ikke interne signalnavn.
    st.markdown("### 🚦 Hva skjer nå?")
    quick_rows = []
    action_nb = {"BUY":"KJØP", "ADD":"ØK", "REDUCE":"REDUSER", "SELL":"SELG", "HOLD":"HOLD"}
    for pos in positions:
        ticker = str(pos.get("ticker") or "-")
        distance = pos.get("distance_to_hard_stop_pct")
        try:
            distance_f = float(distance) if distance is not None else None
        except Exception:
            distance_f = None
        pressure = str(pos.get("stop_pressure") or "").upper()
        if pressure == "CRITICAL" or (distance_f is not None and distance_f <= 1.0):
            level, meaning = "🔴 KRITISK", "Nær stop - krever oppmerksomhet"
        elif pressure in {"HIGH", "SEVERE"} or (distance_f is not None and distance_f <= 3.0):
            level, meaning = "🟠 HANDLING", "Tett på beskyttelsesgrense"
        elif pressure == "MEDIUM" or (distance_f is not None and distance_f <= 5.0):
            level, meaning = "🟡 FØLG MED", "Økt stop-press"
        else:
            level, meaning = "🟢 OK", "Ingen akutt handling"
        adv = advisory_by_ticker.get(ticker) or {}
        action = action_nb.get(str(adv.get("action") or "").upper(), str(adv.get("action") or "HOLD"))
        from_pct = adv.get("from_pct")
        to_pct = adv.get("to_pct")
        if adv and from_pct is not None and to_pct is not None:
            action = f"{action} {float(from_pct):.1f}% → {float(to_pct):.1f}%"
        weight_pct = float(pos.get("target_weight_pct") or 0)
        pnl_pct = float(pos.get("pnl_pct") or 0)
        position_value = portfolio_value * weight_pct / 100.0
        position_pnl_nok = position_value * pnl_pct / 100.0
        quick_rows.append({
            "Status": level, "Aksje": ticker, "Hva betyr det": meaning,
            "Vekt %": round(weight_pct,1),
            "Verdi NOK": round(position_value,0),
            "P/L NOK": round(position_pnl_nok,0),
            "P/L %": round(pnl_pct,2),
            "Til stop %": round(distance_f,2) if distance_f is not None else None,
            "AI nå": action,
        })
    quick_rows.sort(key=lambda r: ({"🔴":0,"🟠":1,"🟡":2,"🟢":3}.get(str(r["Status"])[:1],9), r.get("Til stop %") if r.get("Til stop %") is not None else 999))
    if quick_rows:
        st.dataframe(pd.DataFrame(quick_rows), width="stretch", hide_index=True, height=min(330, 42 + 38*len(quick_rows)))
    else:
        st.info("Ingen aktive Super Portfolio-posisjoner ennå.")

    if advisory:
        action_rows=[]
        for a in advisory:
            raw=str(a.get("action") or "HOLD").upper()
            action_rows.append({
                "Aksje": a.get("ticker") or "-",
                "Handling": action_nb.get(raw, raw),
                "Fra %": round(float(a.get("from_pct") or 0),1),
                "Til %": round(float(a.get("to_pct") or 0),1),
                "Hvorfor": a.get("reason") or a.get("reason_code") or "-",
            })
        st.markdown("**Foreslåtte handlinger nå**")
        st.dataframe(pd.DataFrame(action_rows), width="stretch", hide_index=True, height=min(250, 42+38*len(action_rows)))

    # Visuell porteføljeutvikling - totalt og alle aksjer samtidig.
    st.markdown("### 📈 Utvikling – totalt")
    history_rows=[]
    per_ticker_rows=[]
    for snap in state.get("history") or []:
        at=snap.get("at")
        if snap.get("portfolio_value") is not None:
            history_rows.append({
                "Tid": at, "Porteføljeverdi": float(snap.get("portfolio_value") or 0),
                "Avkastning %": float(snap.get("portfolio_return_pct") or 0),
            })
        for hp in snap.get("positions") or []:
            ticker=str(hp.get("ticker") or "")
            if ticker:
                per_ticker_rows.append({"Tid":at, "Aksje":ticker, "Fra inngang %":float(hp.get("pnl_pct") or 0)})
    if history_rows:
        hdf=pd.DataFrame(history_rows).drop_duplicates(subset=["Tid"],keep="last")
        st.line_chart(hdf.set_index("Tid")[["Porteføljeverdi"]], height=260)
        st.caption(f"Siste registrerte NAV: NOK {float(hdf.iloc[-1]['Porteføljeverdi']):,.0f} · Avkastning {float(hdf.iloc[-1]['Avkastning %']):+.2f}%")
    else:
        st.info("Totalgrafen bygges automatisk når NAV-historikk er registrert.")

    st.markdown("### 📉 Utvikling – alle aksjer")
    if per_ticker_rows:
        tdf=pd.DataFrame(per_ticker_rows).drop_duplicates(subset=["Tid","Aksje"],keep="last")
        pivot=tdf.pivot(index="Tid",columns="Aksje",values="Fra inngang %").sort_index()
        st.line_chart(pivot, height=300)
        selected=st.selectbox("Detalj per aksje", list(pivot.columns), key="sp_perf_ticker_ui_hotfix")
        st.line_chart(pivot[[selected]].dropna(), height=220)
    else:
        st.caption("Per-aksje kurver vises etter neste vurdering som lagrer posisjonshistorikk.")

    if positions:
        contribution=[]
        for pos in positions:
            w=float(pos.get("target_weight_pct") or 0)
            pnl=float(pos.get("pnl_pct") or 0)
            contribution.append({"Aksje":pos.get("ticker"),"Bidrag pp":round(w*pnl/100.0,3)})
        cdf=pd.DataFrame(contribution).sort_values("Bidrag pp",ascending=False)
        st.markdown("### 🧮 Hvem skaper resultatet?")
        st.bar_chart(cdf.set_index("Aksje")[["Bidrag pp"]], height=230)

    if health.get("components"):
        hc = health["components"]
        st.caption(
            f"🧠 Quality {float(hc.get('quality') or 0):.1f} · 🛡️ Risk {float(hc.get('risk') or 0):.1f} · "
            f"🧬 Diversification {float(hc.get('diversification') or 0):.1f} · 🚦 Stop safety {float(hc.get('stop_safety') or 0):.1f} · "
            f"🔗 Correlation {float(hc.get('correlation') or 0):.1f}"
        )

    recover_stale_job()
    current_job = get_job()
    evaluation_running = str(current_job.get("state") or "") in ACTIVE_STATES
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
        try:
            started = start_job("MANUAL", True)
            st.session_state["sp_evaluation_notice"] = (
                f"Super Portfolio-jobb startet: {started.get('job_id')}. "
                "Du kan bruke resten av programmet mens den arbeider."
            )
        except Exception as exc:
            st.session_state["sp_evaluation_error"] = f"Kunne ikke starte Super Portfolio-jobben: {exc}"
        st.rerun()

    def _render_sp_job_progress() -> None:
        job = get_job()
        if not job:
            st.caption("Ingen Super Portfolio-jobb er registrert ennå.")
            return
        successful_run_id = str(job.get("latest_successful_run_id") or "")
        refreshed_run_id = str(st.session_state.get("sp_refreshed_run_id") or "")
        if _terminal_job_needs_app_refresh(job, refreshed_run_id):
            st.session_state["sp_refreshed_run_id"] = successful_run_id
            st.rerun(scope="app")
            return
        from ui_library.components import render_job_status
        from ui_library.job_status import super_portfolio_job_view
        state_name = str(job.get("state") or "UKJENT")
        percent = max(0, min(100, int(job.get("percent") or 0)))
        view = super_portfolio_job_view(job)
        render_job_status(st, view, {"pause": lambda: request_control("PAUSE", view.job_id), "resume": lambda: request_control("RESUME", view.job_id), "stop": lambda: request_control("STOP", view.job_id)})
        st.caption(
            f"Siste fremdrift: {job.get('last_progress_at') or '-'} · "
            f"Heartbeat: {job.get('heartbeat_at') or '-'} · "
            f"Siste verifiserte scan: {job.get('latest_successful_run_id') or '-'}"
        )
        # Controls are rendered once by the shared capability-based component.
        if False:  # retained branch body below for source-compatible rollback
            pause_col, resume_col, stop_col = st.columns(3)
            if pause_col.button("⏸ Pause", disabled=state_name in {"PAUSE_REQUESTED", "PAUSED", "STOP_REQUESTED"}, width="stretch", key="sp_pause_job_32k"):
                request_control("PAUSE", str(job.get("job_id") or ""))
            if resume_col.button("▶ Fortsett", disabled=state_name not in {"PAUSE_REQUESTED", "PAUSED"}, width="stretch", key="sp_resume_job_32k"):
                request_control("RESUME", str(job.get("job_id") or ""))
            if stop_col.button("⏹ Stopp", disabled=state_name == "STOP_REQUESTED", width="stretch", key="sp_stop_job_32k"):
                request_control("STOP", str(job.get("job_id") or ""))
        elif state_name in {"FAILED", "INTERRUPTED"}:
            st.error(f"{job.get('message') or state_name}: {job.get('error') or job.get('failure_type') or '-'}")
        elif state_name == "CANCELLED":
            st.warning("Jobben ble stoppet. Forrige verifiserte portefølje er beholdt.")
        else:
            st.success(
                f"Jobben er {state_name.lower()} og sluttresultatet er verifisert. "
                f"{int(job.get('applied_changes') or 0)} godkjente Shadow-endring(er) ble anvendt."
            )
        st.download_button(
            "⬇️ Last ned SP jobbdiagnose", data=job_diagnostic_zip(str(job.get("job_id") or "")),
            file_name=f"SP_jobdiagnose_{job.get('job_id') or 'latest'}.zip",
            mime="application/zip", width="stretch", key="sp_job_diagnostic_32k",
        )

    fragment = getattr(st, "fragment", None)
    if callable(fragment):
        fragment(run_every="5s")(_render_sp_job_progress)()
    else:
        _render_sp_job_progress()
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
    d1,d2,d3 = st.columns(3)
    d1.download_button(
        "⬇️ Last ned PDF", data=pdf_bytes,
        file_name=f"SuperPortfolio_{str(state.get('updated_at') or 'latest')[:10]}.pdf",
        mime="application/pdf", width="stretch", key="sp_download_pdf_ui_hotfix",
    )
    if report_url:
        try:
            from public_report_ui import with_report_return
            report_link = with_report_return(report_url, "super_portfolio")
        except Exception:
            report_link = report_url
        d2.link_button("🔗 Åpne / del", report_link, width="stretch")
        d3.link_button("🖨️ Print PDF", report_link, width="stretch")
        st.code(report_link, language=None)
    else:
        d2.caption("Publiser PDF først for delbar lenke.")
        d3.caption("Print blir tilgjengelig etter publisering.")

    st.markdown("### 📊 Benchmark")
    bench = benchmark_summary(state, portfolio_return_pct=portfolio_return)
    b1,b2,b3 = st.columns(3)
    idx = bench.get("index") or {}
    aur = bench.get("aurora") or {}
    b1.metric(str(idx.get("label") or "Indeks"), f"{float(idx.get('return_pct') or 0):+.2f}%", delta=f"Alpha {float(idx.get('alpha_pct') or 0):+.2f} pp" if idx.get("return_pct") is not None else None)
    b2.metric(str(aur.get("label") or "Aurora"), f"{float(aur.get('return_pct') or 0):+.2f}%", delta=f"Alpha {float(aur.get('alpha_pct') or 0):+.2f} pp" if aur.get("return_pct") is not None else None)
    confidence = state.get("decision_confidence") or {}
    b3.metric("🧠 Decision Confidence", f"{confidence.get('icon','⚪')} {float(confidence.get('score') or 0):.1f}/100")

    with st.expander("🧾 Innsiderkontroll – lesbar visning", expanded=False):
        checks=state.get("insider_checks") or {}
        st.caption("Offisielle primærkilder. Ansattprogram vises som informasjon, ikke som positivt innsidermomentum.")
        insider_rows=[]
        source_rows=[]
        for ticker, check in checks.items():
            evidence=list(check.get("evidence") or [])
            if not evidence:
                insider_rows.append({"Aksje":ticker,"Status":check.get("signal") or check.get("coverage") or "Ingen treff","Type":"-","Innsider":"-","Aksjer":"-","Dato":"-"})
            for fact in evidence[:5]:
                context="Ansattprogram" if fact.get("transaction_context")=="EMPLOYEE_SHARE_PROGRAMME" else str(fact.get("type") or "Handel")
                insider_rows.append({
                    "Aksje":ticker,"Status":check.get("signal") or check.get("coverage") or "-",
                    "Type":context,"Innsider":fact.get("insider") or "Ukjent",
                    "Aksjer":fact.get("shares",0),"Dato":fact.get("date") or "-",
                })
                if fact.get("source_url"):
                    source_rows.append((ticker, context, str(fact.get("source_url"))))
        if insider_rows:
            st.dataframe(pd.DataFrame(insider_rows), width="stretch", hide_index=True, height=min(360,60+36*len(insider_rows)))
            if source_rows:
                st.caption("Kildemeldinger")
                for idx,(ticker,context,url) in enumerate(source_rows[:12]):
                    st.link_button(f"{ticker} · {context}", url, width="stretch")
        else:
            st.info("Ingen innsiderkontroll fra siste markedsskanning er tilgjengelig.")

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

    st.markdown("### 🛡️ Rebalance Gate")
    gate = state.get("rebalance_gate") or {}
    impact = state.get("rebalance_impact") or {}
    g1,g2,g3,g4 = st.columns(4)
    gate_allowed = bool(gate.get("allowed"))
    g1.metric("Status", "🟢 ÅPEN" if gate_allowed else "🔴 BLOKKERT")
    g2.metric("Feed-alder", f"{float(gate.get('pipeline_age_minutes') or 0):.0f} min" if gate.get('pipeline_age_minutes') is not None else "-")
    gate_conf = gate.get("confidence") or {}
    g3.metric("Confidence", f"{gate_conf.get('icon','⚪')} {float(gate_conf.get('score') or 0):.1f}/100")
    g4.metric("Decision run", str(gate.get("decision_run_id") or "-")[-18:])
    gate_reasons = list(gate.get("reason_codes") or [])
    if gate_reasons:
        st.warning(" · ".join(gate_reasons))
    else:
        st.caption("Ordinær Shadow-rebalansering kan bare utføres når market-feed og beslutningsgrunnlag består freshness- og confidence-gatene.")

    with st.expander("🎛️ Regime Policy", expanded=False):
        regime = state.get("regime_policy") or gate.get("regime_policy") or {}
        rp1,rp2,rp3,rp4 = st.columns(4)
        rp1.metric("Regime", regime.get("regime") or "NORMAL")
        rp2.metric("Persistence", f"{int(regime.get('required_persistence_runs') or 0)} runs")
        rp3.metric("Min confidence", f"{float(regime.get('min_confidence') or 0):.1f}")
        rp4.metric("Challenger-margin", f"{float(regime.get('replacement_score_margin') or 0):.1f}")

    with st.expander("🎯 Candidate Entry Gate", expanded=False):
        entry_gate = state.get("entry_gate") or {}
        gate_rows=[]
        for ticker, row in entry_gate.items():
            coverage=row.get("coverage") or {}
            gate_rows.append({
                "Aksje":ticker,
                "Tillatt":"🟢 JA" if row.get("allowed") else "🔴 NEI",
                "Coverage %":coverage.get("score","-"),
                "Persistence":f"{row.get('persistence_streak','-')}/{row.get('required_persistence_runs','-')}",
                "Regime":row.get("regime") or "-",
                "Blokkering":" · ".join(row.get("reason_codes") or []) or "-",
            })
        if gate_rows:
            st.dataframe(pd.DataFrame(gate_rows), width="stretch", hide_index=True, height=260)
        else:
            st.caption("Ingen nye challengers har vært gjennom entry-gaten i siste beslutningsrunde.")

    vacancy=state.get("vacancy_diagnostics") or {}
    if vacancy:
        st.markdown("### 💵 Ledige plasser / kontantandel")
        v1,v2,v3,v4=st.columns(4)
        v1.metric("Posisjoner", f"{int(vacancy.get('position_count') or 0)}/{int(vacancy.get('target_positions') or 0)}")
        v2.metric("Ledige plasser", int(vacancy.get("open_slots") or 0))
        v3.metric("Kontantandel", f"{float(vacancy.get('cash_pct') or 0):.1f}%")
        v4.metric("Status", str(vacancy.get("status") or "-"))
        considered=list(vacancy.get("considered") or [])
        if considered:
            st.dataframe(pd.DataFrame([{
                "Aksje":r.get("ticker"),"Status":r.get("status"),"Målvekt %":r.get("target_weight_pct"),
                "Blokkering":" · ".join(r.get("gate_reason_codes") or []) or "Ingen gate-blokkering",
            } for r in considered]), width="stretch", hide_index=True, height=220)

    st.markdown("### 📊 Før / etter rebalansering")
    if impact:
        before = impact.get("health_before") or {}
        after = impact.get("health_after") or {}
        i1,i2,i3,i4 = st.columns(4)
        i1.metric("Health før", f"{float(before.get('score') or 0):.1f}")
        i2.metric("Health etter", f"{float(after.get('score') or 0):.1f}", delta=f"{float(impact.get('health_delta') or 0):+.1f}")
        i3.metric("Risk før → etter", f"{float(impact.get('risk_before') or 0):.1f} → {float(impact.get('risk_after') or 0):.1f}")
        i4.metric("Foreslått turnover", f"{float(impact.get('turnover_pct') or 0):.1f}%")
        st.caption(
            f"Correlation {float(impact.get('correlation_before') or 0):.1f} → {float(impact.get('correlation_after') or 0):.1f} · "
            f"Run {impact.get('decision_run_id') or '-'}"
        )
    else:
        st.caption("Før/etter-impact fylles ved neste SP-vurdering.")

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

    if positions:
        rows=[]
        technical_rows=[]
        for pos in positions:
            ticker=str(pos.get("ticker") or "-")
            score=float(pos.get("portfolio_score_adjusted") or pos.get("portfolio_score") or 0)
            weight=float(pos.get("target_weight_pct") or 0)
            pnl=float(pos.get("pnl_pct") or 0)
            theoretical_value=portfolio_value*weight/100.0
            pnl_nok=theoretical_value*pnl/100.0
            dist=pos.get("distance_to_hard_stop_pct")
            try: dist_f=float(dist) if dist is not None else None
            except Exception: dist_f=None
            pressure=str(pos.get("stop_pressure") or "").upper()
            if pressure=="CRITICAL" or (dist_f is not None and dist_f<=1): status="🔴 KRITISK"
            elif pressure in {"HIGH","SEVERE"} or (dist_f is not None and dist_f<=3): status="🟠 HANDLING"
            elif pressure=="MEDIUM" or (dist_f is not None and dist_f<=5): status="🟡 FØLG MED"
            else: status="🟢 OK"
            adv=advisory_by_ticker.get(ticker) or {}
            raw=str(adv.get("action") or "HOLD").upper()
            action=action_nb.get(raw,raw)
            if adv and adv.get("to_pct") is not None:
                action=f"{action} → {float(adv.get('to_pct') or 0):.1f}%"
            fr=pos.get("data_freshness") or {}
            rows.append({
                "Status":status,"Aksje":ticker,"Marked":pos.get("market"),"Vekt %":round(weight,1),
                "Verdi NOK":round(theoretical_value,0),"P/L NOK":round(pnl_nok,0),"P/L %":round(pnl,2),
                "Til stop %":round(dist_f,2) if dist_f is not None else None,"AI nå":action,
                "Data":f"{fr.get('icon','⚪')} {fr.get('status','-')}",
            })
            technical_rows.append({
                "Aksje":ticker,"Sektor":pos.get("sector"),"Stop":f"{pos.get('stop_icon','')} {pos.get('stop_status','')}",
                "Press":f"{pos.get('stop_pressure_icon','')} {pos.get('stop_pressure','')} {pos.get('stop_direction_arrow','→')}",
                "Fra topp %":pos.get("drawdown_from_peak_pct"),"Stopkurs":pos.get("hard_stop_price"),
                "AI-score":round(score,1),"Rank":f"#{pos.get('rank','-')} {pos.get('rank_arrow','→')}","Δ rank":pos.get("rank_change"),
                "Sektorstraff":pos.get("sector_penalty"),"Korr.straff":pos.get("correlation_penalty"),"Risiko":pos.get("risk_score"),
                "Event":f"{(pos.get('event_risk') or {}).get('icon','⚪')} {(pos.get('event_risk') or {}).get('date','-')}",
            })
        st.markdown("### 💼 Porteføljen nå")
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=min(420,60+38*len(rows)))
        with st.expander("🔬 Tekniske kolonner / diagnose", expanded=False):
            st.dataframe(pd.DataFrame(technical_rows), width="stretch", hide_index=True, height=300)

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
                st.caption("🧠 AI THINKS — hva AI ønsker å gjøre nå. Dette er rådgivende og er ikke det samme som utførte Shadow-endringer.")
                icons={"BUY":"🟢","ADD":"🔵","REDUCE":"🟠","SELL":"🔴"}
                advisory_rows=[{
                    "Handling":f"{icons.get(action.get('action'),'•')} {action.get('action')}",
                    "Aksje":action.get("ticker"),
                    "Fra %":round(float(action.get("from_pct") or 0),1),
                    "Til %":round(float(action.get("to_pct") or 0),1),
                    "Status":action.get("execution_status") or "ADVISORY_ONLY",
                    "Årsak":action.get("reason") or "-",
                    "Kode":action.get("reason_code") or "-",
                } for action in advisory]
                if advisory_rows:
                    st.dataframe(pd.DataFrame(advisory_rows), width="stretch", hide_index=True, height=280)
                else:
                    st.caption("Ingen foreslåtte endringer akkurat nå.")

        with st.expander("✅ SHADOW EXECUTED", expanded=False):
            st.caption("Kun handlinger som faktisk ble gjennomført i Shadow-porteføljen i siste beslutningsrunde.")
            executed = state.get("shadow_executed") or state.get("last_changes") or []
            executed_rows=[{
                "Handling":f"{icons.get(action.get('action'),'•')} {action.get('action')}",
                "Aksje":action.get("ticker"),
                "Fra %":round(float(action.get("from_pct") or 0),1),
                "Til %":round(float(action.get("to_pct") or 0),1),
                "Årsak":action.get("reason") or "-",
                "Kode":action.get("reason_code") or "-",
            } for action in executed]
            if executed_rows:
                st.dataframe(pd.DataFrame(executed_rows), width="stretch", hide_index=True, height=260)
            else:
                st.caption("Ingen faktiske Shadow-endringer i siste beslutningsrunde.")

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

    st.markdown("### 🔎 Decision Trace / diagnose")
    trace = dict(state.get("decision_trace") or {})
    trace_rows = dict(trace.get("by_ticker") or {})
    diagnostic_tickers = sorted(trace_rows)
    if diagnostic_tickers:
        diag_ticker = st.selectbox("Aksje for diagnose", diagnostic_tickers, key="sp_diagnostic_ticker_32h")
        dc1, dc2 = st.columns(2)
        if dc1.button("🔎 Diagnostiser valgt aksje", width="stretch", key="sp_run_diagnostic_32h"):
            st.session_state["sp_diagnostic_selected_32h"] = diag_ticker
        selected_diag = str(st.session_state.get("sp_diagnostic_selected_32h") or diag_ticker)
        diag_row = dict(trace_rows.get(selected_diag) or {})
        if diag_row:
            alert_text = ", ".join(diag_row.get("alerts") or []) or "Ingen"
            if "INCONSISTENT_DECISION" in (diag_row.get("alerts") or []):
                st.error(f"🔴 INCONSISTENT DECISION: {selected_diag} · {diag_row.get('exclusion_reason') or '-'}")
            elif diag_row.get("snapshot_mismatch"):
                st.warning(f"🟠 Snapshot mismatch: {selected_diag}")
            st.dataframe(pd.DataFrame([{
                "Aksje": selected_diag,
                "Posisjon run": diag_row.get("position_source_run_id"),
                "Beslutning run": diag_row.get("decision_run_id"),
                "I pipeline": diag_row.get("in_current_pipeline"),
                "Eligible": diag_row.get("eligible"),
                "Rank": diag_row.get("rank"),
                "Score": diag_row.get("score"),
                "Target": diag_row.get("target_selected"),
                "Målvekt %": diag_row.get("target_weight_pct"),
                "Handling": diag_row.get("action"),
                "Eksklusjonsårsak": diag_row.get("exclusion_reason"),
                "Varsler": alert_text,
            }]), width="stretch", hide_index=True)
        diagnostic_bytes = build_diagnostic_zip(state, ticker=diag_ticker)
        dc2.download_button(
            "📦 Last ned diagnose-ZIP",
            data=diagnostic_bytes,
            file_name=f"SuperPortfolio_Diagnose_{diag_ticker.replace('.', '_')}.zip",
            mime="application/zip",
            width="stretch",
            key="sp_download_diagnostic_32h",
        )
    else:
        st.caption("Diagnose blir tilgjengelig etter neste Super Portfolio-vurdering.")

    challengers=state.get("challengers") or []
    st.markdown("### ⚔️ Utfordrere til porteføljen")
    if challengers:
        challenger_rows=[]
        for r in challengers:
            replaces=r.get("replaces") or r.get("incumbent_ticker") or r.get("target_ticker") or "-"
            challenger_rows.append({
                "Aksje":r.get("ticker"),"Marked":r.get("market"),"AI-score":round(float(r.get("portfolio_score_adjusted",r.get("portfolio_score")) or 0),1),
                "Rank":f"#{r.get('rank','-')} {r.get('rank_arrow','→')}","Δ rank":r.get("rank_change"),
                "Utfordrer":replaces if replaces!="-" else "Kandidat til porteføljen",
                "Risiko":r.get("risk_score"),
            })
        st.dataframe(pd.DataFrame(challenger_rows),width="stretch",hide_index=True,height=min(320,60+38*len(challenger_rows)))
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
