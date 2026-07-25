"""Autonomy-owned runtime gateway with legacy engine compatibility."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from autonomi_core.configuration.policy import AutonomyPolicy, load_policy
from autonomi_core.missions.market_mission import build_market_mission

# Runtime contract remains in the v18.8 compatibility series; v18.9.0 is the
# independent Learning & Reporting layer version.
CORE_VERSION = "v19.0.18b"


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
    # v19.0.18b: Autonomi must receive candidates for diagnostics and controlled
    # learning even when evidence/data gates prevent a final BUY recommendation.
    # Real trading is still impossible; the downstream portfolio is explicitly
    # theoretical-only. Normal decision-valid candidates are preferred, but when
    # every candidate is filtered out we forward the observed list as a learning
    # probe so the portfolio engine can explain and, if configured, create small
    # theoretical learning positions instead of silently skipping the run.
    valid_observed = [item for item in observed if item.get("valid_for_decision", True)]
    forward_source = valid_observed if valid_observed else observed
    governed_run["autonomy_learning_probe"] = bool(observed and not valid_observed)
    governed_run["candidates"] = [
        {**dict(item), "autonomy_learning_probe": bool(observed and not valid_observed)}
        for item in forward_source
        if not item.get("portfolio_action") or str(item.get("portfolio_action")).upper() in {"BUY", "HOLD", "SELL", "REVIEW", "SKIP"}
    ]
    raw_proposals = list(governed_run.get("proposals") or [])
    valid_proposals = [
        item for item in raw_proposals
        if item.get("valid_for_decision", True)
        and (not item.get("portfolio_action") or str(item.get("portfolio_action")).upper() in {"BUY", "REVIEW"})
    ]
    governed_run["proposals"] = valid_proposals if valid_proposals else [
        {**dict(item), "autonomy_learning_probe": True} for item in raw_proposals[:10]
    ]
    governed_run["autonomy_handoff_input"] = {
        "observed_candidates": len(observed),
        "valid_observed": len(valid_observed),
        "forwarded_candidates": len(governed_run["candidates"]),
        "forwarded_proposals": len(governed_run["proposals"]),
        "review_candidates_forwarded": sum(1 for item in governed_run["candidates"] if str(item.get("portfolio_action") or item.get("status") or "").upper() in {"REVIEW", "KREVER MANUELL VURDERING"}),
        "learning_probe_mode": bool(governed_run.get("autonomy_learning_probe")),
    }

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
        "handoff_input": governed_run.get("autonomy_handoff_input") or {},
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
