import sys
import types

class SessionState(dict):
    pass

class ExpanderMock:
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def metric(self, *a, **k): return None

def columns_mock(spec, **kwargs):
    count = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
    return [ExpanderMock() for _ in range(count)]

streamlit_mock = types.SimpleNamespace(
    session_state=SessionState(),
    expander=lambda *a, **k: ExpanderMock(),
    caption=lambda *a, **k: None,
    button=lambda *a, **k: False,
    selectbox=lambda label, options, *a, **k: options[0],
    multiselect=lambda label, options, *a, **k: k.get("default", []),
    text_input=lambda *a, **k: "",
    number_input=lambda *a, **k: k.get("value", 0),
    checkbox=lambda *a, **k: k.get("value", False),
    columns=columns_mock,
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
