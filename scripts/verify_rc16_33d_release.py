from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = [
    "quality_valuation.py",
    "quality_valuation_data.py",
    "quality_valuation_ui.py",
    "quality_extended_report.py",
    "pdf_mobile_return.py",
    "public_report_ui.py",
    "app_version.py",
]
src = {}
for path in paths:
    src[path] = (ROOT / path).read_text(encoding="utf-8")
    ast.parse(src[path], filename=path)

assert ('APP_VERSION = "v19.22.0-rc16.33d"' in src["app_version.py"]
        or 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33d"' in src["app_version.py"]
        or "rc16.33d" in src["app_version.py"])
assert 'quality_v1.2@1.2' in src["quality_valuation.py"]
assert '"FINANCIAL"' in src["quality_valuation.py"]
assert '"REAL_ESTATE"' in src["quality_valuation.py"]
assert '"CYCLICAL"' in src["quality_valuation.py"]
assert "peer_tickers" in src["quality_valuation.py"]
assert "fiscal_periods[0]" in src["quality_valuation_data.py"]
assert "P/E ved dagens kurs" in src["quality_valuation_ui.py"]
assert "P/E ved dagens kurs" in src["quality_extended_report.py"]
assert "publish_durable_pdf" in src["quality_valuation_ui.py"]
assert "publish_durable_file" in src["quality_valuation_ui.py"]
assert "PDF-returknappen er skjerm-only" in src["quality_valuation_ui.py"]
assert "NumberObject(0)" in src["pdf_mobile_return.py"]
print("rc16.33d sector-aware quality/mobile-report gate OK")
