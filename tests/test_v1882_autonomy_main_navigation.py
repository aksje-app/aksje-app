from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FakeStreamlit:
    def __init__(self, params):
        self.query_params = dict(params)


def test_new_autonomy_url_is_canonical():
    from navigation_state import get_global_navigation_state

    state = get_global_navigation_state(FakeStreamlit({
        "aa_nav": "autonomy", "aa_group": "Autonomi",
        "aa_panel": "🧠 Autonomi – Kontrollsenter", "aa_tab": "orchestrator",
    }))
    assert state == {
        "nav": "autonomy", "group": "Autonomi",
        "panel": "🧠 Autonomi – Kontrollsenter", "tab": "orchestrator", "subtab": "",
    }


def test_old_learning_portfolio_url_maps_to_new_workspace():
    from navigation_state import get_global_navigation_state

    state = get_global_navigation_state(FakeStreamlit({
        "mobile_nav": "autonomous", "aa_group": "Testing og portefølje",
        "panel": "🧠 Autonomi – Learning Portfolio",
    }))
    assert state["nav"] == "autonomy"
    assert state["group"] == "Autonomi"
    assert state["panel"] == "🧠 Autonomi – Kontrollsenter"
    assert state["tab"] == "learning_portfolio"


def test_old_orchestrator_url_maps_to_new_workspace():
    from navigation_state import normalize_navigation_values

    state = normalize_navigation_values(
        "autonomi", "Andre paneler", "🚦 Autonomi – Orchestrator & Scheduler", "", ""
    )
    assert state["nav"] == "autonomy"
    assert state["tab"] == "orchestrator"


def test_responsive_sidebar_is_single_navigation_surface():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert '"autonomy": _mobile_nav_href_v18646("autonomy")' in source
    assert "Do not inject a second mobile/navigation DOM into the main page" in source
    assert "showSidebarNavigation = false" in config
    href_block = source[source.index("def _mobile_nav_href_v18646"):source.index("def _ui_state_path_v18658")]
    assert 'params.pop(key, None)' in href_block


def test_fresh_mobile_tap_has_priority_over_refresh_state():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def _apply_mobile_nav_query_v18646")
    block = source[start:source.index("show_drift_controls_v1863cc", start)]
    assert block.index('params.get("mobile_nav")') < block.index("get_global_navigation_state(st)")


def test_desktop_and_app_targets_use_same_route():
    sidebar = (ROOT / "ui_sidebar_stable.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '"🧠 Autonomi", "autonomy"' in sidebar
    assert 'elif nav == "autonomy":' in app
    assert '"🧠 Autonomi – Kontrollsenter"' in app


def test_refresh_restores_autonomy_workspace_slug():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    autonomy = (ROOT / "pages" / "autonomy.py").read_text(encoding="utf-8")
    assert 'apply_route_tab_to_session_state_v19220_rc7(' in source
    assert 'saved = normalize_navigation_values(' in source
    assert 'st.session_state["autonomy_core_workspace_v1880"] = workspace_labels[requested_workspace]' in autonomy
    assert 'tab=workspace_slug' in autonomy


def test_learning_and_orchestrator_are_lazy_in_one_panel():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def render_autonomy_core_control_center_v1880")
    block = source[start:source.index("def control_center_extra_panels_v18535", start)]
    assert 'if workspace == "Orkestrering og tidsplan"' in block
    assert 'elif workspace == "Læringsportefølje"' in block
    assert "render_autonomous_orchestrator_control_center()" in block
    assert 'render_autonomous_portfolio(view="learning")' in block


def test_release_is_navigation_only_at_core_boundary():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")
    assert '"v18.8.2: Autonomi i hovedmenyen:' in version
