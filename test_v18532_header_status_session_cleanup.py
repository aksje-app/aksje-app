from pathlib import Path


def test_header_status_consolidation_and_old_boxes_removed():
    source = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    assert "v18532-header-status" in source
    assert "v18534-trading-control-stack" in source
    assert "Trading-kontroll" in source
    assert "active_panel = _render_active_main_panel_selector_v18531()" in source
    header = source.index("v18532-header-status")
    banner = source.index("render_live_market_banner()", header)
    assert header < banner
    after_banner = source[source.index("render_ai_control_center()") : source.index("Global oppdatering")]
    assert "v15-desktop-status-strip" not in after_banner
    assert "<div class='v15-status-title'>Driftstatus</div>" not in source
    assert "<div class='v15-status-title'>Børsstatus</div>" not in source


def test_market_status_is_in_sticky_topbar_and_busy_is_fixed():
    sticky = Path("sticky_topbar.py").read_text()
    css = Path("workspace_layout.py").read_text()
    assert "market_statuses" in sticky
    assert "ptw-market-chip" in sticky
    assert "ptw-global-busy-fixed" in sticky
    assert ".ptw-global-busy-fixed" in css
    assert "ptw-market-open" in css


def test_sidebar_session_details_removed_and_top_session_colored():
    auth = Path("auth.py").read_text(encoding="utf-8", errors="ignore")
    app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    assert "Sesjonsinfo" not in auth
    assert "Innlogget siden" not in auth
    assert "Husk meg: <b>{remember}</b>" in app
    assert "green' if remember == 'På' else 'red'" in app
