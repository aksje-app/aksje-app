from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_special_watch_banner_is_surface_between_main_banner_and_menus():
    app = _read("app.py")
    version = _read("app_version.py")
    py_compile.compile(str(ROOT / "app.py"), doraise=True)

    assert 'APP_VERSION = "v18.6.22"' in version
    assert "def render_special_watch_banner_surface_v18620" in app
    assert (
        "render_live_market_banner()\n"
        "    render_special_watch_banner_surface_v18620()\n"
        "    render_special_watch_menu_v18619()\n"
        "    render_banner_main_controls()"
    ) in app

    menu_start = app.index("def render_special_watch_menu_v18619")
    menu_end = app.index("def _render_nordnet_datatest_v18610", menu_start)
    menu_block = app[menu_start:menu_end]
    assert "_render_special_banner_watch_v18612(banner_cards, config)" not in menu_block
    assert "Særskilt banner vises rett under hovedbanneret" in menu_block


def test_special_watch_banner_uses_same_two_copy_tape_pattern_as_main_banner():
    app = _read("app.py")
    start = app.index("def _render_special_banner_watch_v18612")
    end = app.index("def render_special_watch_banner_surface_v18620", start)
    special_banner_block = app[start:end]

    assert "specialWatchTickerTapeScrollV18621 {speed_seconds}s linear infinite !important" in special_banner_block
    assert special_banner_block.count('+ "".join(cards_html)') == 2


def test_control_center_keeps_active_panel_when_group_reruns():
    layout = _read("workspace_layout.py")
    py_compile.compile(str(ROOT / "workspace_layout.py"), doraise=True)

    assert "Paper Trading og kontroll" in _read("app.py")
    assert "previous_active_label = st.session_state.get(\"ai_control_center_active_panel_v1863aj\") or \"\"" in layout
    assert "if previous_active_label in direct_panels:" in layout
    assert "st.session_state[\"ai_control_center_active_panel_v1863aj\"] = previous_active_label" in layout
