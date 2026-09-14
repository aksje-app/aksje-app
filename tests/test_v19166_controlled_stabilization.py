from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json


def test_web_process_does_not_start_workers_by_default():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'ENABLE_WEB_BACKGROUND_SERVICES", "false"' in app
    assert 'ENABLE_WEB_SCHEDULER_KICK", "false"' in app


def test_more_menu_readability_guard():
    sidebar = (ROOT / "ui_sidebar_stable.py").read_text(encoding="utf-8")
    assert "min-width: 184px" in sidebar
    assert 'st.sidebar.expander("☰ Mer"' in sidebar
