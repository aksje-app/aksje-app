from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in [
    "super_portfolio.py",
    "pages/super_portfolio.py",
    "app_version.py",
]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
core = (ROOT / "super_portfolio.py").read_text(encoding="utf-8")
page = (ROOT / "pages" / "super_portfolio.py").read_text(encoding="utf-8")

assert 'APP_VERSION = "v19.22.0-rc16.33p"' in version
assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33o"' in version

for token in (
    "def portfolio_value_update(",
    '"portfolio_value": cfg.start_cash',
    '"portfolio_tracking_started_at": _now()',
    '"portfolio_value": performance["portfolio_value"]',
    '"portfolio_return_pct": performance["portfolio_return_pct"]',
    "Avkastning siden NAV-sporing",
):
    assert token in core, token

for token in (
    "Teoretisk verdi",
    "Siden NAV-start",
    "Superporteføljen – utvikling",
    "Utvikling per aksje",
    "Teoretisk verdi NOK",
    "P/L NOK",
    "Åpne / del",
    "Print PDF",
):
    assert token in page, token

print("rc16.33p Super Portfolio Performance & Reports gate OK")
