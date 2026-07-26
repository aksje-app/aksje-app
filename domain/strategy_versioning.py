"""Canonical strategy version contracts introduced in v19.5.0.

This module describes strategy identity and lifecycle only. It contains no
signal calculation, order execution, portfolio sizing or risk thresholds.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping

STRATEGY_CONTRACT_SCHEMA_VERSION = "1.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrategyStatus(str, Enum):
    PRODUCTION = "PRODUCTION"
    SHADOW = "SHADOW"
    CHALLENGER = "CHALLENGER"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


class ExecutionMode(str, Enum):
    PAPER = "PAPER"
    SHADOW_READ_ONLY = "SHADOW_READ_ONLY"
    DISABLED = "DISABLED"


_ALLOWED_TRANSITIONS: dict[StrategyStatus, set[StrategyStatus]] = {
    StrategyStatus.PRODUCTION: set(),  # Production binding is locked in v19.5.0.
    StrategyStatus.SHADOW: {StrategyStatus.CHALLENGER, StrategyStatus.PAUSED, StrategyStatus.RETIRED},
    StrategyStatus.CHALLENGER: {StrategyStatus.SHADOW, StrategyStatus.PAUSED, StrategyStatus.RETIRED},
    StrategyStatus.PAUSED: {StrategyStatus.SHADOW, StrategyStatus.CHALLENGER, StrategyStatus.RETIRED},
    StrategyStatus.RETIRED: set(),
}


def normalize_strategy_status(value: Any) -> StrategyStatus:
    if isinstance(value, StrategyStatus):
        return value
    raw = str(value or "").strip().upper()
    try:
        return StrategyStatus(raw)
    except ValueError as exc:
        raise ValueError(f"Ugyldig strateg status: {value}") from exc


def normalize_execution_mode(value: Any) -> ExecutionMode:
    if isinstance(value, ExecutionMode):
        return value
    raw = str(value or "").strip().upper()
    try:
        return ExecutionMode(raw)
    except ValueError as exc:
        raise ValueError(f"Ugyldig execution mode: {value}") from exc


def stable_config_checksum(config: Mapping[str, Any] | None) -> str:
    payload = json.dumps(dict(config or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_version_id(strategy_id: str, strategy_version: str) -> str:
    sid = re.sub(r"[^a-z0-9_.-]+", "-", str(strategy_id or "").strip().lower()).strip("-")
    version = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(strategy_version or "").strip()).strip("-")
    if not sid or not version:
        raise ValueError("strategy_id og strategy_version er påkrevd")
    return f"{sid}@{version}"


@dataclass(frozen=True)
class StrategyVersion:
    strategy_id: str
    strategy_family: str
    display_name: str
    strategy_version: str
    parameter_version: str
    status: str
    execution_mode: str
    implementation_version: str
    version_id: str = ""
    parent_version_id: str = ""
    description: str = ""
    config_checksum: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    activated_at: str = ""
    retired_at: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = STRATEGY_CONTRACT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["metadata"] = dict(self.metadata or {})
        return value


def validate_strategy_version(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value or {})
    errors: list[str] = []
    required = (
        "strategy_id", "strategy_family", "display_name", "strategy_version",
        "parameter_version", "status", "execution_mode", "implementation_version",
    )
    for key in required:
        if not str(row.get(key) or "").strip():
            errors.append(f"Mangler {key}")
    try:
        status = normalize_strategy_status(row.get("status"))
    except ValueError as exc:
        errors.append(str(exc)); status = None
    try:
        mode = normalize_execution_mode(row.get("execution_mode"))
    except ValueError as exc:
        errors.append(str(exc)); mode = None
    expected_id = ""
    try:
        expected_id = build_version_id(row.get("strategy_id", ""), row.get("strategy_version", ""))
        if row.get("version_id") and str(row.get("version_id")) != expected_id:
            errors.append("version_id stemmer ikke med strategy_id og strategy_version")
    except ValueError as exc:
        errors.append(str(exc))
    if status == StrategyStatus.PRODUCTION and mode != ExecutionMode.PAPER:
        errors.append("Produksjonsstrategi må bruke PAPER i dagens teoretiske system")
    if status in {StrategyStatus.SHADOW, StrategyStatus.CHALLENGER} and mode != ExecutionMode.SHADOW_READ_ONLY:
        errors.append("Shadow/challenger må være skrivebeskyttet")
    if status in {StrategyStatus.PAUSED, StrategyStatus.RETIRED} and mode != ExecutionMode.DISABLED:
        errors.append("Pauset/avviklet strategi må være deaktivert")
    return {"ok": not errors, "errors": errors, "expected_version_id": expected_id}


def assert_transition_allowed(current: Any, target: Any) -> None:
    source = normalize_strategy_status(current)
    destination = normalize_strategy_status(target)
    if destination == source:
        return
    if destination not in _ALLOWED_TRANSITIONS[source]:
        raise ValueError(f"Overgang {source.value} → {destination.value} er ikke tillatt i v19.5.0")


def execution_mode_for_status(status: Any) -> ExecutionMode:
    normalized = normalize_strategy_status(status)
    if normalized == StrategyStatus.PRODUCTION:
        return ExecutionMode.PAPER
    if normalized in {StrategyStatus.SHADOW, StrategyStatus.CHALLENGER}:
        return ExecutionMode.SHADOW_READ_ONLY
    return ExecutionMode.DISABLED
