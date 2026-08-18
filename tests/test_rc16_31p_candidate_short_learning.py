from __future__ import annotations

import random

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from candidate_data_governance import assess_candidate_data, build_candidate_data_audit, deterministic_global_shortlist
from short_intelligence import build_short_report, normalize_short_snapshot, portfolio_short_exposure
from report_portfolio_intelligence import build_portfolio_report
from ai_learning_foundation import learning_report


def test_version_contract_and_production_threshold_are_not_recalibrated_here():
    assert APP_VERSION == "v19.22.0-rc16.31z"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.31y"
    from autonomous_portfolio import AutonomousParameters
    assert AutonomousParameters().minimum_investment_score == 73.0


def test_optional_missing_data_is_unknown_and_strong_partial_candidate_is_rescued():
    audit = assess_candidate_data({"ticker": "GOLD", "market": "USA", "price": 10, "risk_score": 20, "investment_score": 68})
    assert audit["missing_critical"] == []
    assert "liquidity" in audit["missing_important"]
    assert audit["decision_data_state"] == "RESCUE"
    assert audit["unknown_optional_fields_are_not_zero"] is True


def test_missing_ticker_is_blocked_not_rescued():
    audit = assess_candidate_data({"market": "USA", "investment_score": 90})
    assert audit["decision_data_state"] == "BLOCKED"
    assert audit["rescue_required"] is False


def test_global_shortlist_is_order_invariant_and_has_no_market_maximum():
    rows = []
    for market, base in (("Norge", 100), ("Sverige", 80), ("USA", 60)):
        rows.extend({"ticker": f"{market[:2]}{i:02}", "market": market, "investment_score": base - i} for i in range(25))
    expected = [row["ticker"] for row in deterministic_global_shortlist(rows, limit=60, minimum_per_market=10)]
    shuffled = list(rows); random.Random(7).shuffle(shuffled)
    assert [row["ticker"] for row in deterministic_global_shortlist(shuffled, limit=60, minimum_per_market=10)] == expected
    assert sum(ticker.startswith("No") for ticker in expected) > 10


def test_candidate_data_audit_balances_the_funnel():
    report = build_candidate_data_audit([
        {"ticker": "A", "market": "USA", "price": 1, "liquidity_score": 7, "risk_score": 2},
        {"ticker": "B", "market": "USA", "price": 1, "risk_score": 2, "investment_score": 70},
        {"market": "USA"},
    ])
    assert report["candidate_count"] == report["ready_count"] + report["rescue_count"] + report["blocked_count"]
    assert report["rescue_count"] == 1 and report["blocked_count"] == 1


def test_short_volume_never_becomes_short_interest_or_neutral_observation():
    snapshot = normalize_short_snapshot({"ticker": "VOL", "market": "USA", "short_volume_pct": 55, "momentum_score": 9})
    assert snapshot["coverage"] == "UNKNOWN"
    assert snapshot["short_interest_pct_float"] is None
    assert snapshot["short_volume_is_not_short_interest"] is True
    assert snapshot["unknown_not_neutral"] is True
    assert snapshot["production_score_contribution"] == 0.0


def test_unverified_short_number_is_not_ranked_as_fact():
    report = build_short_report([
        {"ticker": "BAD", "short_data": {"short_interest_pct_float": 40}},
        {"ticker": "OK", "short_data": {"short_interest_pct_float": 12, "source": "Official", "as_of": "2026-08-15", "status": "OFFICIAL"}},
    ])
    assert report["verified_count"] == 1
    assert [row["ticker"] for row in report["most_shorted_verified"]] == ["OK"]
    assert report["production_score_changed"] is False


def test_portfolio_short_exposure_excludes_unknown_capital():
    exposure = portfolio_short_exposure([
        {"ticker": "A", "market_value": 600, "short_data": {"short_interest_pct_float": 15, "days_to_cover": 6, "source": "Official", "as_of": "2026-08-15", "status": "OFFICIAL"}},
        {"ticker": "B", "market_value": 400},
    ])
    assert exposure["verified_short_coverage_pct"] == 60.0
    assert exposure["capital_weighted_short_interest_pct"] == 15.0
    assert exposure["high_short_exposure_pct"] == 60.0


def test_portfolio_report_marks_unknown_short_and_keeps_accounting_integrity():
    portfolio = {"initial_cash": 1000, "cash": 500, "positions": {"A": {"ticker": "A", "quantity": 5, "average_price": 100, "last_price": 100}}}
    report = build_portfolio_report(portfolio, [])
    assert report["positions"][0]["short_intelligence"]["coverage"] == "UNKNOWN"
    assert report["short_exposure"]["verified_short_coverage_pct"] == 0.0
    assert report["reconciliation"]["ok"] is True


def test_learning_report_contains_curve_short_analysis_and_never_changes_production():
    portfolio = {"trades": [
        {"ticker": "A", "type": "BUY", "shares": 1, "price": 100, "time": "2026-01-01T00:00:00+00:00", "short_intelligence": {"verified": True, "short_interest_pct_float": 12}},
        {"ticker": "A", "type": "SELL", "shares": 1, "price": 110, "time": "2026-02-01T00:00:00+00:00"},
    ]}
    report = learning_report(portfolio)
    assert report["learning_curve"][-1]["equity_index"] == 110.0
    assert report["short_outcome_analysis"][0]["name"] == "HØY SHORT"
    assert report["portfolio_learning"]["automatic_production_change"] is False
