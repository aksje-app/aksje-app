from dataclasses import replace

import pytest

from staged_entries import StagedEntryPolicy, may_advance_stage, stage_target_weight


def test_disabled_policy_preserves_existing_target():
    assert stage_target_weight(15, 1, policy=StagedEntryPolicy(), ceiling_pct=15) == 15


def test_three_stages_respect_portfolio_cap():
    policy = StagedEntryPolicy(enabled=True)
    assert stage_target_weight(15, 1, policy=policy, ceiling_pct=10) == pytest.approx(3)
    assert stage_target_weight(15, 2, policy=policy, ceiling_pct=10) == pytest.approx(6)
    assert stage_target_weight(15, 3, policy=policy, ceiling_pct=10) == pytest.approx(10)


def test_invalid_stages_and_fractions_rejected():
    with pytest.raises(ValueError):
        StagedEntryPolicy(fractions=(0.4, 0.4, 0.4))
    with pytest.raises(ValueError):
        stage_target_weight(10, 0, policy=StagedEntryPolicy(enabled=True), ceiling_pct=10)


def test_increase_requires_all_validated_fresh_signals():
    kwargs=dict(policy=StagedEntryPolicy(enabled=True), current_stage=1,
                new_observations=2, original_thesis_valid=True,
                positive_relative_strength=True, score_not_weaker=True,
                price_above_entry=True, data_fresh=True,
                cooldown_active=False, overheated=False)
    assert may_advance_stage(**kwargs)
    assert not may_advance_stage(**{**kwargs, "price_above_entry": False})
    assert not may_advance_stage(**{**kwargs, "data_fresh": False})
    assert not may_advance_stage(**{**kwargs, "overheated": True})
    assert not may_advance_stage(**{**kwargs, "cooldown_active": True})
    assert not may_advance_stage(**{**kwargs, "new_observations": 1})
    assert not may_advance_stage(**{**kwargs, "policy": StagedEntryPolicy()})
