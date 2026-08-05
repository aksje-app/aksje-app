"""Durable background execution for manually started full-chain jobs.

The worker is deliberately independent of Streamlit's script thread.  UI
reruns, page navigation and browser disconnects therefore do not cancel an
accepted job.  PostgreSQL/StorageService is authoritative for status while a
local JSON file remains a backwards-compatible diagnostic mirror.
"""
from __future__ import annotations

import os
import threading
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from durable_runtime import read_json, write_json
from execution_control import ExecutionCancelled
from local_time import as_local, local_display
from storage_architecture import runtime_data_path
from background_execution import background_execution


ROOT = runtime_data_path("manual_background_jobs")
ACTIVE_PATH = ROOT / "active.json"
ACTIVE_KEY = "manual_background_jobs/active.json"
_LOCK = threading.Lock()
_THREADS: dict[str, threading.Thread] = {}
_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
_STAGE_ORDER = ["MARKET_DATA", "INSIDER", "NEWS", "SCORING", "PORTFOLIO_PROPOSAL", "AUTONOMOUS", "REPORT", "COMPLETE"]


def _process_identity() -> str:
    """Stable identity for the current OS process, including PID reuse safety."""
    start_ticks = "unknown"
    try:
        fields = open("/proc/self/stat", "r", encoding="utf-8").read().split()
        if len(fields) > 21:
            start_ticks = fields[21]
    except Exception:
        pass
    return f"{os.getpid()}:{start_ticks}"


_PROCESS_IDENTITY = _process_identity()


def _explicit_job_name(job: Any) -> str:
    name = str(getattr(job, "name", "") or "").strip()
    if name and name.casefold() != "uten navn":
        return name
    markets = [str(value).strip() for value in list(getattr(job, "markets", []) or []) if str(value).strip()]
    market_label = " + ".join(markets) if markets else "valgte markeder"
    return f"Utkast – {market_label}"


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


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse persisted UTC timestamps without letting corrupt telemetry break the UI."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _thread_is_alive(execution_id: str) -> bool:
    thread = _THREADS.get(str(execution_id or ""))
    return bool(thread and thread.is_alive())


def reconcile_orphaned_status(
    status: Mapping[str, Any],
    *,
    stale_seconds: int = 90,
    same_process_stale_seconds: int = 900,
    force: bool = False,
) -> dict[str, Any]:
    """Reconcile durable status without mistaking a Streamlit rerun for restart.

    RC12 records an OS-process identity on acceptance.  A different identity is
    positive evidence of a real service restart.  A missing thread in the same
    process is not labelled as restart; it receives a longer heartbeat grace and
    becomes FAILED with a precise worker-lifecycle reason if it remains stale.
    """
    current = dict(status or {})
    execution_id = str(current.get("execution_id") or "")
    state = str(current.get("state") or "").upper()
    if not execution_id or state not in {"QUEUED", "RUNNING", "STOP_REQUESTED"}:
        return current
    if _thread_is_alive(execution_id):
        return current

    updated = _parse_timestamp(
        current.get("heartbeat_at") or current.get("updated_at") or current.get("accepted_at")
    )
    age = datetime.now(timezone.utc) - updated if updated is not None else None
    worker_identity = str(current.get("worker_process_identity") or "").strip()
    actual_restart = bool(worker_identity and worker_identity != _PROCESS_IDENTITY)

    if actual_restart:
        now = _now()
        current.update({
            "state": "CANCELLED",
            "message": "Kjøringen ble avsluttet ved en faktisk serverprosess-restart",
            "updated_at": now, "completed_at": now, "error": "",
            "cancel_requested": True,
            "cancel_reason": "Worker-prosessen tilhører en tidligere serverprosess",
            "partial_results_published": False, "recovered_orphan": True,
            "orphan_reason_code": "SERVER_PROCESS_RESTART",
            "recovered_at": now, "current_process_identity": _PROCESS_IDENTITY,
        })
        return _write_status(current)

    if worker_identity == _PROCESS_IDENTITY:
        grace = max(60, int(same_process_stale_seconds))
        if not force and age is not None and age < timedelta(seconds=grace):
            return current
        now = _now()
        current.update({
            "state": "FAILED",
            "message": "Bakgrunnsarbeideren sluttet å svare i samme serverprosess",
            "updated_at": now, "completed_at": now,
            "error": "Workertråden finnes ikke og ingen fersk heartbeat er registrert",
            "error_type": "WorkerLifecycleError",
            "error_stage": str(current.get("active_stage") or "PREFLIGHT"),
            "error_code": "WORKER_LOST_SAME_PROCESS",
            "cancel_requested": False, "partial_results_published": False,
            "recovered_orphan": True, "orphan_reason_code": "WORKER_LOST_SAME_PROCESS",
            "recovered_at": now,
        })
        return _write_status(current)

    # Legacy RC11-and-older records have no process identity.  Keep the previous
    # short grace but label the uncertainty explicitly rather than asserting a
    # server restart as fact.
    grace = max(15, int(stale_seconds))
    if not force and age is not None and age < timedelta(seconds=grace):
        return current
    now = _now()
    current.update({
        "state": "CANCELLED",
        "message": "Eldre kjøring uten worker-identitet er frigitt",
        "updated_at": now, "completed_at": now, "error": "",
        "cancel_requested": True,
        "cancel_reason": "Legacy-status manglet worker-identitet etter oppstart/deploy",
        "partial_results_published": False, "recovered_orphan": True,
        "orphan_reason_code": "LEGACY_WORKER_IDENTITY_MISSING",
        "recovered_at": now,
    })
    return _write_status(current)


