from __future__ import annotations

import builtins
import sys
import types

import pandas as pd

from background_execution import background_execution, is_background_execution
from candidate_market_data import enrich_candidate_row
from investment_pipeline import (
    canonical_market_ticker,
    filter_candidate_rows_for_market,
)
from services.state_service import StateService
from ui_dataframe_guard import arrow_safe_dataframe


def test_background_state_service_never_imports_streamlit(monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "streamlit" or name.startswith("streamlit."):
            raise AssertionError("background worker attempted to import Streamlit")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    service = StateService()
    with background_execution("MBJ-RC15"):
        assert is_background_execution() is True
        assert service.get("missing", "fallback") == "fallback"
        service.set("ignored", 1)
    assert is_background_execution() is False


def test_candidate_filter_removes_non_equity_and_cross_market_symbols():
    rows = [
        {"ticker": "AAPL"},
        {"ticker": "US10Y"},
        {"ticker": "PEXIP"},
        {"ticker": "SPEMIX"},
        {"ticker": "SCRAN"},
    ]
    accepted, rejected = filter_candidate_rows_for_market(rows, "USA")
    assert [row["ticker"] for row in accepted] == ["AAPL"]
    reasons = {row["ticker"]: row["reason"] for row in rejected}
    assert reasons["US10Y"] == "NON_EQUITY_SYMBOL"
    assert reasons["SPEMIX"] == "NON_EQUITY_SYMBOL"
    assert reasons["PEXIP"].startswith("CROSS_MARKET_")
    assert reasons["SCRAN"] == "UNVERIFIED_PLAIN_US_SYMBOL"


def test_verified_oslo_aliases_receive_yahoo_suffix():
    assert canonical_market_ticker("IDEX", "Norge") == "IDEX.OL"
    assert canonical_market_ticker("PEXIP", "Norge") == "PEXIP.OL"


def test_yfinance_history_receives_bounded_timeout(monkeypatch, tmp_path):
    captured = {}

    class FakeIndexValue:
        def isoformat(self):
            return "2026-08-05T00:00:00+00:00"

        def date(self):
            return "2026-08-05"

    class FakeHistory(pd.DataFrame):
        @property
        def _constructor(self):
            return FakeHistory

    history = FakeHistory({
        "Close": [100.0 + i for i in range(260)],
        "Volume": [1000.0 for _ in range(260)],
    })
    history.index = pd.Index([FakeIndexValue() for _ in range(260)])

    class FakeTicker:
        def __init__(self, ticker):
            captured["ticker"] = ticker

        def history(self, **kwargs):
            captured.update(kwargs)
            return history

        @property
        def info(self):
            return {"shortName": "Apple"}

    fake_yf = types.SimpleNamespace(Ticker=FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setattr("candidate_market_data.CACHE_DIR", tmp_path)
    row = enrich_candidate_row({"ticker": "AAPL", "market": "USA"}, force_refresh=True)
    assert captured["ticker"] == "AAPL"
    assert 3 <= float(captured["timeout"]) <= 30
    assert row["data_fetch_status"] == "OK"


def test_arrow_guard_normalizes_blank_numeric_weight_column():
    frame = pd.DataFrame({"Weight": [1.5, "", None, "2.75"], "Label": ["A", "B", "C", "D"]})
    safe = arrow_safe_dataframe(frame)
    assert str(safe["Weight"].dtype) != "object"
    assert pd.isna(safe.loc[1, "Weight"])
    assert float(safe.loc[3, "Weight"]) == 2.75


def test_report_worker_has_independent_heartbeat_and_progress_timestamps():
    source = open("manual_job_background.py", encoding="utf-8").read()
    assert "manual-heartbeat-" in source
    assert 'current["worker_heartbeat_at"]' in source
    assert '"last_progress_at": _now()' in source
    assert "with background_execution(execution_id):" in source


def test_scan_profile_widget_does_not_mix_session_value_and_default_index():
    source = open("market_intelligence.py", encoding="utf-8").read()
    block = source[source.index('scan_state_token ='):source.index('st.caption(f"Planlagt maksimum:')]
    assert 'if "mi_scan_profile_v18693" not in st.session_state:' in block
    assert 'scan_profile_kwargs["index"]' in block
    assert 'st.selectbox("Skanneprofil per marked", scan_profile_options, **scan_profile_kwargs)' in block
