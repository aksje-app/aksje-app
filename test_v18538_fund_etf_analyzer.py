from fund_etf_analyzer import estimate_fund_etf_run, run_fund_etf_lab, analyze_fund_record, parse_fund_list


def _data(symbol):
    prices = [100, 102, 104, 103, 108, 112, 118, 121, 124, 128, 132, 136, 140, 144, 148, 151, 155, 158, 162, 166, 170, 174, 178, 181, 185, 190]
    if symbol == "EXPENSIVE":
        prices = [100, 94, 98, 91, 95, 93, 97, 96, 99, 98, 100, 99, 101, 100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106]
        return {"symbol": symbol, "name": "Expensive Active", "expenseRatio": 1.8, "prices": prices, "quoteType": "MUTUALFUND"}
    return {"symbol": symbol, "name": f"{symbol} Index ETF", "expenseRatio": 0.0003, "prices": prices, "quoteType": "ETF"}


def test_parse_fund_list_dedupes_symbols():
    assert parse_fund_list("SPY, voo\nSPY; qqq") == ["SPY", "VOO", "QQQ"]


def test_estimate_fund_etf_run_counts_tests():
    est = estimate_fund_etf_run(["SPY", "VOO", "SPY"], test_mode="Normal", include_benchmark=True, fetch_costs=True)
    assert est["funds"] == 2
    assert est["tests_per_fund"] >= 7
    assert est["total_tests"] == est["funds"] * est["tests_per_fund"]
    assert est["load_label"] in {"Lav", "Medium", "Høy"}


def test_analyze_fund_record_scores_low_cost_index_candidate():
    row = analyze_fund_record("SPY", _data("SPY"), fund_type="ETF", objective="Grunnmur", benchmark_data=_data("VOO"))
    assert row["symbol"] == "SPY"
    assert row["fund_type"] == "ETF"
    assert row["decision_quality"] >= 60
    assert row["expense_ratio_pct"] == 0.03
    assert row["grade"] in {"Middels", "Høy"}


def test_run_fund_etf_lab_emits_progress_and_continues():
    events = []
    result = run_fund_etf_lab(
        ["SPY", "EXPENSIVE"],
        data_provider=_data,
        benchmark_provider=_data,
        benchmark_symbol="VOO",
        fund_type="Alle",
        objective="Balansert",
        test_mode="Normal",
        progress_callback=events.append,
    )
    assert result["summary"]["analyzed"] == 2
    assert result["completed_tests"] == result["total_tests"]
    assert events[0]["status"] == "starting"
    assert max(e.get("percent", 0) for e in events) == 100.0
    assert result["ranked"][0]["decision_quality"] >= result["ranked"][-1]["decision_quality"]
