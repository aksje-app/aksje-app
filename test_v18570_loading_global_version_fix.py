from pathlib import Path


def test_app_version_18570_is_centralized():
    src = Path("app_version.py").read_text()
    assert 'APP_VERSION = "v18.5.73"' in src
    assert 'APP_BUILD_ID = "v18573-fund-names-ui-layout-fix"' in src
    sticky = Path("sticky_topbar.py").read_text()
    assert "get_app_build_label" in sticky
    

def test_global_update_button_is_visible_and_top_level():
    app = Path("app.py").read_text()
    assert "v18570-global-update-row" in app
    assert "v18570-global-update-action" in app
    assert "top_apply_all_changes_v18570" in app
    assert "set_global_busy(\"Global oppdatering\"" in app
    assert "v18570-global-running-note" in app


def test_no_dim_safety_and_busy_indicator_css():
    app = Path("app.py").read_text()
    ws = Path("workspace_layout.py").read_text()
    combined = app + ws
    assert "filter:none !important" in combined
    assert "transition:none !important" in combined
    assert ".ptw-busy-spinner" in combined
    assert "visibility:visible !important" in combined
    assert "ptw-v18570-status-zone" in combined


def test_choice_updates_do_not_set_running_busy():
    gb = Path("global_busy.py").read_text()
    body = gb.split("def mark_choice_update", 1)[1].split("def get_global_busy_snapshot", 1)[0]
    assert '"running": False' in body
    assert "set_global_busy(" not in body