def get_active_status() -> dict[str, Any]:
    active = read_json(ACTIVE_KEY, ACTIVE_PATH, {})
    if not isinstance(active, Mapping) or not active.get("execution_id"):
        return {}
    status = get_status(str(active["execution_id"]))
    return reconcile_orphaned_status(status)


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
    return {"START": "PREFLIGHT", "MARKET": "MARKET_DATA", "PREPARE": "MARKET_DATA",
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
        written = _write_status(status)
        # If the web service was restarted, no worker remains to reach another
        # checkpoint.  Finalise immediately instead of leaving STOP_REQUESTED
        # persisted forever.
        if not _thread_is_alive(execution_id):
            return reconcile_orphaned_status(written, stale_seconds=15, force=True)
        return written


def _worker(
    execution_id: str,
    job_payload: Mapping[str, Any],
    trigger: str,
    force_refresh: bool,
    scheduled_for: str = "",
) -> None:
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
            now = _now()
            status.update({"state": "RUNNING", "started_at": now, "updated_at": now,
                           "heartbeat_at": now, "worker_process_identity": _PROCESS_IDENTITY,
                           "worker_pid": os.getpid(), "worker_thread_name": threading.current_thread().name,
                           "message": "Starter markedsskanning", "percent": 1})
            _write_status(status)
    if cancelled_before_start:
        return

    heartbeat_stop = threading.Event()

    def _heartbeat_loop() -> None:
        sequence = 0
        while not heartbeat_stop.wait(10.0):
            sequence += 1
            with _LOCK:
                current = get_status(execution_id)
                if not current or str(current.get("state") or "").upper() in _TERMINAL:
                    return
                current["heartbeat_at"] = _now()
                current["worker_heartbeat_at"] = current["heartbeat_at"]
                current["heartbeat_sequence"] = sequence
                current["worker_process_identity"] = _PROCESS_IDENTITY
                current["worker_pid"] = os.getpid()
                current["heartbeat_thread_name"] = threading.current_thread().name
                # Do not touch ``updated_at`` here. It remains the timestamp of
                # the latest real progress event, making a live-but-stalled
                # worker distinguishable from genuine progress in the UI.
                _write_progress_status(current)

    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        name=f"manual-heartbeat-{execution_id}",
        daemon=True,
    )
    heartbeat_thread.start()

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
                "state": "RUNNING", "updated_at": _now(), "heartbeat_at": _now(),
                "last_progress_at": _now(),
                "worker_process_identity": _PROCESS_IDENTITY, "worker_pid": os.getpid(),
                "worker_thread_name": threading.current_thread().name,
                "phase": phase, "active_stage": active_stage,
                "completed_steps": completed_steps,
                "percent": max(int(current.get("percent") or 0), progress_percent(event)), "message": message,
                "progress_event": dict(event),
            })
            _write_progress_status(current)

    try:
        run_kwargs = {
            "trigger": trigger,
            "progress_callback": progress,
            "force_refresh": force_refresh,
        }
        if str(scheduled_for or "").strip():
            run_kwargs["scheduled_for"] = str(scheduled_for)
        with background_execution(execution_id):
            result = run_job(JobProfile.from_dict(job_payload), **run_kwargs)
        # run_job performs the authoritative read-after-write check.  Keep
        # compatibility with injected/legacy runners that predate this field.
        persistence = result.get("persistence")
        if isinstance(persistence, Mapping) and not persistence.get("ok"):
            raise RuntimeError(str(persistence.get("error") or "Rapportlagring kunne ikke bekreftes"))
        full_execution = result.get("full_autonomy_execution")
        if isinstance(full_execution, Mapping) and not full_execution.get("self_contained"):
            raise RuntimeError("Full Autonomy Execution ufullstendig: " + ", ".join(full_execution.get("failed_stages") or []))
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
            "full_autonomy_execution": dict(full_execution or {}),
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
        last_percent = max(0, min(99, int(failed.get("percent") or 0)))
        last_phase = str(failed.get("phase") or "START")
        report_context = dict(getattr(exc, "context", {}) or {})
        failed.update({
            "state": "FAILED", "percent": last_percent,
            "message": f"Kjøringen stoppet med feil ved {display_stage(last_phase)}",
            "updated_at": _now(), "completed_at": _now(), "error": str(exc),
            "error_type": report_context.get("error_type") or type(exc).__name__,
            "error_stage": report_context.get("stage") or display_stage(last_phase),
            "error_trace": report_context.get("traceback") or traceback.format_exc(limit=12)[-12000:],
            "error_code": report_context.get("error_code") or "",
            "report_path": report_context.get("report_path") or "",
            "diagnostic_path": report_context.get("diagnostic_path") or "",
            "app_runtime_root": report_context.get("app_runtime_root") or "",
            "storage_mode": report_context.get("storage_mode") or "",
        })
        _write_status(failed)
    finally:
        heartbeat_stop.set()
        with _LOCK:
            _THREADS.pop(execution_id, None)


