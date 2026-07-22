"""Operational Autonomy overview for v18.8.3.

This module is deliberately a read/command facade over existing durable
services.  It contains no candidate, ranking, portfolio or scheduler logic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from autonomous_portfolio import (
    DECISIONS_PATH, NOTIFICATIONS_PATH, PERFORMANCE_PATH,
    load_parameters, load_portfolio, portfolio_equity,
)
from controlled_parameter_learning import APPROVALS_PATH, resolve_promotion_approval
from durable_runtime import read_json
from local_time import local_display
from manual_job_background import get_active_status, is_running, request_cancel, start_manual_job
from market_intelligence import _load_report_archive, load_draft_job, load_jobs, load_run
from notifier import pushover_audit, pushover_enabled
from scheduler_background import scheduler_status
from services.storage_service import get_storage_service


VERSION = "v18.9.0"
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rows(key: str, path: Any) -> list[dict[str, Any]]:
    value = read_json(key, path, [])
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _next_scheduled_run(jobs: list[Any], now: datetime | None = None) -> dict[str, Any]:
    """Return the next enabled wall-clock schedule in each job's timezone."""
    now_utc = now or datetime.now(timezone.utc)
    choices: list[dict[str, Any]] = []
    for job in jobs:
        if not bool(getattr(job, "enabled", False)):
            continue
        zone_name = str(getattr(job, "timezone_name", "Europe/Oslo") or "Europe/Oslo")
        try:
            zone = ZoneInfo(zone_name)
        except Exception:
            zone_name, zone = "Europe/Oslo", ZoneInfo("Europe/Oslo")
        local_now = now_utc.astimezone(zone)
        weekdays = set(int(day) for day in (getattr(job, "weekdays", []) or range(7)))
        schedules = list(getattr(job, "schedules", []) or [])
        found_for_job = False
        for offset in range(8):
            day = (local_now + timedelta(days=offset)).date()
            if day.weekday() not in weekdays:
                continue
            for raw in schedules:
                try:
                    hour, minute = (int(part) for part in str(raw).split(":", 1))
                    candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
                except Exception:
                    continue
                if candidate > local_now:
                    choices.append({
                        "job_name": getattr(job, "name", "-"), "at": candidate,
                        "timezone_name": zone_name,
                    })
                    found_for_job = True
            if found_for_job:
                break
    return min(choices, key=lambda item: item["at"].astimezone(timezone.utc)) if choices else {}


def collect_autonomy_overview() -> dict[str, Any]:
    """Collect a resilient snapshot; missing optional runtime data stays visible."""
    status = get_active_status() or {}
    jobs = load_jobs()
    active_jobs = [job for job in jobs if bool(getattr(job, "enabled", False))]
    archive = _load_report_archive()
    latest_archive = dict(archive[0]) if archive else {}
    latest_run = load_run(str(latest_archive.get("run_id") or "")) if latest_archive else {}
    candidates = list(latest_run.get("candidates") or status.get("top_candidates") or [])
    portfolio = load_portfolio()
    params = load_parameters()
    positions = list((portfolio.get("positions") or {}).values())
    decisions = _rows("autonomous_portfolio/decisions.json", DECISIONS_PATH)
    notifications = _rows("autonomous_portfolio/notifications.json", NOTIFICATIONS_PATH)
    performance = read_json("autonomous_portfolio/performance.json", PERFORMANCE_PATH, {})
    performance = dict(performance) if isinstance(performance, Mapping) else {}
    approvals = _rows("controlled_learning/promotion_approvals.json", APPROVALS_PATH)
    pending = [{**row, "approval_source": "LEARNING"} for row in approvals if str(row.get("status") or "").upper() == "PENDING"]
    try:
        from autonomi_core.configuration.registry import load_registry
        pending += [{**row, "approval_source": "CONFIGURATION"} for row in load_registry().get("approvals", []) if str(row.get("status") or "").upper() == "PENDING"]
    except Exception:
        pass
    contract = dict(latest_run.get("data_contract") or {})
    quality = dict(latest_run.get("data_quality") or {})
    push_rows = pushover_audit(100)
    push_latest = dict(push_rows[-1]) if push_rows else {}
    storage = get_storage_service().health()
    next_run = _next_scheduled_run(active_jobs)
    equity = portfolio_equity(portfolio)
    initial = _number(portfolio.get("initial_cash"), _number(getattr(params, "initial_cash", 0)))
    drawdown = _number(performance.get("drawdown_pct"), 0)
    return {
        "version": VERSION, "status": status, "running": is_running(status),
        "jobs": jobs, "active_jobs": active_jobs, "next_run": next_run,
        "archive": archive, "latest_archive": latest_archive, "latest_run": latest_run,
        "candidates": candidates, "portfolio": portfolio, "positions": positions,
        "equity": equity, "return_pct": ((equity / initial - 1) * 100 if initial else 0),
        "drawdown_pct": drawdown, "decisions": decisions,
        "notifications": notifications, "pending_approvals": pending,
        "data_contract": contract, "data_quality": quality,
        "pushover_ready": pushover_enabled(), "pushover_latest": push_latest,
        "scheduler": scheduler_status(), "storage": storage,
        "report_url": str(latest_archive.get("report_url") or latest_run.get("report_url") or ""),
        "report_pdf_path": latest_archive.get("pdf_path"),
    }


