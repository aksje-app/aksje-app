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
