"""Durable background execution for manually started full-chain jobs.

The worker is deliberately independent of Streamlit's script thread.  UI
reruns, page navigation and browser disconnects therefore do not cancel an
accepted job.  PostgreSQL/StorageService is authoritative for status while a
local JSON file remains a backwards-compatible diagnostic mirror.
"""
from __future__ import annotations

import json
import io
import hashlib
import os
import threading
import traceback
import uuid
import zipfile
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
_SNAPSHOT_LOCK = threading.Lock()
_LATEST_ACTIVE_SNAPSHOT: dict[str, Any] = {}
_THREADS: dict[str, threading.Thread] = {}
_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "STALLED"}
_STAGE_ORDER = ["MARKET_DATA", "INSIDER", "NEWS", "SCORING", "PORTFOLIO_PROPOSAL", "AUTONOMOUS", "REPORT", "COMPLETE"]
_STAGE_PROGRESS_LIMIT_SECONDS = {
    "PREFLIGHT": 150,
    "MARKET_DATA": 600,
    "INSIDER": 360,
    "NEWS": 360,
    "SCORING": 360,
    "PORTFOLIO_PROPOSAL": 300,
    # Autonomi performs persisted portfolio, learning-account and replay work.
    # It must emit internal checkpoints (RC16.30), while the hard silence limit
    # allows Render's single CPU and durable database normal operating room.
    "AUTONOMOUS": 900,
    "REPORT": 420,
}


def _stage_progress_limit(stage: str) -> int:
    """Maximum silence between real progress events, never heartbeats."""
    stage_name = str(stage or "PREFLIGHT").upper()
    default = _STAGE_PROGRESS_LIMIT_SECONDS.get(stage_name, 600)
    raw = os.environ.get(f"MANUAL_JOB_{stage_name}_PROGRESS_TIMEOUT_SECONDS", "")
    try:
        return max(60, int(raw)) if raw else default
    except (TypeError, ValueError):
        return default


def _seconds_since(value: Any) -> int | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


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


def _publish_runtime_snapshot(status: Mapping[str, Any]) -> dict[str, Any]:
    """Publish one copy-on-write status snapshot for low-latency UI polling.

    The Streamlit fragment and the worker run in the same web process. Reading
    this snapshot avoids opening two PostgreSQL connections and rewriting two
    diagnostic mirror files every few seconds. Durable storage remains the
    authoritative recovery source after process restarts.
    """
    global _LATEST_ACTIVE_SNAPSHOT
    payload = dict(status or {})
    with _SNAPSHOT_LOCK:
        _LATEST_ACTIVE_SNAPSHOT = payload
    return dict(payload)


def _runtime_snapshot() -> dict[str, Any]:
    with _SNAPSHOT_LOCK:
        return dict(_LATEST_ACTIVE_SNAPSHOT)


