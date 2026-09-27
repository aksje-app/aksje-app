"""Durable oversight for Quality Model v2 shadow qualification."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

STATE_KEY = "quality_v2_shadow/state"
EVALUATION_KEY = "quality_v2_shadow/evaluation"
MILESTONES = (10, 25, 50)


def _path():
    return runtime_data_path("quality_v2_shadow", "state")


def load_shadow_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, _path(), {})
    return dict(value) if isinstance(value, Mapping) else {}


def _evaluation_path():
    return runtime_data_path("quality_v2_shadow", "evaluation")


def load_shadow_evaluation() -> dict[str, Any]:
    value = read_json(EVALUATION_KEY, _evaluation_path(), {})
    return dict(value) if isinstance(value, Mapping) else {}


def _component_status(shadow: Mapping[str, Any]) -> list[dict[str, Any]]:
    evaluated = int(shadow.get("evaluated") or 0)
    weakening = int(shadow.get("weakening_count") or 0)
    moat = int(shadow.get("moat_documented_count") or 0)
    return [
        {"component": "ROCE trend", "status": "REVIEW_FOR_PROMOTION" if evaluated else "CONTINUE_SHADOW",
         "reason": f"{evaluated} selskaper vurdert; {weakening} med svekkende trend."},
        {"component": "FCF consistency", "status": "REVIEW_FOR_PROMOTION" if evaluated else "CONTINUE_SHADOW",
         "reason": "Flerperiodisk FCF-observasjon er tilgjengelig der provider leverer historikk."},
        {"component": "ROIC-WACC", "status": "CONTINUE_SHADOW",
         "reason": "Kan ikke promoteres uten eksplisitt dokumentert ROIC- og WACC-grunnlag."},
        {"component": "Moat evidence", "status": "CONTINUE_SHADOW" if not moat else "REVIEW_FOR_PROMOTION",
         "reason": "Regnskapstall alene er ikke moat-bevis; eksplisitt evidens kreves."},
    ]


def _write_milestone_evaluation(*, runs: int, result: Mapping[str, Any], shadow: Mapping[str, Any]) -> dict[str, Any]:
    report = {
        "schema": "quality_v2_milestone_evaluation@1.0",
        "generated_at": result.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "milestone": runs,
        "run_key": result.get("run_key"),
        "shadow_only": True,
        "production_effect": False,
        "summary": {
            "evaluated": int(shadow.get("evaluated") or 0),
            "disagreement_count": int(shadow.get("disagreement_count") or 0),
            "weakening_count": int(shadow.get("weakening_count") or 0),
            "strong_or_improving": int(shadow.get("strong_or_improving") or 0),
        },
        "components": _component_status(shadow),
        "decision_required": runs >= MILESTONES[-1],
    }
    write_json(EVALUATION_KEY, _evaluation_path(), report)
    return report


def record_shadow_run(result: Mapping[str, Any]) -> dict[str, Any]:
    shadow = result.get("quality_v2_shadow") if isinstance(result.get("quality_v2_shadow"), Mapping) else {}
    if not shadow or not shadow.get("shadow_only"):
        return load_shadow_state()

    state = load_shadow_state()
    runs = int(state.get("complete_runs") or 0)
    if str(result.get("state") or "") == "COMPLETED":
        runs += 1
    current_evaluated = int(shadow.get("evaluated") or 0)
    current_disagreements = int(shadow.get("disagreement_count") or 0)
    current_weakening = int(shadow.get("weakening_count") or 0)
    evaluated_observations = int(state.get("evaluated_observations_total") or state.get("evaluated_companies") or 0) + current_evaluated
    disagreement_observations = int(state.get("disagreement_observations_total") or state.get("disagreement_count") or 0) + current_disagreements
    weakening_observations = int(state.get("weakening_observations_total") or state.get("weakening_count") or 0) + current_weakening

    next_milestone = next((value for value in MILESTONES if runs < value), None)
    reached = max((value for value in MILESTONES if runs >= value), default=0)
    decision_required = runs >= MILESTONES[-1]
    status = "SHADOW_DECISION_REQUIRED" if decision_required else "SHADOW_LEARNING"

    previous_reached = int(state.get("reached_milestone") or 0)
    milestone_evaluation = load_shadow_evaluation()
    if reached in MILESTONES and reached > previous_reached:
        milestone_evaluation = _write_milestone_evaluation(runs=reached, result=result, shadow=shadow)

    state = {
        "status": status,
        "complete_runs": runs,
        # User-facing/current-state counters: never accumulate the same company
        # across repeated manual runs. The overview must answer "what disagrees now?".
        "evaluated_companies": current_evaluated,
        "disagreement_count": current_disagreements,
        "weakening_count": current_weakening,
        # Historical observation totals are retained only for diagnostics/audit.
        "evaluated_observations_total": evaluated_observations,
        "disagreement_observations_total": disagreement_observations,
        "weakening_observations_total": weakening_observations,
        "last_run_at": result.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "last_run_state": result.get("state"),
        "last_run_key": result.get("run_key"),
        "reached_milestone": reached,
        "next_milestone": next_milestone,
        "decision_required": decision_required,
        "milestones": list(MILESTONES),
        "latest_evaluation": milestone_evaluation,
        "rule": "V2 kan ikke forbli i ubestemt shadow etter 50 komplette kjøringer uten eksplisitt beslutning.",
    }
    write_json(STATE_KEY, _path(), state)
    return state
