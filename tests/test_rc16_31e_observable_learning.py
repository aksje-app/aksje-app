from __future__ import annotations

import autonomous_portfolio as ap
import controlled_parameter_learning as learning
from app_version import APP_VERSION, PREVIOUS_APP_VERSION


def _candidate(ticker="AAA", price=100.0, score=70.0):
    return {
        "ticker": ticker, "price": price, "investment_score": score,
        "risk_score": 40, "data_quality_score": 95,
        "evidence_valid_for_decision": True,
    }


def test_release_identity_is_explicit():
    assert APP_VERSION == "v19.22.0-rc16.31e"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.31d"


def test_observations_are_isolated_idempotent_and_mature(monkeypatch):
    store = []
    monkeypatch.setattr(ap, "load_learning_observations", lambda limit=5000: [dict(row) for row in store])
    monkeypatch.setattr(ap, "_write", lambda path, value: store.__setitem__(slice(None), value))
    production = {"ticker": "AAA", "action": "BUY", "reason": "production"}
    shadow = {"ticker": "AAA", "action": "OBSERVE", "reason": "learning"}
    first = ap._update_candidate_observations([_candidate()], [production, shadow], "RUN-1", {"market_date": "2026-01-01"})
    assert first["created"] == 1
    assert store[0]["decision_outcome"] == "PRODUCTION_BUY"
    assert store[0]["production_applied"] is False
    repeat = ap._update_candidate_observations([_candidate()], [production, shadow], "RUN-1", {"market_date": "2026-01-01"})
    assert repeat["created"] == 0
    for day in range(2, 61):
        ap._update_candidate_observations(
            [_candidate(price=100 + day)], [production], f"RUN-{day}",
            {"market_date": f"2026-{1 + (day - 1) // 28:02d}-{1 + (day - 1) % 28:02d}"},
        )
    original = next(row for row in store if row["source_run_id"] == "RUN-1")
    assert [row["horizon_days"] for row in original["outcome_measurements"]] == [5, 10, 20, 60]
    assert original["status"] == "MATURED"
    assert original["maximum_gain_pct"] > 0
    assert original["simulated_exit_outcomes"]["TAKE_PROFIT"]["production_applied"] is False
    assert len(store) <= 2000


def test_mature_rejected_observations_create_shadow_only_hypothesis(monkeypatch):
    observations = []
    for index in range(20):
        observations.append({
            "observation_id": f"LO-{index}", "ticker": f"T{index}",
            "decision_outcome": "REJECTED",
            "entry_score": 69, "entry_risk": 40, "entry_data_quality": 95,
            "outcome_measurements": [{"horizon_days": 20, "return_pct": 6 if index < 8 else -1}],
        })
    db = {learning.HYPOTHESES_PATH: []}
    monkeypatch.setattr(learning, "load_learning_observations", lambda: observations)
    monkeypatch.setattr(learning, "_closed_trades", lambda: [])
    monkeypatch.setattr(learning, "load_state", lambda: {**learning.default_state(), "hypothesis_min_mature_observations": 20})
    monkeypatch.setattr(learning, "_read", lambda path, default: db.get(path, default))
    monkeypatch.setattr(learning, "_write", lambda path, value: db.__setitem__(path, value))
    monkeypatch.setattr(learning, "_audit", lambda *args: None)
    monkeypatch.setattr(learning, "_notify", lambda *args: None)
    created = learning.generate_hypotheses()
    assert len(created) == 1
    assert created[0]["parameter"] == "minimum_investment_score"
    assert created[0]["after"] >= 60
    assert created[0]["production_applied"] is False
    assert created[0]["evidence_basis"] == "MATURE_OBSERVATIONS"


def test_report_labels_are_unambiguous():
    from report_contracts import REPORT_SPECS
    assert REPORT_SPECS["DAGSRAPPORT"].label == "Ettermiddagsrapport"
    source = open("market_intelligence.py", encoding="utf-8").read()
    assert "Kjøpsgodkjente kandidater" in source
    assert "Kjøpsanbefalinger 1-3" not in source


def test_learning_details_are_bounded_and_protected():
    import storage_retention
    retention_source = open("storage_retention.py", encoding="utf-8").read()
    autonomy_source = open("autonomous_portfolio.py", encoding="utf-8").read()
    assert "bounded_learning_observations" in retention_source
    assert "rows[:2000]" in autonomy_source
    assert not any("learning_observations" in prefix for prefix in storage_retention.KV_LIMITS)
