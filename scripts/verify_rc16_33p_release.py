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

assert 'APP_VERSION = "v19.22.0-' in version

for token in (
    "def portfolio_value_update(",
    '"portfolio_value": cfg.start_cash',
    '"portfolio_tracking_started_at": _now()',
    '"portfolio_value": performance["portfolio_value"]',
    '"portfolio_return_pct": performance["portfolio_return_pct"]',
    "Avkastning siden NAV-sporing",
):
    assert token in core, token

assert ("Teoretisk verdi" in page or "Porteføljeverdi" in page)
assert ("Superporteføljen – utvikling" in page or "Utvikling – totalt" in page)
assert ("Utvikling per aksje" in page or "Utvikling – alle aksjer" in page)
assert ("Teoretisk verdi NOK" in page or '"Verdi NOK"' in page)

for token in (
    "Siden NAV-start",
    "P/L NOK",
    "Åpne / del",
    "Print PDF",
):
    assert token in page, token

print("rc16.33p Super Portfolio Performance & Reports gate OK")
