from fund_etf_analyzer import (
    future_value_after_costs,
    build_cost_impact_table,
    build_fund_cost_impact,
    run_fund_etf_lab,
)


def test_future_value_lower_fee_beats_higher_fee():
    low = future_value_after_costs(start_amount=100000, monthly_saving=2000, annual_return_pct=7, annual_fee_pct=0.18, years=20)
    high = future_value_after_costs(start_amount=100000, monthly_saving=2000, annual_return_pct=7, annual_fee_pct=1.50, years=20)
    assert low > high
    assert low - high > 100000


def test_cost_impact_table_uses_cheapest_fee_as_baseline():
    impact = build_cost_impact_table([
        {"symbol": "LOW", "expense_ratio_pct": 0.18},
        {"symbol": "HIGH", "expense_ratio_pct": 1.5},
    ], start_amount=100000, monthly_saving=2000, annual_return_pct=7, years=20)
    rows = impact["rows"]
    assert impact["baseline_fee_pct"] == 0.18
    assert rows[0]["expense_ratio_pct"] == 0.18
    assert rows[-1]["expense_ratio_pct"] == 1.5
    assert rows[0]["vs_baseline"] == 0
    assert rows[-1]["vs_baseline"] < 0
    assert impact["summary"]["difference_best_worst"] > 0


def test_build_fund_cost_impact_includes_reference_levels_when_cost_missing():
    impact = build_fund_cost_impact([
        {"symbol": "NOFEE", "expense_ratio_pct": None},
        {"symbol": "ETF", "expense_ratio_pct": 0.20},
    ], include_standard_levels=True)
    labels = [r["label"] for r in impact["rows"]]
    assert any("ETF" in label for label in labels)
    assert any("Referanse 1.50%" in label for label in labels)


def test_fund_lab_result_contains_cost_impact():
    def provider(symbol):
        return {"prices": [100, 105, 110, 120, 130] * 60, "expenseRatio": 0.002 if symbol == "LOW" else 0.015}

    result = run_fund_etf_lab(["LOW", "HIGH"], data_provider=provider, benchmark_provider=provider, benchmark_symbol="LOW", test_mode="Rask")
    assert "cost_impact" in result
    assert result["cost_impact"]["summary"]["count"] >= 2
