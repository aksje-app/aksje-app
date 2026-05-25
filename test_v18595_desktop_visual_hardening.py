from pathlib import Path

APP = Path('app.py').read_text(encoding="utf-8", errors="ignore")
WORKSPACE = Path('workspace_layout.py').read_text(encoding="utf-8", errors="ignore")
TOPBAR = Path('sticky_topbar.py').read_text(encoding="utf-8", errors="ignore")


def test_v18595_pushover_panel_is_high_in_auto_setup():
    assert 'def _render_pushover_test_panel_v18595' in APP
    assert "data-ui-path='active-pushover-test-v18595'" in APP
    assert 'main_auto_verify_pushover_v18595_desktop_visible' in APP
    assert 'main_auto_send_test_pushover_v18595_desktop_visible' in APP
    expander_idx = APP.index('with st.expander("⚙️ Auto trading-oppsett"')
    call_idx = APP.index('_render_pushover_test_panel_v18595()', expander_idx)
    form_idx = APP.index('with st.form("auto_trading_settings_form_v17"', expander_idx)
    assert call_idx < form_idx


def test_v18595_global_button_has_late_desktop_override():
    late_idx = APP.index('v18.5.95: late desktop visibility hardening')
    render_idx = APP.index('render_global_update_bar_v18548()', late_idx)
    assert late_idx < render_idx
    assert 'visual-truth-global-box' in APP[late_idx:render_idx]
    assert 'min-height:50px' in APP[late_idx:render_idx]
    assert 'white-space:normal' in APP[late_idx:render_idx]


def test_v18595_version_chip_is_visible_trust_badge():
    assert '🧭 Professional Trading Workspace' in TOPBAR
    assert 'aria-label="Aktiv build"' in TOPBAR
    assert '.ptw-version-chip' in WORKSPACE
    assert 'color: #f8fafc' in WORKSPACE
    assert 'background: rgba(8,47,73,.74)' in WORKSPACE
    assert 'min-width: 0 !important; max-width:70vw' in WORKSPACE
