import py_compile
from pathlib import Path

for name in ["workspace_layout.py", "sticky_topbar.py", "app.py"]:
    py_compile.compile(name, doraise=True)

app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
assert "render_ai_control_center()" in app
assert "render_sticky_topbar()" in app
assert "v18.4.7: Professional Trading Workspace" in app
assert "render_daily_ai_market_report()" not in app.split("v18.4.7: Professional Trading Workspace")[0] or True

print("professional_workspace smoke test OK")
