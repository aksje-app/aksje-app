"""Non-blocking in-process scheduler kick for the Streamlit web service."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any
from storage_architecture import runtime_log_path
from durable_runtime import append_event, read_events

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STATUS: dict[str, Any] = {"state": "IDLE", "started_at": None, "completed_at": None, "runs": 0, "error": ""}
_AUDIT_PATH = runtime_log_path("scheduler_audit.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _worker() -> None:
    global _STATUS
    try:
        from market_intelligence import run_due_jobs
        results = run_due_jobs()
        _STATUS = {"state": "IDLE", "started_at": _STATUS.get("started_at"), "completed_at": _now(), "runs": len(results), "error": ""}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": _now(), "event": "BACKGROUND_CHECK_COMPLETED", "runs": len(results)})
    except Exception as exc:
        _STATUS = {"state": "ERROR", "started_at": _STATUS.get("started_at"), "completed_at": _now(), "runs": 0, "error": str(exc)}
        append_event("scheduler/audit.jsonl", _AUDIT_PATH, {"at": _now(), "event": "BACKGROUND_CHECK_FAILED", "error": str(exc)})


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
