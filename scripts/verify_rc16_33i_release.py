from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
paths=[
    "quality_valuation.py",
    "quality_valuation_ui.py",
    "quality_extended_report.py",
    "quality_model_v2.py",
    "quality_v2_shadow_store.py",
    "pages/overview.py",
    "public_report_ui.py",
    "ui_library/shell.py",
    "ui_library/theme.py",
    "app_version.py",
]
src={}
for p in paths:
    src[p]=(ROOT/p).read_text(encoding="utf-8")
    ast.parse(src[p], filename=p)

assert ('APP_VERSION = "v19.22.0-rc16.33i"' in src["app_version.py"]
        or 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33i"' in src["app_version.py"]
        or "rc16.33i" in src["app_version.py"])
assert "IKKE KLASSIFISERT ENNÅ" in src["pages/overview.py"]
assert "Ny kvalitetskjøring kreves" in src["pages/overview.py"]
assert "classification_available" in src["quality_model_v2.py"]
assert "classification_available" in src["quality_v2_shadow_store.py"]
assert "tone-neutral" in src["ui_library/theme.py"]
assert "flex-wrap:nowrap!important" in src["ui_library/theme.py"]
assert "_render_in_app_file" in src["public_report_ui.py"]
assert "st.download_button" in src["public_report_ui.py"]
assert "ensure_valuation_context" in src["quality_valuation.py"]
assert "ensure_valuation_context(dict(item))" in src["quality_valuation_ui.py"]
assert "ensure_valuation_context(dict(item))" in src["quality_extended_report.py"]
assert "QUALITY_CONFIRMED" in src["quality_valuation.py"]
print("rc16.33i quality navigation/consistency gate OK")
