"""Isolated tests of actual candidate input shapes; no network or writes."""
from datetime import datetime, timezone
import pandas as pd
from autonomous_portfolio import _autonomy_entry_inputs, _autonomy_entry_safety


def test_nested_pipeline_ohlc_is_used():
    raw = {"ticker":"MSFT", "decision_inputs": {
        "session_open": 100, "previous_close": 99,
        "session_date":"2026-10-12", "entry_signal_date":"2026-10-09"}}
    resolved = _autonomy_entry_inputs(raw)
    assert resolved["session_open"] == 100
    reason, price = _autonomy_entry_safety(raw, datetime(2026,10,12,14,tzinfo=timezone.utc))
    assert reason == "" and price == 100


def test_history_ohlc_does_not_invent_prior_signal():
    idx = pd.to_datetime(["2026-10-09","2026-10-12"])
    hist = pd.DataFrame({"Open":[98,100],"Close":[99,101]},index=idx)
    resolved = _autonomy_entry_inputs({"ticker":"MSFT","hist":hist})
    assert resolved["session_open"] == 100
    assert resolved["previous_close"] == 99
    assert resolved["session_date"] == "2026-10-12"
    assert "entry_signal_date" not in resolved
    reason, price = _autonomy_entry_safety({"ticker":"MSFT","hist":hist}, datetime(2026,10,12,14,tzinfo=timezone.utc))
    assert "UNVERIFIED" in reason and price == 0
