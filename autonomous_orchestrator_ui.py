"""Visible UI integration for v18.6.90a autonomous orchestration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from autonomous_orchestrator import AUDIT_PATH, LATEST_PATH, ROOT, RUNS_DIR, load_audit, load_latest_chain
from market_intelligence import _load_report_archive, load_draft_job, load_jobs, render_market_intelligence
from manual_job_background import get_active_status, is_running, start_manual_job
from services.storage_service import get_storage_service

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover - optional UI convenience
    st_autorefresh = None


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
    c3.metric("Lagrede kjøringer", len(_load_report_archive()))
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
    background_status = get_active_status()
    background_running = is_running(background_status)
    if st.button(run_label, type="primary", use_container_width=True, key="orchestrator_ui_run_v18692d", disabled=background_running):
        trigger = "MANUAL_DRAFT_TEST" if is_draft else "MANUAL_FULL_CHAIN"
        background_status = start_manual_job(selected_job, trigger=trigger, force_refresh=force_refresh)
        st.session_state["orchestrator_background_execution_v1878"] = background_status.get("execution_id")
        st.rerun()

    background_status = get_active_status()
    if background_status:
        state = str(background_status.get("state") or "UKJENT")
        pct = int(background_status.get("percent") or 0)
        message = str(background_status.get("message") or state)
        st.progress(min(100, max(0, pct)), text=f"{pct} % · {message}")
        b1, b2, b3 = st.columns(3)
        b1.metric("Bakgrunnsjobb", background_status.get("execution_id") or "-")
        b2.metric("Jobbstatus", state)
        b3.metric("Sist oppdatert", background_status.get("updated_at") or "-")
        if is_running(background_status):
            st.info("Kjøringen fortsetter på serveren. Du kan bytte panel, oppdatere eller lukke nettleseren.")
            if st_autorefresh is not None:
                st_autorefresh(interval=3000, limit=None, key=f"orchestrator_background_refresh_{background_status.get('execution_id')}")
        elif state == "FAILED":
            st.error(f"Bakgrunnskjøringen feilet: {background_status.get('error') or 'ukjent feil'}")
        elif state == "COMPLETED":
            chain_result = background_status.get("chain") or {}
            if chain_result.get("status") == "OK":
                st.success("Hele kjeden er fullført uten tekniske feil.")
            else:
                st.warning(f"Kjeden ble avsluttet med status {chain_result.get('status', 'UKJENT')}.")
            st.session_state["orchestrator_ui_latest_v18692d"] = chain_result

    chain = (background_status.get("chain") if background_status else None) or st.session_state.get("orchestrator_ui_latest_v18692d") or load_latest_chain()
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
        top = list((background_status.get("top_candidates") if background_status else None) or latest_run.get("candidates") or [])[:3]
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
        audit_rows = load_audit(1000)
        health = get_storage_service().health()
        r1,r2,r3 = st.columns(3)
        r1.metric("Lagring", "PostgreSQL" if health.persistent and health.ok else "Lokal fallback")
        r2.metric("Orchestratorhendelser", len(audit_rows))
        r3.metric("Rapporter", len(_load_report_archive()))
        if audit_rows:
            st.dataframe(pd.DataFrame(audit_rows[-200:][::-1]), use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen orchestratorhendelser er registrert ennå.")
        st.code(
            f"{ROOT}/\n├── latest_run.json\n├── audit.jsonl\n└── runs/",
            language="text",
        )
        st.caption(f"Latest: {LATEST_PATH} · Audit: {AUDIT_PATH}")
