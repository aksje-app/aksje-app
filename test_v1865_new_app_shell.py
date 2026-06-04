from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def test_version_identifies_current_consolidation_round():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8", errors="ignore")

    assert 'APP_VERSION = "v18.6.20"' in version
    assert "Saerskilt banner under hovedbanner og stabilt panelvalg" in version
    assert "v18615-banner-import-paper-tests" in version


def test_market_room_is_the_single_market_workspace():
    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")

    assert "def render_market_room_control_center_v1863cb" in app
    assert '("Marked", render_market_room_control_center_v1863cb)' in app
    assert '["Oversikt", "Rangering", "Heatmap", "Markedsklima", "Lagrede signaler", "IPO", "Regime", "Makro", "Nyheter"]' in app
    assert "render_market_ranking_control_center_v18535(selected_market=" in app
    assert "render_market_climate_panel()" in app
    assert "render_market_intelligence_center()" in app
    assert "render_ipo()" in app
    assert "render_market_regime_widget()" in app
    assert "render_macro_rates_breadth_panel()" in app
    assert "render_news_control_center_v18535()" in app


def test_alerts_watchlist_is_the_single_alert_workspace():
    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")

    assert "def render_alerts_watchlist_control_center_v1869" in app
    assert 'st.tabs(["Varselsenter", "Watchlist / signaler", "Valutavarsler"])' in app
    assert 'render_common_alert_center(location="alerts_watchlist_v1869")' in app
    assert "render_watchlist_signals_control_center_v18535()" in app
    assert "render_currency_alerts_control_center_v1863af()" in app
    assert '"Varsler og watchlist", render_alerts_watchlist_control_center_v1869' in app


def test_control_center_filters_old_standalone_panels():
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    active_layout = layout.split("def _render_ai_control_center_v1863aj", 1)[1]

    assert '("Varsler", lambda: render_common_alert_center(location="workspace"))' not in active_layout
    assert '("Intelligence", render_market_intelligence_center)' not in active_layout
    assert '("Heatmaps", render_ai_heatmaps)' not in active_layout
    assert '("Regime", render_market_regime_widget)' not in active_layout
    assert '("Makro/renter", render_macro_rates_breadth_panel)' not in active_layout
    assert '("Services", _render_storage_services_status)' not in active_layout
    assert '"Marked og signaler": _matching_panel_labels("marked", "varsler og watchlist", "top picks", "beslut", "muligheter", "alpha")' in active_layout

    for hidden in [
        "markedsklima",
        "ipo",
        "nyheter",
        "marked/rangering",
        "watchlist/signaler",
        "valutavarsler",
    ]:
        assert hidden in app
    assert "legacy_hidden_tokens" in app


def test_legacy_cleanup_registry_documents_hidden_panels():
    for name in ["app.py", "workspace_layout.py", "app_version.py", "legacy_cleanup.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

    from legacy_cleanup import legacy_cleanup_status

    status = legacy_cleanup_status()
    assert status["version"] == "v18.6.20"
    for label in ["Markedsklima", "IPO", "Nyheter", "Marked/rangering", "Watchlist/signaler", "Valutavarsler", "Services"]:
        assert label in status["removed_main_panels"]
    assert "Marked/rangering" in status["single_sources"]
    assert "cleanup_candidates" in status and status["cleanup_candidates"]





