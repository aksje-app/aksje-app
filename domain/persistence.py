"""Domain contracts for persistent application data (v19.2.0)."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

PERSISTENCE_SCHEMA_VERSION = "2.0"

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

@dataclass(frozen=True)
class PersistentRecord:
    record_id: str
    kind: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    schema_version: str = PERSISTENCE_SCHEMA_VERSION
    source: str = "application"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, record_id: str, kind: str, source: str = "application") -> "PersistentRecord":
        now = utc_now()
        return cls(
            record_id=str(record_id), kind=str(kind), payload=dict(value),
            created_at=str(value.get("created_at") or now),
            updated_at=str(value.get("updated_at") or now), source=source,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class MigrationResult:
    source_path: str
    target_repository: str
    rows_discovered: int
    rows_imported: int
    rows_skipped: int
    checksum: str
    dry_run: bool
    ok: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
