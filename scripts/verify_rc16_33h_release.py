from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
paths=[
    "quality_valuation.py",
    "quality_valuation_ui.py",
    "quality_extended_report.py",
    "quality_valuation_store.py",
    "quality_model_v2.py",
    "quality_v2_shadow_store.py",
    "pages/overview.py",
    "ui_library/shell.py",
    "ui_library/theme.py",
    "app_version.py",
]
src={}
for p in paths:
    src[p]=(ROOT/p).read_text(encoding="utf-8")
    ast.parse(src[p], filename=p)

assert ('APP_VERSION = "v19.22.0-rc16.33h"' in src["app_version.py"]
        or 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33h"' in src["app_version.py"]
        or "rc16.33h" in src["app_version.py"])
assert "KURS / PRIS" in src["quality_valuation_ui.py"]
assert "VERDSETTELSE" in src["quality_valuation_ui.py"]
assert "P/E er multipler, ikke aksjekurs." in src["quality_valuation_ui.py"]
assert "valuation_position_text" in src["quality_valuation.py"]
assert "peer_basis_quality" in src["quality_valuation.py"]
assert "previous_overall_stars" in src["quality_valuation_store.py"]
assert "v2_weaker_count" in src["quality_model_v2.py"]
assert "v2_stronger_count" in src["quality_model_v2.py"]
assert "v2_weaker_tickers" in src["quality_v2_shadow_store.py"]
assert ("AV DISSE: V2 SVAKERE" in src["pages/overview.py"] or "V2 SVAKERE" in src["pages/overview.py"])
assert ("AV DISSE: V2 STERKERE" in src["pages/overview.py"] or "V2 STERKERE" in src["pages/overview.py"])
assert 'ShellRoute("overview","Start","overview")' in src["ui_library/shell.py"]
assert "repeat(5" in src["ui_library/theme.py"]
print("rc16.33h quality-clarity/start-navigation gate OK")
