from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_v18614_navigation_watchlist_paper_static_guards():
    for name in [
        "app.py",
        "workspace_layout.py",
        "alert_center.py",
        "paper_trading_valuation.py",
        "alpha_radar_ui.py",
        "app_version.py",
    ]:
        py_compile.compile(str(ROOT / name), doraise=True)

    app = _read("app.py")
    workspace = _read("workspace_layout.py")
    alert_center = _read("alert_center.py")
    valuation = _read("paper_trading_valuation.py")
    alpha = _read("alpha_radar_ui.py")
    version = _read("app_version.py")

    assert 'APP_VERSION = "v18.6.22"' in version
    assert "_close_control_center_panel_v18611" in workspace
    assert "banner_detail_suppress_picker_once_v18611" in app
    assert "remember_token" in app
    assert "cached_score_stock_manual(clean, use_news=False, force=True)" in app
    assert "Manuelle tilleggstickere" in app
    assert "Paper Trading varselkontroll / Pushover" in app
    assert "Detaljert Paper-portef" in app
    assert '"Snittkurs/NAV"' in app
    assert '"Siste kurs/NAV"' in valuation
    assert "PAPER_FUND_LOOKUP_CATALOG_V18611" in app
    assert "Fondnavn / ISIN / ETF-symbol" in app
    assert "Oppdater visning fra lagrede varsler" in alert_center
    assert "Send til Beslutningsgrunnlag" not in alpha



