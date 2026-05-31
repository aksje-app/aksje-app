from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_startup_defaults_to_no_selected_panel_and_hides_drift_controls():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")

    assert 'st.session_state.setdefault("ai_control_center_active_panel_v1863aj", "")' in app
    assert 'st.session_state.setdefault("ai_control_center_group_v1863aj", "")' in app
    startup_block = app[app.index("ai_control_center_landed_default_v1864l") - 250 : app.index("ai_control_center_landed_default_v1864l") + 420]
    assert '"Marked"' not in startup_block
    assert "Marked og signaler" not in startup_block
    assert "Drift: vis global oppdatering" in app
    assert "Vanlig arbeid starter uten valgt panel" in app
    assert "Paper-kontrollene ligger i Paper Trading" in app
    assert "show_drift_controls_v1863cc" in app
    assert "render_global_update_action_panel_v1863g()" in app
    assert "if bool(globals().get(\"show_drift_controls_v1863cc\", False))" in app
    active_layout = layout[layout.index("def _render_ai_control_center_v1863aj") :]
    assert "Velg hovedom" in active_layout and "relevant arbeidsflate" in active_layout
    assert "Ingen valgt" not in active_layout


def test_remember_token_is_not_reinserted_in_url_after_login():
    auth = (ROOT / "auth.py").read_text(encoding="utf-8")

    assert 'st.query_params["remember_token"] = token' not in auth
    assert 'parentUrl.searchParams.delete("remember_token")' in auth
    assert 'window.parent.history.replaceState(null, "", parentUrl.toString())' in auth
    assert 'del st.query_params["remember_token"]' in auth


def test_primary_buttons_are_normal_height_globally():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")

    assert "min-height:36px !important;" in app
    assert "padding:.34rem .72rem !important;" in app
    assert "overflow-wrap:anywhere !important;" in app
    assert "min-height:50px !important;" not in app
    assert ".ptw-control-selector-shell div[data-testid=\"stButton\"] button" in layout
    assert "min-height: 34px !important;" in layout




