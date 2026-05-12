from core_models import StockCandidate, UniverseRequest, UniverseResult
from services.service_registry import build_service_registry


FAKE_DATA = {
    "AAPL": {
        "ticker": "AAPL",
        "name": "Apple",
        "score": 8.0,
        "score_parts": {"momentum": 0.8, "trend": 0.75, "volume": 0.5},
        "volatility": 0.018,
        "max_drawdown": -0.12,
        "sentiment": 0.6,
        "sector": "Technology",
    },
    "MSFT": {
        "ticker": "MSFT",
        "name": "Microsoft",
        "score": 7.2,
        "score_parts": {"momentum": 0.7, "trend": 0.7, "volume": 0.5},
        "volatility": 0.017,
        "max_drawdown": -0.16,
        "sentiment": 0.5,
        "sector": "Technology",
    },
}


def fake_score_provider(ticker, use_news=False):
    return FAKE_DATA.get(ticker)


def test_universe_request_normalizes_shared_model():
    request = UniverseRequest.from_config({
        "mode": "Smart AI-utvalg",
        "scopes": ["Watchlist"],
        "manual_ticker": " aapl ",
        "max_count": 999,
        "max_risk": "Middels",
        "sectors": ["Technology"],
    })
    assert request.manual_ticker == "AAPL"
    assert request.max_count == 250
    assert request.scopes == ["Watchlist"]


def test_universe_service_runs_engine_and_stores_shared_result():
    session_state = {"latest_watchlist_tickers_v156": ["MSFT", "AAPL"]}
    services = build_service_registry(session_state, score_provider=fake_score_provider)
    service_result = services.universe.run_smart_universe({
        "scopes": ["Watchlist"],
        "max_count": 5,
        "max_risk": "Middels",
        "sectors": ["Technology"],
        "min_top_pick_score": 6.0,
        "min_strength": 50,
    })

    assert service_result.status == "ok"
    result = service_result.data["result"]
    assert result["version"] == "v18.5.36"
    assert result["matched_candidates"] == 2
    assert "ai_analysis_universe_smart_result_v1859" in session_state
    assert "SmartAI" in session_state["latest_rankings_v148"]


def test_top_picks_and_watchlist_services_use_same_result_shape():
    candidate = StockCandidate(ticker="AAPL", ai_score=8.0, smart_score=75, strength=80, risk="Lav", source="Smart AI")
    result = UniverseResult(request=UniverseRequest(scopes=["Watchlist"]), candidates=[candidate], top_picks=[candidate]).as_dict()
    session_state = {}
    services = build_service_registry(session_state)

    top_result = services.top_picks.save_from_universe_result(result)
    watch_result = services.watchlist.set_from_candidates(result)

    assert top_result.ok
    assert watch_result.ok
    assert session_state["latest_rankings_v148"]["TopPicks_SmartAI"][0]["ticker"] == "AAPL"
    assert session_state["latest_watchlist_tickers_v156"] == ["AAPL"]
