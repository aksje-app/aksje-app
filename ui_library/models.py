from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

PAGE_STATES = frozenset({"READY", "LOADING", "EMPTY", "STALE", "PARTIAL", "ERROR", "BLOCKED"})
SEMANTIC_TONES = frozenset({"neutral", "info", "success", "warning", "danger", "portfolio", "market", "reports", "autonomy"})


@dataclass(frozen=True)
class MetricView:
    label: str
    value: str
    delta: str = ""
    tone: str = "neutral"


@dataclass(frozen=True)
class ActionView:
    action_id: str
    label: str
    tone: str = "neutral"
    disabled: bool = False
    confirmation: str = ""
    help_text: str = ""


@dataclass(frozen=True)
class DecisionView:
    ticker: str
    action: str
    reason: str
    confidence: float | None = None
    horizon: str = ""
    consequence: str = ""
    tone: str = "neutral"

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "DecisionView":
        raw = str(row.get("decision") or row.get("action") or "HOLD").upper()
        labels = {"BUY": "KJØP", "KJØP": "KJØP", "HOLD": "HOLD", "SELL": "SELG", "SELG": "SELG", "REPLACE_REVIEW": "BYTT-VURDERING", "REJECTED": "FORKASTET"}
        tones = {"BUY": "success", "KJØP": "success", "HOLD": "neutral", "SELL": "danger", "SELG": "danger", "REPLACE_REVIEW": "warning", "REJECTED": "neutral"}
        confidence = row.get("confidence")
        try:
            confidence = float(confidence) if confidence not in (None, "") else None
        except (TypeError, ValueError):
            confidence = None
        return cls(
            str(row.get("ticker") or "-"), labels.get(raw, raw),
            str(row.get("reason") or row.get("decision_reason") or "Ingen begrunnelse registrert"),
            confidence=confidence, horizon=str(row.get("horizon") or ""),
            consequence=str(row.get("consequence") or ""), tone=tones.get(raw, "neutral"),
        )


@dataclass(frozen=True)
class TimelineStepView:
    step_id: str
    label: str
    scheduled_at: str
    status: str
    tone: str = "neutral"
    details: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PageStateView:
    state: str
    message: str
    code: str = ""
    occurred_at: str = ""
    action: ActionView | None = None

    @classmethod
    def empty(cls, message: str) -> "PageStateView": return cls("EMPTY", message)
    @classmethod
    def stale(cls, message: str) -> "PageStateView": return cls("STALE", message)
    @classmethod
    def error(cls, message: str, *, code: str = "") -> "PageStateView": return cls("ERROR", message, code=code)


@dataclass(frozen=True)
class JobStatusView:
    job_id: str
    state: str
    label: str
    phase: str = ""
    percent: int | None = None
    completed_units: int | None = None
    total_units: int | None = None
    started_at: str = ""
    last_activity_at: str = ""
    message: str = ""
    error: str = ""
    can_pause: bool = False
    can_resume: bool = False
    can_stop: bool = False
    diagnostic_available: bool = False
