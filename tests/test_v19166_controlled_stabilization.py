from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_version_and_safe_login():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")
    auth = (ROOT / "auth.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v19.16.6"' in version
    assert "midlertidig deaktivert" in auth
    assert "window.parent.location.reload" not in auth


def test_web_process_does_not_start_workers_by_default():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'ENABLE_WEB_BACKGROUND_SERVICES", "false"' in app
    assert 'ENABLE_WEB_SCHEDULER_KICK", "false"' in app


def test_more_menu_readability_guard():
    sidebar = (ROOT / "ui_sidebar_stable.py").read_text(encoding="utf-8")
    assert "min-width: 184px" in sidebar
    assert 'st.sidebar.expander("☰ Mer"' in sidebar
