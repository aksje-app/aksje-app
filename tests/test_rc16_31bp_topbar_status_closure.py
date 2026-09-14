from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_version_bumped_to_bp():
    import app_version
    assert app_version.APP_VERSION == "v19.22.0-rc16.31bp"
    assert app_version.PREVIOUS_APP_VERSION == "v19.22.0-rc16.31bo"


def test_regime_and_macro_persist_topbar_snapshots():
    regime = (ROOT / "market_regime_ui.py").read_text(encoding="utf-8")
    macro = (ROOT / "macro_rates_breadth_ui.py").read_text(encoding="utf-8")
    assert 'save_status("market_regime", payload)' in regime
    assert 'load_status("market_regime")' in regime
    assert 'save_status("macro_rates_breadth", payload)' in macro
    assert 'load_status("macro_rates_breadth")' in macro


def test_topbar_reads_durable_regime_and_macro():
    source = (ROOT / "sticky_topbar.py").read_text(encoding="utf-8")
    assert 'load_status("market_regime")' in source
    assert 'load_status("macro_rates_breadth")' in source
    assert 'compact_time' in source


def test_learning_topbar_uses_controlled_learning_engine():
    source = (ROOT / "sticky_topbar.py").read_text(encoding="utf-8")
    assert 'from learning_observation_engine import load_engine_state' in source
    assert 'active = int(daily.get("active") or 0)' in source
    assert 'completed_at' in source
    assert 'Learning: {learning}' in source


def test_status_store_uses_persistent_storage_service():
    source = (ROOT / "topbar_status_store.py").read_text(encoding="utf-8")
    assert 'get_storage_service' in source
    assert 'storage.write_json' in source
    assert 'storage.read_json' in source
