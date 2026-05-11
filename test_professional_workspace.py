import py_compile
from pathlib import Path

for name in ["workspace_layout.py", "sticky_topbar.py", "app.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
sticky = Path("sticky_topbar.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert "render_ai_control_center()" in app
assert "render_sticky_topbar()" in app
assert 'APP_VERSION = "v18.5.32"' in version
assert "get_app_version()" in sticky
assert "Professional Trading Workspace {get_app_version()}" in sticky
assert "v18.4.7" not in sticky

print("professional_workspace smoke test OK")
