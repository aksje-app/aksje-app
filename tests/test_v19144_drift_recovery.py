from __future__ import annotations

import importlib
from pathlib import Path


class FakeState(dict):
    pass


class FakeStreamlit:
    def __init__(self):
        self.session_state = FakeState()


def _reload_auth_modules(monkeypatch, tmp_path, *, render=False, persistent=True):
    monkeypatch.delenv("AUTH_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AUTH_STORAGE_MODE", "local")
    monkeypatch.setenv("AUTH_STORAGE_ROOT", str(tmp_path / "auth"))
    monkeypatch.setenv("AUTH_REQUIRE_PERSISTENT", "true" if render else "false")
    monkeypatch.setenv("AUTH_STORAGE_PERSISTENT", "true" if persistent else "false")
    if render:
        monkeypatch.setenv("RENDER_SERVICE_NAME", "aksje-app-stabilisering")
    else:
        monkeypatch.delenv("RENDER_SERVICE_NAME", raising=False)
    import auth_persistence
    import user_store
    importlib.reload(auth_persistence)
    importlib.reload(user_store)
    return auth_persistence, user_store


def test_render_auth_storage_fails_closed_when_ephemeral(monkeypatch, tmp_path):
    auth_persistence, _ = _reload_auth_modules(monkeypatch, tmp_path, render=True, persistent=False)
    status = auth_persistence.auth_storage_status()
    assert status["required"] is True
    assert status["persistent"] is False
    assert status["ready"] is False
    assert "flyktig" in status["message"].lower()


def test_local_persistent_user_survives_reload_and_password_invalidates_sessions(monkeypatch, tmp_path):
    _, user_store = _reload_auth_modules(monkeypatch, tmp_path, render=True, persistent=True)
    assert user_store.create_user("admin", "hemmelig123", role="admin")[0] is True
    ok, user, _ = user_store.authenticate("admin", "hemmelig123")
    assert ok is True
    assert user["session_version"] == 1
    importlib.reload(user_store)
    ok, user_after, _ = user_store.authenticate("admin", "hemmelig123")
    assert ok is True
    assert user_after["session_version"] == 1
    assert user_store.update_user("admin", password="nyhemmelig123")[0] is True
    assert user_store.get_user("admin")["session_version"] == 2


def test_first_admin_is_logged_in_immediately_and_cookie_is_environment_scoped():
    source = Path("auth.py").read_text(encoding="utf-8")
    assert "Admin opprettet og innlogget" in source
    assert "_set_logged_in(user, remember=False)" in source
    assert "_remember_cookie_name_v19144" in source
    assert "auth_environment_id" in source
    assert "app_auth_sessions" in source
    assert "token_hash" in source
    assert 'tokens[_remember_token_hash_v19144(token)]' in source


def test_separate_auth_database_does_not_enable_application_database():
    source = Path("auth_persistence.py").read_text(encoding="utf-8")
    safety = Path("runtime_safety.py").read_text(encoding="utf-8")
    assert 'os.getenv("AUTH_DATABASE_URL")' in source
    assert 'database_configured = bool(_raw("DATABASE_URL"))' in safety
    assert '"auth_storage": auth_storage' in safety


def test_navigation_checkpoint_restores_background_mutations_but_not_user_clicks():
    from navigation_state import capture_navigation_checkpoint_v19144, restore_navigation_checkpoint_v19144
    st = FakeStreamlit()
    st.session_state.update({
        "navigation_user_revision_v19143": 4,
        "active_nav_target_v18674c": "reports",
        "ai_control_center_group_v1863aj": "Autonomi",
        "autonomy_core_workspace_slug_v1882": "reports",
    })
    checkpoint = capture_navigation_checkpoint_v19144(st)
    st.session_state["active_nav_target_v18674c"] = "autonomy"
    st.session_state["autonomy_core_workspace_slug_v1882"] = "orchestrator"
    assert restore_navigation_checkpoint_v19144(st, checkpoint) is True
    assert st.session_state["active_nav_target_v18674c"] == "reports"
    assert st.session_state["autonomy_core_workspace_slug_v1882"] == "reports"

    checkpoint = capture_navigation_checkpoint_v19144(st)
    st.session_state["navigation_user_revision_v19143"] = 5
    st.session_state["active_nav_target_v18674c"] = "portfolio"
    assert restore_navigation_checkpoint_v19144(st, checkpoint) is False
    assert st.session_state["active_nav_target_v18674c"] == "portfolio"


