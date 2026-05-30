from pathlib import Path
import py_compile

import universe_engine


for name in [
    "daily_ai_market_report.py",
    "forecast_ui.py",
    "analysis_universe_ai.py",
    "services/universe_service.py",
    "universe_engine.py",
    "app.py",
    "app_version.py",
]:
    py_compile.compile(name, doraise=True)

app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
daily = Path("daily_ai_market_report.py").read_text(encoding="utf-8", errors="ignore")
forecast = Path("forecast_ui.py").read_text(encoding="utf-8", errors="ignore")
analysis = Path("analysis_universe_ai.py").read_text(encoding="utf-8", errors="ignore")
service = Path("services/universe_service.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.4r"' in version

# 1. Hidden defaults must not appear as UI values in the main user-facing modules.
for source in [daily, forecast, service]:
    assert 'value="AAPL,MSFT,NVDA"' not in source
    assert 'value="AAPL,NVDA,MSFT"' not in source
    assert 'default_manual = "AAPL"' not in source
    assert 'manual_raw else "AAPL"' not in source

# 2. Daily Report manual input may only be an explicit manual source, not a fallback.
assert "Manuelle tickere (brukes kun ved fokus Manuelle tickere)" in daily
assert "Manuell fallback" not in daily
assert "Bruker markedsunivers" in daily

# 3. Analyseunivers/UniverseService Markedvalg must not pass manual tickers into market resolution.
assert 'manual_ticker=""' in service
assert 'manual_ticker=manual_ticker if mode in {"Markedvalg", "Multi-marked"} else ""' not in service

tickers, source = universe_engine.resolve_strict_universe_tickers(
    {"mode": "Markedvalg", "scopes": ["Watchlist"], "manual_ticker": "AAPL", "max_count": 5},
    existing_tickers_by_scope={"Watchlist": ["MSFT"], "USA": ["AAPL"]},
)
assert source == "Markedvalg"
assert "AAPL" not in tickers

tickers, source = universe_engine.resolve_strict_universe_tickers(
    {"mode": "Manuell liste", "scopes": ["Manuell liste"], "manual_list": "AAPL,MSFT", "max_count": 5},
    existing_tickers_by_scope={"Watchlist": ["EQNR.OL"]},
)
assert source == "Manuell liste"
assert tickers == ["AAPL", "MSFT"]

# 4. UI navigation should not start heavy dashboard/banner work while control center state is active.
assert "_cc_fast_nav_v1863ak" in app
assert "if not _cc_fast_nav_v1863ak" in app
assert "startup_heavy_update_pending_v1863an" in app
assert "_clear_startup_heavy_update_for_control_center_v1863an()" in app

# 5. Visual-smoke static guard: no user-facing panel should introduce known legacy default text as a rendered default.
rendered_defaults = [
    'value="AAPL,MSFT,NVDA"',
    'value="AAPL,NVDA,MSFT"',
    'value=st.session_state.get("daily_report_manual_v1862", "AAPL,MSFT,NVDA")',
]
for needle in rendered_defaults:
    assert needle not in daily + forecast + analysis + app










