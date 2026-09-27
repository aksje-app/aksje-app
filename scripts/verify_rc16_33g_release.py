from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
paths=["quality_valuation_ui.py","quality_extended_report.py","public_report_ui.py","app_version.py"]
src={}
for p in paths:
    src[p]=(ROOT/p).read_text(encoding="utf-8")
    ast.parse(src[p], filename=p)

assert ('APP_VERSION = "v19.22.0-rc16.33g"' in src["app_version.py"]
        or 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33g"' in src["app_version.py"]
        or "rc16.33g" in src["app_version.py"])
assert "_quality_report_choice_cards" in src["quality_valuation_ui.py"]
assert "← Tilbake til Kvalitet" in src["quality_valuation_ui.py"]
assert "return_to=quality_reports" in src["quality_valuation_ui.py"]
assert '_absolute_report_return_url("quality_reports")' in src["quality_valuation_ui.py"]
assert '_absolute_report_return_url("quality_reports")' in src["quality_extended_report.py"]
assert '"quality_reports"' in src["public_report_ui.py"]
assert "← Tilbake til rapportvalg" in src["public_report_ui.py"]
assert "Skriv ut PDF" in src["public_report_ui.py"]
assert "Del / åpne PDF" in src["public_report_ui.py"]
assert "render_mobile_file_delivery" not in src["public_report_ui.py"]
assert "st.code" not in src["public_report_ui.py"]
print("rc16.33g quality-report-ux gate OK")
