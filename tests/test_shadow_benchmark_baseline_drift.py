from datetime import datetime, timezone
from unittest.mock import patch
from learning_observation_engine import evaluate_observations


def test_benchmark_baseline_drift_preserves_historical_denominator():
    row = {"observation_id":"x","ticker":"TEST","benchmark_ticker":"^GSPC",
           "entry_market_date":"2026-09-01","entry_price":100.0,
           "benchmark_entry_price":200.0,"status":"ACTIVE","horizon_measurements":{},
           "daily_marks":[]}
    def loader(symbols, start):
        return {"TEST":[{"date":"2026-09-01","close":100.0},
                        {"date":"2026-09-02","close":101.0}],
                "^GSPC":[{"date":"2026-08-31","close":210.0},
                         {"date":"2026-09-02","close":212.0}]}
    with patch("learning_observation_engine.load_observations",return_value=[row]),patch(
        "learning_observation_engine.save_observations") as saved,patch(
        "learning_observation_engine.write_json"),patch(
        "learning_observation_engine.load_engine_state",return_value={}),patch(
        "learning_observation_engine._audit"):
        result=evaluate_observations(series_loader=loader,now=datetime(2026,9,3,tzinfo=timezone.utc))
    assert result["missing"] == 1
    assert saved.call_args.args[0][0]["benchmark_entry_price"] == 200.0
    assert saved.call_args.args[0][0]["source_health"]["status"] == "BENCHMARK_BASELINE_DRIFT"
