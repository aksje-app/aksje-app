"""Durable background execution for manually started full-chain jobs.

The worker is deliberately independent of Streamlit's script thread.  UI
reruns, page navigation and browser disconnects therefore do not cancel an
accepted job.  PostgreSQL/StorageService is authoritative for status while a
local JSON file remains a backwards-compatible diagnostic mirror.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Mapping

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path


ROOT = runtime_data_path("manual_background_jobs")
ACTIVE_PATH = ROOT / "active.json"
ACTIVE_KEY = "manual_background_jobs/active.json"
_LOCK = threading.Lock()
_THREADS: dict[str, threading.Thread] = {}
_TERMINAL = {"COMPLETED", "FAILED"}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _status_path(execution_id: str):
    return ROOT / "runs" / f"{execution_id}.json"


def _status_key(execution_id: str) -> str:
    return f"manual_background_jobs/runs/{execution_id}.json"


def _write_status(status: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(status)
    execution_id = str(payload["execution_id"])
    write_json(_status_key(execution_id), _status_path(execution_id), payload)
    write_json(ACTIVE_KEY, ACTIVE_PATH, {
        "execution_id": execution_id,
        "state": payload.get("state"),
        "updated_at": payload.get("updated_at"),
    })
    return payload


def get_status(execution_id: str) -> dict[str, Any]:
    if not execution_id:
        return {}
    value = read_json(_status_key(execution_id), _status_path(execution_id), {})
    return dict(value) if isinstance(value, Mapping) else {}


def get_active_status() -> dict[str, Any]:
    active = read_json(ACTIVE_KEY, ACTIVE_PATH, {})
    if not isinstance(active, Mapping) or not active.get("execution_id"):
        return {}
    return get_status(str(active["execution_id"]))


def progress_percent(event: Mapping[str, Any]) -> int:
    phase = str(event.get("phase") or "START")
    done = int(event.get("completed") or 0)
    total = max(1, int(event.get("total") or 1))
    bases = {"START": 2, "MARKET": 5, "PREPARE": 8, "MARKET_DATA": 10,
             "SCORING": 48, "DEDUP": 68, "PORTFOLIO_PROPOSAL": 74,
             "AUTONOMOUS": 82, "REPORT": 92, "COMPLETE": 100}
    if phase == "MARKET_DATA":
        return min(45, 10 + int(35 * done / total))
    if phase == "SCORING":
        return min(66, 48 + int(18 * done / total))
    return min(100, max(0, bases.get(phase, 5)))


def _worker(execution_id: str, job_payload: Mapping[str, Any], trigger: str, force_refresh: bool) -> None:
    from market_intelligence import JobProfile, run_job

    status = get_status(execution_id)
    status.update({"state": "RUNNING", "started_at": _now(), "updated_at": _now(),
                   "message": "Starter markedsskanning", "percent": 1})
    _write_status(status)

    def progress(event: Mapping[str, Any]) -> None:
        current = get_status(execution_id) or status
        message = str(event.get("message") or event.get("phase") or "Kjører")
        ticker = str(event.get("ticker") or "")
        if ticker and ticker not in message:
            message = f"{message} · {ticker}"
        current.update({
            "state": "RUNNING", "updated_at": _now(),
            "phase": str(event.get("phase") or "START"),
            "percent": progress_percent(event), "message": message,
            "progress_event": dict(event),
        })
        _write_status(current)

    try:
        result = run_job(JobProfile.from_dict(job_payload), trigger=trigger,
                         progress_callback=progress, force_refresh=force_refresh)
        chain = dict(result.get("autonomous_chain") or {})
        final = get_status(execution_id) or status
        final.update({
            "state": "COMPLETED", "phase": "COMPLETE", "percent": 100,
            "message": "Hele kjeden er ferdig", "updated_at": _now(),
            "completed_at": _now(), "run_id": result.get("run_id"),
            "chain_id": chain.get("chain_id"), "chain_status": chain.get("status"),
            "chain": chain, "top_candidates": list(result.get("candidates") or [])[:3],
            "data_refresh": dict(result.get("data_refresh") or {}), "error": "",
        })
        _write_status(final)
    except Exception as exc:
        failed = get_status(execution_id) or status
        failed.update({
            "state": "FAILED", "percent": 100, "message": "Kjøringen stoppet med feil",
            "updated_at": _now(), "completed_at": _now(), "error": str(exc),
        })
        _write_status(failed)
    finally:
        with _LOCK:
            _THREADS.pop(execution_id, None)


def start_manual_job(job: Any, *, trigger: str, force_refresh: bool = False) -> dict[str, Any]:
    """Accept one manual job and return immediately with its durable status."""
    with _LOCK:
        active = get_active_status()
        if active and active.get("state") not in _TERMINAL:
            return active
        execution_id = f"MBJ-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        status = _write_status({
            "execution_id": execution_id, "state": "QUEUED", "phase": "START",
            "percent": 0, "message": "Klargjør bakgrunnskjøring", "trigger": trigger,
            "job_id": getattr(job, "job_id", ""), "job_name": getattr(job, "name", ""),
            "force_refresh": bool(force_refresh), "accepted_at": _now(),
            "started_at": None, "completed_at": None, "updated_at": _now(), "error": "",
        })
        thread = threading.Thread(
            target=_worker,
            args=(execution_id, asdict(job), trigger, bool(force_refresh)),
            name=f"manual-chain-{execution_id}", daemon=True,
        )
        _THREADS[execution_id] = thread
        thread.start()
        return status


def is_running(status: Mapping[str, Any] | None = None) -> bool:
    value = status if status is not None else get_active_status()
    return bool(value) and value.get("state") in {"QUEUED", "RUNNING"}
