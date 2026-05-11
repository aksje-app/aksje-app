from pathlib import Path


def test_storage_service_reports_local_fallback_and_roundtrips(tmp_path):
    from services.storage_service import StorageService

    storage = StorageService(base_dir=str(tmp_path / "services"), database_url="")
    status = storage.status_dict()
    assert status["backend"] == "local_json_fallback"
    assert status["persistent"] is False

    used_pg = storage.write_json("settings/example.json", {"ok": True})
    assert used_pg is False
    assert storage.read_json("settings/example.json") == {"ok": True}

    storage.append_jsonl("alerts/events.jsonl", {"ticker": "AAPL"})
    assert storage.read_jsonl("alerts/events.jsonl") == [{"ticker": "AAPL"}]


def test_paper_store_local_fallback_uses_storage_service_not_root_file(tmp_path, monkeypatch):
    from services.storage_service import StorageService
    import paper_store

    storage = StorageService(base_dir=str(tmp_path / "services"), database_url="")
    monkeypatch.setattr(paper_store, "DATABASE_URL", "")
    monkeypatch.setattr(paper_store, "STORE_FILE", tmp_path / "paper_portfolio.json")
    monkeypatch.setattr(paper_store, "_storage", lambda: storage)

    portfolio = {"cash": 12345.0, "positions": {"AAPL": {"shares": 1, "last_price": 200}}, "trades": []}
    saved_db = paper_store.save_portfolio(portfolio)

    assert saved_db is False
    assert not (tmp_path / "paper_portfolio.json").exists()
    loaded = paper_store.load_portfolio()
    assert loaded["cash"] == 12345.0
    assert "AAPL" in loaded["positions"]


def test_persistent_storage_status_lists_core_runtime_categories():
    from persistent_storage_status import storage_status_snapshot

    snap = storage_status_snapshot()
    categories = {row["category"] for row in snap["categories"]}
    expected = {
        "learning_stats",
        "forecast_logs",
        "forecast_alerts/event_risk",
        "score_explanations",
        "watchlist",
        "paper_trading",
        "active_smart_universe",
        "strategy_testing",
        "signal_alert_state",
    }
    assert expected.issubset(categories)
