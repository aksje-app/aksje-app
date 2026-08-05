from __future__ import annotations

from control_center_route_state import consume_control_center_route_lock_v19220_rc6
from navigation_state import (
    AUTONOMY_GROUP, AUTONOMY_PANEL, pin_autonomy_workspace_route_v19220_rc11,
)


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.query_params = {"aa_nav": "analysis", "aa_tab": "overview"}


def test_pending_report_route_is_consumed_before_radios_render():
    st = FakeStreamlit()
    pin_autonomy_workspace_route_v19220_rc11(st)
    assert "ai_control_center_group_radio_v1863aj" not in st.session_state

    group_map = {AUTONOMY_GROUP: [AUTONOMY_PANEL]}
    panel_map = {AUTONOMY_PANEL: lambda: None}
    group_by_option = {"Autonomi (1)": AUTONOMY_GROUP}

    assert consume_control_center_route_lock_v19220_rc6(
        st.session_state, group_map, panel_map, group_by_option,
    ) is True
    assert st.session_state["ai_control_center_group_radio_v1863aj"] == "Autonomi (1)"
    assert st.session_state["ai_control_center_panel_radio_v1863aj_Autonomi"] == AUTONOMY_PANEL
    assert st.session_state["autonomy_core_workspace_slug_v1882"] == "reports"
    assert st.query_params["aa_nav"] == "autonomy"
    assert st.query_params["aa_tab"] == "reports"


def test_report_rerun_helper_uses_rc11_pending_route():
    source = open("market_intelligence.py", encoding="utf-8").read()
    block = source[source.index("def _rerun_reports_v19220_rc11"):source.index("ROOT = runtime_data_path")]
    assert "pin_autonomy_workspace_route_v19220_rc11" in block
    assert "st.rerun()" in block


def test_report_rerun_executes_after_pending_route_is_queued():
    from market_intelligence import _rerun_reports_v19220_rc11

    class RerunStreamlit(FakeStreamlit):
        def __init__(self):
            super().__init__()
            self.rerun_calls = 0

        def rerun(self):
            self.rerun_calls += 1

    st = RerunStreamlit()
    _rerun_reports_v19220_rc11(st)
    assert st.rerun_calls == 1
    assert st.session_state["ai_control_center_route_lock_v19220_rc6"]["tab"] == "reports"
    assert "ai_control_center_group_radio_v1863aj" not in st.session_state
