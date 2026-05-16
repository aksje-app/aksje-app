from pathlib import Path
import py_compile


def test_control_center_can_disable_legacy_main_sections():
    for name in ["app.py", "workspace_layout.py"]:
        py_compile.compile(name, doraise=True)
    app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
    assert "AI_CONTROL_CENTER_MAIN_PANEL_LABEL_V18598" in layout
    assert "return active_label" in layout
    assert "_active_control_center_panel_v18598 = render_ai_control_center(extra_panels=control_center_extra_panels_v18535())" in app
    assert "st.stop()" in app
    assert "Underliggende hovedpaneler er skjult" in app


def test_auto_lab_decision_rows_define_score_chips_before_markup():
    app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    start = app.index("def _render_auto_lab_decision_rows_v18536")
    end = app.index("def _render_auto_lab_combination_rows_v18536", start)
    body = app[start:end]
    assert "composite_score =" in body
    assert "base_score =" in body
    assert body.index("composite_score =") < body.index("Intelligens {composite_score}/100")
    assert body.index("base_score =") < body.index("Grunnscore {base_score}/100")
