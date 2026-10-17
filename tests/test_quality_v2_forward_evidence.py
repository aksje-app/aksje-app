from services.quality_v2_forward_evidence import compare_quality_v2_forward


def test_actual_forward_sessions_not_calendar_days():
    row = {"ticker":"ABC","comparison_direction":"V2_STRONGER",
           "decision_date":"2026-10-01","adjusted_entry_price":100}
    marks = {"ABC":[{"market_date":"2026-10-01","adjusted_close":999},
        {"market_date":"2026-10-02","adjusted_close":101},
        {"market_date":"2026-10-05","adjusted_close":105}]}
    result = compare_quality_v2_forward([row], marks, sessions=(2, 7))
    assert result["cohorts"][0]["count"] == 1
    assert result["cohorts"][0]["mean_return_pct"] == 5
    assert result["rejected"]["INSUFFICIENT_7_SESSIONS"] == 1
    assert result["production_promotion_allowed"] is False


def test_no_fabricated_results_without_prices():
    row = {"ticker":"ABC","comparison_direction":"V2_STRONGER","decision_date":"2026-10-01"}
    result = compare_quality_v2_forward([row], {})
    assert result["cohorts"] == []
    assert result["rejected"]["MISSING_DECISION_DATE_OR_ADJUSTED_ENTRY_PRICE"] == 1
