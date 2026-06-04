from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_paper_trading_panel_uses_stable_plain_label():
    app = _read("app.py")
    version = _read("app_version.py")
    py_compile.compile(str(ROOT / "app.py"), doraise=True)

    assert 'APP_VERSION = "v18.6.20"' in version
    assert "Saerskilt banner under hovedbanner og stabilt panelvalg" in version
    assert '("Paper Trading og kontroll", render_paper_trading_dashboard)' in app
    assert 'st.subheader("Paper Trading og kontroll")' in app
    assert 'elif "Paper Trading" in str(active_panel or ""):' in app
    assert '("🧪 Paper Trading og kontroll", render_paper_trading_dashboard)' not in app


def test_special_watch_banner_is_visible_scrollable_and_removable():
    app = _read("app.py")

    assert "def _has_special_watch_rules_v18618" in app
    assert "abs(float(rules.get(key) or 0.0)) > 0" in app
    assert "Særskilt overvåking" in app
    assert "Særskilt overvåking - administrer tickere" in app
    assert "Fjern ticker" in app
    assert "Tøm særskilt overvåking" in app
    assert "min-width: max-content" in app
    assert app.count(' + "".join(cards_html)') == 2
    assert "Saerskilt overvaking" not in app

