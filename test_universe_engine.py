from universe_engine import (
    candidate_dicts_for_app,
    resolve_universe_tickers,
    run_smart_ai_universe,
)


FAKE_DATA = {
    "AAPL": {
        "ticker": "AAPL",
        "name": "Apple",
        "score": 8.2,
        "score_parts": {"momentum": 0.82, "trend": 0.78, "volume": 0.55},
        "ret_1m": 0.05,
        "ret_3m": 0.14,
        "ret_6m": 0.24,
        "volatility": 0.018,
        "max_drawdown": -0.12,
        "sentiment": 0.65,
        "sector": "Technology",
    },
    "MSFT": {
        "ticker": "MSFT",
        "name": "Microsoft",
        "score": 7.4,
        "score_parts": {"momentum": 0.70, "trend": 0.72, "volume": 0.55},
        "ret_1m": 0.02,
        "ret_3m": 0.09,
        "ret_6m": 0.18,
        "volatility": 0.016,
        "max_drawdown": -0.15,
        "sentiment": 0.55,
        "sector": "Technology",
    },
    "WEAK": {
        "ticker": "WEAK",
        "name": "Weak Co",
        "score": 4.1,
        "score_parts": {"momentum": 0.25, "trend": 0.30, "volume": 0.40},
        "ret_1m": -0.04,
        "ret_3m": -0.12,
        "ret_6m": -0.20,
        "volatility": 0.055,
        "max_drawdown": -0.55,
        "sentiment": 0.35,
        "sector": "Technology",
    },
}


def fake_score_provider(ticker, use_news=False):
    return FAKE_DATA.get(ticker)


def test_resolve_universe_uses_existing_watchlist_scope():
    tickers = resolve_universe_tickers(
        scopes=["Watchlist"],
        max_count=10,
        existing_tickers_by_scope={"Watchlist": ["AAPL", "MSFT", "AAPL"]},
    )
    assert tickers == ["AAPL", "MSFT"]


def test_run_smart_ai_universe_filters_and_ranks_candidates():
    config = {
        "scopes": ["Watchlist"],
        "max_count": 5,
        "manual_ticker": "",
        "use_news": False,
        "max_risk": "Middels",
        "sectors": ["Technology"],
        "min_top_pick_score": 6.5,
        "min_strength": 50,
    }
    result = run_smart_ai_universe(
        config,
        existing_tickers_by_scope={"Watchlist": ["WEAK", "MSFT", "AAPL"]},
        score_provider=fake_score_provider,
    )

    assert result["status"] == "ok"
    assert result["matched_candidates"] == 2
    assert [row["ticker"] for row in result["candidates"]] == ["AAPL", "MSFT"]
    assert result["candidates"][0]["smart_score"] >= result["candidates"][1]["smart_score"]


def test_candidate_dicts_for_app_are_compatible_with_rank_cache():
    result = run_smart_ai_universe(
        {"scopes": ["Watchlist"], "max_count": 2, "min_top_pick_score": 0, "max_risk": "Ukjent"},
        existing_tickers_by_scope={"Watchlist": ["AAPL"]},
        score_provider=fake_score_provider,
    )
    rows = candidate_dicts_for_app(result)
    assert rows[0]["ticker"] == "AAPL"
    assert "score" in rows[0]
    assert rows[0]["source"] == "Smart AI"
