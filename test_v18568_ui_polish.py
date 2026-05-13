from pathlib import Path


def test_ai_control_center_typography_and_chips_are_balanced():
    src = Path('workspace_layout.py').read_text(encoding='utf-8')
    assert '.ptw-control-title' in src
    assert 'font-size: 1.34rem' in src
    assert '.ptw-status-line .ptw-pill' in src
    assert 'font-size: .68rem' in src


def test_global_update_button_is_readable_and_column_has_space():
    src = Path('app.py').read_text(encoding='utf-8')
    assert 'v18.5.68: UI polish' in src
    assert 'Global oppdatering must be visible' in src
    assert 'c1, c2 = st.columns([1.15, 1.15], gap="small")' in src
    assert 'font-size: .92rem' in src
    assert '-webkit-text-fill-color: #ffffff' in src


def test_sidebar_admin_is_compact_and_not_wrapped_vertically():
    app = Path('app.py').read_text(encoding='utf-8')
    auth = Path('auth.py').read_text(encoding='utf-8')
    assert 'word-break: normal' in app
    assert 'overflow-wrap: normal' in app
    assert 'hyphens: none' in app
    assert 'st.sidebar.expander("🔐 Admin"' in auth


def test_no_dim_rerun_and_busy_widget_visibility_css_present():
    app = Path('app.py').read_text(encoding='utf-8')
    ws = Path('workspace_layout.py').read_text(encoding='utf-8')
    assert 'opacity: 1 !important' in app
    assert 'filter: none !important' in app
    assert '[data-testid="stStatusWidget"]' in ws
    assert '.ptw-busy-spinner' in ws


def test_ui_patch_marker_present():
    src = Path('app.py').read_text(encoding='utf-8')
    assert 'v18.5.68: UI polish' in src
