from datetime import datetime, timezone

from exit_policy import DEFAULT_EXIT_POLICY, evaluate_exit
from report_portfolio_intelligence import build_portfolio_report
from trading_settings import DEFAULT_RULES
from autonomous_portfolio import AutonomousParameters, _sell, _validate_execution_integrity


def test_all_default_engines_share_one_exit_profile():
    assert DEFAULT_RULES["stop_loss_pct"] == DEFAULT_EXIT_POLICY.stop_loss_pct == 5.0
    assert DEFAULT_RULES["take_profit_pct"] == DEFAULT_EXIT_POLICY.take_profit_pct == 14.0
    assert DEFAULT_RULES["trailing_stop_pct"] == DEFAULT_EXIT_POLICY.trailing_stop_pct == 7.0
    assert DEFAULT_RULES["rsi_exit_level"] == DEFAULT_EXIT_POLICY.rsi_exit_level == 75.0


def test_hard_loss_and_trailing_stop_sell_all():
    loss = evaluate_exit(entry_price=100, current_price=94.9, highest_price=100)
    trail = evaluate_exit(entry_price=100, current_price=111.5, highest_price=120)
    assert (loss["action"], loss["reason_code"], loss["sell_pct"]) == ("SELL", "STOP_LOSS", 100.0)
    assert (trail["action"], trail["reason_code"], trail["sell_pct"]) == ("SELL", "TRAILING_STOP", 100.0)


def test_take_profit_is_partial_once_then_winner_can_run():
    first = evaluate_exit(entry_price=100, current_price=114, highest_price=114, take_profit_taken=False)
    later = evaluate_exit(entry_price=100, current_price=116, highest_price=116, take_profit_taken=True)
    assert first["action"] == "SELL_PARTIAL" and first["sell_pct"] == 25.0
    assert later["action"] == "HOLD"


def test_score_exit_and_falling_rsi_are_distinct_exits():
    score = evaluate_exit(entry_price=100, current_price=102, highest_price=103, entry_score=78, current_score=54.9)
    rsi = evaluate_exit(entry_price=100, current_price=105, highest_price=105, entry_score=78, current_score=70, rsi=76, previous_rsi=80)
    assert score["reason_code"] == "SCORE_EXIT"
    assert rsi["reason_code"] == "RSI_EXIT"


def test_stagnation_only_becomes_replacement_with_named_superior_candidate():
    review = evaluate_exit(entry_price=100, current_price=100.5, highest_price=102, entry_score=78, current_score=70,
                           holding_days=25, best_replacement_score=74)
    replace = evaluate_exit(entry_price=100, current_price=100.5, highest_price=102, entry_score=78, current_score=69,
                            holding_days=25, best_replacement_score=76)
    assert review["reason_code"] == "CAPITAL_STAGNATION"
    assert replace["reason_code"] == "CAPITAL_REPLACEMENT"


def test_report_names_the_replacement_and_exposes_active_policy():
    portfolio = {"initial_cash": 100000, "cash": 90000, "realized_pnl": 0, "reserve_cash_pct": 10,
                 "positions": {"OLD": {"ticker": "OLD", "quantity": 100, "average_price": 100,
                                              "last_price": 100.5, "highest_price": 102, "entry_score": 78,
                                              "opened_at": "2026-07-01T00:00:00+00:00"}}}
    candidates = [
        {"ticker": "OLD", "investment_score": 69, "valid_for_decision": True, "evidence_valid_for_decision": True},
        {"ticker": "NEW", "investment_score": 76, "valid_for_decision": True, "evidence_valid_for_decision": True},
    ]
    report = build_portfolio_report(portfolio, candidates, now=datetime(2026, 8, 16, tzinfo=timezone.utc))
    row = report["positions"][0]
    assert row["capital_efficiency_status"] == "VURDER UTSKIFTING"
    assert row["replacement_ticker"] == "NEW"
    assert report["active_exit_policy"]["partial_take_profit_pct"] == 25.0


def test_partial_realization_keeps_position_and_reconciles_execution():
    portfolio = {"cash": 1000.0, "realized_pnl": 0.0,
                 "positions": {"WIN": {"ticker": "WIN", "quantity": 100.0, "average_price": 100.0}}}
    trade = _sell(portfolio, "WIN", 114.0, "TAKE_PROFIT_PARTIAL", "RUN-1", AutonomousParameters(), commit=False, sell_pct=25)
    assert trade["action"] == "SELL_PARTIAL"
    assert trade["quantity"] == 25.0 and trade["remaining_quantity"] == 75.0
    assert portfolio["positions"]["WIN"]["quantity"] == 75.0
    assert portfolio["positions"]["WIN"]["partial_take_profit_taken"] is True
    assert _validate_execution_integrity([trade], {}, portfolio)["ok"] is True
