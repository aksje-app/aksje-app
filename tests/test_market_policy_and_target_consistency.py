from datetime import datetime, timezone

import market_universe as markets
import super_portfolio as sp


def _candidate(ticker, market, score, *, price=100.0):
    return {
        "ticker": ticker,
        "market": market,
        "investment_score": score,
        "risk_score": 25.0,
        "data_quality_score": 95.0,
        "price": price,
        "sector": "Test",
        "raw": {"last_price": price, "volatility_pct": 20.0},
    }


def _position(ticker, market, weight, score):
    return {
        "ticker": ticker,
        "market": market,
        "sector": "Test",
        "target_weight_pct": weight,
        "entry_price": 100.0,
        "last_price": 100.0,
        "peak_price": 100.0,
        "risk_score": 25.0,
        "quality_score": 95.0,
        "portfolio_score": score,
        "portfolio_score_adjusted": score,
        "rank": 1,
        "max_portfolio_correlation": 0.1,
        "correlation_source": "MULTI_HORIZON_RETURN_PROFILE",
    }


def test_one_market_contract_controls_production_and_shadow():
    assert markets.production_market_scopes() == ["Norge", "Sverige", "USA"]
    assert markets.shadow_market_scopes() == ["Danmark", "Finland"]
    scanner_source = open("scanner_worker.py", encoding="utf-8").read()
    assert "production_market_scopes()" in scanner_source
    assert 'PRODUCTION_NORWAY_ONLY", "false"' in scanner_source
    assert markets.market_activation_level("Danmark") == "SHADOW"
    assert markets.market_activation_level("Brasil") == "OFF"


def test_shadow_markets_cannot_enter_super_portfolio_target(monkeypatch):
    now = datetime(2026, 9, 17, 15, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(target_positions=2, candidate_persistence_runs=1)
    state = sp.default_state(cfg)
    monkeypatch.setattr(sp, "load_state", lambda: state)
    pipeline = {
        "run_id": "POLICY-RUN",
        "created_at": now.isoformat(),
        "candidates": [
            _candidate("DK.TOP", "Danmark", 99),
            _candidate("FI.TOP", "Finland", 98),
            _candidate("NO.ONE", "Norge", 90),
            _candidate("US.ONE", "USA", 89),
        ],
    }

    result = sp.evaluate(pipeline=pipeline, persist=False, now=now, rebalance_policy="ANALYZE_ONLY")

    target = result["state"]["decision_trace"]["by_ticker"]
    assert target["DK.TOP"]["target_selected"] is False
    assert target["DK.TOP"]["eligible"] is False
    assert target["FI.TOP"]["target_selected"] is False
    assert target["FI.TOP"]["eligible"] is False
    assert target["NO.ONE"]["target_selected"] is True
    assert target["US.ONE"]["target_selected"] is True
    assert not any(row["ticker"] in {"DK.TOP", "FI.TOP"} for row in result["ai_would_do_today"])
    activation = result["state"]["history"][-1]["market_activation"]
    assert activation["shadow_candidate_count"] == 2
    assert result["state"]["positions"] == {}


def test_selected_incumbent_can_never_be_advisory_sell(monkeypatch):
    now = datetime(2026, 9, 17, 15, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(target_positions=1, candidate_persistence_runs=2)
    state = sp.default_state(cfg)
    state["source_run_id"] = "POSITION-RUN"
    state["positions"] = {"AKER.OL": _position("AKER.OL", "Norge", 100.0, 80.0)}
    monkeypatch.setattr(sp, "load_state", lambda: state)
    pipeline = {
        "run_id": "DECISION-RUN",
        "created_at": now.isoformat(),
        "candidates": [
            _candidate("HSHP.OL", "Norge", 99),
            _candidate("AKER.OL", "Norge", 80),
        ],
    }

    result = sp.evaluate(pipeline=pipeline, persist=False, now=now, rebalance_policy="ANALYZE_ONLY")
    trace = result["state"]["decision_trace"]["by_ticker"]["AKER.OL"]

    assert trace["target_selected"] is True
    assert trace["action"] != "SELL"
    assert "TARGET_ACTION_CONTRADICTION" not in trace["alerts"]
    assert trace["snapshot_mismatch"] is False
    assert trace["position_precedes_decision"] is True
