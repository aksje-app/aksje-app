from app_version import get_app_version
from fund_etf_analyzer import (
    analyze_fund_record,
    classify_fund,
    fund_selection_sources,
    fund_type_options,
    parse_fund_list,
    run_fund_etf_lab,
    select_fund_candidates,
)
from portfolio_mixed_analyzer import analyze_mixed_portfolio


def _prices(start=100.0, step=0.05, n=260):
    values = []
    v = start
    for i in range(n):
        v = v * (1 + step / 100.0)
        if i % 40 == 0:
            v *= 0.985
        values.append(round(v, 4))
    return values


def test_version_is_18546():
    assert get_app_version() == "v18.5.70"


def test_fund_type_options_include_fixed_income_and_high_yield():
    options = fund_type_options()
    assert "Rente-/obligasjonsfond" in options
    assert "High yield-fond" in options
    assert "Pengemarkedsfond" in options
    assert "Kombinasjonsfond" in options


def test_selection_sources_include_fixed_income_auto_sources():
    sources = fund_selection_sources()
    assert "Auto rente-/obligasjonsfond" in sources
    assert "Auto high yield-fond" in sources
    assert "Auto pengemarkedsfond" in sources
    selected = select_fund_candidates(source="Auto high yield-fond", fund_type="High yield-fond", max_funds=3)
    assert selected["symbols"][:3] == ["HYG", "JNK", "ANGL"]
    assert selected["display_limit"] == 3
    assert len(selected["symbols"]) > 3
    assert all(row["type"] == "High yield-fond" for row in selected["selected"])


def test_kraft_high_yield_alias_is_parsed_as_single_candidate():
    assert parse_fund_list("Kraft High Yield D, HYG")[:2] == ["KRAFT_HIGH_YIELD_D", "HYG"]


def test_high_yield_is_not_treated_as_safe_bond_core():
    row = analyze_fund_record(
        "HYG",
        {
            "name": "High Yield Credit ETF",
            "category": "High Yield Bond",
            "expenseRatio": 0.0049,
            "yield": 0.06,
            "duration": 3.2,
            "prices": _prices(step=0.08),
        },
        fund_type="Alle",
        objective="Lav risiko",
        benchmark_data={"prices": _prices(step=0.05)},
    )
    assert row["fund_type"] == "High yield-fond"
    assert row["recommended_role"] in {"Kredittsatellitt", "Krever mer bevis"}
    assert row["fixed_income_risk_level"] == "Høy kredittrisiko"
    assert any("high yield" in msg.lower() or "kreditt" in msg.lower() for msg in row["reasons_caution"])


def test_defensive_bond_fund_gets_fixed_income_profile():
    row = analyze_fund_record(
        "BND",
        {
            "name": "Broad Bond ETF",
            "category": "Intermediate Core Bond",
            "expenseRatio": 0.0003,
            "yield": 0.04,
            "duration": 6.0,
            "prices": _prices(step=0.025),
        },
        fund_type="Alle",
        objective="Lav risiko",
        benchmark_data={"prices": _prices(step=0.02)},
    )
    assert row["fund_type"] == "Rente-/obligasjonsfond"
    assert row["fixed_income_profile"]["is_fixed_income"] is True
    assert row["recommended_role"] in {"Defensiv komponent", "Krever mer bevis"}


def test_run_fund_lab_returns_fixed_income_buckets():
    data = {
        "BND": {"name": "Bond", "category": "Bond", "expenseRatio": 0.0003, "prices": _prices(step=0.02)},
        "HYG": {"name": "High Yield", "category": "High Yield Bond", "expenseRatio": 0.0049, "yield": 0.06, "prices": _prices(step=0.08)},
    }
    result = run_fund_etf_lab(
        ["BND", "HYG"],
        data_provider=lambda symbol: data[symbol],
        benchmark_provider=lambda symbol: {"prices": _prices(step=0.02)},
        fund_type="Alle",
        objective="Balansert",
        max_funds=2,
    )
    assert result["fixed_income_candidates"]
    assert result["high_yield_candidates"]
    assert result["comparator"]["leaders"]["best_rente_obligasjon"] != "-"


def test_portfolio_analyzer_counts_high_yield_separately():
    result = analyze_mixed_portfolio([
        {"symbol": "VOO", "asset_type": "ETF", "weight_pct": 60, "recommended_role": "Grunnmur"},
        {"symbol": "BND", "asset_type": "Rente-/obligasjonsfond", "weight_pct": 25},
        {"symbol": "HYG", "asset_type": "High yield-fond", "weight_pct": 15},
    ], profile="Balansert")
    summary = result["summary"]
    assert summary["fixed_income_pct"] == 25
    assert summary["high_yield_pct"] == 15
    assert result["status"] == "ok"
