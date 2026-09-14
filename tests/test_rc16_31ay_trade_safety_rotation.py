from datetime import datetime, timedelta

from exit_policy import evaluate_exit
from trading_engine import _automatic_repeat_buy_block_v1931ay, _automatic_signal_fresh_v1931ay, _reentry_block_v1931ay


def _sell(*, ticker="FRO.OL", when, price=411.50, reason="PAPER-SALG: SELL signal", rule="SELL/AVOID signal"):
    return {
        "type": "SELL",
        "ticker": ticker,
        "time": when.isoformat(timespec="seconds"),
        "price": price,
        "confidence": 80,
        "reason": reason,
        "rule_used": rule,
    }


def test_fro_roundtrip_is_blocked_after_ordinary_sell():
    now = datetime(2026, 9, 2, 11, 12)
    portfolio = {"trades": [_sell(when=datetime(2026, 9, 2, 9, 2))]}
    blocked, message = _reentry_block_v1931ay(
        portfolio, "FRO.OL", 79,
        {"sell_signal_cooldown_days": 5, "risk_exit_cooldown_days": 10},
        buy_price=416.20, now=now,
    )
    assert blocked is True
    assert "karantene" in message.lower()


def test_risk_exit_uses_longer_quarantine():
    now = datetime(2026, 9, 9, 12, 0)
    sold = _sell(when=datetime(2026, 9, 2, 12, 0), reason="Trailing stop -2.40%", rule="Trailing stop")
    blocked, message = _reentry_block_v1931ay(
        {"trades": [sold]}, "FRO.OL", 90,
        {"sell_signal_cooldown_days": 5, "risk_exit_cooldown_days": 10},
        buy_price=400, now=now,
    )
    assert blocked is True
    assert "risikoutgang" in message.lower()


def test_other_ticker_is_not_blocked_by_fro_sell():
    now = datetime(2026, 9, 2, 11, 12)
    blocked, _ = _reentry_block_v1931ay(
        {"trades": [_sell(when=datetime(2026, 9, 2, 9, 2))]}, "DNB.OL", 79,
        {"sell_signal_cooldown_days": 5}, buy_price=200, now=now,
    )
    assert blocked is False


def test_automatic_trade_requires_fresh_timestamp():
    now = datetime(2026, 9, 2, 12, 0)
    ok, _ = _automatic_signal_fresh_v1931ay(
        {"automatic": True, "market_data_at": (now - timedelta(minutes=30)).isoformat()},
        {"automatic_signal_max_age_minutes": 120}, now=now,
    )
    assert ok is True
    stale, message = _automatic_signal_fresh_v1931ay(
        {"automatic": True, "market_data_at": (now - timedelta(minutes=121)).isoformat()},
        {"automatic_signal_max_age_minutes": 120}, now=now,
    )
    assert stale is False
    assert "gamle" in message
    missing, _ = _automatic_signal_fresh_v1931ay(
        {"automatic": True}, {"automatic_signal_max_age_minutes": 120}, now=now,
    )
    assert missing is False


def test_manual_trade_is_not_rejected_for_missing_automatic_timestamp():
    ok, message = _automatic_signal_fresh_v1931ay({"automatic": False}, {}, now=datetime(2026, 9, 2))
    assert ok is True
    assert message == ""


def test_repeated_automatic_buy_is_blocked_across_cron_runs():
    now = datetime(2026, 9, 2, 12, 0)
    portfolio = {"trades": [{"type": "BUY", "ticker": "FRO.OL", "time": (now - timedelta(hours=2)).isoformat()}]}
    blocked, message = _automatic_repeat_buy_block_v1931ay(
        portfolio, "FRO.OL", {"automatic_same_ticker_buy_cooldown_hours": 24}, now=now,
    )
    assert blocked is True
    assert "tilleggskjøp" in message.lower()


def test_40_day_weak_position_is_cash_review_without_replacement():
    decision = evaluate_exit(
        entry_price=100,
        current_price=100.5,
        highest_price=104,
        entry_score=78,
        current_score=70,
        holding_days=43,
        best_replacement_score=None,
        policy={
            "stop_loss_pct": 5,
            "trailing_stop_pct": 99,
            "take_profit_pct": 99,
            "score_exit_threshold": 55,
            "score_drop_review_points": 7,
            "stagnation_days": 20,
            "stagnation_band_pct": 2,
            "cash_review_days": 40,
            "cash_review_max_return_pct": 1,
        },
    )
    assert decision["action"] == "CASH_REVIEW"
    assert decision["reason_code"] == "OPPORTUNITY_COST"


def test_profitable_position_is_not_forced_to_cash():
    decision = evaluate_exit(
        entry_price=100, current_price=106, highest_price=106,
        entry_score=78, current_score=72, holding_days=43,
        policy={"stop_loss_pct": 5, "trailing_stop_pct": 99, "take_profit_pct": 99,
                "score_exit_threshold": 55, "score_drop_review_points": 7,
                "stagnation_days": 20, "stagnation_band_pct": 2,
                "cash_review_days": 40, "cash_review_max_return_pct": 1},
    )
    assert decision["action"] in {"HOLD", "REVIEW"}
