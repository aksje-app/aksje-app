"""Live provider acceptance check. Never accesses account state or executes orders.

Run in CI with: python -m pytest -q tests/test_superportfolio_live_ohlc_acceptance.py
Uses historical daily OHLC from Yahoo Finance. Failure must block rollout.
"""
from datetime import datetime, timedelta, timezone

import pytest

from super_portfolio_market_data import _download_batch


@pytest.mark.parametrize("symbol", ["MYCR.ST", "MSFT"])
def test_live_daily_ohlc_has_verifiable_open_and_previous_close(symbol):
    start = (datetime.now(timezone.utc) - timedelta(days=25)).date().isoformat()
    history = _download_batch([symbol], start, timeout=20).get(symbol, [])
    assert len(history) >= 5, f"{symbol}: no usable live provider daily history"
    for previous, current in zip(history[:-1], history[1:]):
        assert current["date"] > previous["date"]
        assert current.get("open", 0) > 0, f"{symbol}: open missing for {current['date']}"
        assert current["previous_close"] == pytest.approx(previous["close"])
    latest = history[-1]
    assert latest["close"] > 0
    assert latest["open"] > 0
    assert latest["previous_close"] > 0
    assert (datetime.now(timezone.utc).date() - datetime.fromisoformat(latest["date"]).date()).days <= 7
