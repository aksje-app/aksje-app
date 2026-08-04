from __future__ import annotations

from pathlib import Path

from navigation_state import (
    apply_route_tab_to_session_state_v19220_rc7,
    canonical_nav_for_panel_v19220_rc7,
    current_route_tab_from_session_v19220_rc7,
    set_global_navigation_state,
)

ROOT = Path(__file__).resolve().parents[1]
AUTONOMY_PANEL = "🧠 Autonomi – Kontrollsenter"


class CountingQuery(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.writes = 0
        self.deletes = 0

    def __setitem__(self, key, value):
        self.writes += 1
        return super().__setitem__(key, value)

    def __delitem__(self, key):
        self.deletes += 1
        return super().__delitem__(key)


class FakeSt:
    def __init__(self, query):
        self.query_params = query


def test_outer_and_inner_autonomy_route_do_not_ping_pong_or_write_query_params():
    query = CountingQuery({
        "aa_nav": "autonomy",
        "aa_group": "Autonomi",
        "aa_panel": AUTONOMY_PANEL,
        "aa_tab": "reports",
    })
    st = FakeSt(query)
    outer_nav = canonical_nav_for_panel_v19220_rc7("Autonomi", AUTONOMY_PANEL)
    assert outer_nav == "autonomy"
    set_global_navigation_state(st, nav=outer_nav, group="Autonomi", panel=AUTONOMY_PANEL)
    set_global_navigation_state(st, nav="autonomy", group="Autonomi", panel=AUTONOMY_PANEL, tab="reports")
    assert query.writes == 0
    assert query.deletes == 0
    assert query["aa_tab"] == "reports"


def test_route_tabs_are_restored_only_to_the_owner_workspace():
    state = {}
    assert apply_route_tab_to_session_state_v19220_rc7(
        state, nav="autonomy", panel=AUTONOMY_PANEL, tab="reports", subtab="ignored"
    )
    assert state["autonomy_core_workspace_slug_v1882"] == "reports"
    assert "paper_trading_active_tab_slug_v18674c" not in state
    assert "ai_discovery_active_tab_slug_v18674c" not in state


def test_autonomy_active_workspace_survives_one_shot_request_consumption():
    state = {
        "autonomy_core_workspace_slug_v1882": "reports",
        "autonomy_core_workspace_v1880": "Oversikt",
    }
    # Mirrors the pre-widget state transition in pages/autonomy.py.
    state["autonomy_core_workspace_v1880"] = "Rapporter"
    state["autonomy_core_workspace_slug_v1882"] = ""
    state["autonomy_core_workspace_active_slug_v19220_rc7"] = "reports"
    assert current_route_tab_from_session_v19220_rc7(
        state, nav="autonomy", panel=AUTONOMY_PANEL
    ) == ("reports", "")
    # A later rerun has no one-shot slug but still owns the Reports radio state.
    state.pop("autonomy_core_workspace_active_slug_v19220_rc7")
    assert current_route_tab_from_session_v19220_rc7(
        state, nav="autonomy", panel=AUTONOMY_PANEL
    ) == ("reports", "")


def test_autonomy_page_has_one_selector_and_no_direct_early_report_render():
    source = (ROOT / "pages" / "autonomy.py").read_text(encoding="utf-8")
    selector_pos = source.index('workspace = st.radio(')
    report_branch_pos = source.index('elif workspace == "Rapporter"')
    assert selector_pos < report_branch_pos
    before_selector = source[:selector_pos]
    assert 'if requested_workspace == "reports"' not in before_selector
    assert before_selector.count('render_market_intelligence()') == 0


def test_control_center_never_writes_generic_route_for_known_panels():
    source = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")
    assert 'set_global_navigation_state(st, nav="control_center", group=selected_group, panel=selected_panel)' not in source
    assert 'set_global_navigation_state(st, nav="control_center", group=active_group_label, panel=active_label)' not in source
    assert source.count('canonical_nav_for_panel_v19220_rc7') >= 4


def test_canonical_routes_cover_user_visible_main_panels():
    assert canonical_nav_for_panel_v19220_rc7("Marked og signaler", "💱 Valutavarsler") == "fx_alerts"
    assert canonical_nav_for_panel_v19220_rc7("Marked og signaler", "Top Picks") == "top_picks"
    assert canonical_nav_for_panel_v19220_rc7("Testing og portefolje", "Paper Trading og kontroll") == "paper_trading"
    assert canonical_nav_for_panel_v19220_rc7("System", "System/admin") == "system"
