"""Operational Autonomy overview for v18.8.3.

This module is deliberately a read/command facade over existing durable
services.  It contains no candidate, ranking, portfolio or scheduler logic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
import json
from typing import Any, Mapping
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from autonomous_portfolio import (
    DECISIONS_PATH, NOTIFICATIONS_PATH, PERFORMANCE_PATH,
    load_parameters, load_portfolio, portfolio_equity, portfolio_status_summary,
)
from controlled_parameter_learning import APPROVALS_PATH
from durable_runtime import read_json
from local_time import local_display
from manual_job_background import (
    diagnostic_bundle, force_release, get_active_status, get_active_status_snapshot,
    is_running, request_cancel, start_manual_job,
)
from market_intelligence import (
    _load_report_archive, load_draft_job, load_jobs, load_run,
    load_archived_run, resolve_report_delivery, safe_report_filename,
)
from notifier import pushover_audit, pushover_enabled
from scheduler_background import scheduler_status
from services.storage_service import get_storage_service
from app_version import get_app_version


VERSION = get_app_version()
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "STALLED"}


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
    # A failed/incomplete publication must not hide the last usable report.
    # Keep the archive order authoritative and select the first public URL.
    latest_linked_archive = next(
        (dict(row) for row in archive if isinstance(row, Mapping) and str(row.get("report_url") or "").strip()),
        {},
    )
    latest_run = load_archived_run(latest_archive) if latest_archive else {}
    completed_run_id = str(status.get("run_id") or "") if str(status.get("state") or "") == "COMPLETED" else ""
    completed_run = load_run(completed_run_id) if completed_run_id else {}
    if completed_run:
        latest_run = completed_run
    parallel_validation = dict(latest_run.get("parallel_validation") or {})
    if parallel_validation:
        try:
            from autonomi_core.runtime.parallel_validation import refresh_parallel_outcomes
            parallel_validation = refresh_parallel_outcomes(parallel_validation)
        except Exception:
            pass
    candidates = list(latest_run.get("candidates") or status.get("top_candidates") or [])
    portfolio = load_portfolio()
    params = load_parameters()
    positions = list((portfolio.get("positions") or {}).values())
    decisions = _rows("autonomous_portfolio/decisions.json", DECISIONS_PATH)
    if not decisions:
        decisions = [dict(row) for row in latest_run.get("autonomous_decisions") or [] if isinstance(row, Mapping)]
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
        "report_url": str(
            latest_archive.get("report_url")
            or latest_run.get("report_url")
            or latest_linked_archive.get("report_url")
            or ""
        ),
        "latest_linked_archive": latest_linked_archive,
        "completed_run": completed_run,
        "report_pdf_path": latest_archive.get("pdf_path"),
        "parallel_validation": parallel_validation,
        "decision_funnel": dict(latest_run.get("decision_funnel") or {}),
    }


def _goto(workspace: str) -> None:
    """Navigate without mutating an instantiated widget key."""
    slug = {
        "Autonom portefølje": "autonomous_portfolio",
        "Læringsportefølje": "learning_portfolio",
        "Learning Portfolio": "learning_portfolio",
        "Rapporter": "reports",
        "Oversikt": "overview",
    }.get(str(workspace), "overview")
    st.session_state["autonomy_core_workspace_slug_v1882"] = slug
    st.rerun()



def _render_autonomy_status_box(snapshot: Mapping[str, Any]) -> None:
    """Always-visible operational status for Autonomy.

    v19.0.18a: The detailed autonomy status existed in the learning portfolio,
    but users could not see it on the main Autonomi page. Keep this box outside
    any expander and place it at the top of Autonomi Oversikt so diagnostics are
    visible immediately after deploy, refresh and mobile navigation.
    """
    try:
        from autonomous_orchestrator import load_latest_chain
        latest_chain = load_latest_chain()
    except Exception:
        latest_chain = dict(snapshot.get("latest_run") or {})

    panel = portfolio_status_summary(latest_chain)
    scheduler_raw = str((snapshot.get("scheduler") or {}).get("state") or "").upper()
    if scheduler_raw in {"IDLE", "RUNNING", "COMPLETED"}:
        panel["Planlegger"] = "Aktiv"
    elif scheduler_raw == "ERROR":
        panel["Planlegger"] = "Feil"

    candidates = int(panel.get("Kandidater mottatt") or 0)
    buys = int(panel.get("Ordinære porteføljekjøp") or panel.get("Teoretiske kjøp") or 0)
    learning_buys = int(panel.get("Læringsposisjoner opprettet") or panel.get("Læringskjøp") or 0)
    reason = str(panel.get("Årsak til ingen kjøp") or "Ingen siste kjøring")
    problem = candidates == 0 or (buys == 0 and learning_buys == 0)

    st.markdown("#### 🧭 Autonomi status")
    st.caption("Samlet driftsstatus for autonom kjøring. Denne boksen er alltid synlig og viser om problemet ligger i runner, planlegger, kandidatflyt eller kjøpsporter.")
    with st.container(border=True):
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        r1c1.metric("Autonomi-runner", panel.get("Autonomi-runner", "Ukjent"))
        r1c2.metric("Planlegger", panel.get("Planlegger", "Ukjent"))
        r1c3.metric("Paper trading", panel.get("Paper trading", "Ukjent"))
        r1c4.metric("Ekte handel", panel.get("Ekte handel", "Deaktivert"))
        r2c1, r2c2, r2c3, r2c4 = st.columns(4)
        r2c1.metric("Kandidater mottatt", candidates)
        r2c2.metric("Ordinære kjøp sist", buys)
        r2c3.metric("Læringsposisjoner opprettet sist", learning_buys)
        r2c4.metric("Læring aktivert", "Ja" if panel.get("Læringskjøp aktivert") else "Nei")
        r3c1, r3c2, r3c3, r3c4 = st.columns(4)
        r3c1.metric("Åpne autonome posisjoner", int(panel.get("Åpne autonome posisjoner") or 0))
        r3c2.metric("Åpne læringsposisjoner", int(panel.get("Åpne læringsposisjoner") or 0))
        r3c3.metric("Porteføljer adskilt", "Ja")
        r3c4.metric("Ekte ordre sendt", "Nei")
        if problem:
            st.warning(f"Årsak til ingen kjøp: {reason}")
        else:
            st.success(reason or "Autonomi har mottatt kandidater og opprettet teoretiske kjøp.")

        handoff = dict((snapshot.get("latest_run") or {}).get("autonomy_candidate_handoff") or {})
        if handoff:
            h1, h2, h3, h4 = st.columns(4)
            h1.metric("Rapportkandidater", int(handoff.get("report_candidates") or 0))
            h2.metric("Sendt til Autonomi", int(handoff.get("forwarded_candidates") or handoff.get("sent_to_autonomy") or 0))
            h3.metric("Mottatt av Autonomi", int(handoff.get("received_by_autonomy") or candidates or 0))
            h4.metric("Avvik", "Ja" if handoff.get("handoff_mismatch") else "Nei")
        st.caption("Ekte handel er fortsatt deaktivert. Ordinære porteføljekjøp og læringsposisjoner føres i separate porteføljer og separate resultatregnskap.")
        nav_left, nav_right = st.columns(2)
        if nav_left.button("📈 Åpne autonom portefølje", width="stretch", key="overview_open_autonomous_portfolio_v19018b"):
            _goto("Autonom portefølje")
        if nav_right.button("🧪 Vis læringsportefølje", width="stretch", key="overview_open_learning_portfolio_v19018b"):
            _goto("Læringsportefølje")

def _safe_public_report_url(value: Any) -> str:
    """Accept only absolute HTTP(S) report links for the rendered anchor."""
    url = str(value or "").strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and bool(parsed.netloc) else ""


def _render_report_link(url: Any) -> bool:
    """Render a stable, high-contrast link independent of Streamlit DOM names."""
    safe_url = _safe_public_report_url(url)
    if not safe_url:
        return False
    st.markdown(
        '<a class="autonomy-report-link-v1901" '
        f'href="{escape(safe_url, quote=True)}" target="_blank" rel="noopener noreferrer" '
        'aria-label="Åpne offentlig PDF utenfor appen">↗ Ekstern PDF (kan forlate appen)</a>',
        unsafe_allow_html=True,
    )
    return True


def _render_report_delivery(run: Mapping[str, Any], entry: Mapping[str, Any], *, key: str) -> bool:
    """Always provide a validated byte download; public URL is only secondary."""
    delivery = resolve_report_delivery(run, entry)
    if not delivery.get("ok"):
        st.error(str(delivery.get("error") or "PDF-en kan ikke gjenopprettes fra rapportdataene."))
        return False
    left, middle = st.columns(2)
    left.download_button(
        "📄 Last ned PDF – kan deles",
        data=delivery["data"],
        file_name=delivery["filename"],
        mime="application/pdf",
        key=f"{key}_pdf",
        width="stretch",
    )
    middle.download_button(
        "{ } Last ned JSON",
        data=json.dumps(dict(run), ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        file_name=safe_report_filename(run, "json"),
        mime="application/json",
        key=f"{key}_json",
        width="stretch",
    )
    st.caption("På mobil: bruk Last ned PDF for å beholde appen åpen og dele filen fra telefonens delingsmeny.")
    if delivery.get("url"):
        with st.expander("Ekstern offentlig PDF", expanded=False):
            st.warning("Denne lenken kan åpne rapporten utenfor appen på iPhone/PWA. Bruk nettleserens tilbakeknapp for å returnere.")
            _render_report_link(delivery["url"])
    else:
        st.caption("Offentlig rapportlenke er ikke tilgjengelig; den nedlastede PDF-filen kan fortsatt deles.")
    status = "Regenerert og validert" if delivery.get("regenerated") else "Generert og validert"
    st.caption(f"PDF-status: {status} · rapport-ID {run.get('run_id') or '-'}")
    return True


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
    now = datetime.now(timezone.utc)
    progress_at = status.get("last_progress_at") or status.get("updated_at")
    heartbeat_at = status.get("worker_heartbeat_at") or status.get("heartbeat_at")
    def _age_seconds(value: Any) -> int | None:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0, int((now - parsed.astimezone(timezone.utc)).total_seconds()))
        except (TypeError, ValueError):
            return None
    progress_age = _age_seconds(progress_at)
    heartbeat_age = _age_seconds(heartbeat_at)
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Siste reelle fremdrift", f"{progress_age} sek siden" if progress_age is not None else "-")
    t2.metric("Worker-heartbeat", f"{heartbeat_age} sek siden" if heartbeat_age is not None else "-")
    work_completed, work_total = status.get("work_completed"), status.get("work_total")
    t3.metric("Arbeidsenheter", f"{work_completed}/{work_total}" if work_total not in (None, "", 0) else "-")
    context = status.get("active_ticker") or status.get("active_market") or "-"
    t4.metric("Arbeider med", context)
    limit = int(status.get("stage_progress_limit_seconds") or 0)
    if state == "RUNNING" and progress_age is not None and progress_age >= 60:
        remaining = max(0, limit - progress_age) if limit else 0
        st.warning(
            f"Worker lever, men steget har ikke meldt reell fremdrift på {progress_age} sekunder. "
            + (f"Automatisk frigivelse skjer senest om ca. {remaining} sekunder." if limit else "Fremdriftsvakten følger jobben.")
        )
    labels = {
        "PREFLIGHT": "Oppstartskontroll", "MARKET_DATA": "Markedsdata", "INSIDER": "Insider", "NEWS": "Nyheter",
        "SCORING": "Rangering", "PORTFOLIO_PROPOSAL": "Portefølje",
        "AUTONOMOUS": "Autonomi", "REPORT": "Rapport", "COMPLETE": "Fullført",
    }
    completed = set(status.get("completed_steps") or [])
    active = str(status.get("active_stage") or "")
    event = dict(status.get("progress_event") or {})
    market_index = int(event.get("market_index") or 0)
    market_total = int(event.get("market_total") or 0)
    # MARKET_DATA/INSIDER/NEWS/SCORING repeat for every market. They are not
    # globally complete until the pipeline reaches DEDUP or a later phase.
    if str(status.get("phase") or "") not in {"DEDUP", "PORTFOLIO_PROPOSAL", "AUTONOMOUS", "REPORT", "COMPLETE"}:
        completed -= {"MARKET_DATA", "INSIDER", "NEWS", "SCORING", "PORTFOLIO_PROPOSAL"}
    if market_total:
        finished_markets = max(0, market_index - (0 if str(status.get("phase")) == "SCORING" and int(event.get("completed") or 0) >= int(event.get("total") or 1) else 1))
        st.caption(f"Markedsgjennomføring: {min(finished_markets, market_total)}/{market_total} ferdig · arbeider med marked {min(max(1, market_index), market_total)}/{market_total}.")
    stage_columns = st.columns(4)
    for index, (stage, label) in enumerate(labels.items()):
        if stage in completed:
            stage_columns[index % 4].success(f"✅ {label}")
        elif stage == active:
            stage_columns[index % 4].warning(f"⏳ {label}")
        else:
            stage_columns[index % 4].caption(f"⬜ {label}")
    if state in {"FAILED", "STALLED"}:
        st.error(
            f"{status.get('error_type') or 'Feil'} i {status.get('error_stage') or active or 'ukjent steg'}: "
            f"{status.get('error') or 'Ingen feildetalj ble lagret.'}"
        )
        with st.expander("Vis teknisk diagnostikk", expanded=False):
            st.code(str(status.get("error_trace") or "Ingen traceback er lagret."))
            st.json({
                "kjørings_id": status.get("execution_id"), "steg": status.get("error_stage") or active,
                "tidspunkt": status.get("updated_at"), "hendelse": event,
            })
    execution_id = str(status.get("execution_id") or "")
    if execution_id and state in TERMINAL_STATES:
        bundle, filename = diagnostic_bundle(execution_id)
        st.download_button(
            "🩺 Last ned diagnosepakke", data=bundle, file_name=filename,
            mime="application/zip", key=f"manual_job_diag_{execution_id}",
        )
    if snapshot.get("running"):
        confirm = st.checkbox("Bekreft kontrollert avbrudd", key="autonomy_overview_cancel_confirm_v1883")
        if st.button("⛔ Avbryt pågående kjøring", disabled=not confirm, key="autonomy_overview_cancel_v1883"):
            request_cancel(str(status.get("execution_id") or ""), requested_by="AUTONOMY_OVERVIEW")
            st.warning("Stoppforespørselen er lagret. Kjøringen stopper ved neste sikre kontrollpunkt.")
            st.rerun()
        if progress_age is not None and progress_age >= 60:
            release_confirm = st.checkbox("Bekreft sikker frigivelse av fastlåst jobb", key=f"manual_release_confirm_{execution_id}")
            if st.button("🔓 Frigi fastlåst jobb", disabled=not release_confirm, key=f"manual_release_{execution_id}"):
                force_release(execution_id, requested_by="AUTONOMY_OVERVIEW")
                st.warning(
                    "Publiseringsretten er tilbakekalt. Vent til workeren og rapportlåsen er avsluttet "
                    "før en ny kjøring startes; ved vedvarende heng må webtjenesten restartes."
                )
                st.rerun()
    elif allow_quick_start:
        if st.button("▶ Start utkastkjøring", type="primary", key="autonomy_overview_start_v1883"):
            start_shared_manual_draft_job(trigger="MANUAL_DRAFT_TEST")
            st.success("Utkastkjøringen er startet. Fremdriften oppdateres automatisk i panelet.")


def _live_progress_panel(*, allow_quick_start: bool = True, refresh_app_on_terminal: bool = True) -> None:
    """Poll only durable job status; never rerender the full Autonomy page."""
    status = get_active_status_snapshot() or {}
    _render_progress({"status": status, "running": is_running(status)}, allow_quick_start=allow_quick_start)
    if is_running(status):
        st.caption("Status og fremdrift oppdateres automatisk hvert 5. sekund mens kjøringen pågår.")
    execution_id = str(status.get("execution_id") or "")
    if refresh_app_on_terminal and str(status.get("state") or "") in TERMINAL_STATES and execution_id:
        refresh_key = "autonomy_overview_terminal_refresh_v1902"
        if st.session_state.get(refresh_key) != execution_id:
            st.session_state[refresh_key] = execution_id
            try:
                st.rerun(scope="app")
            except TypeError:
                st.rerun()


def _render_live_progress(
    *,
    allow_quick_start: bool = True,
    refresh_app_on_terminal: bool = True,
) -> None:
    # A periodic Streamlit fragment remains scheduled until the fragment is
    # removed from the page.  Only create it for an actually active job;
    # completed/failed/cancelled pages are rendered once and stay idle.
    status = get_active_status() or {}
    running = is_running(status)
    fragment = getattr(st, "fragment", None)
    if running and callable(fragment):
        fragment(run_every="5s")(_live_progress_panel)(
            allow_quick_start=allow_quick_start,
            refresh_app_on_terminal=refresh_app_on_terminal,
        )
    else:
        _live_progress_panel(
            allow_quick_start=allow_quick_start,
            refresh_app_on_terminal=refresh_app_on_terminal,
        )


def start_shared_manual_draft_job(*, trigger: str = "MANUAL_DRAFT_TEST") -> dict[str, Any]:
    """Start the one authoritative draft engine used by Overview and Reports.

    This function deliberately owns both draft loading and worker acceptance so
    report-center buttons cannot drift into a second execution path.
    """
    return start_manual_job(
        load_draft_job(),
        trigger=str(trigger or "MANUAL_DRAFT_TEST"),
        force_refresh=False,
    )


def render_shared_manual_job_progress(
    *,
    allow_quick_start: bool = False,
    refresh_app_on_terminal: bool = False,
) -> None:
    """Render the same proven progress fragment used by Autonomi Oversikt."""
    _render_live_progress(
        allow_quick_start=allow_quick_start,
        refresh_app_on_terminal=refresh_app_on_terminal,
    )


def render_autonomy_overview(*, allow_quick_start: bool = True) -> None:
    st.markdown("""
    <style>
    html body .stApp .autonomy-readable-card {font-size:clamp(1.05rem,.96rem + .15vw,1.18rem)!important;line-height:1.65!important;color:#f1f5f9!important;}
    html body .stApp .autonomy-readable-card .ar-row {display:grid;grid-template-columns:minmax(10rem,auto) 1fr;gap:1rem;margin:.38rem 0;align-items:start;min-height:1.7rem;}
    html body .stApp .autonomy-readable-card .ar-label {font-weight:800;color:#f8fafc;}
    html body .stApp .autonomy-readable-card .ar-value {overflow-wrap:anywhere;min-width:0;}
    html body .stApp div[data-testid="stCaptionContainer"] {font-size:.92rem!important;line-height:1.45!important;color:#b9c7da!important;}
    html body .stApp div[data-testid="stAlert"] p {font-size:.96rem!important;line-height:1.4!important;}
    html body .stApp div[data-testid="stCheckbox"] label p {font-size:1rem!important;line-height:1.35!important;}
    html body .stApp div[data-testid="stCheckbox"] input {width:1.15rem!important;height:1.15rem!important;}
    html body .stApp [data-testid="stVerticalBlockBorderWrapper"]:has(.autonomy-readable-card){min-height:13rem!important;padding:1.05rem 1.15rem!important;}
    html body .stApp [data-testid="stVerticalBlockBorderWrapper"]:has(.autonomy-readable-card) h4{font-size:1.35rem!important;line-height:1.35!important;margin-bottom:.65rem!important;}
    html body .stApp [data-testid="stVerticalBlockBorderWrapper"]:has(.autonomy-readable-card) .stButton button,
    html body .stApp [data-testid="stVerticalBlockBorderWrapper"]:has(.autonomy-readable-card) a[data-testid="stBaseLinkButton-secondary"]{min-height:3rem!important;font-size:1rem!important;font-weight:800!important;background:#172033!important;color:#fff!important;border:1px solid #4d6484!important;opacity:1!important;}
    html body .stApp [data-testid="stVerticalBlockBorderWrapper"]:has(.autonomy-readable-card) a[data-testid="stBaseLinkButton-secondary"]:hover,
    html body .stApp [data-testid="stVerticalBlockBorderWrapper"]:has(.autonomy-readable-card) a[data-testid="stBaseLinkButton-secondary"]:focus{background:#087fb3!important;color:#fff!important;border-color:#38bdf8!important;}
    html body .stApp [data-testid="stVerticalBlockBorderWrapper"]:has(.autonomy-readable-card) a[data-testid="stBaseLinkButton-secondary"] p{color:#fff!important;opacity:1!important;}
    html body .stApp a.autonomy-report-link-v1901,
    html body .stApp a.autonomy-report-link-v1901:link,
    html body .stApp a.autonomy-report-link-v1901:visited{
      display:flex!important;align-items:center!important;justify-content:center!important;
      width:100%!important;min-height:3rem!important;padding:.58rem .9rem!important;
      margin:.45rem 0 .1rem!important;border:1px solid #64748b!important;border-radius:.55rem!important;
      background:#172033!important;color:#fff!important;-webkit-text-fill-color:#fff!important;
      font-size:1rem!important;font-weight:850!important;line-height:1.25!important;
      text-decoration:none!important;opacity:1!important;box-shadow:0 1px 4px rgba(0,0,0,.28)!important;
    }
    html body .stApp a.autonomy-report-link-v1901:hover,
    html body .stApp a.autonomy-report-link-v1901:focus,
    html body .stApp a.autonomy-report-link-v1901:focus-visible{
      background:#087fb3!important;color:#fff!important;-webkit-text-fill-color:#fff!important;
      border-color:#7dd3fc!important;outline:3px solid rgba(56,189,248,.38)!important;outline-offset:2px!important;
    }
    @media (max-width:700px){html body .stApp .autonomy-readable-card .ar-row{grid-template-columns:1fr;gap:.05rem}.autonomy-readable-card{font-size:.98rem!important}}
    </style>
    """, unsafe_allow_html=True)
    snapshot = collect_autonomy_overview()
    status = snapshot["status"]
    latest = snapshot["latest_run"]
    st.markdown("### 🧭 Autonomi Oversikt")
    st.caption("Samlet daglig drift og overvåking. Alle tall hentes fra eksisterende, varige motor- og servicelag.")

    _render_autonomy_status_box(snapshot)

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Aktivt oppdrag", status.get("job_name") or (snapshot["active_jobs"][0].name if snapshot["active_jobs"] else "Ingen aktiv tidsplan"))
    top2.metric("Produksjonskjede", status.get("active_stage") or status.get("chain_status") or "Klar")
    next_run = snapshot["next_run"]
    top3.metric("Neste kjøring", local_display(next_run.get("at"), next_run.get("timezone_name", "Europe/Oslo")) if next_run else "Ikke planlagt")
    top4.metric("Ventende godkjenninger", len(snapshot["pending_approvals"]))

    with st.container(border=True):
        st.markdown("#### Pågående kjøring, fremdrift og avbryt")
        _render_live_progress(allow_quick_start=allow_quick_start)
        # Never present an older successful run as part of a new running or
        # failed job.  The worker exposes the result run_id only after the
        # current execution has completed and persistence is verified.
        current_result_id = str(status.get("run_id") or "")
        latest_result_id = str(latest.get("run_id") or "")
        show_current_execution = (
            str(status.get("state") or "") == "COMPLETED"
            and bool(current_result_id)
            and current_result_id == latest_result_id
        )
        full_execution = dict(latest.get("full_autonomy_execution") or {}) if show_current_execution else {}
        if full_execution:
            done = int(full_execution.get("completed_steps") or 0)
            total = int(full_execution.get("total_steps") or 13)
            if full_execution.get("self_contained"):
                st.success(f"Full Autonomy Execution: {done}/{total} trinn fullført · ingen manuelle avhengigheter")
            else:
                st.error("Full Autonomy Execution er ufullstendig: " + ", ".join(full_execution.get("failed_stages") or []))
            with st.expander("Vis alle 13 Autonomi-trinn", expanded=False):
                st.dataframe(pd.DataFrame([{ "#": x.get("number"), "Trinn": x.get("label"), "Status": x.get("status") } for x in full_execution.get("stages") or []]), width="stretch", hide_index=True)
            if full_execution.get("self_contained"):
                st.markdown("##### Ferdig rapport")
                current_entry = next(
                    (dict(row) for row in snapshot.get("archive") or []
                     if str(row.get("run_id") or "") == current_result_id),
                    {},
                )
                _render_report_delivery(
                    latest,
                    current_entry,
                    key=f"autonomy_completed_{current_result_id}",
                )
        parallel = dict(snapshot.get("parallel_validation") or {})
        if parallel:
            comparison = dict(parallel.get("comparison") or {})
            candidate_cmp = dict(comparison.get("candidates") or {})
            decision_cmp = dict(comparison.get("decisions") or {})
            gate = dict(parallel.get("validation_gate") or {})
            shadow_summary = (
                f"Shadow Mode {parallel.get('version')}: gammel kjede er autoritativ · "
                f"kandidatoverlapping {candidate_cmp.get('jaccard_pct', 0)} % · "
                f"beslutningssamsvar {decision_cmp.get('agreement_pct', 0)} %"
            )
            if gate.get("status") == "RED":
                st.error("🔴 " + shadow_summary + " · aktivering sperret")
                for warning in gate.get("warnings") or []:
                    st.caption(str(warning))
            elif gate.get("status") == "YELLOW":
                st.warning("🟡 " + shadow_summary + " · avvik krever forklaring")
            else:
                st.success("🟢 " + shadow_summary)
            with st.expander("Vis Parallel Validation", expanded=False):
                st.json({"autoritet": parallel.get("authoritative_chain"), "modus": parallel.get("mode"), "kontrollport": gate})
                decision_diff = list(decision_cmp.get("diff") or [])
                if decision_diff:
                    st.dataframe(pd.DataFrame(decision_diff), width="stretch", hide_index=True)
                else:
                    st.caption("Ingen kandidatvis beslutningsdiff er tilgjengelig for denne eldre kjøringen.")
        discovery_learning = dict(latest.get("controlled_discovery_learning") or {})
        if discovery_learning:
            created = list(discovery_learning.get("created_challengers") or [])
            if discovery_learning.get("error"):
                st.warning(f"Controlled Discovery Learning: {discovery_learning.get('error')}")
            else:
                st.caption(f"Controlled Discovery Learning: {len(created)} nye Challenger-forslag · produksjon uendret · godkjenning kreves.")

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
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
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
            if st.button("Åpne Læringsportefølje", key="autonomy_overview_portfolio_v1883"):
                _goto("Læringsportefølje")
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
                st.dataframe(pd.DataFrame(decision_rows), width="stretch", hide_index=True)
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

    funnel = snapshot.get("decision_funnel") or {}
    if funnel:
        with st.expander("Beslutningstrakt og kjøpsvurdering", expanded=False):
            f1, f2, f3, f4 = st.columns(4)
            f1.metric("Vurdert", funnel.get("evaluated", 0))
            f2.metric("Kjøpskvalifisert", funnel.get("eligible", 0))
            f3.metric("Avvist", funnel.get("rejected", 0))
            f4.metric("Produksjonsterskel", funnel.get("production_threshold", 78))
            near = list(funnel.get("near_threshold") or [])
            if near:
                st.dataframe(pd.DataFrame([{
                    "Ticker": row.get("ticker"), "Score / terskel": f"{row.get('score')} / {row.get('production_threshold')}",
                    "Datakvalitet": row.get("data_quality"), "Risiko": row.get("risk"),
                    "Portefølje": row.get("portfolio_action"), "Avslagsgrunn": "; ".join(row.get("reasons") or []),
                } for row in near]), width="stretch", hide_index=True)
            shadow = list(funnel.get("shadow_thresholds") or [])
            if shadow:
                st.markdown("##### Shadow Mode – kjøpsterskel")
                st.dataframe(pd.DataFrame([{
                    "Terskel": row.get("threshold"), "Rolle": row.get("role"),
                    "Score bestått": row.get("score_qualified_count"), "Alle porter bestått": row.get("eligible_count"),
                    "Kandidater": ", ".join(row.get("eligible_tickers") or []) or "Ingen",
                    "Produksjon endret": "NEI",
                } for row in shadow]), width="stretch", hide_index=True)
            st.info("Challenger-tersklene er kun diagnostikk. Produksjonsterskelen endres ikke uten eksplisitt godkjenning.")

    ops1, ops2, ops3 = st.columns(3)
    with ops1:
        with st.container(border=True):
            st.markdown("#### Pushover og drift")
            storage = snapshot["storage"]
            st.markdown(
                "<div class='autonomy-readable-card'>"
                f"<div class='ar-row'><span class='ar-label'>Pushover</span><span class='ar-value'>{'Klar' if snapshot['pushover_ready'] else 'Ikke konfigurert'}</span></div>"
                f"<div class='ar-row'><span class='ar-label'>Lagring</span><span class='ar-value'>{'PostgreSQL' if storage.ok and storage.persistent else 'Lokal fallback'}</span></div>"
                f"<div class='ar-row'><span class='ar-label'>Planlegger</span><span class='ar-value'>{ {'IDLE':'Venter','ERROR':'Feil','RUNNING':'Kjører','COMPLETED':'Fullført'}.get(str(snapshot['scheduler'].get('state') or 'IDLE').upper(), snapshot['scheduler'].get('state') or 'Venter') }</span></div>"
                "</div>", unsafe_allow_html=True,
            )
            push = snapshot["pushover_latest"]
            if push:
                st.markdown(
                    "<div class='autonomy-readable-card'>"
                    f"<div class='ar-row'><span class='ar-label'>Siste levering</span><span class='ar-value'>{'OK' if push.get('success') else 'Feil'} · {push.get('at', '-')}</span></div>"
                    "</div>", unsafe_allow_html=True,
                )
    with ops2:
        with st.container(border=True):
            st.markdown("#### Ventende godkjenninger")
            pending = snapshot["pending_approvals"]
            if pending:
                from approval_governance_ui import render_approval_card, inject_approval_mobile_css
                inject_approval_mobile_css()
                for item in pending[:5]:
                    render_approval_card(item, key_prefix="overview", compact=True)
                if st.button("Åpne Læringsportefølje", key="autonomy_overview_approvals_v1913", width="stretch"):
                    _goto("Læringsportefølje")
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
                report_run = load_archived_run(report) or snapshot.get("latest_run") or {}
                _render_report_delivery(
                    report_run,
                    report,
                    key=f"autonomy_latest_{report.get('run_id') or 'none'}",
                )
            else:
                st.info("Ingen rapport er lagret.")

    c1, c2 = st.columns(2)
    if c1.button("Åpne Orchestrator og tidsplan", width="stretch", key="autonomy_overview_orchestrator_v1883"):
        _goto("Orchestrator og tidsplan")
    if c2.button("↻ Oppdater oversikten", width="stretch", key="autonomy_overview_refresh_v1883"):
        st.rerun()
