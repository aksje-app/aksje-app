from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_version_identifies_new_app_shell():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")

    assert 'APP_VERSION = "v18.6.5"' in version
    assert "New App Shell Left Navigation" in version
    assert "v1865-new-app-shell-left-navigation" in version


def test_left_navigation_routes_directly_to_main_rooms():
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "APP_SHELL_PAGE_KEY_V1865" in app
    assert '("Marked", "◎", "Marked")' in app
    assert '("Testflyt", "▦", "Testflyt")' in app
    assert "def _render_app_shell_sidebar_v1865" in app
    assert 'render_market_room_control_center_v1863cb()' in app
    assert 'render_analysis_pipeline_control_center_v1863bv()' in app
    assert 'render_ai_analysis_universe_workspace(expanded=True)' in app
    assert 'render_mixed_portfolio_control_center_v18544()' in app
    assert 'render_decision_support_panel()' in app
    assert 'Gammelt Kontrollsenter / fallback' in app
    assert "render_ai_control_center(extra_panels=control_center_extra_panels_v18535())" in app
    assert "Gammelt Kontrollsenter ligger under Admin" in app
