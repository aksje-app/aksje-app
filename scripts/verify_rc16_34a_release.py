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
    "market_universe.py",
    "market_intelligence.py",
    "pages/top_picks.py",
    "investment_pipeline.py",
    "analysis_universe_ai.py",
]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
app = (ROOT / "app.py").read_text(encoding="utf-8")
quality = (ROOT / "quality_valuation_ui.py").read_text(encoding="utf-8")
overview = (ROOT / "pages" / "overview.py").read_text(encoding="utf-8")
portfolio = (ROOT / "pages" / "super_portfolio.py").read_text(encoding="utf-8")
report = (ROOT / "public_report_ui.py").read_text(encoding="utf-8")
shell = (ROOT / "ui_library" / "shell.py").read_text(encoding="utf-8")

version_lines = {line.strip() for line in version.splitlines()}
assert (
    'APP_VERSION = "v19.22.0-rc16.34a"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34b"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34c"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34d"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34e"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34f"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34g"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34h"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34i"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34j"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34k"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34l"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34n"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34m"' in version_lines
)
if 'APP_VERSION = "v19.22.0-rc16.34a"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33q"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34b"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34a"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34c"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34b"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34d"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34c"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34e"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34d"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34f"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34e"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34g"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34f"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34h"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34g"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34i"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34h"' in version_lines
else:
    assert ('PREVIOUS_APP_VERSION = "v19.22.0-rc16.34m"' if 'APP_VERSION = "v19.22.0-rc16.34n"' in version_lines else 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34l"' if 'APP_VERSION = "v19.22.0-rc16.34m"' in version_lines else 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34k"' if 'APP_VERSION = "v19.22.0-rc16.34l"' in version_lines else 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34j"' if 'APP_VERSION = "v19.22.0-rc16.34k"' in version_lines else 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34i"') in version_lines

market_universe = (ROOT / "market_universe.py").read_text(encoding="utf-8")
assert "def production_market_scope_options(" in market_universe
assert "production_market_scope_options(include_aggregate=True)" in app
assert "production_market_scope_options(include_aggregate=True)" in (ROOT / "pages/top_picks.py").read_text(encoding="utf-8")
pipeline_src = (ROOT / "investment_pipeline.py").read_text(encoding="utf-8")
assert "production_market_scope_options(include_aggregate=True)" in pipeline_src
assert 'activation in {"PRODUCTION", "SHADOW"}' in pipeline_src
assert 'OFF markets (Brazil)' in pipeline_src
assert "production_market_scope_options(include_aggregate=True)" in (ROOT / "analysis_universe_ai.py").read_text(encoding="utf-8")
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
assert (
    'returning_report_url = with_report_return(report_url, "super_portfolio")' in portfolio
    or 'report_link = with_report_return(report_url, "super_portfolio")' in portfolio
)
assert ('st.code(returning_report_url' in portfolio or 'st.code(report_link' in portfolio)
assert 'with_report_return(report_url, "portfolio")' not in portfolio
assert ('"super_portfolio":"autonomy"' in shell or '"super_portfolio":"market"' in shell)

print("rc16.34a Production Readiness Audit gate OK")
