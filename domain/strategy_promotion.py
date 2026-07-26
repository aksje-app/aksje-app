"""Controlled strategy promotion and rollback contracts for v19.12.0."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

STRATEGY_PROMOTION_SCHEMA_VERSION = "1.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_payload_checksum(value: Mapping[str, Any] | None) -> str:
    raw = json.dumps(dict(value or {}), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_promotion_id(family: str, target_version_id: str, created_at: str) -> str:
    raw = f"{family}|{target_version_id}|{created_at}"
    return f"PROMO-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


@dataclass(frozen=True)
class StrategyProductionBinding:
    binding_id: str
    strategy_family: str
    version_id: str
    previous_version_id: str = ""
    promotion_id: str = ""
    state: str = "ACTIVE"
    pending_version_id: str = ""
    updated_at: str = field(default_factory=utc_now_iso)
    updated_by: str = "system"
    reason: str = ""
    binding_revision: int = 1
    schema_version: str = STRATEGY_PROMOTION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyPromotion:
    promotion_id: str
    strategy_family: str
    previous_version_id: str
    target_version_id: str
    approval_id: str
    experiment_id: str
    lab_run_id: str
    status: str
    actor: str
    reason: str
    created_at: str = field(default_factory=utc_now_iso)
    activated_at: str = ""
    rolled_back_at: str = ""
    rollback_actor: str = ""
    rollback_reason: str = ""
    preflight: Mapping[str, Any] = field(default_factory=dict)
    previous_version_snapshot: Mapping[str, Any] = field(default_factory=dict)
    target_version_snapshot: Mapping[str, Any] = field(default_factory=dict)
    production_binding_before: Mapping[str, Any] = field(default_factory=dict)
    production_binding_after: Mapping[str, Any] = field(default_factory=dict)
    automatic_promotion: bool = False
    execution_authorized: bool = False
    schema_version: str = STRATEGY_PROMOTION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        for key in ("preflight", "previous_version_snapshot", "target_version_snapshot", "production_binding_before", "production_binding_after"):
            row[key] = dict(row.get(key) or {})
        row["record_checksum"] = stable_payload_checksum({k: v for k, v in row.items() if k != "record_checksum"})
        return row
