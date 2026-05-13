from fund_etf_analyzer import analyze_fund_record, build_composite_fund_intelligence_profile


def test_layer5_composite_profile_uses_all_available_layers():
    row = {
        "base_score": 72,
        "decision_quality": 68,
        "data_quality": 90,
    }
    holdings = {"holdings_available": True, "concentration_score": 80}
    insider = {"covered_top_holdings_weight_pct": 25, "insider_score": 70, "direction": "Positiv"}
    profile = build_composite_fund_intelligence_profile(row, holdings, insider)
    assert profile["layer"] == "Layer 5"
    assert profile["fund_intelligence_score"] > 70
    assert profile["coverage"]["holdings"] is True
    assert profile["coverage"]["insider"] is True
    assert profile["weights"]["base"] == 0.35


def test_layer5_reweights_when_holdings_and_insider_missing():
    profile = build_composite_fund_intelligence_profile({"base_score": 80, "decision_quality": 60, "data_quality": 90}, {}, {})
    assert profile["coverage"]["holdings"] is False
    assert profile["coverage"]["insider"] is False
    assert set(profile["weights"].keys()) == {"base", "decision"}
    assert 60 <= profile["fund_intelligence_score"] <= 80


def test_analyze_fund_record_exposes_composite_score():
    data = {
        "symbol": "TST",
        "name": "Test Fund",
        "expense_ratio": 0.1,
        "period_return_pct": 8,
        "benchmark_return_pct": 6,
        "volatility_pct": 12,
        "max_drawdown_pct": -8,
        "holdings": [
            {"symbol": "AAA", "name": "Alpha", "weight_pct": 4, "sector": "Technology", "country": "US"},
            {"symbol": "BBB", "name": "Beta", "weight_pct": 3, "sector": "Health Care", "country": "US"},
        ],
        "insider_events": {
            "AAA": [{"type": "buy", "role": "CEO", "value": 1000000}],
        },
    }
    row = analyze_fund_record("TST", data=data, objective="Balansert", fund_type="ETF")
    assert "composite_intelligence_profile" in row
    assert row["fund_intelligence_score"] == row["composite_intelligence_profile"]["fund_intelligence_score"]
    assert row["composite_summary"]
