"""Isolated feed-to-entry regression: no database, network, state writes or orders."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

import super_portfolio as sp
from super_portfolio_market_data import _close_rows


def test_daily_ohlc_survives_compaction_and_normalization():
    dates = pd.to_datetime(["2026-10-09", "2026-10-12"])
    frame = pd.DataFrame(
        {"Open": [98.0, 100.0], "Close": [99.0, 101.0]}, index=dates
    )
    daily = _close_rows(frame, "MOCK.ST", single=True)
    assert daily[1]["date"] == "2026-10-12"
    assert daily[1]["open"] == 100.0
    assert daily[1]["previous_close"] == 99.0

    source = {
        "ticker": "MOCK.ST", "market": "SVERIGE", "last_price": 101.0,
        "session_date": daily[-1]["date"], "session_open": daily[-1]["open"],
        "previous_close": daily[-1]["previous_close"],
    }
    assessment = SimpleNamespace(
        ticker="MOCK.ST", market="SVERIGE", sector="Industrials",
        raw={"last_price": 101.0}, investment_score=80.0, risk_score=20.0,
        data_quality=90.0,
    )
    compact = sp._compact_market_candidate(assessment, source)
    assert compact["raw"]["session_open"] == 100.0
    assert compact["raw"]["previous_close"] == 99.0
    assert compact["raw"]["session_date"] == "2026-10-12"
    normalized = sp._normalized_candidate(compact)
    assert normalized["raw_candidate"]["raw"]["session_open"] == 100.0

    pending = {"entry_signal_date": "2026-10-09"}
    # Date is before the Swedish close, within regular session.
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    reasons, fill = sp._verified_next_session_open(normalized, pending, now)
    assert reasons == []
    assert fill == 100.0
    position = sp._position_from_row(
        dict(normalized, _shadow_entry_fill_price=fill), 1.5, {}, now.isoformat(),
        sp.SuperPortfolioConfig(), []
    )
    assert position["entry_price"] == 100.0
    assert position["entry_price_basis"] == "NEXT_SESSION_OPEN_SHADOW"


def test_live_feed_without_session_date_must_not_fill():
    raw = {"ticker": "MOCK.ST", "market": "SVERIGE", "price": 105.0,
           "source": "Super Portfolio independent market universe",
           "raw": {"session_open": 104.0, "previous_close": 100.0}}
    normalized = sp._normalized_candidate(raw)
    reasons, fill = sp._verified_next_session_open(
        normalized, {"entry_signal_date": "2026-10-09"},
        datetime(2026, 10, 12, 12, tzinfo=timezone.utc),
    )
    assert "ENTRY_OPEN_QUOTE_UNVERIFIED" in reasons
    assert fill == 0.0
