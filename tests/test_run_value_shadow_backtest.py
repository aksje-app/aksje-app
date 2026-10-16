import json
from scripts.run_value_shadow_backtest import run


def test_missing_dataset_fails_closed(tmp_path):
    result = run(str(tmp_path / "absent.json"))
    assert result["status"] == "BACKTEST_NOT_VERIFIABLE"
    assert result["can_authorize_buy"] is False


def test_invalid_dataset_schema_fails_closed(tmp_path):
    data = tmp_path / "sample.json"
    data.write_text(json.dumps({"ticker": "BAD"}), encoding="utf-8")
    result = run(str(data))
    assert result["error"] == "INVALID_INPUT_SCHEMA"


def test_offline_matched_historical_samples(tmp_path):
    data = tmp_path / "sample.json"
    records = []
    for ticker, cohort, ret in [("VALUE.OL", "value_shadow", 6),
                                ("CONTROL.OL", "legacy_finalist", 3)]:
        records.append({"ticker": ticker, "cohort": cohort,
                        "snapshot_date": "2024-04-01",
                        "fundamentals_known_at": "2024-03-20",
                        "price_date": "2024-04-01", "outcome_date": "2024-04-15",
                        "forward_return_pct": ret, "horizon_sessions": 7,
                        "historical_universe_member": True})
    data.write_text(json.dumps(records), encoding="utf-8")
    result = run(str(data))
    assert result["status"] == "DESCRIPTIVE_COMPARISON_ONLY"
    assert result["comparisons"][0]["difference_percentage_points"] == 3
    assert result["can_authorize_buy"] is False
