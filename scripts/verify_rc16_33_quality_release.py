"""Static release gate for rc16.33 Quality v1.1 + V2 Shadow."""
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = {
    name: (ROOT / name).read_text(encoding="utf-8")
    for name in ("quality_valuation.py", "quality_model_v2.py", "quality_v2_shadow_store.py",
                 "quality_extended_report.py", "quality_valuation_ui.py", "quality_valuation_data.py", "app_version.py")
}
for name, source in files.items():
    ast.parse(source, filename=name)

assert 'APP_VERSION = "v19.22.0-rc16.33"' in files["app_version.py"]
assert '"production_effect": False' in files["quality_model_v2.py"]
assert '"shadow_only": True' in files["quality_model_v2.py"]
assert 'MILESTONES = (10, 25, 50)' in files["quality_v2_shadow_store.py"]
assert 'quality_state = "IMPROVING"' in files["quality_valuation.py"]
assert 'roce_trend == "SVEKKENDE"' in files["quality_valuation.py"]
assert 'free_cash_flow_history' in files["quality_valuation_data.py"]
assert 'Last ned utvidet analyse PDF' in files["quality_valuation_ui.py"]
assert '"quality_v2_shadow": result.get("quality_v2_shadow")' in files["quality_valuation_ui.py"]
assert 'raw_provider_payloads_included' in files["quality_valuation_ui.py"]
print("GO rc16.33: syntax + V1.1/V2 shadow/report/diagnosis architecture gates OK")
