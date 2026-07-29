"""Durable authentication storage policy for AI Aksje Analyzer v19.14.4.

Authentication data is intentionally separated from portfolio/report storage.
A test service may therefore use ``AUTH_DATABASE_URL`` without gaining access
to the production ``DATABASE_URL``. Local authentication files are stored below
``APP_RUNTIME_ROOT/data/auth`` (or ``AUTH_STORAGE_ROOT``) and are only treated as
persistent on Render when the path is mounted on a persistent disk or the
operator explicitly confirms persistence.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from storage_architecture import get_runtime_paths

try:
    import psycopg2  # type: ignore
except Exception:  # pragma: no cover
    psycopg2 = None  # type: ignore

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_VALID_MODES = {"auto", "postgres", "local"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return bool(default)


def is_render_environment() -> bool:
    return bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_NAME") or os.getenv("RENDER_SERVICE_ID"))


def auth_database_url() -> str:
    return str(
        os.getenv("AUTH_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("RENDER_DATABASE_URL")
        or ""
    ).strip()


def auth_storage_mode() -> str:
    raw = str(os.getenv("AUTH_STORAGE_MODE", "auto") or "auto").strip().lower()
    return raw if raw in _VALID_MODES else "auto"


def auth_storage_root() -> Path:
    raw = str(os.getenv("AUTH_STORAGE_ROOT", "") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path
    else:
        path = get_runtime_paths().data / "auth"
    path.mkdir(parents=True, exist_ok=True)
    return path


def auth_json_path(name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "auth.json")).strip("._") or "auth.json"
    return auth_storage_root() / safe


def auth_using_postgres() -> bool:
    mode = auth_storage_mode()
    url = auth_database_url().lower()
    return mode != "local" and bool(url.startswith(("postgres://", "postgresql://"))) and psycopg2 is not None


def auth_persistence_required() -> bool:
    explicit = os.getenv("AUTH_REQUIRE_PERSISTENT")
    if explicit is not None:
        return _env_bool("AUTH_REQUIRE_PERSISTENT", True)
    return is_render_environment()


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def auth_local_is_persistent() -> bool:
    explicit = os.getenv("AUTH_STORAGE_PERSISTENT")
    if explicit is not None:
        return _env_bool("AUTH_STORAGE_PERSISTENT", False)
    if not is_render_environment():
        return True
    mount = str(os.getenv("RENDER_DISK_MOUNT_PATH", "") or "").strip()
    if mount:
        return _path_is_within(auth_storage_root(), Path(mount).expanduser())
    return False


def auth_environment_id() -> str:
    raw = str(
        os.getenv("AUTH_COOKIE_NAMESPACE")
        or os.getenv("APP_ENVIRONMENT")
        or os.getenv("RENDER_SERVICE_NAME")
        or os.getenv("RENDER_SERVICE_ID")
        or "local"
    ).strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")
    return value[:48] or "local"


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


@dataclass(frozen=True)
class AuthStorageStatus:
    backend: str
    persistent: bool
    required: bool
    ready: bool
    database_configured: bool
    local_path: str
    environment_id: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def auth_storage_status() -> dict[str, Any]:
    required = auth_persistence_required()
    database_configured = bool(auth_database_url())
    if auth_using_postgres():
        status = AuthStorageStatus(
            backend="postgres",
            persistent=True,
            required=required,
            ready=True,
            database_configured=True,
            local_path=str(auth_storage_root()),
            environment_id=auth_environment_id(),
            message="Autentisering bruker separat, varig PostgreSQL-lagring.",
        )
        return status.to_dict()

    mode = auth_storage_mode()
    local_allowed = mode in {"auto", "local"}
    local_persistent = auth_local_is_persistent() if local_allowed else False
    ready = local_allowed and (local_persistent or not required)
    if not local_allowed:
        message = "AUTH_STORAGE_MODE krever PostgreSQL, men AUTH_DATABASE_URL er ikke tilgjengelig."
    elif local_persistent:
        message = "Autentisering bruker varig lokal lagring på persistent disk."
    elif required:
        message = (
            "Autentiseringslageret er flyktig. Koble AUTH_DATABASE_URL til en separat database "
            "eller monter en Render-disk og sett AUTH_STORAGE_ROOT til diskbanen."
        )
    else:
        message = "Autentisering bruker lokal utviklingslagring."
    return AuthStorageStatus(
        backend="local" if local_allowed else "unavailable",
        persistent=local_persistent,
        required=required,
        ready=ready,
        database_configured=database_configured,
        local_path=str(auth_storage_root()),
        environment_id=auth_environment_id(),
        message=message,
    ).to_dict()


__all__ = [
    "atomic_write_json",
    "auth_database_url",
    "auth_environment_id",
    "auth_json_path",
    "auth_local_is_persistent",
    "auth_persistence_required",
    "auth_storage_mode",
    "auth_storage_root",
    "auth_storage_status",
    "auth_using_postgres",
    "is_render_environment",
    "read_json",
]
