from pathlib import Path


def test_legacy_cleanup_registry_is_present():
    from legacy_cleanup import legacy_cleanup_status

    status = legacy_cleanup_status()
    assert status["version"] == "v18.5.35"
    assert "🧪 Backtesting" in status["removed_main_panels"]
    assert "Strategi-test" in status["single_sources"]


def test_old_backtesting_main_panel_removed_from_selector():
    source = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    selector_line = next(line for line in source.splitlines() if line.strip().startswith("_PANEL_OPTIONS_V18531"))
    assert "🧪 Backtesting" not in selector_line
    assert "elif active_panel == \"🧪 Backtesting\"" not in source


def test_legacy_strategy_button_removed_from_analysis_cards():
    source = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    assert "Kjør strategi-test for {selected}" not in source
    assert "strategy_{label}_{selected}" not in source
    assert "Strategi-optimalisering" not in source
    assert "Legacy cleanup: standalone strategy testing" in source


def test_old_visible_duplicate_title_caption_removed():
    source = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    assert "gammel duplikat-tittel er fjernet" not in source
