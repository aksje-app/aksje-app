from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in [
    "ui_library/shell.py", "pages/autonomy.py", "app.py", "app_version.py",
]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
shell = (ROOT / "ui_library" / "shell.py").read_text(encoding="utf-8")
autonomy = (ROOT / "pages" / "autonomy.py").read_text(encoding="utf-8")
app = (ROOT / "app.py").read_text(encoding="utf-8")

assert 'APP_VERSION = "v19.22.0-' in version
assert 'AURORA_MOBILE_NAV_RC1633O' in shell
assert 'active_nav_target_v18674c' in shell
assert 'queue_global_navigation_route_v19220_rc14' in shell
assert 'if requested_direct == "super_portfolio":' in autonomy
assert 'render_super_portfolio(_legacy_context)' in autonomy
assert 'tab="super_portfolio"' in autonomy
assert 'front_open_super_portfolio_v1932c' in app
print("rc16.33o Mobile Navigation Recovery gate OK")
