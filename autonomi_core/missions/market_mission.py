"""Immutable handoff from analysis/reporting into Autonomy Core."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from autonomi_core.configuration.policy import AutonomyPolicy, load_policy


@dataclass(frozen=True)
class MarketMission:
    source_run_id: str
    trigger: str
    market_run: Mapping[str, Any]
    policy: AutonomyPolicy

    def validate(self) -> None:
        if not isinstance(self.market_run, Mapping):
            raise TypeError("market_run må være et mapping-objekt")
        if not self.source_run_id:
            raise ValueError("Autonomi-oppdraget mangler source_run_id")
        if not self.policy.theoretical_only:
            raise ValueError("Kun teoretiske oppdrag er tillatt")


def build_market_mission(
    market_run: Mapping[str, Any], *, trigger: str = "SCHEDULED",
    policy: AutonomyPolicy | None = None,
) -> MarketMission:
    mission = MarketMission(
        source_run_id=str(market_run.get("run_id") or ""),
        trigger=str(trigger or "SCHEDULED"), market_run=market_run,
        policy=policy or load_policy(),
    )
    mission.validate()
    return mission
