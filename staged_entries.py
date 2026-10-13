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
