from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_version_identifies_new_app_shell():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")

    assert 'APP_VERSION = "v18.6.5c"' in version
    assert "App Shell Menu Recovery" in version
    assert "v1865c-app-shell-menu-recovery" in version


def test_left_navigation_routes_directly_to_main_rooms():
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "APP_SHELL_PAGE_KEY_V1865" in app
    assert '"Marked")' in app
    assert '"Testflyt")' in app
    assert "def _render_app_shell_sidebar_v1865" in app
    assert 'render_market_room_control_center_v1863cb()' in app
    assert 'render_analysis_pipeline_control_center_v1863bv()' in app
    assert 'render_ai_analysis_universe_workspace(expanded=True)' in app
    assert 'render_mixed_portfolio_control_center_v18544()' in app
    assert 'render_decision_support_panel()' in app
    assert 'Gammelt Kontrollsenter / fallback' in app
    assert "render_ai_control_center(extra_panels=control_center_extra_panels_v18535())" in app
    assert "APP_SHELL_SUBPAGES_V1865C" in app


def test_analysis_flow_input_clamps_candidate_slider():
    module = (ROOT / "analysis_universe_ai.py").read_text(encoding="utf-8")

    assert "def _analysis_flow_input_count_for_smart_ai()" in module
    assert 'if mode == "Analyseflyt input":' in module
    assert "slider_max = max(1, flow_input_count)" in module
    assert "ikke flere enn pakken som kom inn" in module


def test_pipeline_pending_navigation_is_consumed_by_app_shell():
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "APP_SHELL_ACTIVE_STAGE_KEY_V1865A" in app
    assert "def _apply_pending_pipeline_nav_v1865a()" in app
    assert "def _render_pipeline_stage_shell_v1865a(stage_id: str)" in app
    assert 'st.session_state["app_shell_active_pipeline_stage_v1865a"] = stage_id' in app
    assert '"smart_ai": "Analyse"' in app
    assert "render_ai_analysis_universe_workspace(expanded=True)" in app
    assert "if not _render_pipeline_stage_shell_v1865a(_shell_stage_v1865a)" in app


def test_dataunderlag_and_testflyt_are_distinct_shell_rooms():
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "def _render_data_foundation_only_shell_v1865c()" in app
    assert "def _render_pipeline_overview_shell_v1865c()" in app
    assert 'elif _shell_page_v1865 == "Dataunderlag":' in app
    assert "_render_data_foundation_only_shell_v1865c()" in app
    assert 'elif _shell_page_v1865 == "Testflyt":' in app
    assert '"Pipeline 1-10"' in app
    assert '"Test 3 Smart AI-filter": "smart_ai"' in app


def test_shell_submenus_restore_hidden_tools():
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    for label in [
        "Finansavisen Bjellesauer",
        "Oljefond/NBIM",
        "Aktorregister",
        "Interaktiv analyse",
        "Valutavarsler",
        "Watchlist/signaler",
        "Fond / ETF",
        "Gammelt Kontrollsenter",
    ]:
        assert label in app


