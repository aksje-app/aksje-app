from __future__ import annotations

from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from navigation_state import GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14
from ui_library.shell import render_shell

ROOT = Path(__file__).resolve().parents[1]


class _Ctx:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class _FakeStreamlit:
    def __init__(self, clicked: str):
        self.clicked = clicked
        self.session_state = {}
        self.query_params = {}
        self.reruns = 0

    def markdown(self, *_args, **_kwargs):
        return None

    def container(self, **_kwargs):
        return _Ctx()

    def columns(self, count, **_kwargs):
        if isinstance(count, int):
            return [_Ctx() for _ in range(count)]
        return [_Ctx() for _ in count]

    def button(self, _label, *, key, **_kwargs):
        return key == self.clicked

    def rerun(self):
        self.reruns += 1


def test_mobile_start_click_queues_new_route_before_rerun():
    st = _FakeStreamlit("aa_mobile_nav_overview")
    render_shell(st, "portfolio")
    assert st.session_state["active_nav_target_v18674c"] == "dashboard"
    assert st.session_state["ai_control_center_force_nav_v18663"] == "dashboard"
    lease = st.session_state[GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14]
    assert lease["nav"] == "dashboard"
    assert lease["source"] == "AURORA_MOBILE_NAV_RC1633O"
    assert st.query_params["aa_nav"] == "dashboard"
    assert st.reruns == 1


def test_mobile_portfolio_click_queues_new_route_before_rerun():
    st = _FakeStreamlit("aa_mobile_nav_portfolio")
    render_shell(st, "overview")
    lease = st.session_state[GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14]
    assert lease["nav"] == "portfolio"
    assert st.session_state["active_nav_target_v18674c"] == "portfolio"
    assert st.query_params["aa_nav"] == "portfolio"


def test_super_portfolio_front_route_bypasses_simple_autonomy_return():
    source = (ROOT / "pages" / "autonomy.py").read_text(encoding="utf-8")
    direct = source.index('if requested_direct == "super_portfolio":')
    mode = source.index("interface_mode = render_mode_selector()")
    assert direct < mode
    block = source[direct:mode]
    assert 'st.session_state["active_nav_target_v18674c"] = "market"' in block
    assert 'panel="🌍 Super Portfolio"' in block
    assert "st.rerun()" in block


def test_rc16_33o_navigation_contract_remains_present():
    source = (ROOT / "ui_library" / "shell.py").read_text(encoding="utf-8")
    assert "AURORA_MOBILE_NAV_RC1633O" in source
