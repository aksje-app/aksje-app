from analysis_universe_ai import collect_universe_candidates, filter_universe_candidates


def test_collect_candidates_from_existing_rankings_only():
    session_state = {
        "latest_rankings_v148": {
            "USA": [
                {"ticker": "AAPL", "score": 8.1, "max_drawdown": -0.12},
                {"ticker": "MSFT", "score": 7.2, "max_drawdown": -0.21},
            ]
        },
        "latest_watchlist_tickers_v156": ["EQNR.OL"],
    }

    candidates = collect_universe_candidates(session_state)
    tickers = {c.ticker for c in candidates}

    assert "AAPL" in tickers
    assert "MSFT" in tickers
    assert "EQNR.OL" in tickers


def test_filter_candidates_respects_scope_risk_and_strength():
    session_state = {
        "latest_rankings_v148": {
            "USA": [
                {"ticker": "AAPL", "score": 8.1, "max_drawdown": -0.12},
                {"ticker": "LOW", "score": 4.2, "max_drawdown": -0.55},
            ],
            "Norge": [
                {"ticker": "EQNR.OL", "score": 7.0, "max_drawdown": -0.20},
            ],
        }
    }
    candidates = collect_universe_candidates(session_state)
    filtered = filter_universe_candidates(
        candidates,
        scopes=["USA"],
        sectors=["Alle sektorer"],
        max_risk="Middels",
        min_score=6.0,
        min_strength=50.0,
    )

    assert [c.ticker for c in filtered] == ["AAPL"]
