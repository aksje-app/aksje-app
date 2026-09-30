from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in ["app.py", "pages/overview.py", "pages/autonomy.py", "app_version.py"]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
app = (ROOT / "app.py").read_text(encoding="utf-8")
overview = (ROOT / "pages" / "overview.py").read_text(encoding="utf-8")
autonomy = (ROOT / "pages" / "autonomy.py").read_text(encoding="utf-8")

assert 'APP_VERSION = "v19.22.0-' in version
assert '("Åpne Super Portfolio", "super_portfolio", "aa_overview_portfolio")' in overview
assert 'direct_super_portfolio = nav in {"super_portfolio", "superportfolio"}' in app
assert '_apply_nav_target_v18658("super_portfolio")' in app
assert 'market_panel = "🌍 Super Portfolio" if direct_super_portfolio else "🔍 Marked – Market Scanner"' in app
assert 'if requested_direct == "super_portfolio":' in autonomy
assert 'panel="🌍 Super Portfolio"' in autonomy
print("rc16.33q Super Portfolio Direct Route gate OK")
