"""Durable, bounded 30-minute Autonomi report/Pushover acceptance mode."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

STATE_KEY = "scheduler/report_test_mode.json"
STATE_PATH = runtime_data_path("scheduler", "report_test_mode.json")
INTERVAL_MINUTES = 30
MAX_SUCCESSES = 4
MAX_DURATION_HOURS = 2
MAX_FAILURES = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_report_test_mode() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    state = dict(value) if isinstance(value, Mapping) else {}
    return {"enabled": False, "successes": 0, "failures": 0, **state}


def set_report_test_mode(enabled: bool) -> dict[str, Any]:
    current = load_report_test_mode()
    now = _now().isoformat(timespec="seconds")
    if enabled and not current.get("enabled"):
        current = {
            "enabled": True, "enabled_at": now, "updated_at": now,
            "last_started_at": "", "last_completed_at": "", "last_report_id": "",
            "last_notification_status": "", "last_error": "", "successes": 0, "failures": 0,
        }
    elif not enabled:
        current.update({"enabled": False, "disabled_at": now, "updated_at": now, "disabled_reason": "OPERATOR"})
    write_json(STATE_KEY, STATE_PATH, current)
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
    last = str(state.get("last_started_at") or "").strip()
    if not last:
        return True
    try:
        return now - datetime.fromisoformat(last.replace("Z", "+00:00")).astimezone(timezone.utc) >= timedelta(minutes=INTERVAL_MINUTES)
    except Exception:
        return True


def build_test_job():
    from market_intelligence import JobProfile, load_jobs

    source = next((job for job in load_jobs() if job.enabled), None) or JobProfile(name="Autonomi rapporttest")
    return replace(
        source, name=f"Autonomi rapporttest · {source.name}", enabled=False,
        notify_pushover=True, notify_only_changes=False, notification_mode="ALWAYS",
        include_report_link=True, save_pdf=True, run_autonomous_portfolio=False,
        run_controlled_learning=False, require_active_portfolio=False,
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
            state.update({"enabled": False, "disabled_at": _now().isoformat(timespec="seconds"), "disabled_reason": "SAFETY_LIMIT"})
            write_json(STATE_KEY, STATE_PATH, state)
        return {**state, "run_state": "NOT_DUE"}
    from market_intelligence import run_job
    test_job = build_test_job()
    started = _now().isoformat(timespec="seconds")
    state.update({"last_started_at": started, "updated_at": started, "last_error": ""})
    write_json(STATE_KEY, STATE_PATH, state)
    try:
        result = run_job(
            test_job, trigger="SCHEDULED_REPORT_TEST_NOTIFICATION",
            send_notifications=True, scheduled_for=started,
        )
        state.update({
            "last_completed_at": _now().isoformat(timespec="seconds"),
            "last_report_id": str(result.get("report_id") or result.get("run_id") or ""),
            "last_notification_status": str((result.get("notification") or {}).get("status_label") or ""),
            "successes": int(state.get("successes") or 0) + 1,
        })
        if int(state["successes"]) >= MAX_SUCCESSES:
            state.update({"enabled": False, "disabled_reason": "SUCCESS_LIMIT", "disabled_at": _now().isoformat(timespec="seconds")})
        state["run_state"] = "COMPLETED"
    except Exception as exc:
        detail = str(exc)[:1000]
        if "allerede aktiv" in detail.casefold():
            state.update({"last_completed_at": _now().isoformat(timespec="seconds"), "last_error": detail, "run_state": "DEFERRED_BUSY"})
            state["last_started_at"] = ""
            write_json(STATE_KEY, STATE_PATH, state)
            return state
        state.update({"last_completed_at": _now().isoformat(timespec="seconds"), "last_error": detail, "failures": int(state.get("failures") or 0) + 1, "run_state": "FAILED"})
        if int(state["failures"]) >= MAX_FAILURES:
            state.update({"enabled": False, "disabled_reason": "FAILURE_LIMIT", "disabled_at": _now().isoformat(timespec="seconds")})
    state["updated_at"] = _now().isoformat(timespec="seconds")
    write_json(STATE_KEY, STATE_PATH, state)
    return state
