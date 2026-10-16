from services.value_historical_comparison import compare_value_shadow_history


def sample(ticker, cohort, ret):
    return {"ticker": ticker, "cohort": cohort, "snapshot_date": "2024-04-01",
            "fundamentals_known_at": "2024-03-15", "price_date": "2024-04-01",
            "outcome_date": "2024-04-15", "forward_return_pct": ret,
            "horizon_sessions": 7, "historical_universe_member": True}


def test_duplicate_observation_cannot_inflate_cohort_mean():
    value = sample("VALUE.OL", "value_shadow", 8)
    control = sample("CONTROL.OL", "legacy_finalist", 3)
    outcome = compare_value_shadow_history([value, dict(value), control])
    assert outcome["status"] == "BACKTEST_NOT_VERIFIABLE"
    assert outcome["duplicate_rows"] == 1
    assert outcome["comparisons"] == []
    assert outcome["can_authorize_buy"] is False


def test_ticker_cannot_appear_in_both_arms_same_date():
    value = sample("SAME.OL", "value_shadow", 8)
    control = sample("SAME.OL", "legacy_finalist", 3)
    assert compare_value_shadow_history([value, control])["duplicate_rows"] == 1
