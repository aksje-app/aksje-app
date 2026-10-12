"""Autonomy safety regression. No broker, account state, or live market calls."""
from datetime import datetime, timezone
from unittest.mock import patch

import autonomous_portfolio as ap


def _now():
    return datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)


def test_no_unverified_same_day_buy():
    candidate = dict(ticker="MSFT", session_open=100, previous_close=99,
                     session_date="2026-10-12", entry_signal_date="2026-10-12")
    reason, price = ap._autonomy_entry_safety(candidate, _now())
    assert "UNVERIFIED" in reason and price == 0


def test_next_session_verified_open_only():
    candidate = dict(ticker="MSFT", session_open=100, previous_close=99,
                     session_date="2026-10-12", entry_signal_date="2026-10-09")
    reason, price = ap._autonomy_entry_safety(candidate, _now())
    assert reason == "" and price == 100


def test_chase_and_gap_rejected():
    base = dict(ticker="MSFT", session_open=102, previous_close=100,
                session_date="2026-10-12", entry_signal_date="2026-10-09")
    assert "GAP" in ap._autonomy_entry_safety(base, _now())[0]
    assert "CHASE_1D" in ap._autonomy_entry_safety(dict(base, return_1d=7.0), _now())[0]
    assert "CHASE_5D" in ap._autonomy_entry_safety(dict(base, return_5d=15.0), _now())[0]


def test_weekend_never_buys():
    candidate = dict(ticker="MSFT", session_open=100, previous_close=99,
                     session_date="2026-10-11", entry_signal_date="2026-10-09")
    reason, price = ap._autonomy_entry_safety(candidate, datetime(2026, 10, 11, 14, tzinfo=timezone.utc))
    assert "MARKET_CLOSED" in reason and price == 0


def test_stop_loss_not_overridden_by_score_or_breakout():
    trades = [{"ticker":"SSAB-A.ST","action":"SELL","timestamp":"2026-10-09T12:00:00+00:00",
               "reason":"STOP_LOSS: loss","exit_score":40}]
    with patch.object(ap, "_read", return_value=trades), patch.object(ap, "_days_opened", return_value=1):
        blocked, message = ap._reentry_cooldown(
            {"ticker":"SSAB-A.ST", "breakout_holding":True, "entry_score":99}, ap.AutonomousParameters()
        )
    assert blocked and "QUARANTINE" in message
