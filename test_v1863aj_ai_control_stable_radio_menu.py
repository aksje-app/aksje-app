from pathlib import Path
import py_compile


for name in ["workspace_layout.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.4p"' in version
assert "Unified AI Candidate Imports" in version
assert "return _render_ai_control_center_v1863aj(extra_panels)" in layout
assert "def _render_ai_control_center_v1863aj" in layout
assert "def _pipeline_relevant_panel_labels_v1864j" in layout
active_layout = layout[layout.index("def _render_ai_control_center_v1863aj") :]
assert "Analyseflyt:" not in active_layout
assert "Testflyt" not in layout
assert "ai_control_center_last_stage_menu_v1864j" not in active_layout
assert "ai_control_center_group_radio_v1863aj" in layout
assert "ai_control_center_panel_radio_v1863aj" in layout
assert "Ingen oppgave er" in layout and "pnet" in layout
assert "Ingen valgt" not in active_layout
assert "AI Kandidattest er hovedarbeidsflaten" in layout
assert "AI Kandidattest: analyse, kilder og radarer" in layout
assert '"folketrygdfondet"' in layout
assert "if len(direct_panels) == 1:" in layout
assert "if len(direct_panels) > 1:" in layout










