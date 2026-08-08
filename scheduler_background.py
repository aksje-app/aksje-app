"""Non-blocking in-process scheduler kick for the Streamlit web service."""
from __future__ import annotations

import threading
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from storage_architecture import runtime_log_path
from durable_runtime import append_event, read_events
from operational_telemetry import record_event, stable_error_code, begin_run_trace, complete_run_trace, mark_run_stage

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STATUS: dict[str, Any] = {"state": "IDLE", "started_at": None, "completed_at": None, "runs": 0, "error": "", "health": {}}
_AUDIT_PATH = runtime_log_path("scheduler_audit.jsonl")
_PG_ADVISORY_LOCK_ID = 1871501


@contextmanager
def global_scheduler_lock():
    """Prevent duplicate scheduled reports across Render processes."""
    connection = None
    acquired = True
    database_url = os.getenv("DATABASE_URL", "").strip()
    try:
        if database_url:
            try:
                import psycopg2
                connection = psycopg2.connect(database_url, connect_timeout=5)
                cursor = connection.cursor()
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (_PG_ADVISORY_LOCK_ID,))
                acquired = bool(cursor.fetchone()[0])
            except Exception as exc:
                append_event("scheduler/audit.jsonl", _AUDIT_PATH, {
                    "at": _now(), "event": "SCHEDULER_COORDINATION_DEGRADED", "error": str(exc)[:500]
                })
                record_event(
                    "SCHEDULER_COORDINATION_DEGRADED", severity="WARNING", component="SCHEDULER",
                    stage="COORDINATION", message="Global scheduler-lås kunne ikke brukes; lokal kjøring fortsetter",
                    error_code=stable_error_code("SCHEDULER", "coordination_degraded", "LOCK"), error=exc,
                )
                # A configured production database is the cross-process source
                # of truth. Continuing without its lock could duplicate reports.
                acquired = False
        yield acquired
    finally:
        if connection is not None:
            try:
                if acquired:
                    cursor = connection.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (_PG_ADVISORY_LOCK_ID,))
                connection.close()
            except Exception:
                pass


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _worker() -> None:
    global _STATUS
    try:
        results = _run_due_jobs_coordinated()
        try:
            from market_intelligence import scheduler_health_snapshot
            health = scheduler_health_snapshot()
        except Exception as health_exc:
            health = {"state": "UNAVAILABLE", "error": str(health_exc)[:500]}
        _STATUS = {"state": "IDLE", "started_at": _STATUS.get("started_at"), "completed_at": _now(), "runs": len(results), "error": "", "health": health}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": _now(), "event": "BACKGROUND_CHECK_COMPLETED", "runs": len(results), "health_state": health.get("state")})
    except Exception as exc:
        _STATUS = {"state": "ERROR", "started_at": _STATUS.get("started_at"), "completed_at": _now(), "runs": 0, "error": str(exc), "health": {}}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": _now(), "event": "BACKGROUND_CHECK_FAILED", "error": str(exc)})
        record_event("BACKGROUND_CHECK_FAILED", severity="ERROR", component="SCHEDULER", stage="WORKER",
                     message="Bakgrunnsscheduler feilet", error_code=stable_error_code("SCHEDULER", "scheduler_failed", "WORKER"), error=exc)


def _run_due_jobs_coordinated(*, authoritative_unattended: bool = False) -> list[dict[str, Any]]:
    with global_scheduler_lock() as acquired:
        if not acquired:
            append_event("scheduler/audit.jsonl", _AUDIT_PATH, {
                "at": _now(), "event": "BACKGROUND_CHECK_SKIPPED", "reason": "another_process_holds_lock"
            })
            return []
        from market_intelligence import run_due_jobs
        if authoritative_unattended:
            return list(run_due_jobs(authoritative_unattended=True) or [])
        return list(run_due_jobs() or [])


