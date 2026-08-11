from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_rc164_version_chain():
    assert APP_VERSION in {"v19.22.0-rc16.4", "v19.22.0-rc16.6", "v19.22.0-rc16.7"}
    assert PREVIOUS_APP_VERSION in {"v19.22.0-rc16.3", "v19.22.0-rc16.4", "v19.22.0-rc16.6", "v19.22.0-rc16.7"}


def test_loaded_sidebar_uses_one_visual_contract():
    source = (ROOT / "ui_sidebar_stable.py").read_text(encoding="utf-8")
    css = source[source.index("_RC16_FINAL_SIDEBAR_LOCK_CSS"):source.index("def inject_rc16_final_sidebar_lock")]
    assert "one visual contract" in css
    assert '.sidebar2026-nav-item' in css
    assert '.sidebar2026-nav-link-v18659' in css
    assert 'div[data-testid="stButton"] > button' in css
    assert 'height: 40px !important' in css
    assert 'width: 224px !important' in css
    assert 'background: linear-gradient(180deg, rgba(14,56,90,.96), rgba(8,30,55,.96))' in css
    assert '[aria-busy="true"]' in css and '[aria-busy="false"]' in css


def test_navigation_behavior_was_not_changed_by_visual_hotfix():
    source = (ROOT / "ui_sidebar_stable.py").read_text(encoding="utf-8")
    assert '_sidebar_nav_set_v18650(st, _nav)' in source
    assert 'navigation_for_mode(mode)' in source
    assert 'st.sidebar.expander("☰ Mer"' in source
