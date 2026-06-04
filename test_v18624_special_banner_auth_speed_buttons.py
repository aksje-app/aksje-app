from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_v18624_version_label():
    version = _read("app_version.py")
    assert 'APP_VERSION = "v18.6.24"' in version
    assert "Sarskilt bannerklikk, fart og kompakte knapper" in version
    assert "v18624-special-banner-auth-speed-buttons" in version


def test_v18624_special_banner_preserves_remember_token_on_click():
    app = _read("app.py")
    special_start = app.index("def _render_special_banner_watch_v18612")
    special_end = app.index("def _special_watch_ticker_items_v18623")
    special = app[special_start:special_end]
    assert 'remember_token = st.session_state.get("remember_token") or _banner_query_value_v18610("remember_token")' in special
    assert 'href += f"&remember_token={quote(str(remember_token))}"' in special
    assert "target='_self'" in special


def test_v18624_special_watch_has_real_scroll_mode_not_seconds_only():
    app = _read("app.py")
    assert "special_watch_scroll_mode_v18624" in app
    assert "special_watch_scroll_speed_v18624" in app
    assert 'modes = ["Arv hovedbanner", "Stoppet", "Egen fart"]' in app
    assert "animation: none !important" in app
    assert "260 - (scroll_speed * 2.2)" in app
    assert "Rullefart: høyere tall = raskere" in app


def test_v18624_special_watch_save_does_not_auto_expand_menu():
    app = _read("app.py")
    assert 'with st.expander("Særskilt overvåking", expanded=False):' in app
    assert 'saved = st.form_submit_button("Lagre", use_container_width=False)' in app
    assert 'settings["special_watch_banner_speed_seconds_v18615"] = 0' in app


def test_v18624_global_update_button_is_compact():
    app = _read("app.py")
    assert '"Kjør oppdatering"' in app
    assert '"Kjør Global oppdatering"' not in app
    assert "use_container_width=False" in app
    assert "max-width:280px" in app
    assert "max-width:260px" in app
