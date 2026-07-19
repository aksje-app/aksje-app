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
    run_label = "🧪 Test hele kjeden fra utkast" if is_draft else "▶ Kjør valgt lagret jobb nå"
    if st.button(run_label, type="primary", use_container_width=True, key="orchestrator_ui_run_v18692a"):
        trigger = "MANUAL_DRAFT_TEST" if is_draft else "MANUAL_FULL_CHAIN"
        with st.status("Kjører markedsskanning og autonome steg …", expanded=True) as status:
            st.write("1. Starter MARKET_SCAN og Investment Pipeline")
            result = run_job(selected_job, trigger=trigger)
            chain = result.get("autonomous_chain") or {}
            st.write("2. Behandler AUTONOMOUS_PORTFOLIO")
            st.write("3. Behandler CONTROLLED_LEARNING")
            if chain.get("status") == "OK":
                status.update(label="Hele kjeden er fullført", state="complete", expanded=True)
            else:
                status.update(label=f"Kjeden avsluttet med status {chain.get('status', 'UKJENT')}", state="error", expanded=True)
            st.session_state["orchestrator_ui_latest_v18690a"] = chain

    chain = st.session_state.get("orchestrator_ui_latest_v18690a") or load_latest_chain()
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