def _read_local_status_file(path) -> dict[str, Any]:
    """Read an atomically replaced local JSON mirror without repository I/O."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _write_status(status: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(status)
    execution_id = str(payload["execution_id"])
    # Publish before durable I/O. A slow database must not prevent the browser
    # from seeing the progress event that the worker has already produced.
    _publish_runtime_snapshot(payload)
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

    thread_alive = _thread_is_alive(execution_id)
    # A heartbeat is emitted by a dedicated thread.  It proves that the process
    # lives, but not that the analysis worker advances.  Reconcile against the
    # last *real* progress event so a blocked network call cannot own the job
    # lease forever while its heartbeat keeps moving.
    if thread_alive and state == "RUNNING":
        progress_reference = (
            current.get("last_progress_at")
            or current.get("updated_at")
            or current.get("started_at")
            or current.get("accepted_at")
        )
        silence = _seconds_since(progress_reference)
        stage = str(current.get("active_stage") or "PREFLIGHT").upper()
        limit = _stage_progress_limit(stage)
        if not force and silence is not None and silence <= limit:
            return current
        if force or (silence is not None and silence > limit):
            now = _now()
            current.update({
                "state": "STALLED",
                "message": f"Kjøringen er frigitt: ingen reell fremdrift i {stage}",
                "updated_at": now,
                "completed_at": now,
                "stalled_at": now,
                "lease_revoked": True,
                "cancel_requested": True,
                "cancel_reason": "Fremdriftsvakten frigjorde en fastlåst worker",
                "partial_results_published": False,
                "error": f"Ingen fremdriftshendelse på {silence if silence is not None else 'ukjent antall'} sekunder (grense {limit})",
                "error_type": "WorkerProgressTimeout",
                "error_stage": stage,
                "error_code": "STAGE_PROGRESS_TIMEOUT",
                "progress_silence_seconds": silence,
                "stage_progress_limit_seconds": limit,
                "recovered_orphan": True,
                "orphan_reason_code": "LIVE_WORKER_PROGRESS_STALLED",
                "recovered_at": now,
            })
            return _write_status(current)
        return current

    if thread_alive:
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
    reconciled = reconcile_orphaned_status(status)
    if reconciled:
        _publish_runtime_snapshot(reconciled)
    return reconciled


def get_active_status_snapshot() -> dict[str, Any]:
    """Return a read-only, low-latency status snapshot for periodic UI polls.

    Poll order is deliberately memory -> atomic local mirror -> durable store.
    The common path performs no database connection, no mirror write, no orphan
    reconciliation and no Session State mutation. This keeps a two-second
    Streamlit fragment rerun small and prevents the full page from appearing
    busy while the report worker continues.
    """
    snapshot = _runtime_snapshot()
    if snapshot.get("execution_id"):
        if snapshot.get("last_progress_at") or snapshot.get("worker_process_identity"):
            snapshot = reconcile_orphaned_status(snapshot)
        snapshot["ui_poll_source"] = "PROCESS_MEMORY"
        return snapshot

    active = _read_local_status_file(ACTIVE_PATH)
    execution_id = str(active.get("execution_id") or "")
    if execution_id:
        local_status = _read_local_status_file(_status_path(execution_id))
        if local_status.get("execution_id"):
            if local_status.get("last_progress_at") or local_status.get("worker_process_identity"):
                local_status = reconcile_orphaned_status(local_status)
            _publish_runtime_snapshot(local_status)
            local_status["ui_poll_source"] = "LOCAL_ATOMIC_MIRROR"
            return local_status

    # Cold process or missing mirror: one authoritative recovery read. Normal
    # fragment ticks return from memory after this point.
    durable = get_active_status()
    if durable:
        durable = dict(durable)
        durable["ui_poll_source"] = "DURABLE_RECOVERY"
    return durable


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


def force_release(execution_id: str, requested_by: str = "UI") -> dict[str, Any]:
    """Revoke a stuck worker lease without deleting reports or runtime data."""
    with _LOCK:
        status = get_status(execution_id)
        if not status or str(status.get("state") or "").upper() in _TERMINAL:
            return status
        now = _now()
        status.update({
            "state": "STALLED",
            "message": "Jobblåsen er frigitt manuelt; en ny kjøring kan startes",
            "updated_at": now,
            "completed_at": now,
            "stalled_at": now,
            "lease_revoked": True,
            "cancel_requested": True,
            "cancel_requested_at": now,
            "cancel_requested_by": requested_by,
            "cancel_reason": "Manuell sikker frigivelse av fastlåst jobb",
            "partial_results_published": False,
            "error": "Workerens publiseringsrett er tilbakekalt",
            "error_type": "WorkerLeaseRevoked",
            "error_stage": str(status.get("active_stage") or "PREFLIGHT"),
            "error_code": "MANUAL_STALE_LEASE_RELEASE",
        })
        return _write_status(status)


def diagnostic_bundle(execution_id: str) -> tuple[bytes, str]:
    """Create a bounded, secret-free job and learning support bundle."""
    status = dict(get_status(execution_id) or {})
    allowed = {
        "execution_id", "state", "phase", "active_stage", "completed_steps",
        "percent", "message", "accepted_at", "started_at", "updated_at",
        "last_progress_at", "heartbeat_at", "worker_heartbeat_at",
        "completed_at", "stalled_at", "error", "error_type", "error_stage",
        "error_code", "progress_event", "stage_history", "stage_started_at",
        "stage_progress_limit_seconds", "progress_silence_seconds",
        "heartbeat_sequence", "worker_process_identity", "worker_pid",
        "worker_thread_name", "heartbeat_thread_name", "job_id", "job_name",
        "trigger", "scan_configuration", "cancel_requested", "cancel_reason",
        "lease_revoked", "partial_results_published", "ui_poll_source",
        "run_id", "chain", "chain_status", "full_autonomy_execution", "error_trace",
    }
    sanitized = {key: status.get(key) for key in sorted(allowed) if key in status}
    try:
        from learning_acceptance import build_learning_diagnostics
        learning = build_learning_diagnostics()
        acceptance = dict(learning.get("acceptance") or {})
        current_run_id = str(status.get("run_id") or "")
        acceptance_report_id = str(acceptance.get("report_id") or "")
        current_match = bool(current_run_id and acceptance_report_id == current_run_id)
        acceptance.update({
            "current_job_match": current_match,
            "evidence_scope": "CURRENT_RUN" if current_match else "PREVIOUS_RUN",
            "diagnostic_execution_id": execution_id,
            "diagnostic_run_id": current_run_id,
        })
        learning["acceptance"] = acceptance
    except Exception as exc:
        learning = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    try:
        from report_test_mode import load_report_test_mode
        report_test = load_report_test_mode()
    except Exception as exc:
        report_test = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    try:
        from report_system_check import load_report_system_check
        system_check = load_report_system_check()
    except Exception as exc:
        system_check = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    try:
        from notifier import pushover_audit
        pushover_rows = list(pushover_audit(limit=50) or [])
    except Exception as exc:
        pushover_rows = [{"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {str(exc)[:500]}"}]
    try:
        from scheduled_runner import load_unattended_state
        scheduler = load_unattended_state()
        scheduler = {key: scheduler.get(key) for key in (
            "state", "started_at", "completed_at", "process", "scheduler",
            "scheduler_health", "report_test_mode", "error",
        ) if key in scheduler}
    except Exception as exc:
        scheduler = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    readme = (
        "Diagnosepakke for manuell bakgrunnskjøring.\n"
        "Pakken inneholder status, fremdrift og avgrenset Autonomi-læringsbevis. "
        "API-nøkler, tokens, passord, miljøverdier, fulle rapporter og ordinær "
        "portefølje er ikke inkludert. Læringsposisjoner er teoretiske.\n"
    )
    payloads = {
        "README.txt": readme.encode("utf-8"),
        "status.json": json.dumps(sanitized, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        "learning/LEARNING_DIAGNOSTICS.json": json.dumps(learning, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        "learning/LEARNING_ACCEPTANCE.json": json.dumps(learning.get("acceptance") or {}, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        "scheduler/SCHEDULER_STATUS.json": json.dumps(scheduler, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        "scheduler/REPORT_TEST_MODE.json": json.dumps(report_test, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        "scheduler/REPORT_TEST_TIMELINE.json": json.dumps(report_test.get("timeline") or [], ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        "scheduler/REPORT_SYSTEM_CHECK.json": json.dumps(system_check, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        "notifications/PUSHOVER_AUDIT.json": json.dumps(pushover_rows, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
    }
    checksums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(payloads.items()))
    payloads["SHA256SUMS"] = checksums.encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
    safe_id = "".join(character for character in execution_id if character.isalnum() or character in "-_") or "ukjent"
    return buffer.getvalue(), f"Bakgrunnsjobb_diagnose_{safe_id}.zip"


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
                           "message": "Oppstartskontroll: klargjør sikker kjøring", "percent": 1,
                           "last_progress_at": now, "stage_started_at": now,
                           "stage_progress_limit_seconds": _stage_progress_limit("PREFLIGHT"),
                           "stage_history": [{"stage": "PREFLIGHT", "entered_at": now}]})
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
                if not current or str(current.get("state") or "").upper() in _TERMINAL or current.get("lease_revoked"):
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
            if current.get("lease_revoked") or str(current.get("state") or "").upper() in {"STALLED", "FAILED", "CANCELLED"}:
                raise ExecutionCancelled("Workerens publiseringsrett er tilbakekalt")
            if phase != "COMPLETE" and (current.get("cancel_requested") or current.get("state") == "STOP_REQUESTED"):
                raise ExecutionCancelled("Stopp forespurt av bruker")
            message = str(event.get("message") or event.get("phase") or "Kjører")
            ticker = str(event.get("ticker") or "")
            if ticker and ticker not in message:
                message = f"{message} · {ticker}"
            active_stage = display_stage(phase)
            completed_steps = list(current.get("completed_steps") or [])
            previous_stage = str(current.get("active_stage") or "")
            now = _now()
            stage_history = list(current.get("stage_history") or [])
            if previous_stage and previous_stage != active_stage and previous_stage not in completed_steps:
                completed_steps.append(previous_stage)
            if previous_stage != active_stage:
                if stage_history and not stage_history[-1].get("left_at"):
                    stage_history[-1] = {**dict(stage_history[-1]), "left_at": now}
                stage_history.append({"stage": active_stage, "entered_at": now})
            event_run_id = str(event.get("run_id") or current.get("run_id") or "")
            current.update({
                "state": "RUNNING", "updated_at": now, "heartbeat_at": now,
                "last_progress_at": _now(),
                "worker_process_identity": _PROCESS_IDENTITY, "worker_pid": os.getpid(),
                "worker_thread_name": threading.current_thread().name,
                "phase": phase, "active_stage": active_stage,
                "completed_steps": completed_steps,
                "stage_started_at": now if previous_stage != active_stage else current.get("stage_started_at"),
                "stage_progress_limit_seconds": _stage_progress_limit(active_stage),
                "stage_history": stage_history,
                "percent": max(int(current.get("percent") or 0), progress_percent(event)), "message": message,
                "progress_event": dict(event),
                "run_id": event_run_id,
                "work_completed": event.get("completed"), "work_total": event.get("total"),
                "active_ticker": ticker, "active_market": event.get("market") or event.get("market_name") or "",
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
        lease = get_status(execution_id) or status
        if lease.get("lease_revoked") or str(lease.get("state") or "").upper() in {"STALLED", "FAILED", "CANCELLED"}:
            raise ExecutionCancelled("Resultatet ble avvist fordi jobblåsen var tilbakekalt")
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
            "completed_steps": list(_STAGE_ORDER),
            "full_autonomy_execution": dict(full_execution or {}),
            "partial_market_failure": bool(result.get("partial_market_failure")),
            "failed_markets": list((result.get("data_quality") or {}).get("failed_markets") or []),
            "timezone_name": result.get("timezone_name"),
            "completed_local": local_display(result.get("created_at"), str(result.get("timezone_name") or "Europe/Oslo")),
        })
        _write_status(final)
    except ExecutionCancelled as exc:
        # Revoke the in-process worker/heartbeat before durable terminal I/O.
        # A slow database write must not leave the UI or watchdog believing
        # that a failed analysis worker is still active.
        heartbeat_stop.set()
        with _LOCK:
            _THREADS.pop(execution_id, None)
        cancelled = get_status(execution_id) or status
        if cancelled.get("lease_revoked") or str(cancelled.get("state") or "").upper() == "STALLED":
            cancelled.update({
                "state": "STALLED", "message": cancelled.get("message") or "Fastlåst jobb ble frigitt",
                "updated_at": _now(), "completed_at": cancelled.get("completed_at") or _now(),
                "cancel_reason": str(exc), "partial_results_published": False,
            })
            _write_status(cancelled)
            return
        cancelled.update({
            "state": "CANCELLED", "message": "Kjøringen ble kontrollert avbrutt",
            "updated_at": _now(), "completed_at": _now(), "error": "",
            "cancel_reason": str(exc), "partial_results_published": False,
        })
        _write_status(cancelled)
    except Exception as exc:
        # Publish and release the terminal failure path immediately.  This is
        # deliberately done before the durable write below so a consistency
        # exception cannot linger as RUNNING until the progress watchdog fires.
        heartbeat_stop.set()
        with _LOCK:
            _THREADS.pop(execution_id, None)
        failed = get_status(execution_id) or status
        failed_result = result if "result" in locals() and isinstance(result, Mapping) else {}
        failed_chain = dict(failed_result.get("autonomous_chain") or {})
        failed_execution = dict(failed_result.get("full_autonomy_execution") or {})
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
            "run_id": str(failed_result.get("run_id") or failed.get("run_id") or ""),
            "chain": failed_chain,
            "chain_status": failed_chain.get("status"),
            "full_autonomy_execution": failed_execution,
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
            "last_progress_at": accepted_at,
            "cancel_requested": False, "lease_revoked": False,
            "completed_steps": [], "active_stage": "PREFLIGHT",
            "stage_started_at": accepted_at,
            "stage_progress_limit_seconds": _stage_progress_limit("PREFLIGHT"),
            "stage_history": [{"stage": "PREFLIGHT", "entered_at": accepted_at}],
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
