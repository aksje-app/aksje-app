from fund_etf_analyzer import analyze_fund_record, run_fund_etf_lab, build_fund_decision_quality_summary


def _prices(start=100, step=1.5, n=120):
    return [start + i * step for i in range(n)]


def _bench(symbol="SPY"):
    return {"symbol": symbol, "quoteType": "ETF", "expenseRatio": 0.0009, "prices": _prices(100, 1.1, 120)}


def _provider(symbol):
    if symbol == "CHEAPCORE":
        return {"symbol": symbol, "name": "Cheap Core ETF", "quoteType": "ETF", "expenseRatio": 0.0005, "prices": _prices(100, 1.35, 120)}
    if symbol == "EXPENSIVEACTIVE":
        return {"symbol": symbol, "name": "Expensive Active Fund", "quoteType": "MUTUALFUND", "expenseRatio": 0.018, "prices": _prices(100, 0.8, 120)}
    return {"symbol": symbol, "name": f"{symbol} ETF", "quoteType": "ETF", "expenseRatio": 0.002, "prices": _prices(100, 1.2, 120)}


def test_fund_decision_quality_profile_has_breakdown_and_role_scores():
    row = analyze_fund_record("CHEAPCORE", _provider("CHEAPCORE"), fund_type="ETF", objective="Grunnmur", benchmark_data=_bench())
    profile = row["fund_decision_quality"]
    assert row["decision_quality"] == profile["decision_quality"]
    assert "cost_impact" in row["quality_breakdown"]
    assert "grunnmur_score" in row["role_scores"]
    assert row["recommended_role"] in {"Grunnmur", "Satellitt", "Krever mer bevis", "Unngå"}
    assert row["why_not_100"]


def test_active_fund_quality_is_capped_when_evidence_not_proven():
    row = analyze_fund_record("EXPENSIVEACTIVE", _provider("EXPENSIVEACTIVE"), fund_type="Aktivt fond", objective="Balansert", benchmark_data=_bench())
    assert row["fund_type"] == "Aktivt fond"
    assert row["decision"] == "Krever mer bevis"
    assert row["recommended_role"] == "Krever mer bevis"
    assert row["decision_quality"] <= 56
    assert any("aktiv" in x.lower() for x in row["why_not_100"])


def test_fund_lab_returns_decision_quality_summary():
    result = run_fund_etf_lab(
        ["CHEAPCORE", "EXPENSIVEACTIVE"],
        data_provider=_provider,
        benchmark_provider=_bench,
        benchmark_symbol="SPY",
        fund_type="Alle",
        objective="Balansert",
        test_mode="Rask",
    )
    summary = result["decision_quality_summary"]
    assert summary["count"] == 2
    assert summary["best_symbol"]
    assert summary["average_quality"] is not None
    assert summary["rows"][0]["component_scores"]


def test_build_fund_decision_quality_summary_handles_empty_rows():
    summary = build_fund_decision_quality_summary([])
    assert summary["count"] == 0
    assert summary["warnings"]
