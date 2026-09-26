from __future__ import annotations
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
paths=["quality_valuation_ui.py","quality_extended_report.py","quality_report_package.py","public_report_ui.py","app_version.py"]
src={}
for p in paths:
    src[p]=(ROOT/p).read_text(encoding="utf-8"); ast.parse(src[p],filename=p)
assert 'APP_VERSION = "v19.22.0-rc16.33c"' in src["app_version.py"]
assert "Last ned / del diagnose" in src["quality_valuation_ui.py"]
assert "Last ned / del komplett kontrollpakke" in src["quality_valuation_ui.py"]
assert '_absolute_report_return_url("overview")' in src["quality_valuation_ui.py"]
assert '_absolute_report_return_url("overview")' in src["quality_extended_report.py"]
print("rc16.33c report-package gate OK")
