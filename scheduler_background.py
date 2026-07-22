"""Non-blocking in-process scheduler kick for the Streamlit web service."""
from __future__ import annotations

import threading
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from storage_architecture import runtime_log_path
from durable_runtime import append_event, read_events

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STATUS: dict[str, Any] = {"state": "IDLE", "started_at": None, "completed_at": None, "runs": 0, "error": ""}
_AUDIT_PATH = runtime_log_path("scheduler_audit.jsonl")
_PG_ADVISORY_LOCK_ID = 1871501


@contextmanager
def _global_scheduler_lock():
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
                acquired = True
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
        _STATUS = {"state": "IDLE", "started_at": _STATUS.get("started_at"), "completed_at": _now(), "runs": len(results), "error": ""}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": _now(), "event": "BACKGROUND_CHECK_COMPLETED", "runs": len(results)})
    except Exception as exc:
        _STATUS = {"state": "ERROR", "started_at": _STATUS.get("started_at"), "completed_at": _now(), "runs": 0, "error": str(exc)}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": _now(), "event": "BACKGROUND_CHECK_FAILED", "error": str(exc)})


def _run_due_jobs_coordinated() -> list[dict[str, Any]]:
    with _global_scheduler_lock() as acquired:
        if not acquired:
            append_event("scheduler/audit.jsonl", _AUDIT_PATH, {
                "at": _now(), "event": "BACKGROUND_CHECK_SKIPPED", "reason": "another_process_holds_lock"
            })
            return []
        from market_intelligence import run_due_jobs
        return list(run_due_jobs() or [])


def run_scheduler_cycle() -> dict[str, Any]:
    """Run one durable due-job check from the persistent runtime worker."""
    global _STATUS
    started = _now()
    _STATUS = {"state": "RUNNING", "started_at": started, "completed_at": None, "runs": 0, "error": ""}
    append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": started, "event": "BACKGROUND_CHECK_STARTED"})
    try:
        results = _run_due_jobs_coordinated()
        _STATUS = {"state": "IDLE", "started_at": started, "completed_at": _now(), "runs": len(results), "error": ""}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {
            "at": _STATUS["completed_at"], "event": "BACKGROUND_CHECK_COMPLETED", "runs": len(results)
        })
    except Exception as exc:
        _STATUS = {"state": "ERROR", "started_at": started, "completed_at": _now(), "runs": 0, "error": str(exc)}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {
            "at": _STATUS["completed_at"], "event": "BACKGROUND_CHECK_FAILED", "error": str(exc)
        })
    return dict(_STATUS)


def kick_scheduler_background() -> dict[str, Any]:
    """Start one daemon check and return immediately; never block UI rendering."""
    global _THREAD, _STATUS
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return dict(_STATUS)
        _STATUS = {"state": "RUNNING", "started_at": _now(), "completed_at": None, "runs": 0, "error": ""}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": _STATUS["started_at"], "event": "BACKGROUND_CHECK_STARTED"})
        _THREAD = threading.Thread(target=_worker, name="market-intelligence-scheduler", daemon=True)
        _THREAD.start()
        return dict(_STATUS)


def scheduler_status() -> dict[str, Any]:
    return dict(_STATUS)


def scheduler_audit(limit: int = 500) -> list[dict[str, Any]]:
    return read_events("scheduler/audit.jsonl", _AUDIT_PATH, limit=limit)
