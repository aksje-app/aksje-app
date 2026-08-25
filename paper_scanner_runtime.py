from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path


PAPER_SCANNER_STATUS_KEY = "paper_trading/scanner_status.json"
PAPER_SCANNER_STATUS_PATH = runtime_data_path("paper_trading", "scanner_status.json")
PAPER_SCANNER_CHECKPOINT_KEY = "paper_trading/scanner_checkpoint.json"
PAPER_SCANNER_CHECKPOINT_PATH = runtime_data_path("paper_trading", "scanner_checkpoint.json")
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


def load_scanner_checkpoint() -> dict:
    value = read_json(PAPER_SCANNER_CHECKPOINT_KEY, PAPER_SCANNER_CHECKPOINT_PATH, {})
    return dict(value) if isinstance(value, dict) else {}


def save_scanner_checkpoint(value: dict) -> None:
    payload = dict(value or {})
    payload["updated_at"] = scanner_now()
    write_json(PAPER_SCANNER_CHECKPOINT_KEY, PAPER_SCANNER_CHECKPOINT_PATH, payload)


def clear_scanner_checkpoint() -> None:
    write_json(PAPER_SCANNER_CHECKPOINT_KEY, PAPER_SCANNER_CHECKPOINT_PATH, {})

def scanner_worker_is_stale(max_age_minutes: int = 45) -> bool:
    status = load_scanner_status()
    raw = str(status.get("heartbeat_at") or status.get("completed_at") or "").strip()
    if not raw: return True
    try:
        heartbeat = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        heartbeat = heartbeat.replace(tzinfo=heartbeat.tzinfo or timezone.utc).astimezone(timezone.utc)
        return (datetime.now(timezone.utc) - heartbeat).total_seconds() > max(15, int(max_age_minutes)) * 60
    except Exception:
        return True


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
    from runtime_identity import publish_runtime_identity, validate_cluster_alignment, validate_expected_runtime
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
        "runtime_identity": publish_runtime_identity("paper_scanner"),
    }
    write_scanner_status(status)
    aligned, reason = validate_expected_runtime()
    status["runtime_alignment"] = {"aligned": aligned, "reason": reason}
    if not aligned:
        status.update({"state": "FAILED", "completed_at": scanner_now(), "error": reason})
        write_scanner_status(status)
        return 0
    cluster_aligned, cluster_reason = validate_cluster_alignment("paper_scanner", ("web",))
    status["cluster_alignment"] = {"aligned": cluster_aligned, "reason": cluster_reason}
    if not cluster_aligned:
        status.update({"state": "BLOCKED_DEPLOY_MISMATCH", "completed_at": scanner_now(), "error": cluster_reason})
        write_scanner_status(status)
        return 0
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
        loaded_status = load_scanner_status() or {}
        # Never inherit a terminal policy state from an older worker.  Only
        # richer heartbeat state belonging to this execution may be merged.
        status = loaded_status if str(loaded_status.get("execution_id") or "") == execution_id else status
        terminal_state = str(status.get("state") or "RUNNING")
        completed_scan = terminal_state not in {"MARKET_CLOSED", "SKIPPED_POLICY", "PARTIAL_CHECKPOINT"}
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
