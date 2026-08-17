"""Cross-process lease for report execution, shared by UI and cron workers."""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Any, Mapping

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

_LOCAL_LOCK = threading.Lock()
_REPORT_EXECUTION_LOCK_ID = 1871502
_OWNER_KEY = "scheduler/report_execution_owner.json"
_OWNER_PATH = runtime_data_path("scheduler", "report_execution_owner.json")


def _process_identity() -> str:
    start_ticks = "unknown"
    try:
        with open("/proc/self/stat", "r", encoding="utf-8") as handle:
            fields = handle.read().split()
        if len(fields) > 21:
            start_ticks = fields[21]
    except Exception:
        pass
    return f"{os.getpid()}:{start_ticks}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def report_execution_owner() -> dict[str, Any]:
    value = read_json(_OWNER_KEY, _OWNER_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def release_orphaned_execution_owner(*, reason: str, execution_id: str = "") -> dict[str, Any]:
    """Close stale diagnostic ownership after the database lock died with its process."""
    previous = report_execution_owner()
    if str(previous.get("state") or "").upper() != "ACTIVE":
        return previous
    owner_execution = str(previous.get("execution_id") or "")
    if execution_id and owner_execution and owner_execution != execution_id:
        return previous
    now = _now()
    released = {
        **previous,
        "state": "RELEASED_AFTER_PROCESS_RESTART",
        "released_at": now,
        "heartbeat_at": now,
        "release_reason": str(reason or "SERVER_PROCESS_RESTART"),
        "released_by_process_identity": _process_identity(),
    }
    write_json(_OWNER_KEY, _OWNER_PATH, released)
    return released


@contextmanager
def report_execution_lock(owner: Mapping[str, Any] | None = None):
    connection = None
    acquired = False
    heartbeat_stop = threading.Event()
    heartbeat_thread = None
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    try:
        if database_url:
            import psycopg2

            connection = psycopg2.connect(database_url, connect_timeout=5)
            cursor = connection.cursor()
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (_REPORT_EXECUTION_LOCK_ID,))
            acquired = bool(cursor.fetchone()[0])
        else:
            acquired = _LOCAL_LOCK.acquire(blocking=False)
        if acquired:
            identity = {
                "state": "ACTIVE", "acquired_at": _now(), "heartbeat_at": _now(),
                "pid": os.getpid(), "process_identity": _process_identity(), **dict(owner or {}),
            }
            write_json(_OWNER_KEY, _OWNER_PATH, identity)

            def _heartbeat() -> None:
                while not heartbeat_stop.wait(10):
                    write_json(_OWNER_KEY, _OWNER_PATH, {**identity, "heartbeat_at": _now()})

            heartbeat_thread = threading.Thread(target=_heartbeat, name="report-lock-heartbeat", daemon=True)
            heartbeat_thread.start()
        yield acquired
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1)
        if connection is not None:
            try:
                if acquired:
                    cursor = connection.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (_REPORT_EXECUTION_LOCK_ID,))
                connection.close()
            except Exception:
                pass
        elif acquired:
            _LOCAL_LOCK.release()
        if acquired:
            previous = report_execution_owner()
            write_json(_OWNER_KEY, _OWNER_PATH, {**previous, "state": "RELEASED", "released_at": _now(), "heartbeat_at": _now()})
