import sys
import types

class SessionState(dict):
    pass

class ExpanderMock:
    def __enter__(self): return self
    def __exit__(self, *args): return None

streamlit_mock = types.SimpleNamespace(
    session_state=SessionState(),
    expander=lambda *a, **k: ExpanderMock(),
    caption=lambda *a, **k: None,
    button=lambda *a, **k: False,
    columns=lambda n, **k: [types.SimpleNamespace(metric=lambda *a, **k: None) for _ in range(n)],
    markdown=lambda *a, **k: None,
    write=lambda *a, **k: None,
    dataframe=lambda *a, **k: None,
    info=lambda *a, **k: None,
    success=lambda *a, **k: None,
)
sys.modules["streamlit"] = streamlit_mock

from daily_ai_market_report import build_daily_market_report, render_daily_ai_market_report

report = build_daily_market_report()
assert "date" in report
assert "alerts" in report
assert "forecasts" in report
render_daily_ai_market_report()
print("daily_ai_market_report smoke test OK")
