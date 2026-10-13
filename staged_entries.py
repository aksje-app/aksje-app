"""Shared, opt-in staged entry policy for theoretical portfolio engines.

Pure calculations only. No order execution, storage mutation or market requests.
Existing positions are never resized by this module.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class StagedEntryPolicy:
    fractions: tuple[float, float, float] = (0.30, 0.30, 0.40)
    enabled: bool = False

    def __post_init__(self):
        if len(self.fractions) != 3 or any(not isfinite(x) or x <= 0 for x in self.fractions):
            raise ValueError("Three positive, finite stage fractions are required")
        if abs(sum(self.fractions) - 1.0) > 1e-9:
            raise ValueError("Stage fractions must add to 1")


def stage_target_weight(target_weight_pct: float, stage: int, *, policy: StagedEntryPolicy,
                        ceiling_pct: float) -> float:
    """Return cumulative portfolio weight, without placing or scheduling an order."""
    if not 1 <= stage <= 3:
        raise ValueError("Stage must be 1, 2 or 3")
    if not all(isfinite(float(v)) for v in (target_weight_pct, ceiling_pct)):
        raise ValueError("Weights must be finite")
    if target_weight_pct < 0 or ceiling_pct < 0:
        raise ValueError("Weights must not be negative")
    capped = min(target_weight_pct, ceiling_pct)
    if not policy.enabled:
        return capped
    return capped * sum(policy.fractions[:stage])


def may_advance_stage(*, policy: StagedEntryPolicy, current_stage: int,
                      new_observations: int, original_thesis_valid: bool,
                      positive_relative_strength: bool, score_not_weaker: bool,
                      price_above_entry: bool, data_fresh: bool,
                      cooldown_active: bool, overheated: bool) -> bool:
    """Conservative entry gate. Every signal must be supplied by the calling engine.

    This is an additional restriction, never a replacement for its own risk,
    cash, liquidity, instrument-hours or idempotency checks.
    """
    return bool(
        policy.enabled and current_stage in (1, 2)
        and new_observations >= 2 and original_thesis_valid
        and positive_relative_strength and score_not_weaker
        and price_above_entry and data_fresh
        and not cooldown_active and not overheated
    )


SUPPORTED_ENGINES = frozenset({"super_portfolio", "autonomi", "superfond"})


def entry_plan(engine: str, target_weight_pct: float, ceiling_pct: float,
               *, enabled: bool = False) -> dict:
    """Read-only cross-engine plan. Caller decides whether to enable integration.

    The three stage weights are cumulative weights within the whole portfolio,
    NOT three independently purchasable percentages. No trading side effects.
    """
    if engine not in SUPPORTED_ENGINES:
        raise ValueError("Unknown portfolio engine")
    policy = StagedEntryPolicy(enabled=enabled)
    stages = tuple(round(stage_target_weight(target_weight_pct, n, policy=policy,
                        ceiling_pct=ceiling_pct), 6) for n in (1, 2, 3))
    increments = (stages[0], stages[1] - stages[0], stages[2] - stages[1])
    return {
        "engine": engine,
        "enabled": enabled,
        "target_weight_pct": round(stages[-1], 6),
        "cumulative_weights_pct": stages,
        "incremental_weights_pct": tuple(round(x, 6) for x in increments),
        "requires_new_evidence_for_addons": enabled,
        "execution_authorized": False,
    }


def propose_next_stage(position: dict, *, policy: StagedEntryPolicy,
                       new_observations: int, original_thesis_valid: bool,
                       positive_relative_strength: bool, score_not_weaker: bool,
                       price_above_entry: bool, data_fresh: bool,
                       cooldown_active: bool, overheated: bool) -> dict:
    """Produce a non-executable proposal based on persisted stage evidence.

    Caller must retain its own transactional locking and unique execution key.
    A legacy position with no stage metadata is never silently migrated.
    """
    stage = position.get("entry_stage")
    if not isinstance(stage, int) or isinstance(stage, bool) or stage not in (1, 2, 3):
        return {"allowed": False, "reason": "MISSING_STAGE_HISTORY"}
    if stage == 3:
        return {"allowed": False, "reason": "FULLY_BUILT"}
    identifier = str(position.get("position_id") or "").strip()
    last_key = str(position.get("last_stage_event_key") or "").strip()
    if not identifier or not last_key:
        return {"allowed": False, "reason": "MISSING_AUDIT_ID"}
    permitted = may_advance_stage(
        policy=policy, current_stage=stage, new_observations=new_observations,
        original_thesis_valid=original_thesis_valid,
        positive_relative_strength=positive_relative_strength,
        score_not_weaker=score_not_weaker,
        price_above_entry=price_above_entry, data_fresh=data_fresh,
        cooldown_active=cooldown_active, overheated=overheated,
    )
    if not permitted:
        return {"allowed": False, "reason": "CONFIRMATION_INCOMPLETE"}
    next_stage = stage + 1
    return {
        "allowed": True,
        "stage": next_stage,
        "idempotency_key": f"{identifier}:ENTRY_STAGE:{next_stage}",
        "execution_authorized": False,
        "reason": "ALL_CONFIRMATIONS_PRESENT_REQUIRES_ENGINE_GATE",
    }


def record_stage_event(position: dict, event: dict) -> dict:
    """Pure state transition; caller must persist atomically with execution.

    The event must be validated as an actually executed paper/shadow fill by
    the engine. Merely proposing a trade never calls this function.
    """
    key = str(event.get("idempotency_key") or "")
    stage = event.get("stage")
    if not isinstance(stage, int) or isinstance(stage, bool) or stage not in (1, 2, 3):
        raise ValueError("Invalid fill stage")
    if not key or not str(event.get("executed_at") or "").strip():
        raise ValueError("Execution key and timestamp required")
    if not isinstance(event.get("fill_price"), (int, float)) or not isfinite(event["fill_price"]) or event["fill_price"] <= 0:
        raise ValueError("Valid positive fill price required")
    if not isinstance(event.get("filled_weight_pct"), (int, float)) or not isfinite(event["filled_weight_pct"]) or event["filled_weight_pct"] <= 0:
        raise ValueError("Valid positive filled weight required")
    prior = [dict(e) for e in position.get("entry_stage_events", [])]
    if any(e.get("idempotency_key") == key for e in prior):
        return dict(position)
    existing_stage = position.get("entry_stage", 0)
    if not isinstance(existing_stage, int) or isinstance(existing_stage, bool) or stage != existing_stage + 1:
        raise ValueError("Stages must advance sequentially")
    position_id = str(position.get("position_id") or "").strip()
    if not position_id or key != f"{position_id}:ENTRY_STAGE:{stage}":
        raise ValueError("Event key does not match position and stage")
    out = dict(position)
    out["entry_stage"] = stage
    out["entry_stage_events"] = prior + [dict(event)]
    out["last_stage_event_key"] = key
    return out
