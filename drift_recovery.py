"""Operational readiness snapshot for v19.14.4 drift restoration."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from auth_persistence import auth_local_is_persistent, auth_storage_status
from runtime_safety import runtime_safety_snapshot
from storage_architecture import get_runtime_paths


def _path_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def runtime_disk_is_persistent() -> bool:
    explicit = os.getenv("APP_RUNTIME_PERSISTENT")
    if explicit is not None:
        return str(explicit).strip().lower() in {"1", "true", "yes", "on"}
    if not (os.getenv("RENDER") or os.getenv("RENDER_SERVICE_NAME")):
        return True
    mount = str(os.getenv("RENDER_DISK_MOUNT_PATH", "") or "").strip()
    return bool(mount and _path_within(get_runtime_paths().root, Path(mount).expanduser()))


def _application_storage_status() -> dict[str, Any]:
    try:
        from services.storage_service import get_storage_service
        return get_storage_service().status_dict()
    except Exception as exc:
        return {"backend": "unknown", "persistent": False, "ok": False, "message": str(exc)}


def drift_recovery_snapshot() -> dict[str, Any]:
    auth = auth_storage_status()
    safety = runtime_safety_snapshot()
    app_storage = _application_storage_status()
    disk_persistent = runtime_disk_is_persistent()
    paper_persistent = bool(app_storage.get("persistent") or disk_persistent)
    analysis_ready = bool(auth.get("ready") and auth.get("persistent") and not safety.get("blocking_violations"))
    paper_buy_test_ready = bool(analysis_ready and paper_persistent and safety.get("is_test_environment"))
    blockers: list[str] = []
    if not auth.get("persistent"):
        blockers.append("Bruker- og sesjonslager er ikke varig")
    if safety.get("blocking_violations"):
        blockers.extend(str(x) for x in safety.get("blocking_violations") or [])
    if not paper_persistent:
        blockers.append("Paper-porteføljen mangler varig testlagring")
    return {
        "analysis_reporting_ready": analysis_ready,
        "paper_buy_test_ready": paper_buy_test_ready,
        "auth": auth,
        "application_storage": app_storage,
        "runtime_disk_persistent": disk_persistent,
        "paper_storage_persistent": paper_persistent,
        "blockers": blockers,
        "normal_operation_label": "KLAR" if analysis_ready else "BLOKKERT",
        "paper_buy_label": "KLAR FOR KONTROLLERT TEST" if paper_buy_test_ready else "VENTER",
    }


__all__ = ["drift_recovery_snapshot", "runtime_disk_is_persistent"]
