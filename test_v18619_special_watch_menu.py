from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_special_watch_has_own_menu_and_shared_ticker_tape():
    app = _read("app.py")
    version = _read("app_version.py")
    py_compile.compile(str(ROOT / "app.py"), doraise=True)

    assert 'APP_VERSION = "v18.6.24"' in version
    assert "Sarskilt bannerklikk, fart og kompakte knapper" in version
    assert "def render_special_watch_menu_v18619" in app
    assert 'with st.expander("Særskilt overvåking"' in app
    assert "render_special_watch_menu_v18619()" in app
    assert "render_live_market_banner()\n    render_special_watch_banner_surface_v18620()\n    render_special_watch_menu_v18619()\n    render_banner_main_controls()" in app
    assert "ticker-tape-wrap special-watch-tape-v18621" in app
    assert "specialWatchTickerTapeScrollV18621 {speed_seconds}s linear infinite !important" in app
    assert "Fjern valgt ticker" in app
    assert "Tøm særskilt overvåking" in app


def test_main_banner_menu_no_longer_contains_special_controls():
    app = _read("app.py")
    start = app.index('with st.expander("Ticker-banner"')
    end = app.index('with st.expander("Importer tickere"', start)
    main_menu_block = app[start:end]

    assert "Vis ticker-banner" in main_menu_block
    assert "Bannerhastighet sekunder" in main_menu_block
    assert "Markeder som vises i banneret" in main_menu_block
    assert "Vis særskilt banner" not in main_menu_block
    assert "special_watch_banner_speed_seconds_v18615" not in main_menu_block


