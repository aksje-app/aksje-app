from __future__ import annotations

from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_identity_rc16_34d():
    assert APP_VERSION.startswith("v19.22.0-rc16.34") and APP_VERSION.split("34", 1)[1] >= "d"
    if APP_VERSION == "v19.22.0-rc16.34d":
        assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.34c"


def test_render_blueprint_matches_current_safe_capacity_and_live_cadence():
    source = _source("render.yaml")
    web, cron = source.split("  - type: cron", 1)
    assert "plan: standard" in web
    assert 'schedule: "*/15 * * * *"' in cron
    assert 'APP_HISTORY_CACHE_MAX_ITEMS' in web
    assert 'value: "1"' in web
    assert 'APP_INFO_CACHE_MAX_ITEMS' in web
    assert 'APP_INSIDER_CACHE_MAX_ITEMS' in web


def test_streamlit_caches_are_bounded():
    checks = {
        "analyst.py": "@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)",
        "earnings.py": "@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)",
        "market_selector.py": "@st.cache_data(ttl=900, max_entries=48, show_spinner=False)",
        "market_climate_ui.py": "@st.cache_data(ttl=900, max_entries=16, show_spinner=False)",
        "mobile_analysis_view.py": "@st.cache_data(ttl=300, max_entries=12, show_spinner=False)",
        "strategy_test_pro.py": "@st.cache_data(ttl=30 * 60, max_entries=4, show_spinner=False)",
    }
    for path, token in checks.items():
        assert token in _source(path), path


def test_scheduler_comments_match_fifteen_minute_runtime():
    source = _source("scheduled_runner.py")
    assert "five-minute Render cron" not in source
    assert "five-minute cron checks" not in source
    assert "fifteen-minute Render cron" in source
    assert "fifteen-minute cron checks" in source


def test_smaller_plan_is_not_enabled_prematurely():
    source = _source("render.yaml")
    web = source.split("  - type: cron", 1)[0]
    assert "plan: standard" in web
    assert "plan: free" not in web
