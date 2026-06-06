from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_login_has_forgot_password_flow_with_env_reset_key():
    auth = (ROOT / "auth.py").read_text(encoding="utf-8")
    assert "ADMIN_RESET_ENV_NAMES" in auth
    assert "reset_user_password_without_login" in auth
    assert "Glemt passord?" in auth
    assert "ADMIN_RESET_KEY" in auth
    assert "_clear_remember_tokens_for_username_v1868" in auth


def test_local_reset_script_exists_for_locked_out_admin():
    script = (ROOT / "reset_admin_password.py").read_text(encoding="utf-8")
    assert "Lokalt nødskript" in script
    assert "getpass.getpass" in script
    assert "update_user(username, password=password)" in script
    assert "_clear_local_remember_tokens" in script
    assert "_clear_db_remember_tokens" in script


def test_paper_button_css_no_longer_forces_primary_full_width():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    primary_block = app[app.index("Broad late primary-button hardening") : app.index("Disabled buttons must still be readable")]
    assert "giant full-width" in primary_block
    assert "width:auto !important" in primary_block
    assert "\n    width:100% !important" not in primary_block

