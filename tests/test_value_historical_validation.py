from services.value_historical_validation import validate_point_in_time_samples


def _sample():
    return {"ticker": "TEST.OL", "snapshot_date": "2024-04-01",
            "fundamentals_known_at": "2024-03-15", "price_date": "2024-04-01",
            "outcome_date": "2024-04-11", "forward_return_pct": 2.0,
            "historical_universe_member": True}


def test_historical_validation_accepts_only_point_in_time_inputs():
    result = validate_point_in_time_samples([_sample()])
    assert result["status"] == "READY_FOR_FURTHER_AUDIT"
    assert result["can_authorize_buy"] is False


def test_future_fundamentals_are_rejected():
    sample = {**_sample(), "fundamentals_known_at": "2024-04-15"}
    result = validate_point_in_time_samples([sample])
    assert result["status"] == "BACKTEST_NOT_VERIFIABLE"
    assert result["rejection_counts"]["LOOKAHEAD_FUNDAMENTALS"] == 1


def test_missing_history_or_outcomes_cannot_claim_backtest_success():
    assert validate_point_in_time_samples([])["status"] == "BACKTEST_NOT_VERIFIABLE"
    sample = {**_sample(), "forward_return_pct": None, "historical_universe_member": False}
    result = validate_point_in_time_samples([sample])
    assert result["rejection_counts"]["MISSING_OUTCOME"] == 1
    assert result["rejection_counts"]["UNVERIFIED_HISTORICAL_UNIVERSE"] == 1
