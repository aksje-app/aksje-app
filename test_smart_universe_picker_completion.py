from services.state_service import get_state_service
from services.storage_service import StorageService
from services.universe_service import ACTIVE_UNIVERSE_RANKING_KEY, UniverseService
from universe_engine import run_smart_ai_universe


FAKE_DATA = {
    "AAPL": {"ticker": "AAPL", "score": 8.0, "sector": "Technology", "volatility": 0.01, "max_drawdown": -0.1},
    "MSFT": {"ticker": "MSFT", "score": 7.5, "sector": "Technology", "volatility": 0.01, "max_drawdown": -0.1},
    "NVDA": {"ticker": "NVDA", "score": 8.6, "sector": "Technology", "volatility": 0.02, "max_drawdown": -0.15},
}


def fake_score_provider(ticker, use_news=False):
    return FAKE_DATA.get(ticker)


def make_service(tmp_path, session_state):
    return UniverseService(
        state_service=get_state_service(session_state),
        storage_service=StorageService(base_dir=str(tmp_path), database_url=""),
        score_provider=fake_score_provider,
    )


def test_picker_resolves_manual_list_and_persists_active_universe(tmp_path):
    session_state = {}
    service = make_service(tmp_path, session_state)

    result = service.save_active_universe({
        "mode": "Manuell liste",
        "scopes": ["Manuell liste"],
        "manual_list": "aapl, msft\nNVDA",
        "max_count": 10,
    })

    assert result.ok
    assert result.data["tickers"] == ["AAPL", "MSFT", "NVDA"]
    assert session_state["smart_universe_picker_tickers_v18517"] == ["AAPL", "MSFT", "NVDA"]
    assert ACTIVE_UNIVERSE_RANKING_KEY in session_state["latest_rankings_v148"]

    loaded = service.load_active_universe()
    assert loaded.data["source"] == "Manuell liste"


def test_picker_resolves_all_non_market_sources(tmp_path):
    session_state = {
        "latest_rankings_v148": {"TopPicks_Alle": [{"ticker": "AAPL"}]},
        "latest_watchlist_tickers_v156": ["MSFT"],
        "paper_positions": {"NVDA": {"qty": 1}},
        "portfolio": {"AAPL": {"qty": 2}},
    }
    service = make_service(tmp_path, session_state)

    cases = {
        "Top Picks": ["AAPL"],
        "Watchlist": ["MSFT"],
        "Paper trading": ["NVDA"],
        "Portefølje": ["AAPL"],
        "Enkeltaksje": ["MSFT"],
    }
    for mode, expected in cases.items():
        config = {"mode": mode, "scopes": [mode], "manual_ticker": "msft", "max_count": 5}
        resolved = service.resolve_picker(config)
        assert resolved.ok
        assert resolved.data["tickers"] == expected


def test_smart_ai_engine_uses_manual_list_when_mode_is_manual_list():
    result = run_smart_ai_universe(
        {
            "mode": "Manuell liste",
            "scopes": ["Manuell liste"],
            "manual_list": "NVDA AAPL",
            "max_count": 5,
            "max_risk": "Ukjent",
            "min_top_pick_score": 0,
        },
        existing_tickers_by_scope={},
        score_provider=fake_score_provider,
    )

    assert result["scanned"] == 2
    assert {row["ticker"] for row in result["candidates"]} == {"AAPL", "NVDA"}
