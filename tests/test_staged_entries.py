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


@pytest.mark.parametrize("engine", ["super_portfolio", "autonomi", "superfond"])
def test_cross_engine_plan_is_read_only_and_capped(engine):
    from staged_entries import entry_plan
    plan = entry_plan(engine, 15.0, 10.0, enabled=True)
    assert plan["cumulative_weights_pct"] == pytest.approx((3, 6, 10))
    assert plan["incremental_weights_pct"] == pytest.approx((3, 3, 4))
    assert plan["execution_authorized"] is False
    assert plan["requires_new_evidence_for_addons"] is True


def test_cross_engine_plan_disabled_by_default():
    from staged_entries import entry_plan
    plan = entry_plan("super_portfolio", 10, 15)
    assert not plan["enabled"]
    assert not plan["execution_authorized"]
    assert plan["target_weight_pct"] == 10


def test_stage_events_require_sequential_fill_and_are_idempotent():
    from staged_entries import record_stage_event
    p={"position_id":"shadow:ABC"}
    first={"idempotency_key":"shadow:ABC:ENTRY_STAGE:1","stage":1,
           "executed_at":"2026-10-13T12:00:00Z","fill_price":100.0,
           "filled_weight_pct":3.0}
    p1=record_stage_event(p,first)
    assert p == {"position_id":"shadow:ABC"}
    assert p1["entry_stage"] == 1
    assert len(record_stage_event(p1,first)["entry_stage_events"]) == 1
    with pytest.raises(ValueError):
        record_stage_event(p1,{"idempotency_key":"shadow:ABC:ENTRY_STAGE:3",
                               "stage":3,"executed_at":"2026-10-13","fill_price":105,
                               "filled_weight_pct":4})
    with pytest.raises(ValueError):
        record_stage_event(p,{"**bad":1})


def test_addon_requires_audited_stage_and_all_signals():
    from staged_entries import propose_next_stage
    checks=dict(policy=StagedEntryPolicy(enabled=True),
                new_observations=2, original_thesis_valid=True,
                positive_relative_strength=True, score_not_weaker=True,
                price_above_entry=True, data_fresh=True,
                cooldown_active=False, overheated=False)
    assert propose_next_stage({"position_id":"X"},**checks)["reason"] == "MISSING_STAGE_HISTORY"
    position={"position_id":"X","entry_stage":1,"last_stage_event_key":"X:ENTRY_STAGE:1"}
    proposal=propose_next_stage(position,**checks)
    assert proposal["allowed"] and proposal["idempotency_key"]=="X:ENTRY_STAGE:2"
    assert proposal["execution_authorized"] is False
    assert not propose_next_stage(position,**{**checks,"price_above_entry":False})["allowed"]


def test_superfund_preview_does_not_mutate_pending_orders():
    from copy import deepcopy
    from superfund_engine import preview_staged_pending_buys
    state={"cash":100000,"positions":{},"orders":[
        {"side":"BUY","id":"TEST","allocation":10000,"requested_at":"2026-10-13T12:00:00Z"},
        {"side":"SELL","id":"OTHER","allocation":8000},
    ]}
    original=deepcopy(state)
    rows=preview_staged_pending_buys(state)
    assert state==original
    assert len(rows)==1
    assert rows[0]["stage_1_allocation_nok"]==3000
    assert rows[0]["status"]=="PREVIEW_ONLY"
    assert not rows[0]["execution_authorized"]


def test_super_portfolio_read_only_preview():
    from super_portfolio import preview_staged_super_portfolio_targets
    requested={"SECT-B.ST":12}
    result=preview_staged_super_portfolio_targets(requested)
    assert requested=={"SECT-B.ST":12}
    assert result["SECT-B.ST"]["incremental_weights_pct"]==pytest.approx((3.6,3.6,4.8))
    assert not result["SECT-B.ST"]["execution_authorized"]


def test_autonomi_read_only_preview():
    from autonomous_portfolio import preview_staged_autonomi_buys
    proposals=[{"ticker":"TEST","action":"BUY","target_weight_pct":10},
               {"ticker":"OTHER","action":"SELL","target_weight_pct":10}]
    result=preview_staged_autonomi_buys(proposals,max_position_pct=8)
    assert len(result)==1
    assert result[0]["ticker"]=="TEST"
    assert result[0]["plan"]["incremental_weights_pct"]==pytest.approx((2.4,2.4,3.2))
    assert not result[0]["execution_authorized"]
