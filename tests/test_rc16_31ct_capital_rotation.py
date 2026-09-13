from datetime import datetime, timedelta, timezone

from autonomous_portfolio import AutonomousParameters, _candidate_event_protection
from exit_policy import evaluate_exit, policy_from


def test_flat_position_exits_to_cash_after_five_business_days():
    result = evaluate_exit(entry_price=100, current_price=100.5, highest_price=101,
                           entry_score=70, current_score=70, holding_days=5,
                           policy=policy_from(AutonomousParameters()))
    assert result["action"] == "SELL"
    assert result["reason_code"] == "OPPORTUNITY_COST_CASH_EXIT"


def test_flat_position_is_not_exited_before_five_business_days():
    result = evaluate_exit(entry_price=100, current_price=100.5, highest_price=101,
                           entry_score=70, current_score=70, holding_days=4,
                           policy=policy_from(AutonomousParameters()))
    assert result["action"] != "SELL"


def test_positive_momentum_protects_flat_position():
    result = evaluate_exit(entry_price=100, current_price=100.5, highest_price=101,
                           entry_score=70, current_score=70, holding_days=5, momentum_pct=1.2)
    assert result["reason_code"] == "FLAT_POSITION_PROTECTED"


def test_score_improvement_protects_flat_position():
    result = evaluate_exit(entry_price=100, current_price=100.5, highest_price=101,
                           entry_score=70, current_score=72, holding_days=5)
    assert result["reason_code"] == "FLAT_POSITION_PROTECTED"


def test_documented_near_event_protects_flat_position():
    date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    protected, reason = _candidate_event_protection({"earnings_date": date})
    assert protected is True
    assert "earnings_date" in reason


def test_event_outside_window_does_not_protect():
    date = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    protected, _ = _candidate_event_protection({"earnings_date": date})
    assert protected is False


def test_new_defaults_are_five_day_and_one_percent():
    params = AutonomousParameters().normalized()
    assert params.cash_review_days == 5
    assert params.stagnation_days == 5
    assert params.cash_review_max_return_pct == 1.0
    assert params.reentry_cooldown_days == 5


def test_hard_stop_still_beats_event_protection():
    result = evaluate_exit(entry_price=100, current_price=90, highest_price=103,
                           entry_score=70, current_score=72, holding_days=5,
                           event_protection_active=True, event_protection_reason="earnings tomorrow")
    assert result["action"] == "SELL"
    assert result["reason_code"] == "STOP_LOSS"
