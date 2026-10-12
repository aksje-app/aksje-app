from datetime import datetime, timezone
from autonomous_portfolio import _autonomy_entry_safety


def _candidate(**updates):
    row = dict(ticker="MSFT", session_open=100.0, previous_close=99.0,
               session_date="2026-10-12", entry_signal_date="2026-10-09")
    row.update(updates)
    return row


def test_nyse_before_0930_is_closed():
    # 13:00 UTC = 09:00 EDT
    assert "MARKET_CLOSED" in _autonomy_entry_safety(_candidate(), datetime(2026,10,12,13,0,tzinfo=timezone.utc))[0]


def test_nyse_at_0930_verified_open():
    reason, price = _autonomy_entry_safety(_candidate(), datetime(2026,10,12,13,30,tzinfo=timezone.utc))
    assert reason == "" and price == 100.0


def test_nyse_previous_signal_does_not_reset():
    row = _candidate(entry_signal_date="2026-10-12")
    assert "UNVERIFIED" in _autonomy_entry_safety(row,datetime(2026,10,12,14,tzinfo=timezone.utc))[0]
    row["entry_signal_date"] = "2026-10-09"
    assert _autonomy_entry_safety(row,datetime(2026,10,12,14,tzinfo=timezone.utc))[1] == 100.0


def test_nyse_holiday_closed():
    assert "MARKET_CLOSED" in _autonomy_entry_safety(
        _candidate(session_date="2026-12-25"), datetime(2026,12,25,15,tzinfo=timezone.utc))[0]


def test_missing_quote_never_fills():
    reason, price = _autonomy_entry_safety(_candidate(session_open=None),datetime(2026,10,12,14,tzinfo=timezone.utc))
    assert "UNVERIFIED" in reason and price == 0.0
