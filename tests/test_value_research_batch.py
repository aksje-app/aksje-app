from services.value_research_batch import run_combined_value_research


def sample(ticker, cohort, return_pct, *, horizon=7):
    return {
        "ticker": ticker, "cohort": cohort, "horizon_sessions": horizon,
        "snapshot_date": "2024-02-01", "fundamentals_known_at": "2024-01-25",
        "price_date": "2024-02-01", "outcome_date": "2024-03-20",
        "forward_return_pct": return_pct, "historical_universe_member": True,
        "fundamentals_source": "archive", "filing_reference": "2023-Q3",
        "historical_universe_source": "archived constituents",
        "price_source": "adjusted historical price series",
    }


def test_read_only_research_returns_matched_risk_metrics():
    rows = [sample("A", "value_shadow", -5), sample("B", "value_shadow", 12),
            sample("C", "legacy_finalist", 4)]
    result = run_combined_value_research(rows, as_of="2024-05-01")
    assert result["status"] == "DESCRIPTIVE_RESEARCH_ONLY"
    assert len(result["comparisons"]) == 1
    value = next(r for r in result["risk_by_cohort"] if r["cohort"] == "value_shadow")
    assert value["win_rate_pct"] == 50
    assert value["worst_return_pct"] == -5
    assert result["can_authorize_buy"] is False


def test_missing_disclosure_blocks_returns():
    rows = [sample("A", "value_shadow", 5), sample("B", "legacy_finalist", 2)]
    rows[0]["filing_reference"] = ""
    result = run_combined_value_research(rows, as_of="2024-05-01")
    assert result["status"] == "BACKTEST_NOT_VERIFIABLE"
    assert result["risk_by_cohort"] == []


def test_future_outcome_blocks_returns():
    rows = [sample("A", "value_shadow", 5), sample("B", "legacy_finalist", 2)]
    assert run_combined_value_research(rows, as_of="2024-02-10")["comparisons"] == []


def test_unmatched_and_duplicate_cohorts_block_results():
    assert run_combined_value_research([sample("A", "value_shadow", 5)],
                                      as_of="2024-05-01")["status"] == "BACKTEST_NOT_VERIFIABLE"
    rows = [sample("A", "value_shadow", 5), sample("A", "legacy_finalist", 2)]
    assert run_combined_value_research(rows, as_of="2024-05-01")["status"] == "BACKTEST_NOT_VERIFIABLE"


def test_nonfinite_returns_block_results():
    rows = [sample("A", "value_shadow", float("nan")), sample("B", "legacy_finalist", 2)]
    assert run_combined_value_research(rows, as_of="2024-05-01")["status"] == "BACKTEST_NOT_VERIFIABLE"


def test_both_seven_and_thirty_sessions():
    rows = [sample("A", "value_shadow", 5), sample("B", "legacy_finalist", 2),
            sample("A", "value_shadow", 8, horizon=30),
            sample("B", "legacy_finalist", -3, horizon=30)]
    result = run_combined_value_research(rows, as_of="2024-05-01")
    assert {c["horizon_sessions"] for c in result["comparisons"]} == {7, 30}
