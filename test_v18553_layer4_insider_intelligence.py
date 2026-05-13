from fund_etf_analyzer import (
    analyze_fund_record,
    build_holdings_aware_profile,
    build_holdings_insider_profile,
    run_fund_etf_lab,
)


def sample_prices(n=260, start=100.0, step=0.05):
    return [start + i * step for i in range(n)]


def test_holdings_profile_detects_concentration_and_sector_risk():
    data = {
        "holdings": [
            {"symbol": "NVDA", "name": "Nvidia", "weight_pct": 18, "sector": "Technology", "geography": "USA", "market_cap_category": "Mega"},
            {"symbol": "MSFT", "name": "Microsoft", "weight_pct": 12, "sector": "Technology", "geography": "USA", "market_cap_category": "Mega"},
            {"symbol": "AAPL", "name": "Apple", "weight_pct": 11, "sector": "Technology", "geography": "USA", "market_cap_category": "Mega"},
            {"symbol": "JPM", "name": "JPMorgan", "weight_pct": 4, "sector": "Financials", "geography": "USA", "market_cap_category": "Large"},
        ]
    }
    profile = build_holdings_aware_profile(data, fund_symbol="TEST")
    assert profile["holdings_available"] is True
    assert profile["top3_weight_pct"] == 41
    assert any("sektorkonsentrasjon" in x for x in profile["vulnerabilities"])
    assert profile["concentration_risk"] in {"Middels", "Høy"}


def test_insider_profile_classifies_negative_cluster_selling():
    holdings = build_holdings_aware_profile({
        "holdings": [
            {"symbol": "AAPL", "weight_pct": 20, "sector": "Technology", "geography": "USA"},
            {"symbol": "MSFT", "weight_pct": 10, "sector": "Technology", "geography": "USA"},
        ]
    })
    insider = build_holdings_insider_profile(holdings, {
        "insider_events": {
            "AAPL": [
                {"type": "sell", "role": "CEO", "value": 1_000_000},
                {"type": "sell", "role": "CFO", "value": 800_000},
            ]
        }
    })
    assert insider["direction"] == "Negativ"
    assert "AAPL" in insider["negative_holdings"]
    assert insider["insider_score"] < 50


def test_analyze_fund_record_adds_layer3_and_layer4_fields():
    data = {
        "prices": sample_prices(),
        "expense_ratio": 0.001,
        "longName": "Example ETF",
        "holdings": [{"symbol": "MSFT", "weight_pct": 12, "sector": "Technology", "geography": "USA", "market_cap_category": "Mega"}],
        "insider_events": {"MSFT": [{"type": "buy", "role": "CEO", "value": 500_000}]},
    }
    row = analyze_fund_record("EXM", data, fund_type="ETF", benchmark_data={"prices": sample_prices(step=0.04)})
    assert row["holdings_profile"]["layer"] == "Layer 3"
    assert row["insider_holdings_profile"]["layer"] == "Layer 4"
    assert row["insider_holdings_profile"]["direction"] == "Positiv"
    assert "fund_intelligence_score" in row


def test_run_fund_etf_lab_ranks_by_intelligence_score_when_insider_adjusts():
    def provider(symbol):
        base = {"prices": sample_prices(), "expense_ratio": 0.001, "longName": symbol}
        if symbol == "GOOD":
            base.update({
                "holdings": [{"symbol": "AAA", "weight_pct": 10, "sector": "Industrial", "geography": "USA"}],
                "insider_events": {"AAA": [{"type": "buy", "role": "CEO", "value": 1_000_000}]},
            })
        else:
            base.update({
                "holdings": [{"symbol": "BBB", "weight_pct": 30, "sector": "Technology", "geography": "USA"}],
                "insider_events": {"BBB": [{"type": "sell", "role": "CEO", "value": 1_000_000}]},
            })
        return base

    result = run_fund_etf_lab(["BAD", "GOOD"], data_provider=provider, benchmark_provider=lambda s: {"prices": sample_prices(step=0.04)}, fund_type="ETF")
    assert result["ranked"][0]["symbol"] == "GOOD"
