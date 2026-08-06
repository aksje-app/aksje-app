"""Background controller for RC16 complete replay exports.

Worker threads never import or call Streamlit.  Status is persisted as JSON and
read by a small UI fragment, so the page remains usable during large exports.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import zipfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from storage_architecture import runtime_data_path
from durable_runtime import read_json as durable_read_json, write_json as durable_write_json

ROOT = runtime_data_path("replay_exports")
STATUS_PATH = ROOT / "status.json"
STATUS_KEY = "replay_exports/status.json"
EXPORT_DIR = ROOT / "files"
_LOCK = threading.RLock()
_WORKERS: dict[str, threading.Thread] = {}
_STATUS_SNAPSHOT: dict[str, Any] = {}
STALE_HEARTBEAT_SECONDS = max(30, int(os.environ.get("REPLAY_EXPORT_STALE_HEARTBEAT_SECONDS", "45")))
WATCHDOG_INTERVAL_SECONDS = max(2, int(os.environ.get("REPLAY_EXPORT_WATCHDOG_INTERVAL_SECONDS", "5")))



def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid_zip_bytes(data: bytes) -> bool:
    if not data or not data.startswith(b"PK"):
        return False
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            return archive.testzip() is None and bool(archive.namelist())
    except Exception:
        return False


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_stamp(value: Any) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc)
    except Exception:
        return None


def _local_worker_alive(execution_id: str) -> bool:
    worker = _WORKERS.get(str(execution_id or ""))
    return bool(worker and worker.is_alive())


def _status_is_stale(status: Mapping[str, Any]) -> bool:
    state = str(status.get("state") or "").upper()
    if state not in {"QUEUED", "RUNNING"}:
        return False
    execution_id = str(status.get("execution_id") or "")
    if _local_worker_alive(execution_id):
        return False
    heartbeat = _parse_stamp(status.get("worker_heartbeat_at") or status.get("updated_at"))
    return heartbeat is None or datetime.now(timezone.utc) - heartbeat > timedelta(seconds=STALE_HEARTBEAT_SECONDS)


def _recover_stale_status(status: Mapping[str, Any]) -> dict[str, Any]:
    current = dict(status)
    if not _status_is_stale(current):
        return current
    current.update({
        "state": "FAILED",
        "stage": "AVBRUTT",
        "message": "Foreldet eksportjobb er avsluttet",
        "error": "Worker mangler eller heartbeat har stoppet. En ny eksport kan startes.",
        "completed_at": _now(),
        "stale_worker_recovered": True,
    })
    return _write_status(current)


def _read_status() -> dict[str, Any]:
    with _LOCK:
        if _STATUS_SNAPSHOT.get("execution_id"):
            return dict(_STATUS_SNAPSHOT)
    value = durable_read_json(STATUS_KEY, STATUS_PATH, {})
    payload = dict(value) if isinstance(value, Mapping) else {}
    if payload:
        with _LOCK:
            _STATUS_SNAPSHOT.clear()
            _STATUS_SNAPSHOT.update(payload)
    return payload


def _write_status(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload["updated_at"] = _now()
    with _LOCK:
        _STATUS_SNAPSHOT.clear()
        _STATUS_SNAPSHOT.update(payload)
    durable_write_json(STATUS_KEY, STATUS_PATH, payload)
    return payload


def get_status() -> dict[str, Any]:
    with _LOCK:
        return _recover_stale_status(_read_status())


def is_running(status: Mapping[str, Any] | None = None) -> bool:
    current = dict(status) if status is not None else get_status()
    if _status_is_stale(current):
        return False
    return str(current.get("state") or "").upper() in {"QUEUED", "RUNNING"}


def _parse_date(value: str | None, *, end: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if end and "T" not in str(value):
            stamp = stamp.replace(hour=23, minute=59, second=59)
        return stamp
    except Exception:
        return None


def _run_export(execution_id: str, filters: Mapping[str, Any]) -> None:
    watchdog_stop = threading.Event()

    def watchdog() -> None:
        while not watchdog_stop.wait(WATCHDOG_INTERVAL_SECONDS):
            with _LOCK:
                current = _read_status()
                if str(current.get("execution_id") or "") != execution_id:
                    return
                if str(current.get("state") or "").upper() not in {"QUEUED", "RUNNING"}:
                    return
                current["worker_heartbeat_at"] = _now()
                current["watchdog_alive"] = True
                _write_status(current)

    watchdog_thread = threading.Thread(
        target=watchdog,
        name=f"replay-watchdog-{execution_id}",
        daemon=True,
    )
    watchdog_thread.start()
    try:
        from report_replay_export import build_complete_replay_export, complete_export_filename

        def progress(done: int, total: int, message: str) -> None:
            text = str(message or "Bygger replay-arkiv")
            if text.startswith("Samler"):
                stage = "INNSAMLING"
            elif text.startswith("Pakker rapport"):
                stage = "RAPPORTER"
            elif text.startswith("Legger til runtime"):
                stage = "RUNTIME-DATA"
            elif text.startswith("Komprimerer"):
                stage = "KOMPRIMERING"
            elif text.startswith("Kontrollerer"):
                stage = "INTEGRITET"
            else:
                stage = "KLARGJØRING"
            current_file = text.split(":", 1)[1].strip() if ":" in text else ""
            with _LOCK:
                current = _read_status()
                if str(current.get("execution_id") or "") != execution_id:
                    return
                current.update({
                    "state": "RUNNING",
                    "stage": stage,
                    "completed": int(done),
                    "total": max(1, int(total)),
                    "percent": max(int(current.get("percent") or 0), max(0, min(99, int(int(done) / max(1, int(total)) * 100)))),
                    "message": text,
                    "current_file": current_file,
                    "worker_heartbeat_at": _now(),
                })
                _write_status(current)

        archive_bytes, summary = build_complete_replay_export(
            date_from=_parse_date(str(filters.get("date_from") or "") or None),
            date_to=_parse_date(str(filters.get("date_to") or "") or None, end=True),
            versions=[str(item) for item in (filters.get("versions") or [])],
            progress_callback=progress,
        )
        if not _valid_zip_bytes(archive_bytes):
            raise RuntimeError("Replay-eksporten produserte ikke en gyldig ZIP-fil")
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        filename = complete_export_filename()
        target = EXPORT_DIR / filename
        _atomic_write_bytes(target, archive_bytes)
        persisted = target.read_bytes()
        if persisted != archive_bytes or not _valid_zip_bytes(persisted):
            raise RuntimeError("Replay-ZIP kunne ikke verifiseres etter lagring")
        archive_sha256 = _sha256(persisted)
        with _LOCK:
            current = _read_status()
            if str(current.get("execution_id") or "") == execution_id:
                current.update({
                    "state": "COMPLETED",
                    "percent": 100,
                    "completed": int(current.get("total") or 1),
                    "message": "Komplett rapport- og læringsarkiv er klart",
                    "stage": "FULLFØRT",
                    "current_file": filename,
                    "completed_at": _now(),
                    "worker_heartbeat_at": _now(),
                    "file_path": str(target),
                    "filename": filename,
                    "file_size": len(persisted),
                    "file_sha256": archive_sha256,
                    "zip_verified": True,
                    "summary": summary,
                })
                _write_status(current)
    except Exception as exc:
        with _LOCK:
            current = _read_status()
            if str(current.get("execution_id") or "") == execution_id:
                current.update({
                    "state": "FAILED",
                    "message": "Replay-eksporten feilet",
                    "error": str(exc),
                    "completed_at": _now(),
                    "worker_heartbeat_at": _now(),
                })
                _write_status(current)
    finally:
        watchdog_stop.set()
        watchdog_thread.join(timeout=1.0)
        with _LOCK:
            _WORKERS.pop(execution_id, None)


def start_export(*, date_from: str = "", date_to: str = "", versions: Sequence[str] | None = None) -> dict[str, Any]:
    with _LOCK:
        current = _recover_stale_status(_read_status())
        if is_running(current):
            return current
        execution_id = "REPLAY-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6].upper()
        filters = {"date_from": str(date_from or ""), "date_to": str(date_to or ""), "versions": list(versions or [])}
        status = _write_status({
            "execution_id": execution_id,
            "state": "QUEUED",
            "percent": 0,
            "completed": 0,
            "total": 1,
            "message": "Replay-eksporten står i kø",
            "stage": "KØ",
            "current_file": "",
            "created_at": _now(),
            "worker_heartbeat_at": _now(),
            "filters": filters,
            "file_path": "",
            "filename": "",
            "summary": {},
        })
        worker = threading.Thread(target=_run_export, args=(execution_id, filters), name=f"replay-export-{execution_id}", daemon=False)
        _WORKERS[execution_id] = worker
        worker.start()
        return status


def read_export_bytes(status: Mapping[str, Any] | None = None) -> bytes | None:
    current = dict(status or get_status())
    path = Path(str(current.get("file_path") or ""))
    try:
        data = path.read_bytes() if path.is_file() else None
        if not data or not _valid_zip_bytes(data):
            return None
        expected = str(current.get("file_sha256") or "")
        if expected and _sha256(data) != expected:
            return None
        return data
    except Exception:
        return None
