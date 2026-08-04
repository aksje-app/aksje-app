from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sidebar_has_dedicated_drift_center_button():
    text = (ROOT / 'ui_sidebar_stable.py').read_text(encoding='utf-8')
    assert 'drift_center' in text
    assert 'active_nav_target_v18674c"] = "drift_center"' in text


def test_app_renders_drift_center_as_independent_page():
    text = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'Driftssenter is a dedicated page, independent from AI Kontrollsenter' in text
    assert 'if _active_nav_v19170rc2 in {"drift", "driftssenter", "drift_center"}' in text
    assert 'render_drift_center(st, current_user=current_user)' in text
    assert 'st.stop()' in text


def test_navigation_contract_contains_separate_drift_center():
    text = (ROOT / 'daily_user_experience.py').read_text(encoding='utf-8')
    assert '("🧭", "Driftssenter", "drift_center")' in text


def test_all_eight_activation_steps_remain_present():
    text = (ROOT / 'drift_center.py').read_text(encoding='utf-8')
    for label in [
        'Markedsskanning', 'Scheduler', 'Pushover', 'Paper Trading',
        'Papirlager', 'Bakgrunnsprosesser', 'Autonomi', 'Produksjonshandel',
    ]:
        assert label in text


def test_release_version_is_release_candidate():
    text = (ROOT / 'app_version.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "v19.22.0-rc' in text
