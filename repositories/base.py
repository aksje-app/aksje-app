"""Repository abstractions backed by the central StorageService.

Repositories are the only preferred application-facing persistence API in
v19.2.0. Exact legacy keys remain supported so migration can be gradual and
non-destructive.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from services.storage_service import StorageService, get_storage_service


class DocumentRepository:
    """Store arbitrary JSON documents under exact, namespaced keys."""

    def __init__(self, namespace: str = "", *, storage: StorageService | None = None):
        self.namespace = str(namespace or "").strip("/")
        self.storage = storage or get_storage_service()

    def key_for(self, name: str) -> str:
        clean = str(name or "document.json").strip("/")
        return f"{self.namespace}/{clean}" if self.namespace else clean

    def read(self, name: str, default: Any = None) -> Any:
        return self.storage.read_json(self.key_for(name), default)

    def write(self, name: str, value: Any) -> bool:
        return self.storage.write_json(self.key_for(name), value)

    def delete(self, name: str) -> bool:
        return self.storage.delete_json(self.key_for(name))

    # Compatibility aliases for modules migrated from direct StorageService use.
    def read_json(self, name: str, default: Any = None) -> Any:
        return self.read(name, default)

    def write_json(self, name: str, value: Any) -> bool:
        return self.write(name, value)

    def exists(self, name: str) -> bool:
        marker = object()
        return self.read(name, marker) is not marker


class JsonRepository:
    """Collection repository for records identified by one stable field."""

    def __init__(self, name: str, *, storage: StorageService | None = None, id_field: str = "id", key: str | None = None):
        self.name = str(name).strip("/")
        self.storage = storage or get_storage_service()
        self.id_field = id_field
        self._key = str(key or f"repositories/{self.name}.json").strip("/")

    @property
    def key(self) -> str:
        return self._key

    def list(self) -> list[dict[str, Any]]:
        value = self.storage.read_json(self.key, [])
        return [dict(x) for x in value] if isinstance(value, list) else []

    def replace_all(self, rows: Iterable[Mapping[str, Any]]) -> bool:
        return self.storage.write_json(self.key, [dict(x) for x in rows])

    def get(self, record_id: Any) -> dict[str, Any] | None:
        wanted = str(record_id)
        return next((row for row in self.list() if str(row.get(self.id_field) or "") == wanted), None)

    def upsert(self, row: Mapping[str, Any]) -> bool:
        value = dict(row)
        record_id = str(value.get(self.id_field) or "")
        if not record_id:
            raise ValueError(f"Missing repository id field: {self.id_field}")
        rows = [x for x in self.list() if str(x.get(self.id_field) or "") != record_id]
        rows.insert(0, value)
        return self.replace_all(rows)

    def delete(self, record_id: Any) -> bool:
        wanted = str(record_id)
        return self.replace_all(x for x in self.list() if str(x.get(self.id_field) or "") != wanted)


class EventRepository:
    """Append-only event stream repository."""

    def __init__(self, name: str, *, storage: StorageService | None = None, key: str | None = None):
        self.name = str(name).strip("/")
        self.storage = storage or get_storage_service()
        self._key = str(key or f"repositories/{self.name}.jsonl").strip("/")

    @property
    def key(self) -> str:
        return self._key

    def append(self, row: Mapping[str, Any]) -> bool:
        return self.storage.append_jsonl(self.key, dict(row))

    def list(self, limit: int = 500) -> list[dict[str, Any]]:
        return self.storage.read_jsonl(self.key, limit=limit)

    def replace_all(self, rows: Iterable[Mapping[str, Any]]) -> bool:
        return self.storage.replace_jsonl(self.key, [dict(row) for row in rows])


class LegacyDocumentRepository(DocumentRepository):
    """Exact-key repository used while legacy modules are migrated safely."""


class LegacyEventRepository:
    """Exact-key event streams used by durable_runtime and telemetry."""

    def __init__(self, *, storage: StorageService | None = None):
        self.storage = storage or get_storage_service()

    def append(self, key: str, row: Mapping[str, Any]) -> bool:
        return self.storage.append_jsonl(str(key).strip("/"), dict(row))

    def list(self, key: str, limit: int = 500) -> list[dict[str, Any]]:
        return self.storage.read_jsonl(str(key).strip("/"), limit=limit)

    def replace_all(self, key: str, rows: Iterable[Mapping[str, Any]]) -> bool:
        return self.storage.replace_jsonl(str(key).strip("/"), [dict(row) for row in rows])
