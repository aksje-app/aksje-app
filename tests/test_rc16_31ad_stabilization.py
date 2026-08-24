from unittest.mock import patch

from advanced_investment_intelligence import calculate_portfolio_fit, derive_scores
from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from autonomi_core.runtime.parallel_validation import build_parallel_validation
from learning_acceptance import evaluate_learning_run


def _candidate(ticker: str, action: str, score: float = 75.0) -> dict:
    return {
        "ticker": ticker,
        "investment_score": score,
        "confidence_score": 80.0,
        "valid_for_decision": action != "SKIP",
        "strategy_scores": {"Quality": {"score": 90.0}},
        "strategy_matches": ["Quality"] if action != "SKIP" else [],
        "portfolio_action": action,
        "data_contract": {"source": "LIVE"},
    }


def test_release_identity_is_stabilization_only():
    assert APP_VERSION == "v19.22.0-rc16.31ae"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.31ad"


def test_shadow_preserves_canonical_action_vocabulary():
    candidates = [
        _candidate("HOLD", "HOLD"),
        _candidate("REVIEW", "REVIEW"),
        _candidate("SKIP", "SKIP"),
    ]
    run = {
        "run_id": "RUN-AD",
        "candidates": candidates,
        "portfolio_decisions": {
            "decisions": [
                {"ticker": row["ticker"], "action": row["portfolio_action"]}
                for row in candidates
            ]
        },
    }
    result = build_parallel_validation(run)
    decisions = result["comparison"]["decisions"]
    assert decisions["agreement_pct"] == 100.0
    assert decisions["action_basis"] == "CANONICAL_ACTION_VOCABULARY"
    assert decisions["score_comparison_advisory_only"] is True
    assert result["validation_gate"]["status"] == "GREEN"
    assert result["validation_gate"]["promotion_blocked"] is True
    assert result["validation_gate"]["promotion_eligible"] is False


def test_exact_48_hold_2_review_10_skip_regression_is_not_false_red():
    actions = ["HOLD"] * 48 + ["REVIEW"] * 2 + ["SKIP"] * 10
    candidates = [
        _candidate(f"TICKER-{index:02d}", action, 80.0 - index / 10)
        for index, action in enumerate(actions)
    ]
    run = {
        "run_id": "RUN-AD-60",
        "candidates": candidates,
        "portfolio_decisions": {
            "decisions": [
                {"ticker": row["ticker"], "action": row["portfolio_action"]}
                for row in candidates
            ]
        },
    }
    result = build_parallel_validation(run)
    decisions = result["comparison"]["decisions"]
    assert decisions["compared"] == 60
    assert decisions["agreements"] == 60
    assert decisions["agreement_pct"] == 100.0
    assert result["validation_gate"]["status"] == "GREEN"
    assert result["validation_gate"]["promotion_blocked"] is True


def test_real_action_disagreement_remains_red():
    candidate = _candidate("DIFF", "BUY")
    candidate["decision_gates"] = [
        {"gate": "EVIDENCE", "passed": False, "reason": "Kilde mangler"}
    ]
    run = {
        "run_id": "RUN-DIFF",
        "candidates": [candidate],
        "portfolio_decisions": {"decisions": [{"ticker": "DIFF", "action": "REVIEW"}]},
    }
    result = build_parallel_validation(run)
    assert result["comparison"]["decisions"]["agreement_pct"] == 0.0
    assert result["validation_gate"]["status"] == "RED"
    assert result["comparison"]["decisions"]["diff"][0]["reason_category"] == "EVIDENCE"


def test_learning_acceptance_counts_canonical_rejection_as_accounted():
    run = {
        "run_id": "RUN-LEARN-AD",
        "candidates": [{"ticker": "GOOD"}, {"ticker": "INVALID"}],
        "portfolio_decisions": {
            "decisions": [
                {"ticker": "GOOD", "action": "HOLD"},
                {"ticker": "INVALID", "action": "SKIP"},
            ]
        },
        "autonomous_chain": {
            "status": "COMPLETED",
            "learning_decisions": [
                {"ticker": "GOOD", "action": "OBSERVE", "reason": "Følges"}
            ],
            "learning_trades": [],
            "learning_portfolio": {
                "last_run_id": "RUN-LEARN-AD",
                "positions": {"GOOD": {"ticker": "GOOD"}},
                "closed_positions": [],
            },
            "learning_performance": {"status": "ACTIVE"},
        },
    }
    with patch("learning_acceptance.write_json"):
        result = evaluate_learning_run(run)
    assert result["verdict"] == "PASS"
    assert result["checks"]["every_candidate_accounted_for"] is True
    assert result["unaccounted_candidate_tickers"] == []
    assert result["learning_accounted_candidate_count"] == 1
    assert result["canonical_accounted_candidate_count"] == 2


def test_present_but_unscorable_numeric_values_are_neutral_not_errors():
    row = {
        "ticker": "NEGATIVE-PE",
        "market": "USA",
        "sector": "Technology",
        "pe": -4.0,
        "average_volume": 0,
        "data_fetch_status": "OK",
    }
    derived = derive_scores(row)
    fit, trace = calculate_portfolio_fit(row, [row])
    assert derived["fundamental"] == 50.0
    assert derived["liquidity"] == 50.0
    assert 0.0 <= fit <= 100.0
    assert trace["liquidity_score"] == 50.0
