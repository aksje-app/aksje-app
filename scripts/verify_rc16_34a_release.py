from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in [
    "app.py",
    "app_version.py",
    "quality_valuation_ui.py",
    "pages/overview.py",
    "pages/super_portfolio.py",
    "public_report_ui.py",
    "quality_stability_contract.py",
    "ui_library/shell.py",
]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
app = (ROOT / "app.py").read_text(encoding="utf-8")
quality = (ROOT / "quality_valuation_ui.py").read_text(encoding="utf-8")
overview = (ROOT / "pages" / "overview.py").read_text(encoding="utf-8")
portfolio = (ROOT / "pages" / "super_portfolio.py").read_text(encoding="utf-8")
report = (ROOT / "public_report_ui.py").read_text(encoding="utf-8")
shell = (ROOT / "ui_library" / "shell.py").read_text(encoding="utf-8")

assert 'APP_VERSION = "v19.22.0-rc16.34a"' in version
assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33q"' in version

assert "def resolve_market_bound_manual_tickers(" in quality
assert "selected_market: str = \"\"" in quality
assert "market_errors" in quality
assert "def validate_result_tickers_within_requested_market(" in quality
assert "MARKET_IDENTITY_MISMATCH" in quality
assert 'result["selected_market"] = str(selected_market or "")' in quality
assert 'result_market != str(selected_market).strip()' in quality
assert 'selected_market=str(config.get("market") or "AI kildegrunnlag")' in app

assert 'state.get("portfolio_value")' in overview
assert 'state.get("portfolio_return_pct")' in overview
assert 'snapshot.get("portfolio_return_pct")' in overview

assert '"super_portfolio"' in report
assert 'return {"aa_nav": "super_portfolio"}' in report
assert 'Tilbake til Super Portfolio' in report
assert portfolio.count('with_report_return(report_url, "super_portfolio")') >= 2
assert 'with_report_return(report_url, "portfolio")' not in portfolio
assert '"super_portfolio":"autonomy"' in shell

print("rc16.34a Production Readiness Audit gate OK")
