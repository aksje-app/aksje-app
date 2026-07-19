"""Visible UI integration for v18.6.90a autonomous orchestration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from autonomous_orchestrator import AUDIT_PATH, LATEST_PATH, ROOT, RUNS_DIR, load_latest_chain
from market_intelligence import load_draft_job, load_jobs, render_market_intelligence, run_job


def _stage_rows(chain: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in chain.get("stages") or []:
        detail = item.get("detail") or {}
        rows.append({
            "Steg": item.get("name", ""),
            "Status": item.get("status", ""),
            "Tid": item.get("at", ""),
            "Detaljer": json.dumps(detail, ensure_ascii=False, default=str),
        })
    return rows


def render_autonomous_orchestrator_control_center() -> None:
    """Dedicated, always-visible control page for scheduler and full chain."""
    import pandas as pd

    st.markdown("## 🚦 Autonom Orchestrator & Scheduler")
    st.caption(
        "Kjør og planlegg hele den teoretiske kjeden: markedsskanning → Investment Pipeline → "
        "Autonomous Learning Portfolio → Controlled Parameter Learning. Ingen ekte handler utføres."
    )

    jobs = load_jobs()
    active_jobs = [job for job in jobs if job.enabled]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Jobbprofiler", len(jobs))
    c2.metric("Aktive jobber", len(active_jobs))
    c3.metric("Lagrede kjøringer", len(list(RUNS_DIR.glob("*.json"))) if RUNS_DIR.exists() else 0)
    latest = load_latest_chain()
    c4.metric("Siste kjedestatus", latest.get("status") or "ALDRI KJØRT")

    st.markdown("### ▶ Test eller kjør hele kjeden")
    draft = load_draft_job()
    labels = {f"🧪 Utkast: {draft.name} · {', '.join(draft.markets)}": draft}
    labels.update({f"📅 {job.name} · {', '.join(job.markets)}": job for job in active_jobs})
    selected = st.selectbox("Velg oppsett", list(labels), key="orchestrator_ui_job_v18692a")
    selected_job = labels[selected]
    is_draft = selected_job.job_id == "MI-DRAFT-AUTOSAVE"
    if is_draft:
        st.info("Dette er det automatisk lagrede utkastet. Du kan teste hele kjeden før du lagrer eller aktiverer en tidsplan.")
    elif not active_jobs:
        st.caption("Ingen aktive tidsplaner finnes, men utkastet kan fortsatt testkjøres.")
    force_refresh = st.checkbox("Tving full ny analyse (ignorer cache)", value=False, key="orchestrator_force_refresh_v18692e", help="Henter ferske data for alle kandidater og viser om resultatene faktisk endrer seg. Kan ta lengre tid og øker belastningen på datakildene.")
    run_label = "🧪 Test hele kjeden fra utkast" if is_draft else "▶ Kjør valgt lagret jobb nå"
    if st.button(run_label, type="primary", use_container_width=True, key="orchestrator_ui_run_v18692d"):
        trigger = "MANUAL_DRAFT_TEST" if is_draft else "MANUAL_FULL_CHAIN"
        progress = st.progress(0, text="0 % · Klargjør kjøring")
        live = st.empty()
        checklist = st.empty()
        steps = ["MARKET_DATA", "SCORING", "PORTFOLIO_PROPOSAL", "AUTONOMOUS", "REPORT", "COMPLETE"]
        completed_steps: set[str] = set()
        def _render_checklist(active: str, message: str) -> None:
            labels = {
                "MARKET_DATA": "Henter pris-, fundamental- og analysedata",
                "SCORING": "Beregner individuelle delscorer og totalscore",
                "PORTFOLIO_PROPOSAL": "Bygger risikobevisst porteføljeforslag",
                "AUTONOMOUS": "Simulerer BUY / HOLD / SELL / SKIP",
                "REPORT": "Lagrer historikk og genererer rapport",
                "COMPLETE": "Fullfører kjeden",
            }
            lines=[]
            for step in steps:
                if step in completed_steps:
                    icon="✅"
                elif step == active:
                    icon="⏳"
                else:
                    icon="⬜"
                lines.append(f"{icon} {labels[step]}")
            checklist.markdown("  \n".join(lines))
            live.info(message)
        def _progress_event(event: Mapping[str, Any]) -> None:
            phase=str(event.get("phase") or "START")
            done=int(event.get("completed") or 0); total=max(1,int(event.get("total") or 1))
            phase_base={"START":2,"MARKET":5,"PREPARE":8,"MARKET_DATA":10,"SCORING":48,"DEDUP":68,"PORTFOLIO_PROPOSAL":74,"AUTONOMOUS":82,"REPORT":92,"COMPLETE":100}
            if phase == "MARKET_DATA": pct=10+int(35*done/total)
            elif phase == "SCORING": pct=48+int(18*done/total)
            else: pct=phase_base.get(phase,5)
            for step in steps:
                if steps.index(step) < steps.index(phase) if phase in steps else False:
                    completed_steps.add(step)
            if phase == "COMPLETE": completed_steps.update(steps)
            msg=str(event.get("message") or phase)
            ticker=event.get("ticker")
            if ticker and ticker not in msg: msg=f"{msg} · {ticker}"
            progress.progress(min(100,max(0,pct)), text=f"{pct} % · {msg}")
            _render_checklist(phase if phase in steps else "MARKET_DATA", msg)
        _render_checklist("MARKET_DATA", "Starter markedsskanning")
        try:
            result = run_job(selected_job, trigger=trigger, progress_callback=_progress_event, force_refresh=force_refresh)
            chain = result.get("autonomous_chain") or {}
            progress.progress(100, text="100 % · Hele kjeden er ferdig")
            completed_steps.update(steps)
            _render_checklist("COMPLETE", "Kjøringen er fullført")
            stage_map={x.get("name"):x for x in chain.get("stages") or []}
            ap=(stage_map.get("AUTONOMOUS_PORTFOLIO") or {}).get("detail") or {}
            if ap:
                st.success(f"Teoretiske beslutninger: {ap.get('buys',0)} kjøp, {ap.get('sells',0)} salg, {ap.get('skips',0)} hoppet over · {ap.get('open_positions',0)} åpne posisjoner.")
            refresh = result.get("data_refresh") or {}
            if refresh.get("force_refresh_requested"):
                if refresh.get("cache_bypass_verified"):
                    dates = ", ".join(refresh.get("latest_trade_dates") or []) or "ukjent"
                    st.success(f"Full ny analyse verifisert: cache ble ignorert for alle kandidater. Live hentinger: {refresh.get('live_count', 0)}. Nyeste handelsdato: {dates}.")
                    if refresh.get("unchanged_market_data_count", 0):
                        st.info(f"{refresh.get('unchanged_market_data_count')} kandidater hadde uendrede siste markedsdata. Dette er normalt når børsene er stengt.")
                else:
                    st.error("Full ny analyse var valgt, men cache-bypass kunne ikke verifiseres for alle kandidater. Se diagnostikk/JSON.")
            if chain.get("status") == "OK":
                st.success("Hele kjeden er fullført uten tekniske feil.")
            else:
                st.warning(f"Kjeden ble avsluttet med status {chain.get('status','UKJENT')}.")
            st.session_state["orchestrator_ui_latest_v18692d"] = chain
        except Exception as exc:
            live.error(f"Kjøringen stoppet: {exc}")
            progress.progress(100, text="Kjøringen stoppet med feil")

    chain = st.session_state.get("orchestrator_ui_latest_v18692d") or load_latest_chain()
    st.markdown("### Diagnostikk")
    if not chain:
        st.info("Ingen kjøring er registrert ennå.")
    else:
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Kjede-ID", chain.get("chain_id") or "-")
        d2.metric("Status", chain.get("status") or "-")
        d3.metric("Start", chain.get("created_at") or "-")
        d4.metric("Kilde", chain.get("trigger") or "-")
        rows = _stage_rows(chain)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        latest_run = st.session_state.get("mi_latest_v18687") or {}
        top = list(latest_run.get("candidates") or [])[:3]
        if top:
            medals = ["🥇", "🥈", "🥉"]
            cols = st.columns(len(top))
            for idx, candidate in enumerate(top):
                cols[idx].metric(f"{medals[idx]} {candidate.get('ticker','-')}", f"{float(candidate.get('investment_score',0)):.2f}", f"Konf. {float(candidate.get('confidence_score',0)):.1f}%")
        if chain.get("errors"):
            st.error(" | ".join(chain.get("errors") or []))
        with st.expander("Rå kjøringsdata", expanded=False):
            st.json(chain)

    st.markdown("---")
    st.markdown("### ⏰ Tidsplan og jobbprofiler")
    st.info(
        "Her velger du faste klokkeslett, ett eller flere skanningsvinduer, intervall (15–240 min), "
        "ukedager, markeder og hvilke steg som skal kjøres etter skanningen."
    )
    render_market_intelligence()

    with st.expander("Runtime og loggfiler", expanded=False):
        st.code(
            f"{ROOT}/\n├── latest_run.json\n├── audit.jsonl\n└── runs/",
            language="text",
        )
        st.caption(f"Latest: {LATEST_PATH} · Audit: {AUDIT_PATH}")
