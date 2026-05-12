from auto_test_lab import estimate_auto_lab_fund_run, run_auto_test_lab_fund_mode


def _prices(start=100, step=1.1, n=120):
    return [start + i * step for i in range(n)]


def _fund_provider(symbol):
    if symbol == "ACTIVEBAD":
        return {"symbol": symbol, "name": "Active Bad", "quoteType": "MUTUALFUND", "expenseRatio": 0.018, "prices": _prices(100, 0.6, 120)}
    return {"symbol": symbol, "name": f"{symbol} ETF", "quoteType": "ETF", "expenseRatio": 0.001, "prices": _prices(100, 1.2, 120)}


def _benchmark(symbol="SPY"):
    return {"symbol": symbol, "name": "Benchmark", "quoteType": "ETF", "expenseRatio": 0.001, "prices": _prices(100, 1.0, 120)}


def test_estimate_auto_lab_fund_run_marks_fund_mode_and_counts_tests():
    est = estimate_auto_lab_fund_run(["VOO", "SPY", "VOO"], test_mode="Normal", include_benchmark=True, fetch_costs=True)
    assert est["lab_mode"] == "Fond / ETF"
    assert est["asset_type"] == "fund_etf"
    assert est["funds"] == 2
    assert est["tests_per_fund"] > 0
    assert est["total_tests"] == est["funds"] * est["tests_per_fund"]


def test_run_auto_test_lab_fund_mode_reuses_fund_engine_and_progress():
    events = []
    result = run_auto_test_lab_fund_mode(
        ["VOO", "ACTIVEBAD"],
        data_provider=_fund_provider,
        benchmark_provider=_benchmark,
        benchmark_symbol="SPY",
        fund_type="Alle",
        objective="Balansert",
        test_mode="Rask",
        progress_callback=events.append,
        max_funds=2,
    )
    assert result["lab_mode"] == "Fond / ETF"
    assert result["asset_type"] == "fund_etf"
    assert result["completed_tests"] == result["total_tests"]
    assert result["best_funds"]
    assert result["fund_comparator"]["count"] == 2
    assert result["fund_decision_quality_summary"]["count"] == 2
    assert "core_satellite" in result
    assert any(e.get("symbol") == "VOO" and e.get("test_name") for e in events)
