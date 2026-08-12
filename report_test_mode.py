"""Durable, bounded 30-minute Autonomi report/Pushover acceptance mode."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import time
from typing import Any, Mapping
import uuid

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

STATE_KEY = "scheduler/report_test_mode.json"
STATE_PATH = runtime_data_path("scheduler", "report_test_mode.json")
INTERVAL_MINUTES = 30
MAX_SUCCESSES = 4
MAX_DURATION_HOURS = 4
MAX_FAILURES = 3
PERSIST_RETRIES = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _exception_detail(exc: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = exc
    while current is not None and len(parts) < 4:
        text = f"{type(current).__name__}: {current}"
        if text not in parts:
            parts.append(text)
        current = current.__cause__ or current.__context__
    return " <- ".join(parts)[:2000]


def _next_half_hour(value: datetime) -> datetime:
    value = value.astimezone(timezone.utc)
    base = value.replace(second=0, microsecond=0)
    if base.minute < 30:
        return base.replace(minute=30)
    return (base.replace(minute=0) + timedelta(hours=1))


def _persist_state(state: Mapping[str, Any]) -> None:
    last_error: BaseException | None = None
    for attempt in range(PERSIST_RETRIES):
        try:
            write_json(STATE_KEY, STATE_PATH, dict(state))
            return
        except Exception as exc:
            last_error = exc
            if attempt + 1 < PERSIST_RETRIES:
                time.sleep(0.25 * (attempt + 1))
    assert last_error is not None
    raise RuntimeError(
        f"Teststatus kunne ikke lagres etter {PERSIST_RETRIES} forsøk: {_exception_detail(last_error)}"
    ) from last_error


def _new_series_id(now: datetime | None = None) -> str:
    value = (now or _now()).astimezone(timezone.utc)
    return f"RTS-{value.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def _add_event(state: dict[str, Any], event: str, **values: Any) -> None:
    row = {"at": _now().isoformat(timespec="seconds"), "event": str(event), **values}
    state["timeline"] = (list(state.get("timeline") or []) + [row])[-40:]


def _send_terminal_summary(state: dict[str, Any], *, passed: bool, reason: str) -> None:
    if state.get("terminal_notification_sent"):
        return
    try:
        from notifier import send_pushover_alert
        from app_version import APP_VERSION

        successes = int(state.get("successes") or 0)
        failures = int(state.get("failures") or 0)
        attempts = int(state.get("attempts") or 0)
        series_id = str(state.get("series_id") or "-")
        outcome = "4/4 BESTÅTT" if passed else "TESTSERIEN FEILET"
        ok, detail = send_pushover_alert(
            "\n".join([
                f"Testserie: {series_id}",
                f"Resultat: {outcome}",
                f"Vellykkede: {successes}/4 · Kjøringsforsøk: {attempts}",
                f"Retry/feilede forsøk: {failures}",
                f"Siste rapport-ID: {state.get('last_report_id') or '-'}",
                f"Programversjon: {APP_VERSION}",
                f"Årsak: {reason}",
            ]),
            title=f"{'✅' if passed else '❌'} RAPPORTTEST · {outcome}",
        )
        state["terminal_notification_sent"] = bool(ok)
        state["terminal_notification_status"] = "Sendt" if ok else f"Feilet: {detail or 'ukjent feil'}"
        _add_event(state, "TERMINAL_NOTIFICATION", sent=bool(ok), outcome=outcome, detail=str(detail or "Sendt"))
    except Exception as exc:
        state["terminal_notification_sent"] = False
        state["terminal_notification_status"] = f"Feilet: {_exception_detail(exc)}"
        _add_event(state, "TERMINAL_NOTIFICATION_FAILED", detail=_exception_detail(exc))


def load_report_test_mode() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    state = dict(value) if isinstance(value, Mapping) else {}
    return {
        "enabled": False, "successes": 0, "failures": 0,
        "phase": "INACTIVE", "status_message": "Testserien er ikke aktiv.",
        "expected_first_start_at": "", "expected_result_at": "",
        **state,
    }


def set_report_test_mode(enabled: bool) -> dict[str, Any]:
    current = load_report_test_mode()
    now = _now().isoformat(timespec="seconds")
    if enabled and not current.get("enabled"):
        current = {
            "enabled": True, "enabled_at": now, "updated_at": now,
            "series_id": _new_series_id(),
            "next_due_at": now,
            "last_started_at": "", "last_completed_at": "", "last_report_id": "",
            "last_notification_status": "", "last_error": "", "successes": 0, "failures": 0,
            "attempts": 0, "timeline": [], "terminal_notification_sent": False,
            "phase": "WAITING_FOR_SCHEDULER",
            "status_message": "Testserien er aktivert. Første rapport starter ved neste schedulerkjøring.",
            "expected_first_start_at": now,
            "expected_result_at": "",
        }
        _add_event(current, "SERIES_ENABLED", part="0/4")
    elif not enabled:
        current.update({
            "enabled": False, "disabled_at": now, "updated_at": now, "disabled_reason": "OPERATOR",
            "phase": "INACTIVE", "status_message": "Testserien er stoppet av operatøren.",
        })
        _add_event(current, "SERIES_DISABLED", reason="OPERATOR")
    _persist_state(current)
    return current


def test_mode_due(state: Mapping[str, Any] | None = None, *, now: datetime | None = None) -> bool:
    state = dict(state or load_report_test_mode())
    now = now or _now()
    if not state.get("enabled"):
        return False
    try:
        enabled_at = datetime.fromisoformat(str(state.get("enabled_at") or "").replace("Z", "+00:00"))
        if now - enabled_at.astimezone(timezone.utc) >= timedelta(hours=MAX_DURATION_HOURS):
            return False
    except Exception:
        return False
    if int(state.get("successes") or 0) >= MAX_SUCCESSES or int(state.get("failures") or 0) >= MAX_FAILURES:
        return False
    next_due = str(state.get("next_due_at") or "").strip()
    if next_due:
        try:
            return now >= datetime.fromisoformat(next_due.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return True
    last = str(state.get("last_started_at") or "").strip()
    if not last:
        return True
    try:
        return now - datetime.fromisoformat(last.replace("Z", "+00:00")).astimezone(timezone.utc) >= timedelta(minutes=INTERVAL_MINUTES)
    except Exception:
        return True


def build_test_job(*, series_id: str = "", part: int = 0, total: int = MAX_SUCCESSES, attempt: int = 0):
    from market_intelligence import CORE_MARKET_SCOPE_LABEL, MARKET_PROFILE_CORE, JobProfile

    return JobProfile(
        job_id="MI-AUTONOMY-REPORT-TEST", name="Autonomi rapporttest", enabled=False,
        markets=[CORE_MARKET_SCOPE_LABEL], market_profile=MARKET_PROFILE_CORE,
        schedules=[], scan_windows=[], scan_limit=25, deep_count=10, evidence_analysis_count=10,
        proposal_count=5, coverage_profile_version="3.1",
        notify_pushover=True, notify_only_changes=False, notification_mode="ALWAYS",
        include_report_link=True, save_pdf=True, run_autonomous_portfolio=True,
        run_controlled_learning=True, require_active_portfolio=False,
        report_test_series_id=series_id, report_test_part=part,
        report_test_total=total, report_test_attempt=attempt,
    )
def run_due_report_test() -> dict[str, Any]:
    state = load_report_test_mode()
    if not test_mode_due(state):
        safety_limit = int(state.get("successes") or 0) >= MAX_SUCCESSES or int(state.get("failures") or 0) >= MAX_FAILURES
        try:
            enabled_at = datetime.fromisoformat(str(state.get("enabled_at") or "").replace("Z", "+00:00"))
            safety_limit = safety_limit or (_now() - enabled_at.astimezone(timezone.utc) >= timedelta(hours=MAX_DURATION_HOURS))
        except Exception:
            safety_limit = safety_limit or bool(state.get("enabled"))
        if state.get("enabled") and safety_limit:
            state.update({
                "enabled": False, "disabled_at": _now().isoformat(timespec="seconds"), "disabled_reason": "SAFETY_LIMIT",
                "phase": "FAILED", "status_message": "Sikkerhetsvinduet utløp før 4/4.",
            })
            _add_event(state, "SERIES_STOPPED", reason="SAFETY_LIMIT")
            _send_terminal_summary(state, passed=False, reason="Sikkerhetsvinduet utløp før 4/4")
            _persist_state(state)
        return {**state, "run_state": "NOT_DUE"}
    from market_intelligence import run_job
    started_at = _now()
    started = started_at.isoformat(timespec="seconds")
    series_id = str(state.get("series_id") or "") or _new_series_id(started_at)
    part = min(MAX_SUCCESSES, int(state.get("successes") or 0) + 1)
    attempt = int(state.get("attempts") or 0) + 1
    test_job = build_test_job(series_id=series_id, part=part, total=MAX_SUCCESSES, attempt=attempt)
    # Persist the next cron boundary before the expensive report starts. If the
    # final database write is transiently unavailable, the series can still be
    # resumed on the following half-hour instead of becoming stuck.
    state.update({
        "last_started_at": started,
        "series_id": series_id,
        "current_part": part,
        "attempts": attempt,
        "next_due_at": _next_half_hour(started_at).isoformat(timespec="seconds"),
        "updated_at": started,
        "last_error": "",
        "persistence_error": "",
        "phase": "RUNNING_FULL_CHAIN",
        "status_message": f"Kjører deltest {part}/{MAX_SUCCESSES}: marked, evidens, Autonomi, PDF, lagring og Pushover.",
        "expected_result_at": (started_at + timedelta(minutes=20)).isoformat(timespec="seconds"),
    })
    _add_event(state, "AUTOMATIC_TEST_STARTED", part=f"{part}/{MAX_SUCCESSES}", attempt=attempt)
    _persist_state(state)
    try:
        result = run_job(
            test_job, trigger="SCHEDULED_REPORT_TEST_NOTIFICATION",
            send_notifications=True, scheduled_for=started,
        )
        notification = dict(result.get("notification") or {})
        notification_sent = notification.get("sent") is True
        state.update({
            "last_completed_at": _now().isoformat(timespec="seconds"),
            "last_report_id": str(result.get("report_id") or result.get("run_id") or ""),
            "last_notification_status": str(notification.get("status_label") or ""),
        })
        if notification_sent:
            state["successes"] = int(state.get("successes") or 0) + 1
            state["run_state"] = "COMPLETED"
            state["phase"] = "WAITING_FOR_NEXT_INTERVAL"
            state["status_message"] = f"Deltest {state['successes']}/{MAX_SUCCESSES} er godkjent. Venter på neste 30-minuttersintervall."
            _add_event(
                state, "AUTOMATIC_TEST_COMPLETED", part=f"{state['successes']}/{MAX_SUCCESSES}",
                attempt=attempt, report_id=state.get("last_report_id"), pushover="SENT",
            )
            if int(state["successes"]) >= MAX_SUCCESSES:
                state.update({
                    "enabled": False, "disabled_reason": "SUCCESS_LIMIT", "disabled_at": _now().isoformat(timespec="seconds"),
                    "phase": "COMPLETED", "status_message": "Alle fire deltester og Pushover-varsler er godkjent.",
                })
                _send_terminal_summary(state, passed=True, reason="Alle fire automatiske rapport- og Pushover-tester er fullført")
        else:
            state["failures"] = int(state.get("failures") or 0) + 1
            state["run_state"] = "FAILED_NOTIFICATION"
            state["last_error"] = str(notification.get("detail") or "Pushover-varselet ble ikke sendt")[:1000]
            state["phase"] = "RETRY_WAIT"
            state["status_message"] = f"Deltest {part}/{MAX_SUCCESSES} ble ikke godkjent. Neste schedulerkjøring prøver igjen."
            _add_event(
                state, "AUTOMATIC_TEST_FAILED", part=f"{part}/{MAX_SUCCESSES}", attempt=attempt,
                report_id=state.get("last_report_id"), pushover="FAILED", detail=state["last_error"],
            )
            if int(state["failures"]) >= MAX_FAILURES:
                state.update({
                    "enabled": False, "disabled_reason": "FAILURE_LIMIT", "disabled_at": _now().isoformat(timespec="seconds"),
                    "phase": "FAILED", "status_message": "Testserien er stoppet etter tre feil.",
                })
                _send_terminal_summary(state, passed=False, reason=state["last_error"])
    except Exception as exc:
        detail = _exception_detail(exc)[:1000]
        if "allerede aktiv" in detail.casefold():
            retry_at = _now().isoformat(timespec="seconds")
            state.update({
                "last_completed_at": retry_at, "last_error": detail, "run_state": "DEFERRED_BUSY",
                "phase": "WAITING_FOR_WORKER", "status_message": "En annen jobb bruker worker. Nytt forsøk skjer ved neste schedulerkjøring.",
                "next_due_at": retry_at,
            })
            state["last_started_at"] = ""
            _add_event(state, "AUTOMATIC_TEST_DEFERRED", part=f"{part}/{MAX_SUCCESSES}", attempt=attempt, detail=detail)
            _persist_state(state)
            return state
        state.update({
            "last_completed_at": _now().isoformat(timespec="seconds"), "last_error": detail,
            "failures": int(state.get("failures") or 0) + 1, "run_state": "FAILED",
            "phase": "RETRY_WAIT", "status_message": f"Deltest {part}/{MAX_SUCCESSES} feilet. Neste schedulerkjøring prøver igjen.",
        })
        _add_event(state, "AUTOMATIC_TEST_FAILED", part=f"{part}/{MAX_SUCCESSES}", attempt=attempt, detail=detail)
        if int(state["failures"]) >= MAX_FAILURES:
            state.update({
                "enabled": False, "disabled_reason": "FAILURE_LIMIT", "disabled_at": _now().isoformat(timespec="seconds"),
                "phase": "FAILED", "status_message": "Testserien er stoppet etter tre feil.",
            })
            _send_terminal_summary(state, passed=False, reason=detail)
    state["updated_at"] = _now().isoformat(timespec="seconds")
    try:
        _persist_state(state)
    except Exception as persist_exc:
        # Preserve the report/notification error in the returned cron status;
        # never replace it with a generic storage error.
        state["persistence_error"] = _exception_detail(persist_exc)
        if state.get("run_state") == "COMPLETED":
            state["run_state"] = "COMPLETED_STATE_NOT_PERSISTED"
        else:
            state["run_state"] = "FAILED_STATE_NOT_PERSISTED"
    return state
