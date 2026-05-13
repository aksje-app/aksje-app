from pathlib import Path


def test_version_v18548():
    from app_version import get_app_version
    assert get_app_version() == "v18.5.62"


def test_choice_update_is_not_busy():
    src = Path("global_busy.py").read_text()
    body = src.split("def mark_choice_update", 1)[1].split("def get_global_busy_snapshot", 1)[0]
    assert '"running": False' in body
    assert "set_global_busy(" not in body


def test_global_button_moved_up_and_no_spinner():
    app = Path("app.py").read_text()
    assert "render_global_update_bar_v18548()" in app
    assert 'key="top_apply_all_changes_v18548"' in app
    assert 'with st.spinner("Oppdaterer hele appen' not in app
    assert app.index("render_global_update_bar_v18548()") < app.index("active_panel = _render_active_main_panel_selector_v18531()")


def test_ui_clean_css_present():
    css = Path("workspace_layout.py").read_text()
    assert ".v18548-global-update-wrap" in css
    assert "filter: none !important" in css
