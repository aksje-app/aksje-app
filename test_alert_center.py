import sys
import types

class SessionState(dict):
    pass

class ExpanderMock:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None

def columns_mock(spec, **kwargs):
    count = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
    return [ExpanderMock() for _ in range(count)]

streamlit_mock = types.SimpleNamespace(
    session_state=SessionState(),
    info=lambda *a, **k: None,
    caption=lambda *a, **k: None,
    expander=lambda *a, **k: ExpanderMock(),
    columns=columns_mock,
    selectbox=lambda label, options, *a, **k: options[0],
    button=lambda *a, **k: False,
    write=lambda *a, **k: None,
    dataframe=lambda *a, **k: None,
)
sys.modules["streamlit"] = streamlit_mock

from alert_center import collect_common_alerts, render_common_alert_center

streamlit_mock.session_state["paper_portfolio"] = {"AAPL": {"value": 1000}}
alerts = collect_common_alerts()
assert isinstance(alerts, list)
assert any(a.get("source") == "Paper trading" for a in alerts)

render_common_alert_center()
print("alert_center smoke test OK")
