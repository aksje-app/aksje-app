"""Durable execution state for Super Portfolio background scans."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import uuid
import zipfile
from typing import Any, Mapping

from durable_runtime import append_event, read_events, read_json, write_json
from storage_architecture import runtime_data_path, runtime_log_path
from app_version import APP_VERSION


VERSION = APP_VERSION
ACTIVE_STATES = {"QUEUED", "STARTING", "RUNNING", "PAUSE_REQUESTED", "PAUSED", "STOP_REQUESTED"}
TERMINAL_STATES = {"CANCELLED", "COMPLETED", "DEGRADED", "FAILED", "INTERRUPTED"}
JOB_KEY = "super_portfolio/job_status.json"
JOB_PATH = runtime_data_path("super_portfolio", "job_status.json")
EVENT_KEY = "super_portfolio/job_events.jsonl"
EVENT_PATH = runtime_log_path("super_portfolio_job_events.jsonl")
CHECKPOINT_KEY = "super_portfolio/job_checkpoints.json"
CHECKPOINT_PATH = runtime_data_path("super_portfolio", "job_checkpoints.json")
CREATION_LOCK_ID = 19320321
EXECUTION_LOCK_ID = 19320322
_LOCAL_LOCKS = {CREATION_LOCK_ID: threading.Lock(), EXECUTION_LOCK_ID: threading.Lock()}


class JobCreationBusy(RuntimeError):
    pass


class SupersededWorker(RuntimeError):
    pass


class ScanCancelled(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


@contextmanager
def _advisory_lock(lock_id: int):
    connection = None
    acquired = False
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    try:
        if database_url:
            import psycopg2
            connection = psycopg2.connect(database_url, connect_timeout=5)
            cursor = connection.cursor()
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (int(lock_id),))
            acquired = bool(cursor.fetchone()[0])
        else:
            acquired = _LOCAL_LOCKS[int(lock_id)].acquire(blocking=False)
        yield acquired
    finally:
        if connection is not None:
            try:
                if acquired:
                    cursor = connection.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (int(lock_id),))
                connection.close()
            except Exception:
                pass
        elif acquired:
            _LOCAL_LOCKS[int(lock_id)].release()


def get_job(job_id: str = "") -> dict[str, Any]:
    value = read_json(JOB_KEY, JOB_PATH, {})
    current = dict(value) if isinstance(value, Mapping) else {}
    if job_id and str(current.get("job_id") or "") != str(job_id):
        return {}
    return current


def _write_status(status: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(status)
    value["updated_at"] = _now()
    write_json(JOB_KEY, JOB_PATH, value)
    return value


def _record_event(status: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    append_event(EVENT_KEY, EVENT_PATH, {
        "timestamp": _now(), "job_id": status.get("job_id"),
        "execution_token_suffix": str(status.get("execution_token") or "")[-6:],
        **dict(event),
    })


def create_or_get_job(trigger: str, force_refresh: bool) -> dict[str, Any]:
    with _advisory_lock(CREATION_LOCK_ID) as acquired:
        if not acquired:
            raise JobCreationBusy("SP job creation lock is busy")
        current = get_job()
        if str(current.get("state") or "").upper() in ACTIVE_STATES:
            return {**current, "duplicate_request": True}
        accepted_at = _now()
        job_id = f"SPJ-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6].upper()}"
        status = {
            "version": VERSION, "job_id": job_id, "execution_token": secrets.token_hex(16),
            "state": "QUEUED", "outcome": "", "trigger": str(trigger or "MANUAL").upper(),
            "force_refresh": bool(force_refresh), "phase": "QUEUED", "market": "",
            "ticker": "", "completed": 0, "total": 0, "percent": 0,
            "message": "SP-jobb er lagt i kø", "requested_at": accepted_at,
            "started_at": None, "completed_at": None, "heartbeat_at": accepted_at,
            "last_progress_at": accepted_at, "worker_pid": None, "worker_process_identity": "",
            "cancel_requested": False, "pause_requested": False, "failure_type": "",
            "failure_phase": "", "error": "", "final_pipeline_run_id": "",
            "latest_successful_run_id": str(current.get("latest_successful_run_id") or current.get("final_pipeline_run_id") or ""),
            "duplicate_request": False,
        }
        status = _write_status(status)
        _record_event(status, {"event": "JOB_CREATED", "state": "QUEUED", "trigger": status["trigger"]})
        return status


def launch_job(job: Mapping[str, Any]) -> dict[str, Any]:
    """Detach a manual SP worker and return immediately to Streamlit."""
    value = dict(job or {})
    if value.get("duplicate_request"):
        return value
    job_id = str(value.get("job_id") or "")
    token = str(value.get("execution_token") or "")
    command = [
        sys.executable, str(Path(__file__).with_name("super_portfolio_worker.py")),
        "--job-id", job_id, "--execution-token", token,
    ]
    try:
        process = subprocess.Popen(
            command, cwd=str(Path(__file__).parent), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return update_job(
            job_id, token, worker_pid=int(process.pid),
            worker_process_identity=f"pid:{int(process.pid)}",
            message="SP-worker er startet i bakgrunnen",
        )
    except Exception as exc:
        return update_job(
            job_id, token, state="FAILED", outcome="FAILED",
            failure_type="LAUNCH_FAILED", failure_phase="STARTING",
            error=f"{type(exc).__name__}: {str(exc)[:500]}",
            message="Kunne ikke starte SP-worker",
        )


def start_job(trigger: str = "MANUAL", force_refresh: bool = True) -> dict[str, Any]:
    job = create_or_get_job(trigger, force_refresh)
    return launch_job(job)


def _require_worker(status: Mapping[str, Any], job_id: str, execution_token: str) -> None:
    if str(status.get("job_id") or "") != str(job_id) or not execution_token or str(status.get("execution_token") or "") != str(execution_token):
        raise SupersededWorker("SP worker no longer owns this job")
    if str(status.get("state") or "").upper() in TERMINAL_STATES:
        raise SupersededWorker("SP job is already terminal")


def update_job(job_id: str, execution_token: str, **changes: Any) -> dict[str, Any]:
    with _advisory_lock(CREATION_LOCK_ID) as acquired:
        if not acquired:
            raise JobCreationBusy("SP status lock is busy")
        status = get_job()
        _require_worker(status, job_id, execution_token)
        next_state = str(changes.get("state") or status.get("state") or "").upper()
        value = {**status, **changes, "state": next_state}
        if next_state not in TERMINAL_STATES:
            value["percent"] = min(99, max(int(status.get("percent") or 0), int(changes.get("percent", status.get("percent") or 0))))
        elif next_state in {"COMPLETED", "DEGRADED"}:
            value["percent"] = 100
            value["completed_at"] = changes.get("completed_at") or _now()
            if value.get("final_pipeline_run_id"):
                value["latest_successful_run_id"] = value["final_pipeline_run_id"]
        else:
            value["percent"] = min(99, max(0, int(value.get("percent") or 0)))
            value["completed_at"] = changes.get("completed_at") or _now()
        value["heartbeat_at"] = changes.get("heartbeat_at") or _now()
        value = _write_status(value)
        _record_event(value, {"event": "STATUS", "state": value["state"], "phase": value.get("phase"), "percent": value.get("percent")})
        return value


def append_progress(job_id: str, execution_token: str, event: Mapping[str, Any]) -> dict[str, Any]:
    status = get_job()
    _require_worker(status, job_id, execution_token)
    incoming = dict(event)
    percent = min(99, max(int(status.get("percent") or 0), int(incoming.get("percent") or 0)))
    now = _now()
    changes = {
        "state": "RUNNING" if str(status.get("state") or "") not in {"PAUSE_REQUESTED", "PAUSED", "STOP_REQUESTED"} else status["state"],
        "phase": str(incoming.get("phase") or incoming.get("stage") or status.get("phase") or "RUNNING"),
        "market": str(incoming.get("market") or status.get("market") or ""),
        "ticker": str(incoming.get("ticker") or ""),
        "completed": int(incoming.get("completed") or 0), "total": int(incoming.get("total") or 0),
        "percent": percent, "message": str(incoming.get("message") or status.get("message") or "Jobber"),
        "last_progress_at": now, "heartbeat_at": now,
    }
    value = update_job(job_id, execution_token, **changes)
    _record_event(value, {"event": "PROGRESS", **incoming, "percent": percent})
    return value


def request_control(action: str, job_id: str = "") -> dict[str, Any]:
    action = str(action or "").upper()
    with _advisory_lock(CREATION_LOCK_ID) as acquired:
        if not acquired:
            raise JobCreationBusy("SP control lock is busy")
        status = get_job(job_id)
        if not status or str(status.get("state") or "") in TERMINAL_STATES:
            return status
        if action == "PAUSE" and status.get("state") not in {"PAUSE_REQUESTED", "PAUSED", "STOP_REQUESTED"}:
            status.update({"state": "PAUSE_REQUESTED", "pause_requested": True, "message": "Pause er bedt om"})
        elif action == "RESUME" and status.get("state") in {"PAUSE_REQUESTED", "PAUSED"}:
            status.update({"state": "RUNNING", "pause_requested": False, "message": "SP-jobben fortsetter"})
        elif action == "STOP" and status.get("state") != "STOP_REQUESTED":
            status.update({"state": "STOP_REQUESTED", "cancel_requested": True, "pause_requested": False, "message": "Stopper ved neste sikre kontrollpunkt"})
        status = _write_status(status)
        _record_event(status, {"event": "CONTROL_REQUESTED", "action": action, "state": status.get("state")})
        return status


def control_state(job_id: str, execution_token: str) -> str:
    status = get_job()
    _require_worker(status, job_id, execution_token)
    if status.get("cancel_requested") or status.get("state") == "STOP_REQUESTED":
        return "STOP"
    if status.get("pause_requested") or status.get("state") in {"PAUSE_REQUESTED", "PAUSED"}:
        return "PAUSE"
    return "RUN"


@contextmanager
def worker_execution_lease(job_id: str, execution_token: str):
    with _advisory_lock(EXECUTION_LOCK_ID) as acquired:
        if not acquired:
            raise JobCreationBusy("Another SP worker owns the execution lease")
        status = get_job()
        _require_worker(status, job_id, execution_token)
        yield


def _worker_is_alive(status: Mapping[str, Any]) -> bool:
    try:
        pid = int(status.get("worker_pid") or 0)
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def recover_stale_job(*, stale_after_seconds: int = 900, now: datetime | None = None) -> dict[str, Any]:
    status = get_job()
    if str(status.get("state") or "") not in ACTIVE_STATES:
        return status
    reference = now or datetime.now(timezone.utc)
    progress_at = _parse_timestamp(status.get("last_progress_at"))
    heartbeat_at = _parse_timestamp(status.get("heartbeat_at"))
    latest = max([value for value in (progress_at, heartbeat_at) if value is not None], default=None)
    if latest is None or (reference - latest).total_seconds() <= max(30, int(stale_after_seconds)) or _worker_is_alive(status):
        return status
    with _advisory_lock(CREATION_LOCK_ID) as acquired:
        if not acquired:
            return status
        current = get_job()
        if current.get("job_id") != status.get("job_id") or str(current.get("state") or "") not in ACTIVE_STATES:
            return current
        current.update({
            "state": "INTERRUPTED", "outcome": "INTERRUPTED", "completed_at": _now(),
            "recovery_action": "RESUME_AVAILABLE" if current.get("checkpoint_count") else "RESTART_AVAILABLE",
            "message": "Worker mistet; jobben er trygt frigitt", "failure_type": "STALE_WORKER",
        })
        current = _write_status(current)
        _record_event(current, {"event": "STALE_WORKER_RECOVERED", "state": "INTERRUPTED"})
        return current


def _scheduled_job_due(now: datetime | None = None) -> tuple[bool, str]:
    """Use the existing SP refresh and weekly rebalance policy for Cron claims."""
    from super_portfolio import (
        SuperPortfolioConfig, load_latest_super_portfolio_market_pipeline, load_state,
    )

    reference = now or datetime.now(timezone.utc).astimezone()
    state = load_state()
    raw_config = state.get("config") if isinstance(state.get("config"), Mapping) else {}
    allowed = set(SuperPortfolioConfig.__dataclass_fields__)
    config = SuperPortfolioConfig(**{key: value for key, value in raw_config.items() if key in allowed})
    if reference.weekday() == int(config.rebalance_weekday) and str(state.get("last_rebalance_date") or "") != reference.date().isoformat():
        return True, "WEEKLY_REBALANCE_DUE"
    pipeline = load_latest_super_portfolio_market_pipeline()
    created_at = _parse_timestamp(pipeline.get("created_at"))
    if created_at is None or not pipeline.get("candidates"):
        return True, "NO_VERIFIED_PIPELINE"
    ref_utc = reference.astimezone(timezone.utc)
    if (ref_utc - created_at.astimezone(timezone.utc)).total_seconds() >= max(1.0, float(config.market_refresh_hours)) * 3600.0:
        return True, "REFRESH_DUE"
    return False, "NOT_DUE"


def run_or_resume_scheduled_job(now: datetime | None = None) -> dict[str, Any]:
    """Claim and finish a due SP job inside the finite Render Cron process."""
    recovered = recover_stale_job(now=now)
    if str(recovered.get("state") or "") in ACTIVE_STATES:
        return {
            "state": "ALREADY_RUNNING", "job_id": str(recovered.get("job_id") or ""),
            "trigger": str(recovered.get("trigger") or ""),
        }
    due, reason = _scheduled_job_due(now)
    if not due:
        return {"state": "NOT_DUE", "reason": reason, "job_id": str(recovered.get("job_id") or "")}
    job = create_or_get_job("SCHEDULED", True)
    if job.get("duplicate_request"):
        return {"state": "ALREADY_RUNNING", "job_id": job.get("job_id"), "trigger": job.get("trigger")}
    from super_portfolio_worker import run_claimed_job

    result = dict(run_claimed_job(str(job["job_id"]), str(job["execution_token"])) or {})
    result.setdefault("job_id", job["job_id"])
    result["schedule_reason"] = reason
    return result


def save_checkpoint(job_id: str, execution_token: str, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    status = get_job()
    _require_worker(status, job_id, execution_token)
    value = read_json(CHECKPOINT_KEY, CHECKPOINT_PATH, {})
    checkpoints = dict(value) if isinstance(value, Mapping) else {}
    rows = list(checkpoints.get(job_id) or [])
    rows.append(dict(checkpoint))
    checkpoints[job_id] = rows[-10:]
    write_json(CHECKPOINT_KEY, CHECKPOINT_PATH, checkpoints)
    return update_job(job_id, execution_token, checkpoint_count=len(rows), last_checkpoint_at=_now())


def job_events(job_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    return [row for row in read_events(EVENT_KEY, EVENT_PATH, limit=max(limit * 2, limit)) if str(row.get("job_id") or "") == str(job_id)][-limit:]


def _redact(value: Any) -> Any:
    blocked = ("token", "secret", "password", "authorization", "database_url", "api_key", "cookie")
    if isinstance(value, Mapping):
        return {str(key): ("[REDACTED]" if any(part in str(key).lower() for part in blocked) else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def diagnostic_zip(job_id: str = "") -> bytes:
    status = get_job(job_id)
    chosen_id = str(status.get("job_id") or job_id or "")
    checkpoints = read_json(CHECKPOINT_KEY, CHECKPOINT_PATH, {})
    manifest = list((checkpoints or {}).get(chosen_id) or []) if isinstance(checkpoints, Mapping) else []
    try:
        from super_portfolio import resource_health
        resources = resource_health()
    except Exception as exc:
        resources = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
    files = {
        "README.txt": f"SUPER PORTFOLIO JOB DIAGNOSE\nJob: {chosen_id or '-'}\nState: {status.get('state') or '-'}\nVersion: {VERSION}\n",
        "job_status.json": json.dumps(_redact(status), ensure_ascii=False, indent=2, default=str),
        "progress_events.json": json.dumps(_redact(job_events(chosen_id)), ensure_ascii=False, indent=2, default=str),
        "checkpoint_manifest.json": json.dumps(_redact(manifest), ensure_ascii=False, indent=2, default=str),
        "resource_health.json": json.dumps(_redact(resources), ensure_ascii=False, indent=2, default=str),
        "version_identity.json": json.dumps({"version": VERSION, "commit": str(os.getenv("RENDER_GIT_COMMIT") or "")[:40]}, indent=2),
    }
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()