def _goto(workspace: str) -> None:
    st.session_state["autonomy_core_workspace_v1880"] = workspace
    st.session_state["autonomy_core_workspace_slug_v1882"] = ""
    st.rerun()


def _render_progress(snapshot: Mapping[str, Any], *, allow_quick_start: bool = True) -> None:
    status = dict(snapshot.get("status") or {})
    state = str(status.get("state") or "INGEN KJØRING")
    pct = max(0, min(100, int(status.get("percent") or 0)))
    st.progress(pct, text=f"{pct} % · {status.get('message') or state}")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Status", state)
    p2.metric("Aktivt steg", status.get("active_stage") or "-")
    p3.metric("Oppdatert", local_display(status.get("updated_at"), str(status.get("timezone_name") or "Europe/Oslo")))
    p4.metric("Kjørings-ID", status.get("execution_id") or "-")
    labels = {
        "MARKET_DATA": "Markedsdata", "INSIDER": "Insider", "NEWS": "Nyheter",
        "SCORING": "Rangering", "PORTFOLIO_PROPOSAL": "Portefølje",
        "AUTONOMOUS": "Autonomi", "REPORT": "Rapport", "COMPLETE": "Fullført",
    }
    completed = set(status.get("completed_steps") or [])
    active = str(status.get("active_stage") or "")
    stage_columns = st.columns(4)
    for index, (stage, label) in enumerate(labels.items()):
        if stage in completed:
            stage_columns[index % 4].success(f"✅ {label}")
        elif stage == active:
            stage_columns[index % 4].warning(f"⏳ {label}")
        else:
            stage_columns[index % 4].caption(f"⬜ {label}")
    if snapshot.get("running"):
        confirm = st.checkbox("Bekreft kontrollert avbrudd", key="autonomy_overview_cancel_confirm_v1883")
        if st.button("⛔ Avbryt pågående kjøring", disabled=not confirm, key="autonomy_overview_cancel_v1883"):
            request_cancel(str(status.get("execution_id") or ""), requested_by="AUTONOMY_OVERVIEW")
            st.warning("Stoppforespørselen er lagret. Kjøringen stopper ved neste sikre kontrollpunkt.")
            st.rerun()
    elif allow_quick_start:
        if st.button("▶ Start utkastkjøring", type="primary", key="autonomy_overview_start_v1883"):
            start_manual_job(load_draft_job(), trigger="MANUAL_DRAFT_TEST", force_refresh=False)
            st.rerun()


