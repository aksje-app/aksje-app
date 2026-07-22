"""One typed policy boundary for autonomous missions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from persistent_config_store import read_persistent_json, write_persistent_json

POLICY_KEY = "autonomi_core/policy.json"


@dataclass(frozen=True)
class AutonomyPolicy:
    schema_version: int = 1
    theoretical_only: bool = True
    run_portfolio_decisions: bool = True
    run_controlled_learning: bool = True
    require_active_portfolio: bool = True
    require_fresh_market_evidence: bool = True
    require_report_persistence: bool = True
    allow_automatic_model_approval: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AutonomyPolicy":
        allowed = cls.__dataclass_fields__
        clean = {key: item for key, item in dict(value or {}).items() if key in allowed}
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_policy() -> AutonomyPolicy:
    return AutonomyPolicy.from_mapping(read_persistent_json(POLICY_KEY, default={}))


def save_policy(policy: AutonomyPolicy) -> None:
    if not policy.theoretical_only:
        raise ValueError("v18.8.0 tillater bare teoretisk autonomi")
    if policy.allow_automatic_model_approval:
        raise ValueError("Modellendringer krever fortsatt eksplisitt godkjenning")
    write_persistent_json(POLICY_KEY, policy.to_dict())
