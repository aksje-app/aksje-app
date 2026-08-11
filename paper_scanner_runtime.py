from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path


PAPER_SCANNER_STATUS_KEY = "paper_trading/scanner_status.json"
PAPER_SCANNER_STATUS_PATH = runtime_data_path("paper_trading", "scanner_status.json")
# Deliberately different from execution_coordination._REPORT_EXECUTION_LOCK_ID.
# Paper scanning and report generation are independent workloads and must never
# suppress each other.
PAPER_SCANNER_ADVISORY_LOCK_ID = 1871503


def scanner_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_scanner_status(value: dict) -> None:
    write_json(PAPER_SCANNER_STATUS_KEY, PAPER_SCANNER_STATUS_PATH, dict(value or {}))


def load_scanner_status() -> dict:
    value = read_json(PAPER_SCANNER_STATUS_KEY, PAPER_SCANNER_STATUS_PATH, {})
    return dict(value) if isinstance(value, dict) else {}


def update_scanner_status(**values) -> dict:
    status = load_scanner_status()
    status.update({key: value for key, value in values.items() if value is not None})
    status["heartbeat_at"] = scanner_now()
    write_scanner_status(status)
    return status


@contextmanager
def paper_scanner_global_lock():
    """Prevent overlapping Render cron workers from executing duplicate orders."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        yield True
        return
    connection = None
    acquired = False
    try:
        import psycopg2

        connection = psycopg2.connect(database_url, connect_timeout=5)
        cursor = connection.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (PAPER_SCANNER_ADVISORY_LOCK_ID,))
        acquired = bool(cursor.fetchone()[0])
    except Exception as exc:
        print(f"Paper scanner-lås feilet; handel stoppes sikkert: {exc}")
        yield False
        return
    try:
        yield acquired
    finally:
        if connection is not None:
            try:
                if acquired:
                    cursor = connection.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (PAPER_SCANNER_ADVISORY_LOCK_ID,))
                connection.close()
            except Exception:
                pass


def run_coordinated(run_impl: Callable[..., int], *, force: bool = False) -> int:
    execution_id = f"PAPER-SCANNER-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    status = {
        "execution_id": execution_id,
        "state": "RUNNING",
        "started_at": scanner_now(),
        "heartbeat_at": scanner_now(),
        "completed_at": None,
        "force": bool(force),
        "process": "scanner_worker",
        "trades_executed": 0,
        "error": "",
    }
    write_scanner_status(status)
    try:
        with paper_scanner_global_lock() as acquired:
            if not acquired:
                status.update({
                    "state": "SKIPPED_LOCKED",
                    "completed_at": scanner_now(),
                    "message": "En annen Paper scanner-worker holder den globale låsen",
                })
                write_scanner_status(status)
                return 0
            trades = int(run_impl(force=force) or 0)
        # The worker may have published richer state/heartbeat fields while it
        # ran. Reload instead of overwriting those fields with the startup copy.
        status = load_scanner_status() or status
        terminal_state = str(status.get("state") or "RUNNING")
        completed_scan = terminal_state not in {"MARKET_CLOSED", "SKIPPED_POLICY"}
        status.update({
            "state": "COMPLETED" if completed_scan else terminal_state,
            "completed_at": scanner_now(),
            "trades_executed": trades,
            "heartbeat_at": scanner_now(),
            "message": status.get("message") or "Paper-skanningen er fullført",
        })
        if completed_scan:
            status["last_successful_scan_at"] = scanner_now()
        write_scanner_status(status)
        return trades
    except Exception as exc:
        status = load_scanner_status() or status
        status.update({
            "state": "FAILED",
            "completed_at": scanner_now(),
            "heartbeat_at": scanner_now(),
            "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
        })
        write_scanner_status(status)
        raise
