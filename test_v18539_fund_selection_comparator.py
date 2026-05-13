from fund_etf_analyzer import (
    select_fund_candidates,
    build_fund_comparator,
    analyze_fund_record,
    run_fund_etf_lab,
)


def _prices(start=100, step=2, n=80):
    return [start + i * step for i in range(n)]


def _bench(symbol="SPY"):
    return {"symbol": symbol, "quoteType": "ETF", "expenseRatio": 0.0009, "prices": _prices(100, 1.2, 80)}


def _provider(symbol):
    if symbol == "ARKK":
        return {"symbol": symbol, "quoteType": "ETF", "name": "ARK Innovation ETF", "expenseRatio": 0.0075, "prices": _prices(100, 0.8, 80)}
    if symbol == "ACTIVEWIN":
        return {"symbol": symbol, "quoteType": "MUTUALFUND", "name": "Active Winner", "expenseRatio": 0.008, "prices": _prices(100, 2.4, 80)}
    return {"symbol": symbol, "quoteType": "ETF", "name": f"{symbol} ETF", "expenseRatio": 0.0003, "prices": _prices(100, 1.8, 80)}


def test_auto_fund_selection_uses_source_not_manual_order():
    selected = select_fund_candidates(
        source="Auto ETF",
        fund_type="Alle",
        manual_symbols=["ONLYMANUAL"],
        max_funds=4,
    )
    assert selected["source"] == "Auto ETF"
    assert selected["display_limit"] == 4
    assert len(selected["symbols"]) > 4
    assert "ONLYMANUAL" not in selected["symbols"]
    assert all(row.get("reason") for row in selected["selected"])


def test_balanced_mix_includes_active_candidate_when_room():
    selected = select_fund_candidates(source="Alle / balansert miks", fund_type="Alle", manual_symbols=[], max_funds=6)
    types = {row.get("type") for row in selected["selected"]}
    assert "Aktivt fond" in types
    assert selected["display_limit"] == 6
    assert len(selected["symbols"]) > 6


def test_active_fund_must_prove_evidence():
    row = analyze_fund_record("ARKK", _provider("ARKK"), fund_type="Aktivt fond", objective="Balansert", benchmark_data=_bench())
    assert row["fund_type"] == "Aktivt fond"
    assert row["active_evidence_status"] in {"Ikke bevist", "Usikker", "Mangler data"}
    assert row["decision"] == "Krever mer bevis"
    assert row["decision_quality"] <= 68


def test_fund_comparator_returns_leaders_and_active_evidence():
    result = run_fund_etf_lab(
        ["VOO", "ARKK", "ACTIVEWIN"],
        data_provider=_provider,
        benchmark_provider=_bench,
        benchmark_symbol="SPY",
        fund_type="Alle",
        objective="Balansert",
        test_mode="Rask",
        selection_info={"source": "test"},
    )
    comp = result["comparator"]
    assert comp["count"] == 3
    assert comp["leaders"]["billigst"] in {"VOO"}
    assert "active_evidence" in result
    assert result["selection"]["source"] == "test"
