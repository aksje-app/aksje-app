import sys
import types

import pandas as pd

streamlit_mock = sys.modules.get("streamlit")
if streamlit_mock is None:
    streamlit_mock = types.SimpleNamespace(session_state={})
    sys.modules["streamlit"] = streamlit_mock
if not hasattr(streamlit_mock, "cache_data"):
    streamlit_mock.cache_data = lambda **kwargs: (lambda func: func)
if not hasattr(streamlit_mock, "session_state"):
    streamlit_mock.session_state = {}

from strategy_testing_workspace import _normalise_history_frame, _run_basic_strategy_test


def test_normalise_history_frame_accepts_yfinance_multiindex_close():
    cols = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Volume", "AAPL")])
    df = pd.DataFrame([[100.0, 1000], [101.0, 1100]], index=pd.date_range("2024-01-01", periods=2), columns=cols)

    out = _normalise_history_frame(df, "AAPL")

    assert out is not None
    assert "Close" in out.columns
    assert list(out["Close"]) == [100.0, 101.0]


def test_basic_strategy_run_persists_renderable_payload(monkeypatch):
    hist = pd.DataFrame(
        {"Close": [100.0, 102.0, 101.0, 105.0]},
        index=pd.date_range("2024-01-01", periods=4),
    )

    monkeypatch.setattr("strategy_testing_workspace._fetch_history", lambda ticker, period: (hist, None))

    result = _run_basic_strategy_test("AAPL", "6mo")

    assert result["ok"] is True
    assert result["ticker"] == "AAPL"
    assert result["period"] == "6mo"
    assert result["value"] > 0
    assert not result["equity"].empty
    assert "stats" in result
