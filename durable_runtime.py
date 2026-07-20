"""Durable runtime helpers for v18.7.7.

PostgreSQL/StorageService is authoritative when configured. Local runtime files
remain as a backwards-compatible mirror for existing exports and diagnostics.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from services.storage_service import get_storage_service


def read_json(key: str, path: Path, default: Any) -> Any:
    storage = get_storage_service()
    stored = storage.read_json(key, default=None)
    if stored is not None:
        _write_local(path, stored)
        return stored
    try:
        local = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    storage.write_json(key, local)
    return local


def write_json(key: str, path: Path, value: Any) -> None:
    _write_local(path, value)
    get_storage_service().write_json(key, value)


def append_event(key: str, path: Path, row: Mapping[str, Any]) -> None:
    payload = dict(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    get_storage_service().append_jsonl(key, payload)


def read_events(key: str, path: Path, limit: int = 500) -> list[dict[str, Any]]:
    rows = list(get_storage_service().read_jsonl(key, limit=limit) or [])
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
        get_storage_service().append_jsonl(key, row)
    return local


def _write_local(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
