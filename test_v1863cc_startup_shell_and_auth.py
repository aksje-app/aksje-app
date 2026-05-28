from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_startup_defaults_to_marked_room_and_hides_drift_controls():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")

    assert '"ai_control_center_active_panel_v1863aj"] = "Marked"' in app
    assert '"ai_control_center_group_v1863aj"] = "Marked og signaler"' in app
    assert "Drift: vis Start/Stopp/Global" in app
    assert "Vanlig arbeid starter i Marked/Testflyt" in app
    assert "show_drift_controls_v1863cc" in app
    assert "render_global_update_action_panel_v1863g()" in app
    assert "if bool(globals().get(\"show_drift_controls_v1863cc\", False))" in app
    assert "Marked åpnes som standard arbeidsflate" in layout or "Marked Ã¥pnes som standard arbeidsflate" in layout


def test_remember_token_is_not_reinserted_in_url_after_login():
    auth = (ROOT / "auth.py").read_text(encoding="utf-8")

    assert 'st.query_params["remember_token"] = token' not in auth
    assert 'parentUrl.searchParams.delete("remember_token")' in auth
    assert 'window.parent.history.replaceState(null, "", parentUrl.toString())' in auth
    assert 'del st.query_params["remember_token"]' in auth


