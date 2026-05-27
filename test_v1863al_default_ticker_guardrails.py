from pathlib import Path
import py_compile
import sys
import types


for name in ["daily_ai_market_report.py", "forecast_ui.py", "ai_service_bridge.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")
daily = Path("daily_ai_market_report.py").read_text(encoding="utf-8", errors="ignore")
forecast = Path("forecast_ui.py").read_text(encoding="utf-8", errors="ignore")
bridge = Path("ai_service_bridge.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.4d"' in version

for source in [daily, forecast, bridge]:
    assert 'else "AAPL,MSFT,NVDA"' not in source
    assert 'value=st.session_state.get("daily_report_manual_v1862", "AAPL,MSFT,NVDA")' not in source
    assert 'default_manual = "AAPL"' not in source
    assert 'else "AAPL"' not in source

assert "Manuell fallback" not in daily
assert "Manuelle tickere (brukes kun ved fokus Manuelle tickere)" in daily
assert "Bruker markedsunivers" in daily

sys.modules.setdefault("streamlit", types.SimpleNamespace(session_state={}))
import daily_ai_market_report as report

report.st.session_state.clear()
report.resolve_universe_tickers = lambda scopes, max_count=20: ["NOKIA.HE", "NESTE.HE"]
rows, diagnostics = report.resolve_report_candidates("Hele markedet", "Finland", 20, manual="AAPL,MSFT,NVDA")
assert [row["ticker"] for row in rows] == ["NOKIA.HE", "NESTE.HE"]
assert all(row["source"] != "Manuell fallback" for row in rows)
assert "AAPL" not in {row["ticker"] for row in rows}






