from datetime import datetime, timedelta, timezone

import pandas as pd

from scanner_fresh_quote import fresh_paper_buy_quote


NOW = datetime(2026, 9, 25, 16, 20, tzinfo=timezone.utc)


def history(at, price=100.0):
    return pd.DataFrame({"Close": [price]}, index=pd.DatetimeIndex([at]))


def test_fresh_intraday_quote_keeps_price_and_utc_observation_together():
    local = NOW.astimezone(timezone(timedelta(hours=-4))) - timedelta(minutes=5)
    quote, reason = fresh_paper_buy_quote("GOOGL", history_provider=lambda _: history(local, 101.25), now=NOW)
    assert reason == ""
    assert quote["price"] == 101.25
    assert quote["market_data_at"] == "2026-09-25T16:15:00+00:00"


def test_absent_stale_future_and_naive_bars_never_become_fresh_orders():
    candidates = [
        pd.DataFrame(),
        history(NOW - timedelta(minutes=121)),
        history(NOW + timedelta(minutes=6)),
        history(NOW.replace(tzinfo=None)),
        history(NOW, price=float("nan")),
    ]
    for frame in candidates:
        quote, reason = fresh_paper_buy_quote("LLY", history_provider=lambda _, data=frame: data, now=NOW)
        assert quote is None and reason


def test_provider_failure_does_not_fabricate_market_time():
    def unavailable(_):
        raise TimeoutError("provider timeout")

    quote, reason = fresh_paper_buy_quote("GOOGL", history_provider=unavailable, now=NOW)
    assert quote is None and "verifisere" in reason


def test_stale_five_minute_bar_retries_one_minute_with_real_timestamp(monkeypatch):
    import scanner_fresh_quote as module
    calls = []
    def fetch(ticker, interval="5m"):
        calls.append((ticker, interval))
        if interval == "5m":
            return history(NOW - timedelta(minutes=21), 98)
        return history(NOW - timedelta(minutes=4), 101)
    monkeypatch.setattr(module, "_intraday_history", fetch)
    quote, error = module.fresh_paper_buy_quote("KCC.OL", now=NOW)
    assert error == ""
    assert quote["source"] == "yfinance 1m Close"
    assert quote["market_data_at"] == (NOW - timedelta(minutes=4)).isoformat(timespec="seconds")
    assert calls == [("KCC.OL", "5m"), ("KCC.OL", "1m")]


def test_stale_both_intervals_stays_blocked(monkeypatch):
    import scanner_fresh_quote as module
    monkeypatch.setattr(module, "_intraday_history",
                        lambda ticker, interval="5m": history(NOW - timedelta(minutes=21)))
    quote, error = module.fresh_paper_buy_quote("GOD.OL", now=NOW)
    assert quote is None
    assert "gammel" in error


def test_one_minute_quote_accepted_with_same_strict_fifteen_minute_limit():
    from scanner_fresh_quote import validate_execution_quote
    quote = {"price": 101, "market_data_at": (NOW - timedelta(minutes=8)).isoformat(),
             "source": "yfinance 1m Close", "adjustment": "raw"}
    assert validate_execution_quote(101, {"execution_quote": quote, "market_data_at": quote["market_data_at"]}, now=NOW)[0]
    late = NOW + timedelta(minutes=8)
    assert not validate_execution_quote(101, {"execution_quote": quote, "market_data_at": quote["market_data_at"]}, now=late)[0]
