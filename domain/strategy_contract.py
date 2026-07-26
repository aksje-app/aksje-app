"""Common read-only strategy evaluation contracts for v19.7.0.

The contract deliberately separates analysis from execution. Strategies may
propose an order intent, but this module never mutates cash, positions or
trades. Execution remains in the existing production engines until the shared
portfolio/execution phase of the roadmap.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping, Protocol

from domain.market_snapshot import CandidateSnapshot

STRATEGY_DECISION_SCHEMA_VERSION = "1.0"
STRATEGY_RUN_SCHEMA_VERSION = "1.0"


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


def _stable_id(payload: Mapping[str, Any], prefix: str) -> str:
    raw = json.dumps(_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


@dataclass(frozen=True)
class StrategyEvaluationContext:
    run_id: str
    source: str
    purpose: str = "PARALLEL_COMPARISON"
    portfolio_state: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    evaluated_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class StrategyDecision:
    decision_id: str
    run_id: str
    strategy_family: str
    strategy_id: str
    strategy_version: str
    strategy_version_id: str
    strategy_status: str
    execution_mode: str
    ticker: str
    action: str
    raw_decision: str
    score: float
    confidence: float
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    market_snapshot_id: str
    candidate_snapshot_id: str
    snapshot_checksum: str
    evaluated_at: str
    purpose: str = "PARALLEL_COMPARISON"
    valid_until: str = ""
    order_intent: Mapping[str, Any] = field(default_factory=dict)
    execution_authorized: bool = False
    error: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = STRATEGY_DECISION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["reasons"] = list(self.reasons)
        row["blockers"] = list(self.blockers)
        row["order_intent"] = _safe(self.order_intent)
        row["metadata"] = _safe(self.metadata)
        return row


@dataclass(frozen=True)
class StrategyRunResult:
    strategy_run_id: str
    run_id: str
    source: str
    market_snapshot_id: str
    started_at: str
    completed_at: str
    strategy_count: int
    candidate_count: int
    decision_count: int
    error_count: int
    decisions: tuple[Mapping[str, Any], ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = STRATEGY_RUN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["decisions"] = [_safe(item) for item in self.decisions]
        row["metadata"] = _safe(self.metadata)
        return row


class Strategy(Protocol):
    version: Mapping[str, Any]

    def evaluate(self, candidate: CandidateSnapshot, context: StrategyEvaluationContext) -> StrategyDecision:
        ...


def build_decision_id(*, run_id: str, strategy_version_id: str, candidate_snapshot_id: str, purpose: str) -> str:
    return _stable_id(
        {
            "run_id": run_id,
            "strategy_version_id": strategy_version_id,
            "candidate_snapshot_id": candidate_snapshot_id,
            "purpose": purpose,
        },
        "SD",
    )


def build_strategy_run_id(*, run_id: str, market_snapshot_id: str, source: str) -> str:
    return _stable_id({"run_id": run_id, "market_snapshot_id": market_snapshot_id, "source": source}, "SR")


def validate_strategy_decision(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value or {})
    errors: list[str] = []
    for key in (
        "decision_id", "run_id", "strategy_family", "strategy_id", "strategy_version",
        "strategy_version_id", "strategy_status", "execution_mode", "ticker", "action",
        "market_snapshot_id", "candidate_snapshot_id", "evaluated_at",
    ):
        if not str(row.get(key) or "").strip():
            errors.append(f"Mangler {key}")
    if row.get("execution_authorized") is not False:
        errors.append("Parallelle strategibeslutninger skal aldri autorisere utførelse")
    if str(row.get("schema_version") or "") != STRATEGY_DECISION_SCHEMA_VERSION:
        errors.append("Ugyldig strategy decision schema")
    return {"ok": not errors, "errors": errors}
