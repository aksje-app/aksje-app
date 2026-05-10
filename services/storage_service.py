"""
services/storage_service.py

v18.5.15
Robust JSON storage adapter for Render.

Priority:
1. PostgreSQL via DATABASE_URL when available.
2. Local JSON/JSONL files as development fallback.

This keeps state-like app data (learning, watchlist, alerts, service outputs)
out of the repository/runtime code path while still working locally without DB.
"""

from __future__ import annotations

import json
import os
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


class StorageService:
    """Small key/value + jsonl storage with Postgres fallback for Render."""

    def __init__(self, base_dir: str = "data/services", database_url: Optional[str] = None):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.database_url = (database_url if database_url is not None else DATABASE_URL).strip()

    def using_postgres(self) -> bool:
        return bool(self.database_url) and psycopg2 is not None

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

    def read_json(self, name: str, default: Any = None) -> Any:
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
            except Exception:
                pass

        path = self.base_dir / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write_json(self, name: str, data: Any) -> bool:
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
                    (name, json.dumps(data, ensure_ascii=False)),
                )
                conn.commit()
                conn.close()
                return True
            except Exception:
                pass

        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return False

    def append_jsonl(self, name: str, row: Dict[str, Any]) -> bool:
        if self.using_postgres():
            try:
                self.init_db()
                conn = self._conn()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO app_jsonl_store (name, payload, created_at) VALUES (%s, %s, NOW()::TEXT)",
                    (name, json.dumps(row, ensure_ascii=False)),
                )
                conn.commit()
                conn.close()
                return True
            except Exception:
                pass

        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return False

    def read_jsonl(self, name: str, limit: int = 500) -> List[Dict[str, Any]]:
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
            except Exception:
                pass

        path = self.base_dir / name
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
        return rows


_default_storage = StorageService()


def get_storage_service(base_dir: str = "data/services") -> StorageService:
    if base_dir != "data/services":
        return StorageService(base_dir=base_dir)
    return _default_storage
