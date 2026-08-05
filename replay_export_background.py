"""Background controller for RC16 complete replay exports.

Worker threads never import or call Streamlit.  Status is persisted as JSON and
read by a small UI fragment, so the page remains usable during large exports.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_status() -> dict[str, Any]:
    value = durable_read_json(STATUS_KEY, STATUS_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _write_status(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload["updated_at"] = _now()
    durable_write_json(STATUS_KEY, STATUS_PATH, payload)
    return payload


def get_status() -> dict[str, Any]:
    return _read_status()


def is_running(status: Mapping[str, Any] | None = None) -> bool:
    return str((status or get_status()).get("state") or "").upper() in {"QUEUED", "RUNNING"}


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
    try:
        from report_replay_export import build_complete_replay_export, complete_export_filename

        def progress(done: int, total: int, message: str) -> None:
            with _LOCK:
                current = _read_status()
                if str(current.get("execution_id") or "") != execution_id:
                    return
                current.update({
                    "state": "RUNNING",
                    "completed": int(done),
                    "total": max(1, int(total)),
                    "percent": max(0, min(99, int(int(done) / max(1, int(total)) * 100))),
                    "message": str(message),
                    "worker_heartbeat_at": _now(),
                })
                _write_status(current)

        archive_bytes, summary = build_complete_replay_export(
            date_from=_parse_date(str(filters.get("date_from") or "") or None),
            date_to=_parse_date(str(filters.get("date_to") or "") or None, end=True),
            versions=[str(item) for item in (filters.get("versions") or [])],
            progress_callback=progress,
        )
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        filename = complete_export_filename()
        target = EXPORT_DIR / filename
        target.write_bytes(archive_bytes)
        with _LOCK:
            current = _read_status()
            if str(current.get("execution_id") or "") == execution_id:
                current.update({
                    "state": "COMPLETED",
                    "percent": 100,
                    "completed": int(current.get("total") or 1),
                    "message": "Komplett rapport- og læringsarkiv er klart",
                    "completed_at": _now(),
                    "worker_heartbeat_at": _now(),
                    "file_path": str(target),
                    "filename": filename,
                    "file_size": len(archive_bytes),
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
        with _LOCK:
            _WORKERS.pop(execution_id, None)


def start_export(*, date_from: str = "", date_to: str = "", versions: Sequence[str] | None = None) -> dict[str, Any]:
    with _LOCK:
        current = _read_status()
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
            "created_at": _now(),
            "worker_heartbeat_at": _now(),
            "filters": filters,
            "file_path": "",
            "filename": "",
            "summary": {},
        })
        worker = threading.Thread(target=_run_export, args=(execution_id, filters), name=f"replay-export-{execution_id}", daemon=True)
        _WORKERS[execution_id] = worker
        worker.start()
        return status


def read_export_bytes(status: Mapping[str, Any] | None = None) -> bytes | None:
    path = Path(str((status or get_status()).get("file_path") or ""))
    try:
        return path.read_bytes() if path.is_file() else None
    except Exception:
        return None