def start_manual_job(
    job: Any,
    *,
    trigger: str,
    force_refresh: bool = False,
    scheduled_for: str = "",
) -> dict[str, Any]:
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
        previous_execution_id = str((active or {}).get("execution_id") or "")
        accepted_at = _now()
        status = _write_status({
            "execution_id": execution_id, "state": "QUEUED", "phase": "START",
            "percent": 0, "message": "Klargjør bakgrunnskjøring", "trigger": trigger,
            "job_id": getattr(job, "job_id", ""), "job_name": _explicit_job_name(job),
            "supersedes_execution_id": previous_execution_id,
            "worker_process_identity": _PROCESS_IDENTITY, "worker_pid": os.getpid(),
            "mission_id": getattr(job, "investment_mission_id", ""),
            "configuration_version": getattr(job, "configuration_version", ""),
            "scan_configuration": {
                "per_market": per_market, "market_count": market_count,
                "planned_maximum": per_market * market_count,
                "markets": selected_markets,
            },
            "force_refresh": bool(force_refresh), "scheduled_for": str(scheduled_for or ""), "accepted_at": accepted_at,
            "timezone_name": timezone_name,
            "started_at": None, "completed_at": None, "updated_at": accepted_at,
            "heartbeat_at": accepted_at, "error": "",
            "cancel_requested": False, "completed_steps": [], "active_stage": "PREFLIGHT",
        })
        thread = threading.Thread(
            target=_worker,
            args=(execution_id, asdict(job), trigger, bool(force_refresh), str(scheduled_for or "")),
            name=f"manual-chain-{execution_id}", daemon=True,
        )
        _THREADS[execution_id] = thread
        thread.start()
        return status


def is_running(status: Mapping[str, Any] | None = None) -> bool:
    value = status if status is not None else get_active_status()
    return bool(value) and value.get("state") in {"QUEUED", "RUNNING", "STOP_REQUESTED"}
