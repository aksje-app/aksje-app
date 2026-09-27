from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
paths=["quality_v2_shadow_store.py","pages/overview.py","app_version.py"]
src={}
for p in paths:
    src[p]=(ROOT/p).read_text(encoding="utf-8")
    ast.parse(src[p], filename=p)

assert ('APP_VERSION = "v19.22.0-rc16.33e"' in src["app_version.py"]
        or 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33e"' in src["app_version.py"]
        or "rc16.33e" in src["app_version.py"])
assert '"disagreement_observations_total"' in src["quality_v2_shadow_store.py"]
assert '"disagreement_count": current_disagreements' in src["quality_v2_shadow_store.py"]
assert ("VURDERT NÅ" in src["pages/overview.py"] or "VURDERT I SISTE KJØRING" in src["pages/overview.py"])
assert ("AKTIVE V1.1 ↔ V2 UENIGHETER" in src["pages/overview.py"]
        or "UENIGHETER NÅ" in src["pages/overview.py"])
assert "latest_shadow" in src["pages/overview.py"]
print("rc16.33e current-shadow-count gate OK")
