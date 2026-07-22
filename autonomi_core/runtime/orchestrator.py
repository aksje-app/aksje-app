"""Autonomy-owned runtime gateway with legacy engine compatibility."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from autonomi_core.configuration.policy import AutonomyPolicy, load_policy
from autonomi_core.missions.market_mission import build_market_mission

# Runtime contract remains in the v18.8 compatibility series; v18.9.0 is the
# independent Learning & Reporting layer version.
CORE_VERSION = "v18.8.9"


def execute_market_mission(
    market_run: Mapping[str, Any], *, trigger: str = "SCHEDULED",
    run_autonomous: bool | None = None, run_learning: bool | None = None,
    require_active_portfolio: bool | None = None,
) -> dict[str, Any]:
    """Execute through one stable Autonomy API while preserving legacy engines."""
    policy = load_policy()
    overrides = {}
    if run_autonomous is not None:
        overrides["run_portfolio_decisions"] = bool(run_autonomous)
    if run_learning is not None:
        overrides["run_controlled_learning"] = bool(run_learning)
    if require_active_portfolio is not None:
        overrides["require_active_portfolio"] = bool(require_active_portfolio)
    effective: AutonomyPolicy = replace(policy, **overrides) if overrides else policy
    mission = build_market_mission(market_run, trigger=trigger, policy=effective)

    governed_run = dict(mission.market_run)
    observed = list(governed_run.get("candidates") or [])
    governed_run["observed_candidates"] = observed
    governed_run["candidates"] = [
        item for item in observed
        if item.get("valid_for_decision", True)
        and (not item.get("portfolio_action") or item.get("portfolio_action") in {"BUY", "HOLD", "SELL"})
    ]
    governed_run["proposals"] = [
        item for item in list(governed_run.get("proposals") or [])
        if item.get("valid_for_decision", True)
        and (not item.get("portfolio_action") or item.get("portfolio_action") == "BUY")
    ]

    # Compatibility bridge. The existing, regression-tested engine remains the
    # executor until its stages are migrated individually behind these contracts.
    from autonomous_orchestrator import run_post_scan_chain
    result = run_post_scan_chain(
        governed_run,
        run_autonomous=effective.run_portfolio_decisions,
        run_learning=effective.run_controlled_learning,
        require_active_portfolio=effective.require_active_portfolio,
        trigger=mission.trigger,
    )
    result["autonomy_core"] = {
        "version": CORE_VERSION, "mission": "MARKET_ANALYSIS",
        "source_run_id": mission.source_run_id,
        "mission_id": governed_run.get("mission_id") or (governed_run.get("investment_mission") or {}).get("mission_id"),
        "configuration_version": governed_run.get("configuration_version") or (governed_run.get("investment_mission") or {}).get("configuration_version"),
        "policy_schema": effective.schema_version,
        "theoretical_only": effective.theoretical_only,
    }
    return result


def runtime_manifest() -> dict[str, Any]:
    policy = load_policy()
    return {
        "version": CORE_VERSION,
        "status": "FOUNDATION_ACTIVE",
        "execution": "THEORETICAL_ONLY",
        "policy": policy.to_dict(),
        "domains": [
            "discovery_data", "analysis_ranking", "portfolio_decisions",
            "learning_reporting", "missions", "runtime", "configuration",
        ],
        "compatibility": [
            "market_intelligence", "autonomous_orchestrator",
            "autonomous_portfolio", "controlled_parameter_learning",
        ],
    }
