from pathlib import Path


def test_v18534_version_and_busy_slot_are_explicit():
    assert 'APP_VERSION = "v18.5.45"' in Path("app_version.py").read_text()
    sticky = Path("sticky_topbar.py").read_text()
    css = Path("workspace_layout.py").read_text()
    busy = Path("global_busy.py").read_text()
    assert "ptw-version-chip" in sticky
    assert "aria-live=\"polite\"" in sticky
    assert "ptw-busy-running" in css
    assert "ptw-busy-glow" in css
    assert "Jobber..." in busy


def test_v18534_trading_warning_has_own_line_before_buttons():
    app = Path("app.py").read_text()
    css = Path("workspace_layout.py").read_text()
    assert "v18534-trading-warning" in app
    assert "v18534-control-button-gap" in app
    assert "v18534-trading-warning" in css
    assert "margin: .16rem 0 .48rem 0" in css
    assert app.index("v18534-trading-warning") < app.index("_tq1, _tq2, _tq3")
