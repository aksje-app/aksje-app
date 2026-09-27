from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
paths=[
    "quality_model_v2.py",
    "quality_v2_shadow_store.py",
    "pages/overview.py",
    "ui_library/theme.py",
    "quality_stability_contract.py",
    "app_version.py",
]
src={}
for p in paths:
    src[p]=(ROOT/p).read_text(encoding="utf-8")
    ast.parse(src[p], filename=p)

assert 'APP_VERSION = "v19.22.0-rc16.33k"' in src["app_version.py"]
assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33j"' in src["app_version.py"]
assert 'CLASSIFICATION_SCHEMA = "quality_v2_direction@1"' in src["quality_model_v2.py"]
assert "build_shadow_comparison" in src["quality_v2_shadow_store.py"]
assert "comparison_available" in src["quality_v2_shadow_store.py"]
assert "unchanged_disagreement_tickers" in src["quality_v2_shadow_store.py"]
assert "Ingen sammenlignbar tidligere klassifisering" in src["pages/overview.py"]
assert "KOMPLETTE KJØRINGER" in src["pages/overview.py"]
assert "VURDERT I SISTE KJØRING" in src["pages/overview.py"]
assert "aa-v2-detail-row" in src["ui_library/theme.py"]
assert "V2_TICKER_DIRECTION_OVERLAP" in src["quality_stability_contract.py"]
print("rc16.33k V2 panel semantics gate OK")
