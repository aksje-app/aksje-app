from portfolio_mixed_analyzer import parse_portfolio_text, build_holdings_from_sources, analyze_mixed_portfolio
from app_version import get_app_version


def test_parse_manual_portfolio_weights_and_types():
    rows = parse_portfolio_text("AAPL 10\nVOO 60 ETF\nARKK 30 Aktivt", default_asset_type="Aksje")
    assert [r["symbol"] for r in rows] == ["AAPL", "VOO", "ARKK"]
    assert rows[0]["weight_pct"] == 10.0
    assert rows[1]["asset_type"] == "ETF"
    assert rows[2]["asset_type"] == "Aktivt fond"


def test_mixed_portfolio_normalizes_and_scores_core_satellite():
    holdings = build_holdings_from_sources(
        manual_stock_text="AAPL 10\nMSFT 10",
        manual_fund_text="VOO 60 ETF\nQQQ 20 ETF",
    )
    assert round(sum(float(h["weight_pct"]) for h in holdings), 2) == 100.0
    result = analyze_mixed_portfolio(holdings, profile="Balansert")
    assert result["version"] == get_app_version()
    assert result["status"] == "ok"
    assert result["portfolio_health"] > 0
    assert result["summary"]["stock_pct"] == 20.0
    assert result["summary"]["fund_pct"] == 80.0
    assert result["summary"]["core_pct"] >= 50.0
    assert result["breakdown"]["asset_type"]["Aksje"] == 20.0


def test_overlap_risk_detects_tech_stock_and_qqq_overlap():
    holdings = build_holdings_from_sources(
        manual_stock_text="AAPL 20\nMSFT 15\nNVDA 10",
        manual_fund_text="QQQ 30 ETF\nVOO 25 ETF",
    )
    result = analyze_mixed_portfolio(holdings, profile="Balansert")
    titles = {r["title"] for r in result["overlap_risks"]}
    assert "Teknologi-overlapp" in titles
    assert result["portfolio_health"] < 90


def test_empty_portfolio_is_safe():
    result = analyze_mixed_portfolio([], profile="Balansert")
    assert result["status"] == "empty"
    assert result["portfolio_health"] == 0
    assert result["suggestions"]
