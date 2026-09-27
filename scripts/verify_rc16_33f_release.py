from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
paths=["quality_valuation.py","quality_valuation_data.py","quality_valuation_ui.py","quality_extended_report.py","app_version.py"]
src={}
for p in paths:
    src[p]=(ROOT/p).read_text(encoding="utf-8")
    ast.parse(src[p], filename=p)

assert ('APP_VERSION = "v19.22.0-rc16.33f"' in src["app_version.py"]
        or 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33f"' in src["app_version.py"]
        or "rc16.33f" in src["app_version.py"])
assert 'quality_v1.3@1.3' in src["quality_valuation.py"]
for policy in ('"FINANCIAL"', '"REAL_ESTATE"', '"CYCLICAL"', '"CAPITAL_INTENSIVE"', '"STANDARD"'):
    assert policy in src["quality_valuation.py"]
assert "GRADE_COLORS" in src["quality_valuation.py"]
assert "overall_stars" in src["quality_valuation.py"]
assert "sector_specific_evidence" in src["quality_valuation.py"]
assert "combined ratio/solvens" in src["quality_valuation.py"]
assert "CET1/kapitaldekning" in src["quality_valuation.py"]
assert "_exchange_name" in src["quality_valuation_data.py"]
assert "fullExchangeName" in src["quality_valuation_data.py"]
assert "_star_html" in src["quality_valuation_ui.py"]
assert "_indicator_html" in src["quality_valuation_ui.py"]
assert "rating_stars" in src["quality_extended_report.py"]
assert "CAPITAL_INTENSIVE" in src["quality_extended_report.py"]
print("rc16.33f explainable-star/sector-robustness gate OK")
