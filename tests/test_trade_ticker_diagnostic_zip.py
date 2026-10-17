"""Per-ticker ZIP must reveal failures and preserve forensic decision trace."""
import io
import json
import zipfile

import durable_runtime
import super_portfolio


def test_per_ticker_zip_includes_operational_errors_and_shadow_decisions(monkeypatch):
    def fake_events(key, path, limit=500):
        if key == "operations/errors.jsonl":
            return [{"event": "SOURCE-FETCH-FAILED", "error_code": "RATE_LIMIT", "severity": "WARNING"}]
        return [{"event": "EVALUATE", "changes": [{"action": "SELL", "ticker": "LLY"}]}]
    monkeypatch.setattr(durable_runtime, "read_events", fake_events)
    state = {"source_run_id": "TEST-1", "decision_trace": {"decision_run_id": "TEST-1", "by_ticker": {"LLY": {"ticker": "LLY", "action": "SELL"}}}, "positions": {}}
    payload = super_portfolio.build_diagnostic_zip(state, ticker="LLY")
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert z.testzip() is None
        assert json.loads(z.read("recent_errors.json"))[0]["error_code"] == "RATE_LIMIT"
        assert json.loads(z.read("recent_shadow_decisions.json"))[0]["changes"][0]["ticker"] == "LLY"
        manifest = json.loads(z.read("manifest.json"))
        assert any(row["path"] == "selected_ticker.json" for row in manifest["files"])
        assert manifest["strategy_validated"] is False


def test_per_ticker_zip_explicit_when_logs_unavailable(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("log unavailable")
    monkeypatch.setattr(durable_runtime, "read_events", broken)
    state = {"decision_trace": {"by_ticker": {}}, "positions": {}}
    with zipfile.ZipFile(io.BytesIO(super_portfolio.build_diagnostic_zip(state, ticker="LLY"))) as z:
        assert "recent_errors_unavailable.json" in z.namelist()
        assert "recent_shadow_unavailable.json" in z.namelist()
        assert z.testzip() is None
