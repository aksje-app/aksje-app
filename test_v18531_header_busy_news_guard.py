from pathlib import Path


def test_version_and_topbar_busy_indicator_present():
    assert 'APP_VERSION = "v18.5.33"' in Path("app_version.py").read_text()
    sticky = Path("sticky_topbar.py").read_text()
    css = Path("workspace_layout.py").read_text()
    assert "global_busy_chip_html" in sticky
    assert "market_statuses" in sticky
    assert "ptw-global-busy-fixed" in css
    assert "Professional Trading Workspace {get_app_version()}" in sticky


def test_active_panel_selector_moved_above_banner():
    source = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    selector = source.index("active_panel = _render_active_main_panel_selector_v18531()")
    banner = source.index("render_live_market_banner()", selector)
    old_caption = source.find("Velg panel. Bare valgt panel beregnes tungt")
    assert selector < banner
    assert old_caption == -1
    assert "_PANEL_OPTIONS_V18531" in source
    assert "🧪 Backtesting" not in source[source.index("_PANEL_OPTIONS_V18531"):source.index("def _on_active_panel_change_v18531")]


def test_newsapi_auto_calls_are_guarded_and_forecast_news_toggle_exists():
    news = Path("news.py").read_text()
    forecast = Path("forecast_ui.py").read_text()
    analysis = Path("analysis.py").read_text()
    assert "NEWSAPI_ALLOW_AUTO_CALLS" in news
    assert "automatisk NewsAPI-kall er slått av" in news
    assert 'source="score_stock"' in analysis
    assert "Bruk nyheter i hendelsesrisiko" in forecast
    assert "include_news=bool(include_news_risk)" in forecast
