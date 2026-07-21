"""Persistent lightweight background services for the Render web process."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()
_STATUS: dict[str, Any] = {
    "state": "NOT_STARTED", "started_at": None, "last_cycle_at": None,
    "last_error": "", "cycles": 0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _worker() -> None:
    global _STATUS
    poll_seconds = max(15, int(os.getenv("FX_ALERT_WORKER_POLL_SECONDS", "30") or 30))
    _STATUS.update({"state": "RUNNING", "started_at": _now()})
    while not _STOP.is_set():
        try:
            from currency_alert_service import run_currency_alert_checks
            run_currency_alert_checks(force=False)
            _STATUS.update({
                "state": "RUNNING", "last_cycle_at": _now(), "last_error": "",
                "cycles": int(_STATUS.get("cycles", 0)) + 1,
            })
        except Exception as exc:
            _STATUS.update({"state": "DEGRADED", "last_cycle_at": _now(), "last_error": str(exc)[:500]})
        _STOP.wait(poll_seconds)


def ensure_runtime_background_services() -> dict[str, Any]:
    """Idempotently start services once per Python process."""
    global _THREAD
    with _LOCK:
        if _THREAD is None or not _THREAD.is_alive():
            _STOP.clear()
            _THREAD = threading.Thread(target=_worker, name="fx-alert-runtime", daemon=True)
            _THREAD.start()
        return dict(_STATUS)


def runtime_background_status() -> dict[str, Any]:
    return dict(_STATUS)
