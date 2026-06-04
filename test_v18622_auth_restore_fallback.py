from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_v18622_auth_restore_does_not_stop_before_login_fallback():
    version = _read("app_version.py")
    auth = _read("auth.py")
    py_compile.compile(str(ROOT / "auth.py"), doraise=True)

    assert 'APP_VERSION = "v18.6.23"' in version
    assert "Sarskilt bannerintervall og tydelig kursvisning" in version
    assert "auth_restore_attempted_v18621" in auth
    assert "gjenopprette innlogging" in auth
    restore_block = auth[auth.index("user = _restore_from_remember_token()"): auth.index("return user", auth.index("user = _restore_from_remember_token()"))]
    assert "render_login()" in restore_block
    assert "st.stop()" not in restore_block

