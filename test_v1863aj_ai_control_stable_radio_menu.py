from pathlib import Path
import py_compile


for name in ["workspace_layout.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.5d"' in version
assert "return _render_ai_control_center_v1863aj(extra_panels)" in layout
assert "def _render_ai_control_center_v1863aj" in layout
assert "ai_control_center_group_radio_v1863aj" in layout
assert "ai_control_center_panel_radio_v1863aj" in layout
assert "Ingen oppgave er" in layout and "pnet" in layout
assert "Ingen valgt" in layout







