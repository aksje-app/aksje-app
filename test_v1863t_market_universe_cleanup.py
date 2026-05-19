from universe_engine import resolve_universe_tickers
from services.universe_service import _extract_non_legacy_tickers, _legacy_seed_only


def test_new_markets_resolve_real_ticker_lists():
    assert resolve_universe_tickers(["Finland"], max_count=5)[0].endswith(".HE")
    assert resolve_universe_tickers(["Danmark"], max_count=5)[0].endswith(".CO")
    assert resolve_universe_tickers(["Brasil"], max_count=5)[0].endswith(".SA")


def test_norden_contains_four_nordic_markets():
    tickers = resolve_universe_tickers(["Norden"], max_count=16)
    assert any(t.endswith(".OL") for t in tickers)
    assert any(t.endswith(".ST") for t in tickers)
    assert any(t.endswith(".HE") for t in tickers)
    assert any(t.endswith(".CO") for t in tickers)
    assert not any(t.endswith(".SA") for t in tickers)


def test_alle_contains_brazil_as_own_market():
    tickers = resolve_universe_tickers(["Alle"], max_count=18)
    assert any(t.endswith(".SA") for t in tickers)
    assert any(t.endswith(".HE") for t in tickers)
    assert any(t.endswith(".CO") for t in tickers)


def test_legacy_seed_only_storage_is_ignored():
    legacy_rows = [{"ticker": "AAPL"}, {"ticker": "STB.OL"}]
    current_rows = [{"ticker": "VOLV-B.ST"}, {"ticker": "NOKIA.HE"}]

    assert _legacy_seed_only(legacy_rows) is True
    assert _extract_non_legacy_tickers(legacy_rows) == []
    assert _legacy_seed_only(current_rows) is False
    assert _extract_non_legacy_tickers(current_rows) == ["VOLV-B.ST", "NOKIA.HE"]


def test_empty_scope_does_not_fall_back_to_usa():
    assert resolve_universe_tickers([], max_count=5) == []


def test_picker_empty_scope_stays_empty(tmp_path):
    from services.state_service import get_state_service
    from services.storage_service import StorageService
    from services.universe_service import UniverseService

    service = UniverseService(
        state_service=get_state_service({}),
        storage_service=StorageService(base_dir=str(tmp_path), database_url=""),
        score_provider=lambda ticker, use_news=False: None,
    )
    resolved = service.resolve_picker({"mode": "Markedvalg", "scopes": [], "max_count": 30})
    assert resolved.ok
    assert resolved.status == "empty"
    assert resolved.data["tickers"] == []