def test_orchestrator_refresh_is_fragment_scoped_and_navigation_guarded():
    source = Path("autonomous_orchestrator_ui.py").read_text(encoding="utf-8")
    assert "capture_navigation_checkpoint_v19144" in source
    assert "restore_navigation_checkpoint_v19144" in source
    assert 'st.rerun(scope="fragment")' in source
    refresh_block = source.split('if st.button("↻ Oppdater status"', 1)[1].split("def _background_status_panel", 1)[0]
    assert "st.rerun()" not in refresh_block


def test_user_navigation_state_is_runtime_scoped_not_git_data():
    source = Path("app.py").read_text(encoding="utf-8")
    block = source.split("def _ui_state_path_v18658", 1)[1].split("def _persist_ui_state_v18658", 1)[0]
    assert "runtime_data_path" in block
    assert "auth_user" in block
    assert 'Path("data/ui_state_v18658.json")' not in block


def test_drift_readiness_requires_persistent_auth_and_paper_storage():
    source = Path("drift_recovery.py").read_text(encoding="utf-8")
    assert "analysis_reporting_ready" in source
    assert "paper_buy_test_ready" in source
    assert "paper_storage_persistent" in source
    assert "Bruker- og sesjonslager er ikke varig" in source


def test_active_session_survives_transient_auth_backend_error(monkeypatch, tmp_path):
    import sys
    import types
    from datetime import datetime, timedelta

    _reload_auth_modules(monkeypatch, tmp_path, render=True, persistent=True)
    fake_streamlit = types.ModuleType("streamlit")
    fake_streamlit.__path__ = []
    fake_streamlit.session_state = FakeState({
        "auth_user": {"username": "admin", "active": True, "session_version": 1},
        "auth_expires_at": (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds"),
        "auth_remember_me": True,
    })
    fake_components = types.ModuleType("streamlit.components")
    fake_components.__path__ = []
    fake_components_v1 = types.ModuleType("streamlit.components.v1")
    fake_components_v1.html = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setitem(sys.modules, "streamlit.components", fake_components)
    monkeypatch.setitem(sys.modules, "streamlit.components.v1", fake_components_v1)
    sys.modules.pop("auth", None)
    auth = importlib.import_module("auth")
    auth.st = fake_streamlit

    def unavailable(_username):
        raise RuntimeError("database restarting")

    monkeypatch.setattr(auth, "get_user", unavailable)
    assert auth._session_is_valid() is True
    assert fake_streamlit.session_state["auth_user"]["username"] == "admin"
    assert "kontrolleres på nytt" in fake_streamlit.session_state["auth_backend_warning_v19144"]

    # A confirmed missing user is still fail-closed once the recheck interval elapses.
    fake_streamlit.session_state.pop("auth_user_version_checked_at_v19144", None)
    monkeypatch.setattr(auth, "get_user", lambda _username: None)
    assert auth._session_is_valid() is False
    assert "auth_user" not in fake_streamlit.session_state


def test_render_blueprint_declares_durable_auth_configuration():
    source = Path("render.yaml").read_text(encoding="utf-8")
    assert source.count("AUTH_STORAGE_MODE") == 2
    assert source.count("AUTH_DATABASE_URL") == 2
    assert source.count("AUTH_REQUIRE_PERSISTENT") == 2
    assert source.count("AUTH_SESSION_RECHECK_SECONDS") == 2
