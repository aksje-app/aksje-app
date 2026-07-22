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
from execution_control import ExecutionCancelled
from local_time import as_local, local_display
from storage_architecture import runtime_data_path


ROOT = runtime_data_path("manual_background_jobs")
ACTIVE_PATH = ROOT / "active.json"
ACTIVE_KEY = "manual_background_jobs/active.json"
_LOCK = threading.Lock()
_THREADS: dict[str, threading.Thread] = {}
_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
_STAGE_ORDER = ["MARKET_DATA", "INSIDER", "NEWS", "SCORING", "PORTFOLIO_PROPOSAL", "AUTONOMOUS", "REPORT", "COMPLETE"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def _write_progress_status(status: Mapping[str, Any]) -> dict[str, Any]:
    """Best-effort telemetry: a display failure may never abort analysis."""
    try:
        return _write_status(status)
    except Exception as exc:
        payload = dict(status)
        payload["telemetry_warning"] = str(exc)
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
    market_index = max(1, int(event.get("market_index") or 1))
    market_total = max(1, int(event.get("market_total") or 1))
    local = {"MARKET": 0.0, "PREPARE": 0.03, "MARKET_DATA": 0.08,
             "INSIDER": 0.46, "NEWS": 0.58, "SCORING": 0.68,
             "PORTFOLIO_PROPOSAL": 0.98}
    if phase == "MARKET_DATA":
        local_value = 0.08 + 0.35 * done / total
    elif phase == "INSIDER":
        local_value = 0.46 + 0.10 * done / total
    elif phase == "NEWS":
        local_value = 0.58 + 0.08 * done / total
    elif phase == "SCORING":
        local_value = 0.68 + 0.27 * done / total
    elif phase in local:
        local_value = local[phase]
    else:
        return {"START": 1, "DEDUP": 72, "AUTONOMOUS": 84,
                "REPORT": 93, "COMPLETE": 100}.get(phase, 2)
    overall_market = ((market_index - 1) + local_value) / market_total
    return min(70, 5 + int(65 * overall_market))


def display_stage(phase: str) -> str:
    return {"START": "MARKET_DATA", "MARKET": "MARKET_DATA", "PREPARE": "MARKET_DATA",
            "DEDUP": "SCORING"}.get(str(phase or "START"), str(phase or "MARKET_DATA"))


def request_cancel(execution_id: str, requested_by: str = "UI") -> dict[str, Any]:
    """Persist a cooperative stop request; the worker stops at its next checkpoint."""
    with _LOCK:
        status = get_status(execution_id)
        if not status or status.get("state") in _TERMINAL:
            return status
        status.update({"state": "STOP_REQUESTED", "cancel_requested": True,
                       "cancel_requested_at": _now(), "cancel_requested_by": requested_by,
                       "message": "Stopp er forespurt; avslutter ved neste sikre kontrollpunkt",
                       "updated_at": _now()})
        return _write_status(status)


def _worker(execution_id: str, job_payload: Mapping[str, Any], trigger: str, force_refresh: bool) -> None:
    from market_intelligence import JobProfile, run_job, verify_report_persistence

    cancelled_before_start = False
    with _LOCK:
        status = get_status(execution_id)
        if status.get("cancel_requested") or status.get("state") == "STOP_REQUESTED":
            status.update({"state": "CANCELLED", "message": "Kjøringen ble avbrutt før start",
                           "completed_at": _now(), "updated_at": _now()})
            _write_status(status)
            _THREADS.pop(execution_id, None)
            cancelled_before_start = True
        else:
            status.update({"state": "RUNNING", "started_at": _now(), "updated_at": _now(),
                           "message": "Starter markedsskanning", "percent": 1})
            _write_status(status)
    if cancelled_before_start:
        return

    def progress(event: Mapping[str, Any]) -> None:
        with _LOCK:
            current = get_status(execution_id) or status
            phase = str(event.get("phase") or "START")
            if phase != "COMPLETE" and (current.get("cancel_requested") or current.get("state") == "STOP_REQUESTED"):
                raise ExecutionCancelled("Stopp forespurt av bruker")
            message = str(event.get("message") or event.get("phase") or "Kjører")
            ticker = str(event.get("ticker") or "")
            if ticker and ticker not in message:
                message = f"{message} · {ticker}"
            active_stage = display_stage(phase)
            completed_steps = list(current.get("completed_steps") or [])
            previous_stage = str(current.get("active_stage") or "")
            if previous_stage and previous_stage != active_stage and previous_stage not in completed_steps:
                completed_steps.append(previous_stage)
            if phase == "COMPLETE":
                completed_steps = list(_STAGE_ORDER)
            current.update({
                "state": "RUNNING", "updated_at": _now(),
                "phase": phase, "active_stage": active_stage,
                "completed_steps": completed_steps,
                "percent": max(int(current.get("percent") or 0), progress_percent(event)), "message": message,
                "progress_event": dict(event),
            })
            _write_progress_status(current)

    try:
        result = run_job(JobProfile.from_dict(job_payload), trigger=trigger,
                         progress_callback=progress, force_refresh=force_refresh)
        # run_job performs the authoritative read-after-write check.  Keep
        # compatibility with injected/legacy runners that predate this field.
        persistence = result.get("persistence")
        if isinstance(persistence, Mapping) and not persistence.get("ok"):
            raise RuntimeError(str(persistence.get("error") or "Rapportlagring kunne ikke bekreftes"))
        chain = dict(result.get("autonomous_chain") or {})
        final = get_status(execution_id) or status
        final.update({
            "state": "COMPLETED", "phase": "COMPLETE", "percent": 100,
            "message": "Hele kjeden er ferdig", "updated_at": _now(),
            "completed_at": _now(), "run_id": result.get("run_id"),
            "chain_id": chain.get("chain_id"), "chain_status": chain.get("status"),
            "chain": chain, "top_candidates": list(result.get("candidates") or [])[:3],
            "data_refresh": dict(result.get("data_refresh") or {}), "error": "",
            "archive_saved": bool(persistence.get("archive_saved")) if isinstance(persistence, Mapping) else True,
            "run_json_saved": bool(persistence.get("run_json_saved")) if isinstance(persistence, Mapping) else True,
            "report_type": (result.get("report_identity") or {}).get("type"),
            "report_label": (result.get("report_identity") or {}).get("label"),
            "mission_id": result.get("mission_id") or (result.get("investment_mission") or {}).get("mission_id"),
            "configuration_version": result.get("configuration_version") or (result.get("investment_mission") or {}).get("configuration_version"),
            "completion_status": result.get("completion_status") or "FULLFØRT",
            "partial_market_failure": bool(result.get("partial_market_failure")),
            "failed_markets": list((result.get("data_quality") or {}).get("failed_markets") or []),
            "timezone_name": result.get("timezone_name"),
            "completed_local": local_display(result.get("created_at"), str(result.get("timezone_name") or "Europe/Oslo")),
        })
        _write_status(final)
    except ExecutionCancelled as exc:
        cancelled = get_status(execution_id) or status
        cancelled.update({
            "state": "CANCELLED", "message": "Kjøringen ble kontrollert avbrutt",
            "updated_at": _now(), "completed_at": _now(), "error": "",
            "cancel_reason": str(exc), "partial_results_published": False,
        })
        _write_status(cancelled)
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
        timezone_name = str(getattr(job, "timezone_name", "Europe/Oslo") or "Europe/Oslo")
        execution_id = f"MBJ-{as_local(datetime.now(timezone.utc), timezone_name):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6].upper()}"
        selected_markets = list(getattr(job, "markets", []) or [])
        market_count = 6 if "Alle" in selected_markets else max(1, len(selected_markets))
        per_market = int(getattr(job, "scan_limit", 25))
        status = _write_status({
            "execution_id": execution_id, "state": "QUEUED", "phase": "START",
            "percent": 0, "message": "Klargjør bakgrunnskjøring", "trigger": trigger,
            "job_id": getattr(job, "job_id", ""), "job_name": getattr(job, "name", ""),
            "mission_id": getattr(job, "investment_mission_id", ""),
            "configuration_version": getattr(job, "configuration_version", ""),
            "scan_configuration": {
                "per_market": per_market, "market_count": market_count,
                "planned_maximum": per_market * market_count,
                "markets": selected_markets,
            },
            "force_refresh": bool(force_refresh), "accepted_at": _now(),
            "timezone_name": timezone_name,
            "started_at": None, "completed_at": None, "updated_at": _now(), "error": "",
            "cancel_requested": False, "completed_steps": [], "active_stage": "MARKET_DATA",
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
    return bool(value) and value.get("state") in {"QUEUED", "RUNNING", "STOP_REQUESTED"}
