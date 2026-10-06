from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in [
    "app_version.py",
    "analyst.py",
    "earnings.py",
    "market_selector.py",
    "market_climate_ui.py",
    "mobile_analysis_view.py",
    "strategy_test_pro.py",
    "scheduled_runner.py",
]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
render = (ROOT / "render.yaml").read_text(encoding="utf-8")
runner = (ROOT / "scheduled_runner.py").read_text(encoding="utf-8")

version_lines = {line.strip() for line in version.splitlines()}
assert (
    'APP_VERSION = "v19.22.0-rc16.34d"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34e"' in version_lines
)
if 'APP_VERSION = "v19.22.0-rc16.34d"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34c"' in version_lines
else:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34d"' in version_lines

web, cron = render.split("  - type: cron", 1)
assert "plan: standard" in web
assert 'schedule: "*/15 * * * *"' in cron
for key, value in (
    ("APP_HISTORY_CACHE_MAX_ITEMS", '"1"'),
    ("APP_INFO_CACHE_MAX_ITEMS", '"8"'),
    ("APP_INSIDER_CACHE_MAX_ITEMS", '"8"'),
):
    assert key in web and value in web

assert "@st.cache_data(ttl=3600, max_entries=64" in (ROOT / "analyst.py").read_text(encoding="utf-8")
assert "@st.cache_data(ttl=3600, max_entries=64" in (ROOT / "earnings.py").read_text(encoding="utf-8")
assert "@st.cache_data(ttl=900, max_entries=48" in (ROOT / "market_selector.py").read_text(encoding="utf-8")
assert "@st.cache_data(ttl=900, max_entries=16" in (ROOT / "market_climate_ui.py").read_text(encoding="utf-8")
assert "@st.cache_data(ttl=300, max_entries=12" in (ROOT / "mobile_analysis_view.py").read_text(encoding="utf-8")
assert "@st.cache_data(ttl=30 * 60, max_entries=4" in (ROOT / "strategy_test_pro.py").read_text(encoding="utf-8")

assert "fifteen-minute Render cron" in runner
assert "fifteen-minute cron checks" in runner

print("rc16.34d Render memory right-size gate OK")
