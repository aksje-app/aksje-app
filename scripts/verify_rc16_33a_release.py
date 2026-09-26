"""Static architecture gate for rc16.33a."""
from __future__ import annotations
import ast, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
paths=["pages/overview.py","quality_v2_shadow_store.py","quality_model_v2.py","quality_v2_benchmark.py",
       "quality_extended_report.py","quality_valuation_data.py","quality_valuation.py","quality_valuation_ui.py","app_version.py"]
src={}
for path in paths:
    src[path]=(ROOT/path).read_text(encoding="utf-8")
    ast.parse(src[path],filename=path)
assert 'APP_VERSION = "v19.22.0-rc16.33a"' in src["app_version.py"]
assert "QUALITY V2 · SHADOW" in src["pages/overview.py"]
assert "MILESTONES = (10, 25, 50)" in src["quality_v2_shadow_store.py"]
assert "_write_milestone_evaluation" in src["quality_v2_shadow_store.py"]
assert "FINANCIAL_ROE" in src["quality_model_v2.py"]
assert "cyclical_normalization" in src["quality_model_v2.py"]
assert "REFERENCE_SYMBOLS" in src["quality_v2_benchmark.py"]
assert "Faktiske tilgjengelige regnskapsperioder" in src["quality_extended_report.py"]
assert "Driftsmargin" in src["quality_extended_report.py"] and "Gjeld" in src["quality_extended_report.py"]
assert '"audit_schema": "quality-diagnosis@2.1"' in src["quality_valuation_ui.py"]
assert '"production_effect": False' in src["quality_model_v2.py"]
manifest=json.loads((ROOT/"release_manifest.json").read_text(encoding="utf-8"))
assert all(row["status"] in {"IMPLEMENTED","MERGED","TESTED","DEPLOY_VERIFIED"} for row in manifest["items"] if row["release_blocker"])
print("rc16.33a architecture gate OK")
