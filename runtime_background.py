"""Persistent lightweight background services for the Render web process."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from operational_telemetry import record_event, stable_error_code, begin_run_trace, complete_run_trace, mark_run_stage
from runtime_safety import runtime_background_allowed, scheduler_allowed

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_SCHEDULER_THREAD: threading.Thread | None = None
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
            code = stable_error_code("RUNTIME", "runtime_worker_failed", "FX")
            _STATUS.update({"state": "DEGRADED", "last_cycle_at": _now(), "last_error": str(exc)[:500], "error_code": code})
            record_event("FX_WORKER_FAILED", severity="ERROR", component="RUNTIME", stage="FX_ALERTS",
                         message="Automatisk valutakontroll feilet", error_code=code, error=exc)
        _STOP.wait(poll_seconds)


def _scheduler_worker() -> None:
    """Continuously check report schedules without blocking FX monitoring."""
    poll_seconds = max(30, int(os.getenv("REPORT_SCHEDULER_POLL_SECONDS", "60") or 60))
    while not _STOP.is_set():
        try:
            from market_intelligence import restore_public_reports
            restore_public_reports(limit=25)
        except Exception as exc:
            # Delivery repair is maintenance. It must never suppress a due scan.
            record_event("REPORT_DELIVERY_REPAIR_FAILED", severity="WARNING", component="RUNTIME", stage="DELIVERY_REPAIR",
                         message="Vedlikehold av offentlige rapportfiler feilet; scheduler fortsetter",
                         error_code=stable_error_code("RUNTIME", "delivery_repair_failed", "REPORTS"), error=exc)
        try:
            from scheduler_background import run_scheduler_cycle
            run_scheduler_cycle()
        except Exception as exc:
            # scheduler_background owns the main audit; this records a worker-boundary failure.
            record_event("SCHEDULER_WORKER_BOUNDARY_FAILED", severity="ERROR", component="RUNTIME", stage="SCHEDULER",
                         message="Runtime-worker kunne ikke starte scheduler-syklusen",
                         error_code=stable_error_code("RUNTIME", "runtime_worker_failed", "SCHEDULER"), error=exc)
        _STOP.wait(poll_seconds)


def ensure_runtime_background_services() -> dict[str, Any]:
    """Idempotently start only the services allowed by the shared safety policy."""
    global _THREAD, _SCHEDULER_THREAD
    background_ok, background_reason = runtime_background_allowed()
    scheduler_ok, scheduler_reason = scheduler_allowed()
    with _LOCK:
        if background_ok and (_THREAD is None or not _THREAD.is_alive()):
            _STOP.clear()
            _THREAD = threading.Thread(target=_worker, name="fx-alert-runtime", daemon=True)
            _THREAD.start()
        if scheduler_ok and (_SCHEDULER_THREAD is None or not _SCHEDULER_THREAD.is_alive()):
            _SCHEDULER_THREAD = threading.Thread(
                target=_scheduler_worker, name="report-scheduler-runtime", daemon=True
            )
            _SCHEDULER_THREAD.start()
        if not background_ok and not scheduler_ok:
            _STATUS.update({"state": "DISABLED", "last_error": "", "background_reason": background_reason, "scheduler_reason": scheduler_reason})
        else:
            _STATUS.update({"background_enabled": background_ok, "scheduler_enabled": scheduler_ok, "background_reason": background_reason, "scheduler_reason": scheduler_reason})
        return dict(_STATUS)


def runtime_background_status() -> dict[str, Any]:
    return dict(_STATUS)
