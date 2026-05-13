from core_risk_engine import (
    build_core_risk_profile,
    build_factor_graph,
    build_risk_budget,
    run_stress_tests,
)
from portfolio_intelligence_engine import build_portfolio_intelligence_profile
from validation_engine import build_validation_profile


def _rows():
    return [
        {"symbol": "QQQ", "asset_type": "ETF", "weight_pct": 40, "sector": "Teknologi/vekst", "geography": "USA/Global"},
        {"symbol": "HYG", "asset_type": "High yield-fond", "weight_pct": 25, "sector": "High yield/kreditt", "geography": "USA/Global"},
        {"symbol": "TLT", "asset_type": "Rente-/obligasjonsfond", "weight_pct": 20, "geography": "USA/Global"},
        {"symbol": "SGOV", "asset_type": "Pengemarkedsfond", "weight_pct": 15, "geography": "USA/Global"},
    ]


def test_factor_graph_builds_holdings_to_factor_edges():
    graph = build_factor_graph(_rows())
    assert graph["model"] == "Core Risk Factor Graph"
    assert graph["holding_count"] == 4
    assert graph["factor_totals"]["tech_ai"] > 30
    assert graph["factor_totals"]["credit_spread"] > 20
    assert graph["hidden_dependencies"]


def test_stress_tests_identify_worst_scenario():
    stress = run_stress_tests(_rows())
    assert stress["model"] == "Core Risk Stress Testing"
    assert stress["scenario_count"] >= 5
    assert stress["worst_scenario"]["estimated_impact_pct"] < 0
    assert stress["worst_scenario"]["top_contributors"]


def test_risk_budget_sums_to_roughly_100():
    budget = build_risk_budget(_rows())
    total = sum(budget["risk_budget"].values())
    assert 99.5 <= total <= 100.5
    assert budget["top_risk_factors"][0]["risk_budget_pct"] > 0


def test_core_risk_profile_combines_graph_stress_and_budget():
    profile = build_core_risk_profile(_rows(), selection_info={"profile": "test"})
    assert profile["model"] == "Core Risk Engine"
    assert profile["status"] == "ok"
    assert profile["factor_graph"]["model"] == "Core Risk Factor Graph"
    assert profile["stress_testing"]["model"] == "Core Risk Stress Testing"
    assert profile["risk_budgeting"]["model"] == "Core Risk Budget"
    assert 0 <= profile["core_risk_score"] <= 100


def test_portfolio_intelligence_and_validation_use_core_risk():
    intel = build_portfolio_intelligence_profile(_rows(), regime="risk_off")
    validation = build_validation_profile(_rows())
    assert intel["model"] == "Portfolio Intelligence Engine"
    assert intel["core_risk_engine"]["model"] == "Core Risk Engine"
    assert validation["model"] == "Validation Engine"
    assert validation["core_risk_engine"]["model"] == "Core Risk Engine"
