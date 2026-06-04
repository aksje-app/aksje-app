from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_v18614_persistent_banner_and_horizontal_detail_static_guards():
    for name in ["app.py", "app_version.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

    app = _read("app.py")
    version = _read("app_version.py")

    assert 'APP_VERSION = "v18.6.18"' in version
    assert "Paper Trading og saerskilt banner-fiks" in version

    # Hovedbanneret skal fortsatt rendres i manuell/cache-modus.
    assert "_banner_fallback_cards_v18614(banner_items)" in app
    assert "banner_cards = _banner_fallback_cards_v18614(banner_items)" in app
    assert "target='_self' href='{href}'" in app

    # Oppfølgingsaksjer skal vises som tickerkort-banner, ikke blå Streamlit-knapper.
    assert "ticker-tape-wrap follow-up" in app
    assert "special_watch_banner_speed_seconds_v18615" in app
    assert "special_watch_open_v18612" not in app

    # Beslutningsdata over grafen skal styres av en horisontal grid med sterke regler.
    assert "def _banner_detail_layout_css_v18614" in app
    assert "grid-template-columns: repeat(6, minmax(132px, 1fr)) !important" in app
    assert "_banner_detail_layout_css_v18614()" in app


