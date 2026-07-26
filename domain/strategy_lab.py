"""Persistent Strategy Lab contracts for v19.10.0.

The lab is deliberately read-only with respect to production bindings and
portfolio execution. It stores hypotheses, replay configuration, comparable
results and review/rollback history.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Sequence

STRATEGY_LAB_SCHEMA_VERSION = "1.0"
STRATEGY_LAB_RUN_SCHEMA_VERSION = "1.0"
STRATEGY_LAB_APPROVAL_SCHEMA_VERSION = "1.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe(item) for item in value]
    return str(value)


def stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    raw = json.dumps(_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


class StrategyLabStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class StrategyLabMode(str, Enum):
    SNAPSHOT_REPLAY = "SNAPSHOT_REPLAY"
    WALK_FORWARD = "WALK_FORWARD"


@dataclass(frozen=True)
class StrategyLabExperiment:
    experiment_id: str
    name: str
    hypothesis: str
    baseline_version_id: str
    challenger_version_ids: Sequence[str]
    snapshot_ids: Sequence[str] = field(default_factory=tuple)
    mode: str = StrategyLabMode.WALK_FORWARD.value
    train_ratio: float = 0.70
    status: str = StrategyLabStatus.DRAFT.value
    created_by: str = "system"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = STRATEGY_LAB_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["challenger_version_ids"] = list(self.challenger_version_ids)
        row["snapshot_ids"] = list(self.snapshot_ids)
        row["metadata"] = _safe(self.metadata)
        return row


@dataclass(frozen=True)
class StrategyLabRun:
    lab_run_id: str
    experiment_id: str
    started_at: str
    completed_at: str
    mode: str
    snapshot_count: int
    decision_count: int
    error_count: int
    metrics: Sequence[Mapping[str, Any]]
    decisions: Sequence[Mapping[str, Any]]
    split: Mapping[str, Any] = field(default_factory=dict)
    production_applied: bool = False
    execution_authorized: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = STRATEGY_LAB_RUN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["metrics"] = [_safe(item) for item in self.metrics]
        row["decisions"] = [_safe(item) for item in self.decisions]
        row["split"] = _safe(self.split)
        row["metadata"] = _safe(self.metadata)
        return row


def build_experiment_id(*, name: str, baseline_version_id: str, created_at: str) -> str:
    return stable_id("LAB", {"name": name, "baseline": baseline_version_id, "created_at": created_at})


def build_lab_run_id(*, experiment_id: str, started_at: str) -> str:
    return stable_id("LABRUN", {"experiment_id": experiment_id, "started_at": started_at})


def validate_experiment(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value or {})
    errors: list[str] = []
    for key in ("experiment_id", "name", "hypothesis", "baseline_version_id", "mode", "status"):
        if not str(row.get(key) or "").strip():
            errors.append(f"Missing {key}")
    challengers = row.get("challenger_version_ids")
    if not isinstance(challengers, list) or not challengers:
        errors.append("At least one challenger is required")
    if str(row.get("mode") or "") not in {item.value for item in StrategyLabMode}:
        errors.append("Invalid Strategy Lab mode")
    try:
        ratio = float(row.get("train_ratio", 0.70))
        if not 0.50 <= ratio <= 0.90:
            errors.append("train_ratio must be between 0.50 and 0.90")
    except Exception:
        errors.append("Invalid train_ratio")
    if str(row.get("schema_version") or "") != STRATEGY_LAB_SCHEMA_VERSION:
        errors.append("Invalid Strategy Lab schema")
    return {"ok": not errors, "errors": errors}
