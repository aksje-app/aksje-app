from __future__ import annotations

from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from local_time import browser_clock_document

ROOT = Path(__file__).resolve().parents[1]


def test_rc163_version_chain_and_protected_navigation_source():
    assert APP_VERSION == "v19.22.0-rc16.3"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.2"
    # Recorded from the accepted RC16.2 FULL package. The navigation renderer
    # itself must remain byte-for-byte unchanged by the clock hotfix.
    assert __import__('hashlib').sha256((ROOT / 'ui_sidebar_stable.py').read_bytes()).hexdigest() == (
        "14243f913540c3c6eaa945fff3338d222197d28b50dc419dad7eeee4d25ff871"
    )


def test_browser_clock_uses_pc_time_and_persisted_app_timezone():
    document = browser_clock_document("Europe/Oslo")
    assert "new Date()" in document
    assert "Intl.DateTimeFormat().resolvedOptions().timeZone" in document
    assert "PC-tid" in document and "App-tid" in document
    assert 'const appTz = "Europe/Oslo"' in document
    assert "window.setInterval(update, 1000)" in document


def test_timezone_save_does_not_force_navigation_rerun():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    block = source[
        source.index("def _render_display_time_settings_v19220_rc8"):
        source.index("def _render_runtime_diagnostics_v19220_rc8")
    ]
    save_branch = block[block.index('if st.button("Lagre visningstidssone"'):]
    assert 'settings["display_timezone"] = selected' in save_branch
    assert "save_settings(settings)" in save_branch
    assert "persisted =" in save_branch
    assert "st.rerun()" not in save_branch
    assert "set_global_navigation_state" not in save_branch
    assert "_apply_nav_target" not in save_branch


def test_clock_is_appended_after_stable_sidebar_navigation():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    sidebar = "show_drift_controls_v1863cc = render_stable_sidebar_v18641(st, current_user, render_user_admin)"
    clock = "render_sidebar_clock_v19220_rc163(st)"
    assert sidebar in source and clock in source
    assert source.index(clock, source.index(sidebar)) > source.index(sidebar)
