"""Visible UI integration for v18.6.90a autonomous orchestration."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import streamlit as st

from autonomous_orchestrator import AUDIT_PATH, LATEST_PATH, ROOT, RUNS_DIR, load_audit, load_latest_chain
from market_intelligence import _load_report_archive, load_draft_job, load_jobs, normalize_markets, render_market_intelligence
from manual_job_background import get_active_status, is_running, request_cancel, start_manual_job
from services.storage_service import get_storage_service
from local_time import local_display
from market_universe import FULL_MARKET_SCOPE_LABEL


USE_JOB_MARKETS = "Bruk markedene i jobbprofilen"
ORCHESTRATOR_MARKET_CHOICES = [
    USE_JOB_MARKETS,
    "Alle kjernemarkeder",
    "Norge",
    "Sverige",
    "USA",
    "Utvidet Norden",
    "Danmark",
    "Finland",
    "Brasil",
    FULL_MARKET_SCOPE_LABEL,
]


def resolve_orchestrator_run_job(selected_job: Any, market_choice: str) -> Any:
    """Return a non-persistent per-run market override for the selected job.

    The saved scheduler profile remains unchanged.  This keeps one-click runs
    explicit and prevents an old six-market profile from being reused silently.
    """
    choice = str(market_choice or USE_JOB_MARKETS).strip()
    if choice == USE_JOB_MARKETS:
        return selected_job
    return replace(selected_job, markets=[choice])


def orchestrator_market_summary(job: Any) -> str:
    markets = normalize_markets(list(getattr(job, "markets", []) or []))
    return ", ".join(markets) or "Ingen gyldige markeder"


def _stage_rows(chain: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in chain.get("stages") or []:
        detail = item.get("detail") or {}
        rows.append({
            "Steg": item.get("name", ""),
            "Status": item.get("status", ""),
            "Tid": local_display(item.get("at"), str(chain.get("timezone_name") or "Europe/Oslo")),
            "Detaljer": json.dumps(detail, ensure_ascii=False, default=str),
        })
    return rows


def _background_status_panel() -> None:
    """Render only the live status block; safe to rerun as a Streamlit fragment."""
    status = get_active_status()
    if not status:
        return
    state = str(status.get("state") or "UKJENT")
    execution_id = str(status.get("execution_id") or "")
    if state in {"COMPLETED", "FAILED", "CANCELLED"} and execution_id:
        refresh_key = "orchestrator_terminal_app_refresh_v18712"
        if st.session_state.get(refresh_key) != execution_id:
            st.session_state[refresh_key] = execution_id
            try:
                st.rerun(scope="app")
            except TypeError:
                st.rerun()
            return
    pct = int(status.get("percent") or 0)
    message = str(status.get("message") or state)
    st.progress(min(100, max(0, pct)), text=f"{pct} % · {message}")
    scan = status.get("scan_configuration") or {}
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Bakgrunnsjobb", execution_id or "-")
    b2.metric("Jobbstatus", state)
    b3.metric("Sist oppdatert", local_display(status.get("updated_at"), str(status.get("timezone_name") or "Europe/Oslo")))
    b4.metric("Skannegrense", f"{scan.get('per_market', '-')} per marked")

    labels = {
        "MARKET_DATA": "Markedsdata", "INSIDER": "Insider Intelligence",
        "NEWS": "News & Sentiment", "SCORING": "Scoring og rangering",
        "PORTFOLIO_PROPOSAL": "Porteføljeforslag", "AUTONOMOUS": "Autonomi",
        "REPORT": "Rapport og historikk", "COMPLETE": "Fullført",
    }
    completed = set(status.get("completed_steps") or [])
    active = str(status.get("active_stage") or "MARKET_DATA")
    stage_cols = st.columns(4)
    for index, (stage, label) in enumerate(labels.items()):
        with stage_cols[index % 4]:
            if stage in completed:
                st.success(f"✅ {label}")
            elif stage == active and state in {"FAILED", "CANCELLED"}:
                st.error(f"⛔ {label}")
            elif stage == active:
                st.warning(f"⏳ {label}")
            else:
                st.markdown(
                    f"<div style='padding:.65rem;border:1px solid #5f6b7a;border-radius:.45rem;background:#1b2430;color:#cbd5e1;margin-bottom:.5rem'>⬜ {label}</div>",
                    unsafe_allow_html=True,
                )
    if is_running(status):
        if state == "STOP_REQUESTED":
            st.warning("Stopp er registrert. Pågående datakall avsluttes før jobben stanser ved neste sikre kontrollpunkt.")
        else:
            st.info("Kjøringen fortsetter på serveren. Meny og andre paneler kan brukes samtidig.")
            confirm = st.checkbox("Jeg bekrefter at den pågående kjøringen skal avbrytes", key=f"cancel_confirm_{status.get('execution_id')}")
            if st.button("⛔ Stopp pågående kjøring", disabled=not confirm, key=f"cancel_job_{status.get('execution_id')}"):
                request_cancel(str(status.get("execution_id") or ""), requested_by="UI")
                st.warning("Stoppforespørsel er sendt.")
    elif state == "FAILED":
        st.error(f"Bakgrunnskjøringen feilet: {status.get('error') or 'ukjent feil'}")
    elif state == "COMPLETED":
        chain = status.get("chain") or {}
        if status.get("partial_market_failure"):
            st.warning("FULLFØRT MED MARKEDSFEIL · " + ", ".join(status.get("failed_markets") or []))
        elif chain.get("status") == "OK":
            st.success("Hele kjeden er fullført uten tekniske feil.")
        else:
            st.warning(f"Kjeden ble avsluttet med status {chain.get('status', 'UKJENT')}.")
        p1, p2, p3 = st.columns(3)
        p1.metric("Rapport-ID", status.get("run_id") or "-")
        p2.metric("Kjede-ID", status.get("chain_id") or "-")
        p3.metric("Rapportarkiv", "BEKREFTET" if status.get("archive_saved") else "IKKE BEKREFTET")
    elif state == "CANCELLED":
        st.warning("Kjøringen ble kontrollert avbrutt. Ingen ufullstendig sluttrapport eller Pushover-melding ble publisert.")
    if st.button("↻ Oppdater hele statusvisningen", key="orchestrator_background_manual_refresh_v1879"):
        st.rerun()


def _render_live_background_status() -> None:
    fragment = getattr(st, "fragment", None)
    if callable(fragment):
        fragment(run_every="3s")(_background_status_panel)()
    else:
        _background_status_panel()


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
    market_choice = st.selectbox(
        "Marked for denne kjøringen",
        ORCHESTRATOR_MARKET_CHOICES,
        index=0,
        key="orchestrator_ui_market_override_v19141",
        help=(
            "Valget gjelder bare denne kjøringen og endrer ikke den lagrede jobbprofilen. "
            "Alle kjernemarkeder betyr Norge, Sverige og USA."
        ),
    )
    run_job = resolve_orchestrator_run_job(selected_job, market_choice)
    st.info(f"Denne kjøringen bruker: {orchestrator_market_summary(run_job)}")
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
        background_status = start_manual_job(run_job, trigger=trigger, force_refresh=force_refresh)
        st.session_state["orchestrator_background_execution_v1878"] = background_status.get("execution_id")
        st.rerun()

    _render_live_background_status()
    background_status = get_active_status()
    if background_status.get("state") == "COMPLETED":
        st.session_state["orchestrator_ui_latest_v18692d"] = background_status.get("chain") or {}

    chain = (background_status.get("chain") if background_status else None) or st.session_state.get("orchestrator_ui_latest_v18692d") or load_latest_chain()
    st.markdown("### Diagnostikk")
    if not chain:
        st.info("Ingen kjøring er registrert ennå.")
    else:
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Kjede-ID", chain.get("chain_id") or "-")
        d2.metric("Status", chain.get("status") or "-")
        d3.metric("Start", local_display(chain.get("created_at"), str(chain.get("timezone_name") or "Europe/Oslo")))
        d4.metric("Kilde", chain.get("trigger") or "-")
        rows = _stage_rows(chain)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        latest_run = st.session_state.get("mi_latest_v18687") or {}
        top = list((background_status.get("top_candidates") if background_status else None) or latest_run.get("candidates") or [])[:3]
        if top:
            st.caption("Prioritert vurderingsrekkefølge – undersøkelsesprioritet, ikke kjøpsanbefaling.")
            cols = st.columns(len(top))
            for idx, candidate in enumerate(top, start=1):
                cols[idx - 1].metric(
                    f"Prioritet {idx} · {candidate.get('ticker','-')}",
                    f"{float(candidate.get('investment_score',0)):.2f}",
                    f"Konf. {float(candidate.get('confidence_score',0)):.1f}%",
                )
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
