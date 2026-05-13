from app_version import get_app_version
from fund_etf_analyzer import (
    analyze_fund_record,
    attach_portfolio_fit_layer,
    build_portfolio_fit_profile,
    run_fund_etf_lab,
)


def _prices(up=True):
    return [100, 102, 104, 106, 108, 110] if up else [100, 99, 101, 98, 102, 101]


def _fund(symbol, sector="Technology", holding_symbol="AAPL"):
    return {
        "name": symbol,
        "expense_ratio": 0.08,
        "prices": _prices(True),
        "holdings": [
            {"symbol": holding_symbol, "name": holding_symbol, "weight_pct": 18, "sector": sector, "geography": "USA", "market_cap": "Mega"},
            {"symbol": f"{holding_symbol}2", "name": "Other", "weight_pct": 8, "sector": sector, "geography": "USA", "market_cap": "Large"},
        ],
    }


def test_version_is_18557():
    assert get_app_version() == "v18.5.71"


def test_portfolio_fit_penalizes_overlap():
    row = analyze_fund_record("TECH", _fund("TECH", "Technology", "AAPL"), fund_type="ETF", benchmark_data={"prices": _prices(True)})
    no_overlap = build_portfolio_fit_profile(row, existing_portfolio={"symbol_weights": {"XOM": 20}, "sector_weights": {"Energy": 20}, "has_existing": True})
    overlap = build_portfolio_fit_profile(row, existing_portfolio={"symbol_weights": {"AAPL": 20}, "sector_weights": {"Technology": 40}, "has_existing": True})
    assert no_overlap["portfolio_fit_score"] > overlap["portfolio_fit_score"]
    assert overlap["overlap_pct"] > 0


def test_attach_portfolio_fit_reranks_by_fit():
    tech = analyze_fund_record("TECH", _fund("TECH", "Technology", "AAPL"), fund_type="ETF", benchmark_data={"prices": _prices(True)})
    energy = analyze_fund_record("ENRG", _fund("ENRG", "Energy", "XOM"), fund_type="ETF", benchmark_data={"prices": _prices(True)})
    fit = attach_portfolio_fit_layer([tech, energy], selection_info={"existing_portfolio": [{"symbol": "AAPL", "weight_pct": 20, "sector": "Technology"}]})
    assert fit["layer"] == "Layer 8"
    assert all("portfolio_fit_score" in r for r in fit["ranked"])
    assert fit["ranked"][0]["symbol"] == "ENRG"


def test_run_fund_lab_returns_layer8_payload():
    data = {"TECH": _fund("TECH", "Technology", "AAPL"), "ENRG": _fund("ENRG", "Energy", "XOM")}
    result = run_fund_etf_lab(
        ["TECH", "ENRG"],
        data_provider=lambda s: data[s],
        benchmark_provider=lambda s: {"prices": _prices(True)},
        fund_type="ETF",
        max_funds=2,
        selection_info={"existing_portfolio": [{"symbol": "AAPL", "weight_pct": 20, "sector": "Technology"}]},
    )
    assert result["version"] == "v18.5.71"
    assert result["portfolio_fit"]["layer"] == "Layer 8"
    assert result["ranked"][0]["portfolio_fit_score"] is not None
    assert result["summary"]["best_portfolio_fit_score"] == result["ranked"][0]["portfolio_fit_score"]
