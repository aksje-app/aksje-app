from __future__ import annotations

from pathlib import Path

from control_center_route_state import consume_control_center_route_lock_v19220_rc6

ROOT = Path(__file__).resolve().parents[1]
PANEL = "💱 Valutavarsler"
GROUP = "Marked og signaler"


def test_route_lock_wins_before_control_center_radios_render():
    state = {
        "ai_control_center_group_v1863aj": "Autonomi",
        "ai_control_center_active_panel_v1863aj": "🧠 Autonomi – Kontrollsenter",
        "ai_control_center_group_radio_v1863aj": "Autonomi (1)",
        "ai_control_center_route_lock_v19220_rc6": {
            "nav": "fx_alerts", "group": GROUP, "panel": PANEL,
        },
    }
    group_map = {
        "Autonomi": ["🧠 Autonomi – Kontrollsenter"],
        GROUP: ["Top Picks", PANEL],
    }
    panel_map = {
        "🧠 Autonomi – Kontrollsenter": lambda: None,
        "Top Picks": lambda: None,
        PANEL: lambda: None,
    }
    group_by_option = {"Autonomi (1)": "Autonomi", f"{GROUP} (2)": GROUP}

    assert consume_control_center_route_lock_v19220_rc6(
        state, group_map, panel_map, group_by_option
    ) is True
    assert state["ai_control_center_group_v1863aj"] == GROUP
    assert state["ai_control_center_active_panel_v1863aj"] == PANEL
    assert state["ai_control_center_active_real_panel_v18598"] == PANEL
    assert state["ai_control_center_group_radio_v1863aj"] == f"{GROUP} (2)"
    assert state[f"ai_control_center_panel_radio_v1863aj_{GROUP}"] == PANEL
    assert "ai_control_center_route_lock_v19220_rc6" not in state


def test_every_currency_action_uses_navigation_preserving_rerun():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    start = app.index("def render_currency_alerts_control_center_v1863af")
    end = app.index("# v18.5.37", start)
    block = app[start:end]

    assert block.count("_rerun_currency_alerts_v19220_rc6()") == 5
    assert "        st.rerun()" not in block
    assert 'source="manual_fetch"' in block
    assert 'source="manual_check"' in block
    assert 'source="pushover_test_quote"' in block


def test_currency_route_has_one_stable_group_in_all_navigation_sources():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    workspace = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")
    sidebar = (ROOT / "ui_sidebar_stable.py").read_text(encoding="utf-8")
    fallback = (ROOT / "tools" / "ui_sidebar_stable.py").read_text(encoding="utf-8")

    assert '"valutavarsler", "top picks"' in workspace
    assert '"fx_alerts": ("Marked og signaler", "💱 Valutavarsler")' in sidebar
    assert '"fx_alerts": ("Marked og signaler", "💱 Valutavarsler")' in fallback
    for source in (app, sidebar, fallback):
        route_slice = source[source.index('elif nav in {"fx_alerts"'):][:900]
        assert '"Marked og signaler"' in route_slice
        assert '"Andre paneler"' not in route_slice


def test_version_identity_is_rc6():
    from app_version import APP_VERSION, PREVIOUS_APP_VERSION

    assert APP_VERSION == "v19.22.0-rc16.3"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.2"
