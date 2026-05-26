from pathlib import Path
import py_compile


for name in ["workspace_layout.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.5d"' in version
assert "return _render_ai_control_center_v1863aj(extra_panels)" in layout
assert "def _render_ai_control_center_v1863ah" in layout
assert "ai_control_center_group_v1863ah" in layout
assert "ai_control_center_show_home_v1863ah" in layout
assert "ai_control_center_submenu_open_v1863ah" in layout
assert "Til hovedvalg" in layout







