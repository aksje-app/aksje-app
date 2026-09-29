from __future__ import annotations

from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_overview_super_portfolio_quick_action_uses_dedicated_route():
    source = (ROOT / "pages" / "overview.py").read_text(encoding="utf-8")
    assert '("Åpne Super Portfolio", "super_portfolio", "aa_overview_portfolio")' in source
    assert '("Åpne Super Portfolio", "portfolio", "aa_overview_portfolio")' not in source


def test_navigation_helper_treats_super_portfolio_as_direct_destination():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def _apply_nav_target_v18658")
    end = source.index("def _apply_mobile_nav_query_v18646", start)
    block = source[start:end]
    assert 'direct_super_portfolio = nav in {"super_portfolio", "superportfolio"}' in block
    assert 'st.session_state["autonomy_core_workspace_slug_v1882"] = "super_portfolio"' in block
    assert 'not direct_super_portfolio' in block
    assert 'tab="super_portfolio"' in block


def test_front_window_uses_same_direct_super_portfolio_route():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def render_super_portfolio_front_window_v1932c")
    end = source.index("def cached_auto_rank_market", start)
    block = source[start:end]
    assert '_apply_nav_target_v18658("super_portfolio")' in block
    assert '_apply_nav_target_v18658("autonomy")' not in block


def test_autonomy_direct_workspace_renders_super_portfolio_before_mode_gate():
    source = (ROOT / "pages" / "autonomy.py").read_text(encoding="utf-8")
    direct = source.index('if requested_direct == "super_portfolio":')
    mode = source.index("interface_mode = render_mode_selector()")
    assert direct < mode
    assert 'render_super_portfolio(_legacy_context)' in source[direct:mode]


def test_rc16_33q_direct_route_contract_remains_present():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'direct_super_portfolio = nav in {"super_portfolio", "superportfolio"}' in source
