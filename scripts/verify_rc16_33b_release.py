from __future__ import annotations
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
paths=["pages/overview.py","quality_valuation_ui.py","quality_valuation_store.py","ui_library/theme.py","app_version.py"]
src={}
for path in paths:
    src[path]=(ROOT/path).read_text(encoding="utf-8")
    ast.parse(src[path],filename=path)
assert 'APP_VERSION = "v19.22.0-rc16.33b"' in src["app_version.py"] or 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33b"' in src["app_version.py"] or "rc16.33b" in src["app_version.py"]
assert src["pages/overview.py"].index("QUALITY V2 · SHADOW") < src["pages/overview.py"].index("SUPER PORTEFØLJE")
assert "load_latest_manual" in src["quality_valuation_store.py"]
assert "⌂ Hovedsiden" in src["quality_valuation_ui.py"]
assert "def _warning_kind" in src["quality_valuation_ui.py"]
print("rc16.33b workflow gate OK")
