import sys
import types

class SessionState(dict):
    pass

class ExpanderMock:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None

streamlit_mock = types.SimpleNamespace(
    session_state=SessionState(),
    expander=lambda *a, **k: ExpanderMock(),
    caption=lambda *a, **k: None,
    columns=lambda n, **k: [types.SimpleNamespace(metric=lambda *a, **k: None) for _ in range(n)],
    metric=lambda *a, **k: None,
    markdown=lambda *a, **k: None,
    dataframe=lambda *a, **k: None,
    info=lambda *a, **k: None,
    success=lambda *a, **k: None,
    write=lambda *a, **k: None,
)
sys.modules["streamlit"] = streamlit_mock

from market_intelligence_center import _market_regime_guess, _top_rows, render_market_intelligence_center

summaries = [
    {"ticker": "AAPL", "horizon": "1m", "strength": 80, "confidence": 70, "base_pct": 5, "bull_pct": 10, "bear_pct": -3, "risk": "Lav"},
    {"ticker": "TSLA", "horizon": "1m", "strength": 30, "confidence": 40, "base_pct": -4, "bull_pct": 5, "bear_pct": -12, "risk": "Høy"},
]
assert _market_regime_guess(summaries, []) in ["Bull / positivt", "Nøytralt / blandet", "Bear / svakt"]
assert _top_rows(summaries, reverse=True)[0]["Ticker"] == "AAPL"
render_market_intelligence_center()
print("market_intelligence_center smoke test OK")
