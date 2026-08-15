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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def report_execution_owner() -> dict[str, Any]:
    value = read_json(_OWNER_KEY, _OWNER_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


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
                "pid": os.getpid(), **dict(owner or {}),
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
