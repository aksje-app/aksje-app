"""Central persistence adapter for AI Aksje Analyzer.

v19.2.0 contract
----------------
* PostgreSQL is the authoritative production backend.
* Local JSON/JSONL is an explicit development, test or emergency fallback.
* A failed database write may never silently create a second production truth
  when local fallback is disabled.
* Local document replacement is atomic and event streams are path-locked.

The public read_json/write_json/append_jsonl/read_jsonl API remains compatible
with earlier releases while repositories provide the preferred application API.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from storage_architecture import get_runtime_paths
from utils import _now_iso

try:
    import psycopg2  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psycopg2 = None  # type: ignore

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
STORAGE_SCHEMA_VERSION = "2.0"
_VALID_MODES = {"auto", "postgres", "local"}
_LOCAL_LOCKS: dict[str, threading.RLock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _safe_name(name: str) -> str:
    """Keep keys portable for Postgres rows and local fallback files."""
    clean = str(name or "").strip().replace("\\", "/").lstrip("/")
    parts: list[str] = []
    for part in clean.split("/"):
        if not part or part in {".", ".."}:
            continue
        safe = "".join(ch for ch in part if ch.isalnum() or ch in ".-_ ")[:128]
        if safe:
            parts.append(safe)
    return "/".join(parts) or "default.json"


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.RLock())


class StorageUnavailableError(RuntimeError):
    """Raised when persistent storage is required but unavailable."""


@dataclass(frozen=True)
class StorageHealth:
    backend: str
    persistent: bool
    database_url_configured: bool
    psycopg2_available: bool
    local_base_dir: str
    ok: bool
    message: str
    checked_at: str
    mode: str = "auto"
    local_fallback_allowed: bool = True
    schema_version: str = STORAGE_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StorageService:
    """Document and event storage with explicit Postgres-first policy.

    Return values preserve the legacy contract:
    * write_json/append_jsonl/replace_jsonl return True when Postgres was used.
    * return False when an explicitly allowed local fallback was used.
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        database_url: Optional[str] = None,
        *,
        mode: str | None = None,
        allow_local_fallback: bool | None = None,
    ):
        self.base_dir = Path(base_dir) if base_dir is not None else get_runtime_paths().services
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.database_url = (database_url if database_url is not None else DATABASE_URL).strip()
        selected_mode = str(mode or os.getenv("STORAGE_MODE", "auto")).strip().lower()
        self.mode = selected_mode if selected_mode in _VALID_MODES else "auto"
        default_fallback = self.mode != "postgres"
        self.allow_local_fallback = (
            _env_bool("ALLOW_LOCAL_STORAGE_FALLBACK", default_fallback)
            if allow_local_fallback is None else bool(allow_local_fallback)
        )
        self._db_initialized = False

    def using_postgres(self) -> bool:
        return self.mode != "local" and bool(self.database_url) and psycopg2 is not None

    def backend(self) -> str:
        if self.using_postgres():
            return "postgres"
        return "local_json_fallback" if self.allow_local_fallback or self.mode == "local" else "unavailable"

    def is_persistent(self) -> bool:
        return self.using_postgres()

    def _local_allowed(self) -> bool:
        return self.mode == "local" or self.allow_local_fallback

    def _require_local_allowed(self, operation: str) -> None:
        if not self._local_allowed():
            raise StorageUnavailableError(
                f"{operation}: PostgreSQL er ikke tilgjengelig og lokal fallback er deaktivert. "
                "Sett DATABASE_URL eller bruk STORAGE_MODE=local kun for utvikling/test."
            )

    def _conn(self):
        if not self.using_postgres():
            raise StorageUnavailableError("Postgres storage er ikke konfigurert eller psycopg2 mangler")
        timeout = max(2, min(30, int(os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "8") or 8)))
        return psycopg2.connect(self.database_url, connect_timeout=timeout)  # type: ignore[union-attr]

    def write_json_immutable(self, name: str, data: Any, *, attempts: int = 3) -> Any:
        """Atomically create one immutable document or return its stored value.

        This removes the vulnerable read-then-write gap used by canonical
        report results. PostgreSQL is retried only for transient availability;
        a caller still validates content identity and fails on a real conflict.
        """
        name = _safe_name(name)
        payload = json.dumps(data, ensure_ascii=False, default=str)
        attempts = max(1, min(5, int(attempts or 1)))
        if self.using_postgres():
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    self.init_db(); conn = self._conn()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            """INSERT INTO app_kv_store (name, payload, updated_at)
                               VALUES (%s, %s, NOW()::TEXT)
                               ON CONFLICT (name) DO NOTHING""",
                            (name, payload),
                        )
                        cur.execute("SELECT payload FROM app_kv_store WHERE name=%s FOR SHARE", (name,))
                        row = cur.fetchone()
                        if not row:
                            raise StorageUnavailableError(f"immutable_json({name}) mangler etter transaksjon")
                        conn.commit()
                        return json.loads(row[0])
                    except Exception:
                        conn.rollback()
                        raise
                    finally:
                        conn.close()
                except Exception as exc:
                    last_error = exc
                    logging.warning("Postgres immutable_json forsøk %s/%s feilet for %s: %s", attempt, attempts, name, exc)
                    if attempt < attempts:
                        time.sleep(0.25 * (2 ** (attempt - 1)))
            if not self._local_allowed():
                raise StorageUnavailableError(f"immutable_json({name}) feilet etter {attempts} forsøk") from last_error
        self._require_local_allowed("immutable_json")
        path = self.base_dir / name
        with _path_lock(path):
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
            self._atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2, default=str))
            return data

    def init_db(self) -> bool:
        if not self.using_postgres():
            return False
        if self._db_initialized:
            return True
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_kv_store (
                    name TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT NOW()::TEXT
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_jsonl_store (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT NOW()::TEXT
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_app_jsonl_store_name_id ON app_jsonl_store(name, id DESC);")
            conn.commit()
            self._db_initialized = True
            return True
        finally:
            conn.close()

    def health(self) -> StorageHealth:
        configured = bool(self.database_url)
        if self.mode == "local":
            return StorageHealth(
                backend="local_json_fallback", persistent=False,
                database_url_configured=configured, psycopg2_available=psycopg2 is not None,
                local_base_dir=str(self.base_dir), ok=True,
                message="Lokal lagringsmodus er eksplisitt aktivert for utvikling/test.",
                checked_at=_now_iso(), mode=self.mode,
                local_fallback_allowed=True,
            )
        if not self.using_postgres():
            allowed = self._local_allowed()
            reason = "DATABASE_URL mangler" if not configured else "psycopg2 mangler"
            return StorageHealth(
                backend="local_json_fallback" if allowed else "unavailable",
                persistent=False, database_url_configured=configured,
                psycopg2_available=psycopg2 is not None,
                local_base_dir=str(self.base_dir), ok=allowed,
                message=(
                    f"{reason}; lokal fallback er aktiv. Kun egnet for utvikling/test."
                    if allowed else
                    f"{reason}; permanent lagring er påkrevd og lokal fallback er deaktivert."
                ),
                checked_at=_now_iso(), mode=self.mode,
                local_fallback_allowed=allowed,
            )
        try:
            self.init_db()
            conn = self._conn()
            try:
                cur = conn.cursor(); cur.execute("SELECT 1"); cur.fetchone()
            finally:
                conn.close()
            return StorageHealth(
                backend="postgres", persistent=True, database_url_configured=True,
                psycopg2_available=True, local_base_dir=str(self.base_dir), ok=True,
                message="PostgreSQL er aktiv som autoritativ permanent lagring.",
                checked_at=_now_iso(), mode=self.mode,
                local_fallback_allowed=self._local_allowed(),
            )
        except Exception as exc:  # pragma: no cover - external DB
            allowed = self._local_allowed()
            return StorageHealth(
                backend="local_json_fallback" if allowed else "unavailable",
                persistent=False, database_url_configured=True,
                psycopg2_available=psycopg2 is not None,
                local_base_dir=str(self.base_dir), ok=allowed,
                message=(
                    f"PostgreSQL feilet; lokal fallback er tillatt: {exc}"
                    if allowed else f"PostgreSQL feilet og fallback er deaktivert: {exc}"
                ),
                checked_at=_now_iso(), mode=self.mode,
                local_fallback_allowed=allowed,
            )

    def status_dict(self) -> Dict[str, Any]:
        return self.health().to_dict()

    def _atomic_write_text(self, path: Path, content: str) -> None:
        with _path_lock(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
            temp = Path(raw)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(content); handle.flush(); os.fsync(handle.fileno())
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)

    def read_json(self, name: str, default: Any = None) -> Any:
        name = _safe_name(name)
        if self.using_postgres():
            try:
                self.init_db(); conn = self._conn()
                try:
                    cur = conn.cursor(); cur.execute("SELECT payload FROM app_kv_store WHERE name=%s", (name,)); row = cur.fetchone()
                finally:
                    conn.close()
                return default if not row else json.loads(row[0])
            except Exception as exc:
                logging.warning("Postgres read_json feilet for %s: %s", name, exc)
                if not self._local_allowed():
                    raise StorageUnavailableError(f"read_json({name}) feilet") from exc
        self._require_local_allowed("read_json")
        path = self.base_dir / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logging.warning("Ugyldig lokal JSON %s: %s", path, exc)
            return default

    def read_json_array_slice(self, name: str, limit: int = 500) -> list[dict[str, Any]]:
        """Read a bounded prefix of a legacy JSON array without transferring the whole payload."""
        name = _safe_name(name); limit = max(0, min(int(limit), 5000))
        if limit <= 0: return []
        if self.using_postgres():
            try:
                self.init_db(); conn = self._conn()
                try:
                    cur = conn.cursor()
                    cur.execute("""SELECT elem::text FROM app_kv_store,
                                      LATERAL jsonb_array_elements(payload::jsonb) WITH ORDINALITY AS x(elem, ord)
                                      WHERE name=%s ORDER BY ord LIMIT %s""", (name, limit))
                    rows = cur.fetchall()
                finally:
                    conn.close()
                out=[]
                for row in rows:
                    val=json.loads(row[0])
                    if isinstance(val, dict): out.append(val)
                return out
            except Exception as exc:
                logging.warning("Postgres bounded JSON read feilet for %s: %s", name, exc)
                if not self._local_allowed(): raise StorageUnavailableError(f"read_json_array_slice({name}) feilet") from exc
        self._require_local_allowed("read_json_array_slice")
        value=self.read_json(name, [])
        return [dict(x) for x in value[:limit] if isinstance(x, dict)] if isinstance(value, list) else []

    def read_json_array_item(self, name: str, id_field: str, record_id: Any, default: Any = None) -> Any:
        """Find one row in a legacy JSON array server-side to avoid multi-hundred-MB Python allocations."""
        name = _safe_name(name); wanted=str(record_id)
        if self.using_postgres():
            try:
                self.init_db(); conn=self._conn()
                try:
                    cur=conn.cursor()
                    cur.execute("""SELECT elem::text FROM app_kv_store,
                                      LATERAL jsonb_array_elements(payload::jsonb) AS x(elem)
                                      WHERE name=%s AND elem ->> %s = %s LIMIT 1""", (name, str(id_field), wanted))
                    row=cur.fetchone()
                finally:
                    conn.close()
                return default if not row else json.loads(row[0])
            except Exception as exc:
                logging.warning("Postgres bounded JSON item read feilet for %s: %s", name, exc)
                if not self._local_allowed(): raise StorageUnavailableError(f"read_json_array_item({name}) feilet") from exc
        self._require_local_allowed("read_json_array_item")
        value=self.read_json(name, [])
        if isinstance(value, list):
            return next((dict(x) for x in value if isinstance(x, dict) and str(x.get(id_field) or "") == wanted), default)
        return default

    def write_json(self, name: str, data: Any) -> bool:
        name = _safe_name(name)
        payload = json.dumps(data, ensure_ascii=False, default=str)
        if self.using_postgres():
            try:
                self.init_db(); conn = self._conn()
                try:
                    cur = conn.cursor()
                    cur.execute(
                        """INSERT INTO app_kv_store (name, payload, updated_at)
                           VALUES (%s, %s, NOW()::TEXT)
                           ON CONFLICT (name) DO UPDATE SET payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at""",
                        (name, payload),
                    )
                    conn.commit()
                finally:
                    conn.close()
                return True
            except Exception as exc:
                logging.warning("Postgres write_json feilet for %s: %s", name, exc)
                if not self._local_allowed():
                    raise StorageUnavailableError(f"write_json({name}) feilet") from exc
        self._require_local_allowed("write_json")
        self._atomic_write_text(self.base_dir / name, json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return False

    def delete_json(self, name: str) -> bool:
        name = _safe_name(name)
        used_postgres = False
        if self.using_postgres():
            self.init_db(); conn = self._conn()
            try:
                cur = conn.cursor(); cur.execute("DELETE FROM app_kv_store WHERE name=%s", (name,)); conn.commit(); used_postgres = True
            finally:
                conn.close()
        path = self.base_dir / name
        if path.exists() and self._local_allowed():
            path.unlink()
        elif not used_postgres:
            self._require_local_allowed("delete_json")
        return used_postgres

    def append_jsonl(self, name: str, row: Dict[str, Any]) -> bool:
        name = _safe_name(name)
        payload = json.dumps(dict(row), ensure_ascii=False, default=str)
        if self.using_postgres():
            try:
                self.init_db(); conn = self._conn()
                try:
                    cur = conn.cursor(); cur.execute(
                        "INSERT INTO app_jsonl_store (name, payload, created_at) VALUES (%s, %s, NOW()::TEXT)",
                        (name, payload),
                    ); conn.commit()
                finally:
                    conn.close()
                return True
            except Exception as exc:
                logging.warning("Postgres append_jsonl feilet for %s: %s", name, exc)
                if not self._local_allowed():
                    raise StorageUnavailableError(f"append_jsonl({name}) feilet") from exc
        self._require_local_allowed("append_jsonl")
        path = self.base_dir / name
        with _path_lock(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
        return False

    def read_jsonl(self, name: str, limit: int = 500) -> List[Dict[str, Any]]:
        name = _safe_name(name); limit = max(0, int(limit))
        if self.using_postgres():
            try:
                self.init_db(); conn = self._conn()
                try:
                    cur = conn.cursor(); cur.execute(
                        "SELECT payload FROM app_jsonl_store WHERE name=%s ORDER BY id DESC LIMIT %s", (name, limit)
                    ); raw = cur.fetchall()
                finally:
                    conn.close()
                rows = [json.loads(item[0]) for item in raw]
                return [dict(x) for x in reversed(rows) if isinstance(x, dict)]
            except Exception as exc:
                logging.warning("Postgres read_jsonl feilet for %s: %s", name, exc)
                if not self._local_allowed():
                    raise StorageUnavailableError(f"read_jsonl({name}) feilet") from exc
        self._require_local_allowed("read_jsonl")
        path = self.base_dir / name
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit if limit else None:]:
            try:
                decoded = json.loads(line)
                if isinstance(decoded, dict): out.append(dict(decoded))
            except Exception as exc:
                logging.warning("Ugyldig JSONL-rad i %s: %s", path, exc)
        return out

    def replace_jsonl(self, name: str, rows: Iterable[Dict[str, Any]]) -> bool:
        name = _safe_name(name); materialized = [dict(row) for row in rows]
        if self.using_postgres():
            try:
                self.init_db(); conn = self._conn()
                try:
                    cur = conn.cursor(); cur.execute("DELETE FROM app_jsonl_store WHERE name=%s", (name,))
                    for row in materialized:
                        cur.execute(
                            "INSERT INTO app_jsonl_store (name, payload, created_at) VALUES (%s, %s, NOW()::TEXT)",
                            (name, json.dumps(row, ensure_ascii=False, default=str)),
                        )
                    conn.commit()
                finally:
                    conn.close()
                return True
            except Exception as exc:
                logging.warning("Postgres replace_jsonl feilet for %s: %s", name, exc)
                if not self._local_allowed():
                    raise StorageUnavailableError(f"replace_jsonl({name}) feilet") from exc
        self._require_local_allowed("replace_jsonl")
        content = "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in materialized)
        self._atomic_write_text(self.base_dir / name, content)
        return False

    def list_json_names(self) -> list[str]:
        names: set[str] = set()
        if self.using_postgres():
            self.init_db(); conn = self._conn()
            try:
                cur = conn.cursor(); cur.execute("SELECT name FROM app_kv_store ORDER BY name"); names.update(str(x[0]) for x in cur.fetchall())
            finally:
                conn.close()
        if self._local_allowed() and self.base_dir.exists():
            names.update(
                p.relative_to(self.base_dir).as_posix() for p in self.base_dir.rglob("*")
                if p.is_file() and p.suffix.lower() == ".json"
            )
        return sorted(names)

    def list_jsonl_names(self) -> list[str]:
        names: set[str] = set()
        if self.using_postgres():
            self.init_db(); conn = self._conn()
            try:
                cur = conn.cursor(); cur.execute("SELECT DISTINCT name FROM app_jsonl_store ORDER BY name"); names.update(str(x[0]) for x in cur.fetchall())
            finally:
                conn.close()
        if self._local_allowed() and self.base_dir.exists():
            names.update(
                p.relative_to(self.base_dir).as_posix() for p in self.base_dir.rglob("*.jsonl") if p.is_file()
            )
        return sorted(names)

    def storage_usage_report(self) -> Dict[str, Any]:
        """Small, read-only capacity report without loading stored payloads."""
        if self.using_postgres():
            self.init_db(); conn = self._conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    """SELECT COUNT(*), COALESCE(SUM(octet_length(payload)), 0),
                              pg_total_relation_size('app_kv_store')
                       FROM app_kv_store"""
                )
                kv_count, kv_payload, kv_relation = cur.fetchone()
                cur.execute(
                    """SELECT COUNT(*), COALESCE(SUM(octet_length(payload)), 0),
                              pg_total_relation_size('app_jsonl_store')
                       FROM app_jsonl_store"""
                )
                event_count, event_payload, event_relation = cur.fetchone()
                cur.execute("SELECT pg_database_size(current_database())")
                database_bytes = int(cur.fetchone()[0] or 0)
                cur.execute(
                    """SELECT split_part(name, '/', 1) AS namespace,
                              COUNT(*), COALESCE(SUM(octet_length(payload)), 0)
                       FROM app_kv_store GROUP BY 1 ORDER BY 3 DESC LIMIT 20"""
                )
                namespaces = [
                    {"namespace": str(row[0] or "root"), "rows": int(row[1] or 0),
                     "payload_bytes": int(row[2] or 0)} for row in cur.fetchall()
                ]
                cur.execute(
                    """SELECT name, octet_length(payload) FROM app_kv_store
                       ORDER BY octet_length(payload) DESC LIMIT 20"""
                )
                largest = [{"name": str(row[0]), "payload_bytes": int(row[1] or 0)} for row in cur.fetchall()]
                capacity_bytes = max(1, int(os.getenv("DATABASE_CAPACITY_BYTES", str(5 * 1024**3)) or 5 * 1024**3))
                capacity_pct = round(database_bytes * 100.0 / capacity_bytes, 2)
                return {
                    "backend": "postgres", "database_bytes": database_bytes,
                    "capacity_bytes": capacity_bytes, "capacity_pct": capacity_pct,
                    "capacity_state": "CRITICAL" if capacity_pct >= 85 else "WARNING" if capacity_pct >= 70 else "OK",
                    "kv_rows": int(kv_count or 0), "kv_payload_bytes": int(kv_payload or 0),
                    "kv_relation_bytes": int(kv_relation or 0),
                    "event_rows": int(event_count or 0), "event_payload_bytes": int(event_payload or 0),
                    "event_relation_bytes": int(event_relation or 0),
                    "kv_namespaces": namespaces, "largest_kv_documents": largest,
                }
            finally:
                conn.close()
        self._require_local_allowed("storage_usage_report")
        files = [path for path in self.base_dir.rglob("*") if path.is_file()]
        return {
            "backend": "local_json_fallback",
            "database_bytes": sum(path.stat().st_size for path in files),
            "file_count": len(files),
        }


_default_storage = StorageService()


def get_storage_service(base_dir: str | Path | None = None) -> StorageService:
    if base_dir is not None:
        return StorageService(base_dir=base_dir)
    return _default_storage


def get_storage_status() -> Dict[str, Any]:
    return get_storage_service().status_dict()


def storage_status_label() -> str:
    health = get_storage_service().health()
    if health.persistent and health.ok:
        return "Storage: PostgreSQL aktiv ✅"
    if health.ok:
        return "Storage: lokal utviklingsfallback ⚠️"
    return "Storage: permanent lagring utilgjengelig ❌"
