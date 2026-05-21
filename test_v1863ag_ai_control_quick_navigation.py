from pathlib import Path
import py_compile


for name in ["workspace_layout.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.3al"' in version
assert "ai_control_center_menu_open_v1863ag" in layout
assert "ai_control_center_recent_panels_v1863ag" in layout
assert "ai_control_center_search_v1863ag" in layout
assert "ai_control_center_work_mode_v1863ag" in layout
assert "Hovedomr" in layout
assert "Favoritter" in layout
assert "Sist brukt" in layout
assert "Undermeny for" in layout
