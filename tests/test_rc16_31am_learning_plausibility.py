from __future__ import annotations

import controlled_parameter_learning as learning
from decision_plausibility import audit_decision_plausibility
from services.strategy_account_service import StrategyAccountService


def _sell(index: int, pnl: float, reason: str = "Læringsobservasjon: stop loss") -> dict:
    return {
        "trade_id": f"LT-{index}", "action": "SELL", "ticker": f"T{index}",
        "timestamp": f"2026-08-{index % 28 + 1:02d}T08:00:00+00:00",
        "pnl": pnl, "pnl_pct": pnl / 150.0, "reason": reason,
        "mode": "LEARNING_ONLY", "learning_probe": True,
    }


def test_controlled_learning_counts_durable_learning_exits(monkeypatch):
    ordinary = [_sell(index, -100.0) for index in range(7)]
    theoretical = [_sell(index + 100, 50.0) for index in range(29)]
    monkeypatch.setattr(learning, "_closed_trades", lambda: ordinary)
    monkeypatch.setattr(learning, "load_learning_trades", lambda: theoretical)
    summary = learning.learning_evidence_summary()
    assert summary["ordinary_closed_trades"] == 7
    assert summary["learning_closed_trades"] == 29
    assert summary["usable_hypothesis_evidence"] == 36
    assert summary["production_parameters_changed"] is False


def test_existing_learning_evidence_can_create_a_shadow_hypothesis(monkeypatch):
    state = learning.default_state()
    state["hypothesis_min_closed_trades"] = 15
    monkeypatch.setattr(learning, "load_state", lambda: state)
    monkeypatch.setattr(learning, "_closed_trades", lambda: [_sell(index, -100.0) for index in range(7)])
    monkeypatch.setattr(learning, "load_learning_trades", lambda: [_sell(index + 100, -50.0) for index in range(29)])
    monkeypatch.setattr(learning, "load_learning_observations", lambda: [])
    monkeypatch.setattr(learning, "_read", lambda _path, default: default)
    monkeypatch.setattr(learning, "_write", lambda *_args: None)
    monkeypatch.setattr(learning, "_audit", lambda *_args: None)
    monkeypatch.setattr(learning, "_notify", lambda *_args: None)
    created = learning.generate_hypotheses()
    assert created
    assert created[0]["evidence"]["learning_closed_trades"] == 29
    assert created[0]["production_applied"] is False


def test_promotions_and_natural_learning_exits_are_separate(monkeypatch):
    rows = [
        _sell(1, 100.0, "Promotert til ordinær autonom portefølje"),
        _sell(2, -100.0),
    ]
    monkeypatch.setattr(learning, "load_learning_trades", lambda: rows)
    summary = learning.learning_evidence_summary()
    assert summary["promoted_learning_exits"] == 1
    assert summary["natural_learning_exits"] == 1


def test_learning_account_return_uses_entry_notional(monkeypatch):
    service = StrategyAccountService.__new__(StrategyAccountService)
    account = {
        "account_id": "autonomy_learning", "role": "LEARNING", "cash": 15000.0,
        "initial_cash": 100000.0, "realized_pnl": -7491.27,
        "positions": {"AAA": {"quantity": 100.0, "average_price": 100.0, "last_price": 102.0}},
        "metadata": {"accounting_mode": "INDEPENDENT_NOTIONAL_OBSERVATIONS", "entry_notional": 10000.0},
    }
    monkeypatch.setattr(service, "get", lambda _account_id: account)
    metrics = service.metrics("autonomy_learning")
    assert metrics["return_basis"] == "ENTRY_NOTIONAL"
    assert metrics["return_pct"] == -72.9127
    assert metrics["return_pct"] != 862.4749


def test_production_buy_without_report_recommendation_is_blocked():
    run = {
        "candidates": [{"ticker": "AAA", "autonomy_outcome_code": "AUTOMATISK_AVVIST", "portfolio_action": "SKIP"}],
        "autonomous_chain": {"stages": [{"name": "AUTONOMOUS_PORTFOLIO", "detail": {"buy_tickers": ["AAA"]}}]},
    }
    audit = audit_decision_plausibility(run)
    assert audit["ok"] is False
    assert "AAA" in audit["errors"][0]


def test_report_recommendation_does_not_require_a_transaction():
    run = {
        "candidates": [{
            "ticker": "AAA", "investment_score": 75.0,
            "autonomy_outcome_code": "KJØPSKANDIDAT", "portfolio_action": "BUY",
            "final_decision_ready": True,
        }],
        "autonomous_chain": {"stages": [{"name": "AUTONOMOUS_PORTFOLIO", "detail": {"buy_tickers": []}}]},
    }
    audit = audit_decision_plausibility(run)
    assert audit["ok"] is True
    assert audit["report_buy_tickers"] == ["AAA"]


def test_zero_buy_streak_is_carried_across_runs():
    candidate = {"ticker": "AAA", "investment_score": 71.0, "autonomy_outcome_code": "OVERVÅKES_AUTOMATISK", "portfolio_action": "HOLD"}
    previous = {"candidates": [candidate], "decision_plausibility": {"zero_buy_streak": 4}}
    audit = audit_decision_plausibility({"candidates": [candidate]}, [previous])
    assert audit["zero_buy_streak"] == 5
    assert any("5 påfølgende" in warning for warning in audit["warnings"])


def test_learning_without_action_after_enough_evidence_warns():
    run = {
        "candidates": [{"ticker": "AAA", "investment_score": 60.0}],
        "autonomous_chain": {"stages": [{
            "name": "CONTROLLED_LEARNING", "detail": {"ran": True, "evaluation": {
                "ordinary_closed_trades": 7, "learning_closed_trades": 29, "actions": [],
            }},
        }]},
    }
    audit = audit_decision_plausibility(run)
    assert audit["learning_evidence_count"] == 36
    assert any("36 avsluttede" in warning for warning in audit["warnings"])


def test_plausibility_is_exported_to_technical_report_and_pushover():
    contracts = open("report_contracts.py", encoding="utf-8").read()
    market = open("market_intelligence.py", encoding="utf-8").read()
    assert '"decision_plausibility"' in contracts
    assert "Plausibilitet:" in market
    assert "null-kjøpsrekke" in market
