"""Durable runtime helpers for v18.7.7.

PostgreSQL/StorageService is authoritative when configured. Local runtime files
remain as a backwards-compatible mirror for existing exports and diagnostics.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

from repositories.application import RepositoryRegistry
from services.storage_service import get_storage_service



def _repositories() -> RepositoryRegistry:
    # Construct from the current storage provider so legacy tests and controlled
    # dependency injection can replace get_storage_service safely.
    return RepositoryRegistry(get_storage_service())

_LOCAL_LOCKS: dict[str, threading.RLock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.RLock())


def read_json(key: str, path: Path, default: Any) -> Any:
    repository = _repositories().documents
    stored = repository.read(key, default=None)
    if stored is not None:
        # PostgreSQL is authoritative. A diagnostic mirror must never make a
        # successful database read fail or interrupt an analysis callback.
        try:
            _write_local(path, stored)
        except OSError:
            pass
        return stored
    try:
        local = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    repository.write(key, local)
    return local


def write_json(key: str, path: Path, value: Any) -> None:
    repository = _repositories().documents
    persisted = repository.write(key, value)
    try:
        _write_local(path, value)
    except OSError:
        if not persisted:
            raise


def append_event(key: str, path: Path, row: Mapping[str, Any]) -> None:
    payload = dict(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    _repositories().events.append(key, payload)


def read_events(key: str, path: Path, limit: int = 500) -> list[dict[str, Any]]:
    rows = list(_repositories().events.list(key, limit=limit) or [])
    if rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows), encoding="utf-8")
        return rows
    if not path.exists():
        return []
    local: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            value = json.loads(line)
            if isinstance(value, Mapping):
                local.append(dict(value))
        except Exception:
            continue
    for row in local:
        _repositories().events.append(key, row)
    return local


def _write_local(path: Path, value: Any) -> None:
    """Atomically update one mirror using a unique temp file and path lock."""
    path = Path(path)
    with _path_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        tmp = Path(raw_tmp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
