from analysis_universe_ai import build_universe_live_status, collect_universe_candidates, filter_universe_candidates


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
                {"ticker": "AAPL", "score": 8.1, "strength": 80, "max_drawdown": -0.12},
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


def test_live_status_contains_real_module_information():
    session_state = {
        "latest_rankings_v148": {
            "USA": [{"ticker": "AAPL", "score": 8.1}],
            "TopPicks_USA": [{"ticker": "MSFT", "score": 8.5}],
        },
        "latest_watchlist_tickers_v156": ["EQNR.OL", "NVDA"],
        "last_update_started_by_v148": "Global oppdatering",
        "last_update_started_at_v148": "2026-05-09 22:00",
    }
    config = {
        "mode": "Markedvalg",
        "scopes": ["USA", "Top Picks"],
        "manual_ticker": "",
        "max_risk": "Middels",
        "min_top_pick_score": 6.5,
        "min_strength": 0,
        "sectors": ["Alle sektorer"],
    }
    candidates = collect_universe_candidates(session_state)
    preview = filter_universe_candidates(candidates, ["USA", "Top Picks"], ["Alle sektorer"], "Middels", 6.5, 0)
    rows = build_universe_live_status(session_state, config, candidates, preview)

    values_by_label = {row["label"]: row["value"] for row in rows}
    assert values_by_label["Watchlist"] == "2 tickere"
    assert values_by_label["Top Picks"] == "1 kandidater"
    assert "totalt" in values_by_label["Kandidater funnet"]