def run_scheduler_cycle(*, authoritative_unattended: bool = False, already_coordinated: bool = False) -> dict[str, Any]:
    """Run one durable due-job check with a complete structured trace."""
    global _STATUS
    started = _now()
    trace = begin_run_trace(kind="SCHEDULER", trigger="BACKGROUND", metadata={
        "worker": "scheduler_background", "authoritative_unattended": bool(authoritative_unattended),
    })
    trace_id = str(trace.get("trace_id") or "")
    _STATUS = {"state": "RUNNING", "started_at": started, "completed_at": None, "runs": 0, "error": "", "health": {}, "trace_id": trace_id}
    append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": started, "event": "BACKGROUND_CHECK_STARTED", "trace_id": trace_id})
    mark_run_stage(trace_id, "DUE_JOB_SCAN", status="RUNNING", message="Kontrollerer planlagte jobber")
    try:
        if already_coordinated:
            from market_intelligence import run_due_jobs
            results = list(run_due_jobs(authoritative_unattended=authoritative_unattended) or [])
        else:
            results = _run_due_jobs_coordinated(authoritative_unattended=authoritative_unattended)
        mark_run_stage(trace_id, "DUE_JOB_SCAN", status="COMPLETED", message="Planlagte jobber er kontrollert", metrics={"runs": len(results)})
        try:
            from market_intelligence import scheduler_health_snapshot
            health = scheduler_health_snapshot()
            mark_run_stage(trace_id, "HEALTH", status="COMPLETED", message="Schedulerhelse er lest", metrics={"health_state": health.get("state")})
        except Exception as health_exc:
            code = stable_error_code("SCHEDULER", "report_stage_failed", "HEALTH")
            health = {"state": "UNAVAILABLE", "error": str(health_exc)[:500], "error_code": code}
            mark_run_stage(trace_id, "HEALTH", status="ERROR", message="Schedulerhelse kunne ikke leses", error_code=code, error=health_exc)
        _STATUS = {"state": "IDLE", "started_at": started, "completed_at": _now(), "runs": len(results), "error": "", "health": health, "trace_id": trace_id}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {
            "at": _STATUS["completed_at"], "event": "BACKGROUND_CHECK_COMPLETED", "runs": len(results), "health_state": health.get("state"), "trace_id": trace_id
        })
        complete_run_trace(trace_id, status="COMPLETED", metrics={"runs": len(results), "health_state": health.get("state")})
    except Exception as exc:
        code = stable_error_code("SCHEDULER", "scheduler_failed", "CYCLE")
        _STATUS = {"state": "ERROR", "started_at": started, "completed_at": _now(), "runs": 0, "error": str(exc), "health": {}, "trace_id": trace_id, "error_code": code}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {
            "at": _STATUS["completed_at"], "event": "BACKGROUND_CHECK_FAILED", "error": str(exc), "error_code": code, "trace_id": trace_id
        })
        mark_run_stage(trace_id, "DUE_JOB_SCAN", status="ERROR", message="Schedulerkjøringen feilet", error_code=code, error=exc)
        complete_run_trace(trace_id, status="FAILED", error_code=code, error=exc)
    return dict(_STATUS)


def kick_scheduler_background() -> dict[str, Any]:
    """Start one daemon check and return immediately; never block UI rendering."""
    global _THREAD, _STATUS
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return dict(_STATUS)
        _STATUS = {"state": "RUNNING", "started_at": _now(), "completed_at": None, "runs": 0, "error": "", "health": {}}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": _STATUS["started_at"], "event": "BACKGROUND_CHECK_STARTED"})
        _THREAD = threading.Thread(target=_worker, name="market-intelligence-scheduler", daemon=True)
        _THREAD.start()
        return dict(_STATUS)


def scheduler_status() -> dict[str, Any]:
    return dict(_STATUS)


def scheduler_audit(limit: int = 500) -> list[dict[str, Any]]:
    return read_events("scheduler/audit.jsonl", _AUDIT_PATH, limit=limit)
