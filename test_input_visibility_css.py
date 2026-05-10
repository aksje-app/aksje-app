from pathlib import Path


def test_input_visibility_css_hardening_present():
    workspace_css = Path("workspace_layout.py").read_text(encoding="utf-8")
    universe_css = Path("analysis_universe_ai.py").read_text(encoding="utf-8")
    assert "v18.5.25: hard input visibility guard" in workspace_css
    assert "v18.5.25: local hard guard" in universe_css
    assert "div[data-baseweb=\"base-input\"]" in workspace_css
    assert "input:-webkit-autofill:active" in workspace_css
    assert "Aktiv ticker:" in universe_css
