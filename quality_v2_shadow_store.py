"""Durable oversight for Quality Model v2 shadow qualification."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

STATE_KEY = "quality_v2_shadow/state"
MILESTONES = (10, 25, 50)


def _path():
    return runtime_data_path("quality_v2_shadow", "state")


def load_shadow_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, _path(), {})
    return dict(value) if isinstance(value, Mapping) else {}


def record_shadow_run(result: Mapping[str, Any]) -> dict[str, Any]:
    shadow = result.get("quality_v2_shadow") if isinstance(result.get("quality_v2_shadow"), Mapping) else {}
    if not shadow or not shadow.get("shadow_only"):
        return load_shadow_state()

    state = load_shadow_state()
    runs = int(state.get("complete_runs") or 0)
    if str(result.get("state") or "") == "COMPLETED":
        runs += 1
    evaluated = int(state.get("evaluated_companies") or 0) + int(shadow.get("evaluated") or 0)
    disagreements = int(state.get("disagreement_count") or 0) + int(shadow.get("disagreement_count") or 0)
    weakening = int(state.get("weakening_count") or 0) + int(shadow.get("weakening_count") or 0)

    next_milestone = next((value for value in MILESTONES if runs < value), None)
    reached = max((value for value in MILESTONES if runs >= value), default=0)
    decision_required = runs >= MILESTONES[-1]
    status = "SHADOW_DECISION_REQUIRED" if decision_required else "SHADOW_LEARNING"

    state = {
        "status": status,
        "complete_runs": runs,
        "evaluated_companies": evaluated,
        "disagreement_count": disagreements,
        "weakening_count": weakening,
        "last_run_at": result.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "last_run_state": result.get("state"),
        "last_run_key": result.get("run_key"),
        "reached_milestone": reached,
        "next_milestone": next_milestone,
        "decision_required": decision_required,
        "milestones": list(MILESTONES),
        "rule": "V2 kan ikke forbli i ubestemt shadow etter 50 komplette kjøringer uten eksplisitt beslutning.",
    }
    write_json(STATE_KEY, _path(), state)
    return state
