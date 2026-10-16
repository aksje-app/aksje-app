from services.learning_evidence_report import summarize_learning_evidence


def test_separates_historical_short_horizons_from_matured_gate():
    baseline = {"status":"VERIFISERT","signal_count":1382,"analysis":{
        "matured_count":0,"horizons":[
            {"horizon_days":1,"return":{"count":1382,"average":-0.9556,"maturity":"MER_ROBUST"},
             "excess_return":{"count":1382,"average":-0.588}},
            {"horizon_days":20,"return":{"count":0,"average":None,"maturity":"FOR_TIDLIG"},
             "excess_return":{"count":0,"average":None}}]}}
    acceptance = {"strategy_readiness":"NOT_VALIDATED",
                  "strategy_quality_gate":{"mature_closed_positions":0,
                                           "benchmark_measured_positions":0}}
    result = summarize_learning_evidence(baseline, acceptance, [{"status":"ACTIVE"}])
    assert result["historical_horizons"][0]["measured_count"] == 1382
    assert result["historical_horizons"][1]["average_return_pct"] is None
    assert result["historical_matured_count"] == 0
    assert result["strategy_readiness"] == "NOT_VALIDATED"
    assert result["observation_status_counts"] == {"ACTIVE":1}
    assert result["can_authorize_buy"] is False


def test_active_shadow_can_have_measured_subhorizons():
    from services.learning_evidence_report import summarize_measured_observation_horizons
    rows = [{"status": "ACTIVE", "horizon_measurements": {
        "1": {"return_pct": -2, "excess_return_pct": -1},
        "5": {"return_pct": 3, "excess_return_pct": 2}}},
        {"status": "ACTIVE", "horizon_measurements": {
        "1": {"return_pct": 4, "excess_return_pct": 3}}}]
    result = summarize_measured_observation_horizons(rows)
    assert result[0]["measured_count"] == 2
    assert result[0]["mean_return_pct"] == 1
    assert result[1]["measured_count"] == 1
    assert result[1]["whole_observation_maturity_independent"] is True
