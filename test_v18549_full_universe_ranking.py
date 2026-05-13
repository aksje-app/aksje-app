from fund_etf_analyzer import select_fund_candidates, FUND_UNIVERSES, run_fund_etf_lab
from app_version import get_app_version


def test_v18549_version():
    assert get_app_version() == "v18.5.71"


def test_auto_source_analyzes_full_starter_universe_not_first_max():
    selection = select_fund_candidates(source="Auto rente-/obligasjonsfond", fund_type="Alle", max_funds=3)
    assert selection["max_funds"] == 3
    assert selection["display_limit"] == 3
    assert selection["available_in_universe"] == len(FUND_UNIVERSES["Rente-/obligasjonsfond"])
    assert len(selection["symbols"]) == selection["available_in_universe"]
    assert len(selection["symbols"]) > 3


def test_run_fund_lab_keeps_all_symbols_and_uses_max_as_display_limit():
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    def provider(symbol):
        return {"symbol": symbol, "name": f"Fund {symbol}", "prices": [10, 11, 12, 13]}
    result = run_fund_etf_lab(symbols, data_provider=provider, fund_type="ETF", max_funds=2)
    assert result["symbols"] == symbols
    assert result["summary"]["analyzed"] == 4
    assert result["summary"]["selected_max"] == 2