def render_autonomy_overview(*, allow_quick_start: bool = True) -> None:
    st.markdown("""
    <style>
    html body .stApp .autonomy-readable-card {font-size:1rem!important;line-height:1.55!important;color:#e5edf8!important;}
    html body .stApp .autonomy-readable-card .ar-row {display:grid;grid-template-columns:minmax(8.5rem,auto) 1fr;gap:.65rem;margin:.22rem 0;align-items:start;}
    html body .stApp .autonomy-readable-card .ar-label {font-weight:800;color:#f8fafc;}
    html body .stApp .autonomy-readable-card .ar-value {overflow-wrap:anywhere;min-width:0;}
    html body .stApp div[data-testid="stCaptionContainer"] {font-size:.92rem!important;line-height:1.45!important;color:#b9c7da!important;}
    html body .stApp div[data-testid="stAlert"] p {font-size:.96rem!important;line-height:1.4!important;}
    html body .stApp div[data-testid="stCheckbox"] label p {font-size:1rem!important;line-height:1.35!important;}
    html body .stApp div[data-testid="stCheckbox"] input {width:1.15rem!important;height:1.15rem!important;}
    @media (max-width:700px){html body .stApp .autonomy-readable-card .ar-row{grid-template-columns:1fr;gap:.05rem}.autonomy-readable-card{font-size:.98rem!important}}
    </style>
    """, unsafe_allow_html=True)
    snapshot = collect_autonomy_overview()
    status = snapshot["status"]
    latest = snapshot["latest_run"]
    st.markdown("### 🧭 Autonomi Oversikt")
    st.caption("Samlet daglig drift og overvåking. Alle tall hentes fra eksisterende, varige motor- og servicelag.")

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Aktivt oppdrag", status.get("job_name") or (snapshot["active_jobs"][0].name if snapshot["active_jobs"] else "Ingen aktiv tidsplan"))
    top2.metric("Produksjonskjede", status.get("active_stage") or status.get("chain_status") or "Klar")
    next_run = snapshot["next_run"]
    top3.metric("Neste kjøring", local_display(next_run.get("at"), next_run.get("timezone_name", "Europe/Oslo")) if next_run else "Ikke planlagt")
    top4.metric("Ventende godkjenninger", len(snapshot["pending_approvals"]))

    with st.container(border=True):
        st.markdown("#### Pågående kjøring, fremdrift og avbryt")
        _render_progress(snapshot, allow_quick_start=allow_quick_start)

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("#### Siste kandidater")
            candidates = snapshot["candidates"][:5]
            if candidates:
                rows = [{
                    "Ticker": row.get("ticker"), "Marked": row.get("market"),
                    "Score": row.get("investment_score"), "Konfidens": row.get("confidence_score"),
                    "Strategier": ", ".join(row.get("strategy_matches") or []) or row.get("strategy_match"),
                    "Handling": row.get("portfolio_action") or "Ikke vurdert",
                    "Datagyldighet": (row.get("data_contract") or {}).get("validity", "UKJENT"),
                } for row in candidates]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("Ingen kandidater er lagret ennå.")
        with st.container(border=True):
            st.markdown("#### Portefølje og risiko")
            q1, q2, q3, q4 = st.columns(4)
            q1.metric("Status", snapshot["portfolio"].get("status") or "-")
            q2.metric("Verdi", f"{snapshot['equity']:,.0f} kr")
            q3.metric("Avkastning", f"{snapshot['return_pct']:+.2f} %")
            q4.metric("Drawdown", f"{snapshot['drawdown_pct']:.2f} %")
            st.caption(f"{len(snapshot['positions'])} åpne teoretiske posisjoner · ingen ekte handler utføres.")
            if st.button("Åpne Learning Portfolio", key="autonomy_overview_portfolio_v1883"):
                _goto("Learning Portfolio")
    with right:
        with st.container(border=True):
            st.markdown("#### Siste beslutninger")
            decisions = snapshot["decisions"][:5]
            if decisions:
                decision_rows = [{
                    "Tid": row.get("timestamp") or row.get("at"),
                    "Ticker": row.get("ticker"), "Beslutning": row.get("decision") or row.get("action"),
                    "Score": row.get("score") or row.get("investment_score"),
                    "Årsak": row.get("reason"),
                } for row in decisions]
                st.dataframe(pd.DataFrame(decision_rows), use_container_width=True, hide_index=True)
            else:
                st.info("Ingen autonome beslutninger er registrert.")
        with st.container(border=True):
            st.markdown("#### Datakvalitet")
            contract = snapshot["data_contract"]
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Kontrollert", contract.get("evaluated", 0))
            d2.metric("Gyldig", contract.get("valid_for_decision", 0))
            d3.metric("Blokkert", len(contract.get("blocked") or []))
            d4.metric("Fallback", len(contract.get("fallback") or []))
            if contract.get("blocked"):
                st.warning("Beslutning blokkert for: " + ", ".join(contract.get("blocked") or []))
            elif latest:
                st.success("Datakontrakten har ingen registrerte kritiske blokkeringer.")
            else:
                st.info("Datakvalitet vises etter første rapportkjøring.")

    ops1, ops2, ops3 = st.columns(3)
    with ops1:
        with st.container(border=True):
            st.markdown("#### Pushover og drift")
            storage = snapshot["storage"]
            st.markdown(
                "<div class='autonomy-readable-card'>"
                f"<div class='ar-row'><span class='ar-label'>Pushover</span><span class='ar-value'>{'Klar' if snapshot['pushover_ready'] else 'Ikke konfigurert'}</span></div>"
                f"<div class='ar-row'><span class='ar-label'>Lagring</span><span class='ar-value'>{'PostgreSQL' if storage.ok and storage.persistent else 'Lokal fallback'}</span></div>"
                f"<div class='ar-row'><span class='ar-label'>Scheduler</span><span class='ar-value'>{snapshot['scheduler'].get('state') or 'IDLE'}</span></div>"
                "</div>", unsafe_allow_html=True,
            )
            push = snapshot["pushover_latest"]
            if push:
                st.caption(f"Siste levering: {'OK' if push.get('success') else 'Feil'} · {push.get('at', '-')}")
    with ops2:
        with st.container(border=True):
            st.markdown("#### Ventende godkjenninger")
            pending = snapshot["pending_approvals"]
            if pending:
                for item in pending[:5]:
                    approval_id = str(item.get("approval_id") or "")
                    st.warning(f"{item.get('version_id') or approval_id} · venter på eksplisitt godkjenning")
                    approve, reject = st.columns(2)
                    if approve.button("Godkjenn", key=f"overview_approve_{approval_id}", use_container_width=True):
                        if item.get("approval_source") == "CONFIGURATION":
                            from autonomi_core.configuration.registry import resolve_approval
                            resolve_approval(approval_id, True)
                        else:
                            resolve_promotion_approval(approval_id, True)
                        st.success("Promoteringen er godkjent.")
                        st.rerun()
                    if reject.button("Avvis", key=f"overview_reject_{approval_id}", use_container_width=True):
                        if item.get("approval_source") == "CONFIGURATION":
                            from autonomi_core.configuration.registry import resolve_approval
                            resolve_approval(approval_id, False)
                        else:
                            resolve_promotion_approval(approval_id, False)
                        st.warning("Promoteringen er avvist.")
                        st.rerun()
                if st.button("Behandle i Learning Portfolio", key="autonomy_overview_approvals_v1883"):
                    _goto("Learning Portfolio")
            else:
                st.success("Ingen ventende godkjenninger.")
    with ops3:
        with st.container(border=True):
            st.markdown("#### Siste rapport")
            report = snapshot["latest_archive"]
            if report:
                st.markdown(
                    "<div class='autonomy-readable-card'>"
                    f"<div class='ar-row'><span class='ar-label'>Rapporttype</span><span class='ar-value'>{report.get('report_label') or 'Rapport'}</span></div>"
                    f"<div class='ar-row'><span class='ar-label'>Jobb</span><span class='ar-value'>{report.get('job_name') or '-'}</span></div>"
                    f"<div class='ar-row'><span class='ar-label'>Tidspunkt</span><span class='ar-value'>{report.get('created_at_local') or report.get('created_at') or '-'}</span></div>"
                    f"<div class='ar-row'><span class='ar-label'>Rapport-ID</span><span class='ar-value'>{report.get('run_id') or '-'}</span></div>"
                    "</div>", unsafe_allow_html=True,
                )
                if snapshot["report_url"]:
                    st.link_button("Åpne siste rapport", snapshot["report_url"], use_container_width=True)
                else:
                    st.info("Offentlig rapportlenke er ikke tilgjengelig. Åpne rapportarkivet.")
            else:
                st.info("Ingen rapport er lagret.")

    c1, c2 = st.columns(2)
    if c1.button("Åpne Orchestrator og tidsplan", use_container_width=True, key="autonomy_overview_orchestrator_v1883"):
        _goto("Orchestrator og tidsplan")
    if c2.button("↻ Oppdater oversikten", use_container_width=True, key="autonomy_overview_refresh_v1883"):
        st.rerun()
