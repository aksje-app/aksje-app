"""Durable status snapshots for the global top bar.

RC16.31bp: regime and macro status must survive Streamlit reruns/reloads and
learning must reflect the controlled learning engine rather than an unrelated
forecast-learning counter.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

STATUS_PREFIX = "ui_status"


def _storage():
    try:
        from services.storage_service import get_storage_service
        return get_storage_service()
    except Exception:
        return None


def _key(name: str) -> str:
    return f"{STATUS_PREFIX}/{name}.json"


def save_status(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(payload or {})
    row.setdefault("updated_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    storage = _storage()
    if storage is not None:
        try:
            storage.write_json(_key(name), row)
        except Exception:
            pass
    return row


def load_status(name: str) -> dict[str, Any]:
    storage = _storage()
    if storage is not None:
        try:
            value = storage.read_json(_key(name), default=None)
            if isinstance(value, Mapping):
                return dict(value)
        except Exception:
            pass
    return {}


def compact_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Global topbar is compact; timestamp identity matters more than locale conversion.
        return dt.astimezone(timezone.utc).strftime("%d.%m %H:%MZ")
    except Exception:
        return text[:16]
