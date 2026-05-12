from fund_etf_analyzer import (
    analyze_fund_record,
    build_core_satellite_portfolio,
    classify_core_satellite_role,
    run_fund_etf_lab,
)


def _prices(start=100, step=1.5, n=90):
    return [start + i * step for i in range(n)]


def _bench(symbol="SPY"):
    return {"symbol": symbol, "quoteType": "ETF", "expenseRatio": 0.0009, "prices": _prices(100, 1.2, 90)}


def _provider(symbol):
    if symbol == "QQQ":
        return {"symbol": symbol, "name": "Nasdaq 100 ETF", "quoteType": "ETF", "expenseRatio": 0.002, "prices": _prices(100, 2.0, 90)}
    if symbol == "ARKK":
        return {"symbol": symbol, "name": "Active Growth", "quoteType": "ETF", "expenseRatio": 0.0075, "prices": _prices(100, 0.7, 90)}
    return {"symbol": symbol, "name": f"{symbol} Broad ETF", "quoteType": "ETF", "expenseRatio": 0.0003, "prices": _prices(100, 1.4, 90)}


def test_classifies_broad_low_cost_etf_as_core():
    row = analyze_fund_record("VOO", _provider("VOO"), fund_type="ETF", objective="Grunnmur", benchmark_data=_bench())
    role = classify_core_satellite_role(row)
    assert role["role"] == "Grunnmur"
    assert "grunnmur" in role["reason"].lower()


def test_core_satellite_portfolio_allocates_core_and_satellite():
    rows = [
        analyze_fund_record("VOO", _provider("VOO"), fund_type="ETF", objective="Balansert", benchmark_data=_bench()),
        analyze_fund_record("QQQ", _provider("QQQ"), fund_type="ETF", objective="Balansert", benchmark_data=_bench()),
        analyze_fund_record("ARKK", _provider("ARKK"), fund_type="Aktivt fond", objective="Balansert", benchmark_data=_bench()),
    ]
    proposal = build_core_satellite_portfolio(rows, profile="Balansert", max_positions=5)
    assert proposal["status"] == "OK"
    assert proposal["allocation"]
    assert round(sum(float(r["weight_pct"]) for r in proposal["allocation"]), 1) == 100.0
    assert any(r["role"] == "Grunnmur" for r in proposal["allocation"])
    assert any(r["symbol"] == "ARKK" for r in proposal["needs_proof"])


def test_run_fund_lab_returns_core_satellite_section():
    result = run_fund_etf_lab(
        ["VOO", "QQQ", "ARKK"],
        data_provider=_provider,
        benchmark_provider=_bench,
        benchmark_symbol="SPY",
        fund_type="Alle",
        objective="Balansert",
        test_mode="Rask",
    )
    assert "core_satellite" in result
    assert result["core_satellite"]["allocation"]
    assert result["core_satellite"]["role_counts"]["grunnmur"] >= 1
