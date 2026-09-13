"""Idempotent cleanup for explicitly retired temporary modules."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.storage_service import get_storage_service
from storage_architecture import runtime_data_path


_MARKER = "migrations/rc16_31cr_jeep_commander_removed.json"
_KEYS = (
    "temporary/jeep_commander_22/config.json",
    "temporary/jeep_commander_22/state.json",
)
_LOCAL_PATHS = (
    runtime_data_path("temporary", "jeep_commander_22", "config.json"),
    runtime_data_path("temporary", "jeep_commander_22", "state.json"),
)


def purge_retired_jeep_commander_once() -> dict[str, Any]:
    """Delete only the retired vehicle namespace and persist an audit marker."""
    storage = get_storage_service()
    previous = storage.read_json(_MARKER, None)
    if isinstance(previous, dict) and previous.get("state") == "COMPLETED":
        return {"state": "ALREADY_COMPLETED", "at": previous.get("at"), "deleted_keys": 2}

    deleted = []
    for key in _KEYS:
        storage.delete_json(key)
        deleted.append(key)
    for path in _LOCAL_PATHS:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    marker = {
        "state": "COMPLETED",
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "deleted_keys": deleted,
        "scope": "temporary/jeep_commander_22 only",
    }
    storage.write_json(_MARKER, marker)
    return marker
