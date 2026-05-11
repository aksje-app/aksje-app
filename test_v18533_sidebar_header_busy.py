from pathlib import Path


def test_v18533_version_label():
    assert 'APP_VERSION = "v18.5.33"' in Path('app_version.py').read_text()


def test_sidebar_admin_is_compact_without_dataframe():
    auth = Path('auth.py').read_text()
    assert 'auth-sidebar-card' in auth
    assert 'Administrer brukere' in auth
    assert 'st.dataframe(' not in auth
    assert 'Kan ikke slette innlogget bruker.' in auth


def test_busy_chip_is_inline_no_top_right_overlap():
    sticky = Path('sticky_topbar.py').read_text()
    css = Path('workspace_layout.py').read_text()
    assert 'Professional Trading Workspace {get_app_version()}' in sticky
    assert 'ptw-global-busy-fixed' in sticky
    assert 'position: static' in css
    assert 'ptw-busy-spinner' in css
    assert 'ptw-topbar-right' in css


def test_control_warning_is_compact():
    app = Path('app.py').read_text()
    assert 'font-size: 0.74rem' in app
    assert 'Trading-kontroll:' in app
