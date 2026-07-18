"""Compatibility adapter backed by the v18.6.91 Configuration Framework.

Older modules can keep using read_persistent_json/write_persistent_json while
all settings are stored in one canonical, versioned configuration document.
"""
from __future__ import annotations

from typing import Any


def read_persistent_json(key: str, default: Any = None) -> Any:
    try:
        from configuration_framework import read_legacy_key
        return read_legacy_key(key, default)
    except Exception:
        return default


def write_persistent_json(key: str, value: Any) -> bool:
    try:
        from configuration_framework import write_legacy_key
        return bool(write_legacy_key(key, value))
    except Exception:
        return False


def persistence_status() -> dict[str, Any]:
    try:
        from configuration_framework import status
        return status()
    except Exception as exc:
        return {
            "backend": "unavailable",
            "persistent": False,
            "ok": False,
            "message": str(exc),
        }
