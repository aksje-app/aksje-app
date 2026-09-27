from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
paths=[
    "app.py", "quality_stability_contract.py", "public_report_ui.py",
    "pdf_mobile_return.py", "quality_valuation.py", "quality_valuation_ui.py",
    "quality_model_v2.py", "pages/overview.py", "app_version.py",
]
src={}
for p in paths:
    src[p]=(ROOT/p).read_text(encoding="utf-8")
    ast.parse(src[p], filename=p)

assert ('APP_VERSION = "v19.22.0-rc16.33j"' in src["app_version.py"]
        or 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33j"' in src["app_version.py"]
        or "rc16.33j" in src["app_version.py"])
assert "if is_supported_deep_link_nav(nav_from_url):" in src["app.py"]
assert '"quality_valuation"' in src["quality_stability_contract.py"]
assert "REPORT_RETURN_ROUTE_REJECTED" in src["quality_stability_contract.py"]
assert "for page_number, page in enumerate(reader.pages)" in src["pdf_mobile_return.py"]
assert "Appens rapportvalg blir stående i denne fanen." in src["public_report_ui.py"]
assert "_enforce_semantic_consistency" in src["quality_valuation.py"]
assert (ROOT/"QUALITY_STABILIZATION.md").exists()
print("rc16.33j quality stabilization gate OK")
