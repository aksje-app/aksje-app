from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_v18614_banner_navigation_paper_static_guards():
    for name in ["app.py", "auth.py", "workspace_layout.py", "app_version.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

    app = _read("app.py")
    auth = _read("auth.py")
    workspace = _read("workspace_layout.py")
    version = _read("app_version.py")

    assert 'APP_VERSION = "v18.6.20"' in version
    assert "Saerskilt banner under hovedbanner og stabilt panelvalg" in version

    # Banneret skal alltid være synlig og tickerklikk skal rydde aktivt Kontrollsenter-panel.
    assert (
        "render_live_market_banner()\n"
        "    render_special_watch_banner_surface_v18620()\n"
        "    render_special_watch_menu_v18619()\n"
        "    render_banner_main_controls()"
    ) in app
    assert 'st.session_state["ai_control_center_active_panel_v1863aj"] = ""' in app
    assert "_banner_decision_cards_v18612" in app
    assert "_render_special_banner_watch_v18612" in app
    assert "live_banner_open_picker_v18610" in app

    # Tickerdetalj skal ha manuell Nordnet-/brokerflate uten ordreintegrasjon.
    assert "Nordnet / manuell handel" in app
    assert "https://www.nordnet.no/" in app
    assert "manual_broker_bought_v18612" in app
    assert "manual_broker_sold_v18612" in app
    assert "manual_broker_order_text_v18612" in app

    # Paper Trading skal ha tydelig kjøp/salg-side, og valgt undermeny skal alltid åpne panel.
    assert "paper_stock_symbol_v1863y" in app
    assert "paper_stock_sell_symbol_v1863y" in app
    assert "if selected_panel:" in workspace
    assert 'st.session_state["ai_control_center_active_panel_v1863aj"] = selected_panel' in workspace

    # Refresh med Husk meg skal kunne hente token fra parent-siden, ikke bare komponent-iframe.
    assert "window.parent.localStorage" in auth
    assert "function getStored()" in auth



