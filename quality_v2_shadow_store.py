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


def _ticker_set(values: Any) -> set[str]:
    return {str(value).strip().upper() for value in (values or []) if str(value).strip()}


def build_shadow_comparison(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    """Compare direction classifications only when both snapshots are truly compatible."""
    previous = dict(previous or {})
    current = dict(current or {})
    previous_available = bool(previous.get("classification_available", False))
    current_available = bool(current.get("classification_available", False))
    previous_schema = str(previous.get("classification_schema") or "")
    current_schema = str(current.get("classification_schema") or "")
    previous_model = str(previous.get("model_version") or "")
    current_model = str(current.get("model_version") or "")

    previous_weaker = _ticker_set(previous.get("v2_weaker_tickers"))
    previous_stronger = _ticker_set(previous.get("v2_stronger_tickers"))
    current_weaker = _ticker_set(current.get("v2_weaker_tickers"))
    current_stronger = _ticker_set(current.get("v2_stronger_tickers"))
    previous_all = previous_weaker | previous_stronger
    current_all = current_weaker | current_stronger

    previous_count = int(previous.get("disagreement_count") or 0)
    current_count = int(current.get("disagreement_count") or 0)
    previous_complete = bool(
        previous.get("comparison_complete", False)
        and len(previous_all) == previous_count
        and not (previous_weaker & previous_stronger)
    )
    current_complete = bool(
        current.get("comparison_complete", False)
        and len(current_all) == current_count
        and not (current_weaker & current_stronger)
    )

    reason = ""
    if not previous:
        reason = "NO_PREVIOUS_RUN"
    elif not previous_available:
        reason = "PREVIOUS_CLASSIFICATION_UNAVAILABLE"
    elif not current_available:
        reason = "CURRENT_CLASSIFICATION_UNAVAILABLE"
    elif not previous_schema or previous_schema != current_schema:
        reason = "CLASSIFICATION_SCHEMA_MISMATCH"
    elif not previous_model or previous_model != current_model:
        reason = "MODEL_VERSION_MISMATCH"
    elif not previous_complete:
        reason = "PREVIOUS_TICKER_LIST_INCOMPLETE"
    elif not current_complete:
        reason = "CURRENT_TICKER_LIST_INCOMPLETE"

    if reason:
        return {
            "comparison_available": False,
            "comparison_reason": reason,
            "new_disagreement_tickers": [],
            "resolved_disagreement_tickers": [],
            "unchanged_disagreement_tickers": [],
        }

    return {
        "comparison_available": True,
        "comparison_reason": "COMPARABLE",
        "new_disagreement_tickers": sorted(current_all - previous_all),
        "resolved_disagreement_tickers": sorted(previous_all - current_all),
        "unchanged_disagreement_tickers": sorted(current_all & previous_all),
    }


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
    current_v2_weaker = int(shadow.get("v2_weaker_count") or 0)
    current_v2_stronger = int(shadow.get("v2_stronger_count") or 0)
    current_v2_weaker_tickers = list(shadow.get("v2_weaker_tickers") or [])
    current_v2_stronger_tickers = list(shadow.get("v2_stronger_tickers") or [])
    comparison = build_shadow_comparison(state, shadow)
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
        "v2_weaker_count": current_v2_weaker,
        "v2_stronger_count": current_v2_stronger,
        "v2_weaker_tickers": current_v2_weaker_tickers,
        "v2_stronger_tickers": current_v2_stronger_tickers,
        "v2_weaker_details": list(shadow.get("v2_weaker_details") or []),
        "v2_stronger_details": list(shadow.get("v2_stronger_details") or []),
        "classification_schema": str(shadow.get("classification_schema") or ""),
        "model_version": str(shadow.get("model_version") or ""),
        "classification_available": bool(shadow.get("classification_available", False)),
        "comparison_complete": bool(shadow.get("comparison_complete", False)),
        "comparison_available": bool(comparison.get("comparison_available")),
        "comparison_reason": str(comparison.get("comparison_reason") or ""),
        "comparison_base_run_key": str(state.get("last_run_key") or "") if comparison.get("comparison_available") else "",
        "new_disagreement_tickers": list(comparison.get("new_disagreement_tickers") or []),
        "resolved_disagreement_tickers": list(comparison.get("resolved_disagreement_tickers") or []),
        "unchanged_disagreement_tickers": list(comparison.get("unchanged_disagreement_tickers") or []),
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
