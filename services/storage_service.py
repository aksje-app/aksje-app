"""
services/storage_service.py

v18.5.29
Robust JSON storage adapter for Render.

Priority:
1. PostgreSQL via DATABASE_URL when available.
2. Local JSON/JSONL files as development fallback only.

Runtime state such as learning, watchlist, alerts, paper trading, score
explanations and Smart Universe selections should go through this service rather
than directly into the GitHub project tree.
"""

from __future__ import annotations
import logging
from utils import _now_iso  # v18.6.3 centralized helpers

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psycopg2  # type: ignore
except Exception:  # pragma: no cover - optional dependency at runtime
    psycopg2 = None  # type: ignore

try:
    from core_models import ServiceResult
except Exception:  # pragma: no cover
    ServiceResult = None  # type: ignore


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()




def _safe_name(name: str) -> str:
    """Keep keys portable for both Postgres rows and local fallback files."""
    clean = str(name or "").strip().replace("\\", "/").lstrip("/")
    parts = []
    for part in clean.split("/"):
        if not part or part in {".", ".."}:
            continue
        safe = "".join(ch for ch in part if ch.isalnum() or ch in ".-_ ")[:96]
        if safe:
            parts.append(safe)
    return "/".join(parts) or "default.json"


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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StorageService:
    """Small key/value + jsonl storage with Postgres-first behavior.

    Return values:
    - write_json/append_jsonl returns True when Postgres was used.
    - returns False when local fallback was used.
    """

    def __init__(self, base_dir: str = "data/services", database_url: Optional[str] = None):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.database_url = (database_url if database_url is not None else DATABASE_URL).strip()

    def using_postgres(self) -> bool:
        return bool(self.database_url) and psycopg2 is not None

    def backend(self) -> str:
        return "postgres" if self.using_postgres() else "local_json_fallback"

    def is_persistent(self) -> bool:
        return self.using_postgres()

    def _conn(self):
        if not self.using_postgres():
            raise RuntimeError("Postgres storage is not configured")
        return psycopg2.connect(self.database_url)  # type: ignore[union-attr]

    def init_db(self) -> bool:
        if not self.using_postgres():
            return False
        conn = self._conn()
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
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT NOW()::TEXT
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_app_jsonl_store_name_id ON app_jsonl_store(name, id DESC);")
        conn.commit()
        conn.close()
        return True

    def health(self) -> StorageHealth:
        if not self.using_postgres():
            return StorageHealth(
                backend="local_json_fallback",
                persistent=False,
                database_url_configured=bool(self.database_url),
                psycopg2_available=psycopg2 is not None,
                local_base_dir=str(self.base_dir),
                ok=True,
                message="Lokal JSON fallback aktiv. OK for dev/test, men Render bør bruke DATABASE_URL/Postgres.",
                checked_at=_now_iso(),
            )
        try:
            self.init_db()
            conn = self._conn()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            conn.close()
            return StorageHealth(
                backend="postgres",
                persistent=True,
                database_url_configured=True,
                psycopg2_available=True,
                local_base_dir=str(self.base_dir),
                ok=True,
                message="Postgres/StorageService aktiv.",
                checked_at=_now_iso(),
            )
        except Exception as exc:  # pragma: no cover - depends on external DB
            return StorageHealth(
                backend="local_json_fallback",
                persistent=False,
                database_url_configured=bool(self.database_url),
                psycopg2_available=psycopg2 is not None,
                local_base_dir=str(self.base_dir),
                ok=False,
                message=f"Postgres feilet, lokal fallback brukes ved behov: {exc}",
                checked_at=_now_iso(),
            )

    def status_dict(self) -> Dict[str, Any]:
        return self.health().to_dict()

    def read_json(self, name: str, default: Any = None) -> Any:
        name = _safe_name(name)
        if self.using_postgres():
            try:
                self.init_db()
                conn = self._conn()
                cur = conn.cursor()
                cur.execute("SELECT payload FROM app_kv_store WHERE name=%s", (name,))
                row = cur.fetchone()
                conn.close()
                if not row:
                    return default
                return json.loads(row[0])
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)

        path = self.base_dir / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write_json(self, name: str, data: Any) -> bool:
        name = _safe_name(name)
        if self.using_postgres():
            try:
                self.init_db()
                conn = self._conn()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO app_kv_store (name, payload, updated_at)
                    VALUES (%s, %s, NOW()::TEXT)
                    ON CONFLICT (name) DO UPDATE SET
                        payload=EXCLUDED.payload,
                        updated_at=EXCLUDED.updated_at
                    """,
                    (name, json.dumps(data, ensure_ascii=False, default=str)),
                )
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)

        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return False

    def append_jsonl(self, name: str, row: Dict[str, Any]) -> bool:
        name = _safe_name(name)
        if self.using_postgres():
            try:
                self.init_db()
                conn = self._conn()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO app_jsonl_store (name, payload, created_at) VALUES (%s, %s, NOW()::TEXT)",
                    (name, json.dumps(row, ensure_ascii=False, default=str)),
                )
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)

        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return False

    def read_jsonl(self, name: str, limit: int = 500) -> List[Dict[str, Any]]:
        name = _safe_name(name)
        if self.using_postgres():
            try:
                self.init_db()
                conn = self._conn()
                cur = conn.cursor()
                cur.execute(
                    "SELECT payload FROM app_jsonl_store WHERE name=%s ORDER BY id DESC LIMIT %s",
                    (name, int(limit)),
                )
                rows = [json.loads(r[0]) for r in cur.fetchall()]
                conn.close()
                return list(reversed(rows))
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)

        path = self.base_dir / name
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                decoded = json.loads(line)
                if isinstance(decoded, dict):
                    rows.append(decoded)
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)
        return rows


_default_storage = StorageService()


def get_storage_service(base_dir: str = "data/services") -> StorageService:
    if base_dir != "data/services":
        return StorageService(base_dir=base_dir)
    return _default_storage


def get_storage_status() -> Dict[str, Any]:
    return get_storage_service().status_dict()


def storage_status_label() -> str:
    health = get_storage_service().health()
    if health.persistent and health.ok:
        return "Storage: Postgres aktiv ✅"
    if health.ok:
        return "Storage: lokal fallback ⚠️"
    return "Storage: Postgres-feil, fallback ⚠️"
