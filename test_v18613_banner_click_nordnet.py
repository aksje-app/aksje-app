from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_v18613_banner_click_and_nordnet_static_guards():
    for name in ["app.py", "app_version.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

    app = _read("app.py")
    version = _read("app_version.py")

    assert 'APP_VERSION = "v18.6.13"' in version
    assert "Bannerklikk og Nordnet-arbeidsflate" in version

    # Bannerklikk må åpne detalj også når det ikke finnes live/cachede bannerkort.
    assert "def _banner_selected_from_query_v18610(cards: list[dict], banner_items=None)" in app
    assert "_banner_selected_from_query_v18610([], banner_items)" in app
    assert "if not banner_cards:" in app
    assert "_render_banner_ticker_detail_v18610(" in app
    assert "bannerklikk skal åpne detalj også når banneret bruker manuell/cache-modus" in app

    # Nordnet skal være synlig som arbeidsflate, uten app-lagret passord eller ordreutsending.
    assert "def _render_nordnet_manual_workspace_v18613" in app
    assert "Nordnet arbeid og innlogging" in app
    assert "Åpne Nordnet innlogging" in app
    assert "Appen lagrer ikke Nordnet-passord og sender ingen ordre" in app
    assert "_render_nordnet_manual_workspace_v18613()" in app
