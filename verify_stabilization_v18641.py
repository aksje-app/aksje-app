from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
app = ROOT / "app.py"
text = app.read_text(encoding="utf-8-sig")

required = [
    "from ui_sidebar_stable import render_stable_sidebar_v18641",
    "show_drift_controls_v1863cc = render_stable_sidebar_v18641",
    "dashboard2026_last_valid_kpi_snapshot_v18641",
]
missing = [x for x in required if x not in text]
if missing:
    raise SystemExit(f"Missing stabilization markers: {missing}")

for file_name in ["app.py", "ui_sidebar_stable.py", "app_version.py"]:
    ast.parse((ROOT / file_name).read_text(encoding="utf-8-sig"))

print("v18.6.41 stabilization verification OK")
