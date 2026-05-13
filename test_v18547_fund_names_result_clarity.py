from fund_etf_analyzer import (
    get_fund_display_name,
    select_fund_candidates,
    FUND_UNIVERSES,
    analyze_fund_record,
)
from app_version import get_app_version


def test_version_is_18547():
    assert get_app_version() == "v18.5.74"


def test_known_bond_funds_get_names_without_yahoo_metadata():
    assert get_fund_display_name("SHY") == "iShares 1-3 Year Treasury Bond ETF"
    assert get_fund_display_name("Kraft High Yield D") == "Kraft High Yield D"


def test_yahoo_metadata_wins_over_fallback():
    assert get_fund_display_name("SHY", {"longName": "Yahoo Long Name"}) == "Yahoo Long Name"


def test_unknown_name_is_explicit_not_ticker():
    assert get_fund_display_name("UNKNOWN_FUND") == "Navn ikke funnet"


def test_starter_universe_metadata_counts_available_and_selected():
    sel = select_fund_candidates(source="Auto rente-/obligasjonsfond", max_funds=8)
    assert sel["available_in_universe"] > 8
    assert sel["display_limit"] == 8
    assert len(sel["symbols"]) == sel["available_in_universe"]
    assert "starter-univers" in sel["universe_note"]


def test_fixed_income_high_yield_money_market_universes_expanded():
    assert len(FUND_UNIVERSES["Rente-/obligasjonsfond"]) > 8
    assert len(FUND_UNIVERSES["High yield-fond"]) > 8
    assert len(FUND_UNIVERSES["Pengemarkedsfond"]) > 5


def test_analyze_record_uses_fallback_name():
    row = analyze_fund_record("LQD", {"prices": [100, 101, 102]}, fund_type="Rente-/obligasjonsfond")
    assert row["name"] == "iShares iBoxx $ Investment Grade Corporate Bond ETF"
