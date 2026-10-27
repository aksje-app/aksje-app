"""Regression tests for startup preflight without stale simulated orders."""
from datetime import datetime, timezone
import pytest

from services import production_routing as routing
from services import simulation_restart as restart
from services import restart_trading as trading
from services import trading_costs


class FakeStore:
    def __init__(self, held=None):
        self.bundle = {"accounts": {"autonomy": {"account": {"positions": held or {}}},
                                   "super_portfolio": {"account": {"positions": held or {}}},
                                   "paper": {"account": {"positions": held or {}}}}}
    def read_json(self, key):
        return self.bundle


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(restart, "verify_bundle", lambda bundle: None)
    monkeypatch.setattr(routing, "strategy_settings", lambda *a, **k: {})
    monkeypatch.setattr(trading_costs, "validate_family", lambda *a, **k: None)
    monkeypatch.setattr(restart, "_key", lambda period: "fixture")
    calls = []
    def preview(**kw):
        calls.append(kw)
        return {"mode": "DRY_RUN_NO_ORDERS_NO_PERSISTENT_WRITES", "evidence": kw["evidence"]}
    monkeypatch.setattr(trading, "preview", preview)
    return calls


def test_autonomy_excludes_one_stale_unheld_candidate_with_explicit_block(monkeypatch,stub):
    candidates = [{"ticker": "STECH.OL", "currency": "NOK"}] + [
        {"ticker": f"OK{i}.OL", "currency": "NOK"} for i in range(10)]
    def evidence(ticker, **kw):
        if ticker == "STECH.OL":
            raise ValueError("Missing documented execution price: STECH.OL; stale")
        return {"price": 100, "currency": "NOK", "observed_at": kw["at"], "source": "documented"}
    monkeypatch.setattr(routing, "market_evidence", evidence)
    result = routing.live_preview("p", "autonomy", strategy_input=candidates,
                                  cost_policy={}, storage=FakeStore())
    assert result["preflight_excluded_candidates"][0]["ticker"] == "STECH.OL"
    assert result["preflight_excluded_candidates"][0]["action"] == "NO_EXECUTION"
    assert "STECH.OL" not in stub[0]["evidence"]
    assert all(row["ticker"] != "STECH.OL" for row in stub[0]["strategy_input"])
    assert len(candidates) == 11  # Original recorded input is not modified


def test_super_portfolio_preserves_pipeline_identity_and_exclusion(monkeypatch,stub):
    pipeline = {"run_id": "original", "candidates": [
        {"ticker": "FSKRS.HE", "currency": "EUR", "source": "Super Portfolio independent market universe"},
        *[{"ticker": f"OK{i}.OL", "currency": "NOK",
           "source": "Super Portfolio independent market universe"} for i in range(10)]]}
    def evidence(ticker, **kw):
        if ticker == "FSKRS.HE":
            raise ValueError("stale")
        return {"price": 100, "currency": "NOK", "observed_at": kw["at"], "source": "documented"}
    monkeypatch.setattr(routing, "market_evidence", evidence)
    result = routing.live_preview("p", "super_portfolio", strategy_input=pipeline,
                                  cost_policy={}, storage=FakeStore())
    assert result["preflight_excluded_candidates"][0]["ticker"] == "FSKRS.HE"
    assert stub[0]["strategy_input"]["run_id"] == "original"
    assert len(stub[0]["strategy_input"]["candidates"]) == 10
    assert len(pipeline["candidates"]) == 11


def test_stale_held_position_cannot_be_excluded(monkeypatch,stub):
    monkeypatch.setattr(routing, "market_evidence",
                        lambda ticker, **kw: (_ for _ in ()).throw(ValueError("stale")))
    rows = [{"ticker": f"OK{i}.OL", "currency": "NOK"} for i in range(10)]
    with pytest.raises(ValueError, match="stale"):
        routing.live_preview("p", "autonomy", strategy_input=rows, cost_policy={},
                             storage=FakeStore(held={"OK0.OL": {"currency": "NOK"}}))
    assert stub == []


def test_many_missing_candidates_do_not_produce_empty_preview(monkeypatch,stub):
    monkeypatch.setattr(routing, "market_evidence",
                        lambda ticker, **kw: (_ for _ in ()).throw(ValueError("stale")))
    rows = [{"ticker": f"BAD{i}.OL", "currency": "NOK"} for i in range(11)]
    with pytest.raises(ValueError, match="No actual candidate execution evidence"):
        routing.live_preview("p", "autonomy", strategy_input=rows, cost_policy={},
                             storage=FakeStore())
    assert stub == []


def test_general_market_closure_does_not_block_evidenced_subset(monkeypatch,stub):
    rows = [{"ticker": f"OLD{i}.OL", "currency": "NOK"} for i in range(99)] + [
        {"ticker": "FRESH", "currency": "USD"}]
    def evidence(ticker, **kw):
        if ticker != "FRESH":
            raise ValueError("Stale quote")
        return {"price": 100, "currency": "USD", "observed_at": kw["at"], "source": "documented"}
    monkeypatch.setattr(routing, "market_evidence", evidence)
    result = routing.live_preview("p", "autonomy", strategy_input=rows,
                                  cost_policy={}, storage=FakeStore())
    assert len(result["preflight_excluded_candidates"]) == 99
    assert [row["ticker"] for row in stub[0]["strategy_input"]] == ["FRESH"]
    assert list(stub[0]["evidence"]) == ["FRESH"]
