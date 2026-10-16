from services.value_historical_comparison import compare_value_shadow_history


def item(ticker, cohort, return_pct, days=7):
    return {"ticker": ticker, "cohort": cohort, "snapshot_date": "2024-04-01",
            "fundamentals_known_at": "2024-03-15", "price_date": "2024-04-01",
            "outcome_date": "2024-04-15", "forward_return_pct": return_pct,
            "horizon_sessions": days, "historical_universe_member": True}


def test_compares_only_matched_date_horizon_cohorts():
    result = compare_value_shadow_history([item("VALUE", "value_shadow", 8),
                                            item("FINALIST", "legacy_finalist", 3)])
    assert result["status"] == "DESCRIPTIVE_COMPARISON_ONLY"
    assert result["comparisons"][0]["difference_percentage_points"] == 5
    assert result["can_authorize_buy"] is False


def test_no_control_arm_means_no_verifiable_comparison():
    result = compare_value_shadow_history([item("VALUE", "value_shadow", 8)])
    assert result["status"] == "BACKTEST_NOT_VERIFIABLE"


def test_missing_point_in_time_metadata_blocks_result():
    row = item("VALUE", "value_shadow", 8)
    row["fundamentals_known_at"] = "2024-05-01"
    result = compare_value_shadow_history([row, item("FINALIST", "legacy_finalist", 3)])
    assert result["status"] == "BACKTEST_NOT_VERIFIABLE"
    assert result["comparisons"] == []


def test_unsupported_horizon_cannot_be_presented_as_valid():
    result = compare_value_shadow_history([item("VALUE", "value_shadow", 8, 90),
                                            item("FINALIST", "legacy_finalist", 3, 90)])
    assert result["status"] == "BACKTEST_NOT_VERIFIABLE"
