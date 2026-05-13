from portfolio_intelligence_engine import (
    PORTFOLIO_INTELLIGENCE_SCHEMA_VERSION,
    PortfolioConstraints,
    build_portfolio_intelligence_profile,
)


def _rows():
    return [
        {"symbol": "QQQ", "asset_type": "ETF", "weight_pct": 38, "sector": "Teknologi/vekst", "geography": "USA/Global", "foundation_score": 86},
        {"symbol": "HYG", "asset_type": "High yield-fond", "weight_pct": 22, "sector": "High yield/kreditt", "geography": "USA/Global", "foundation_score": 72},
        {"symbol": "TLT", "asset_type": "Rente-/obligasjonsfond", "weight_pct": 18, "geography": "USA/Global", "foundation_score": 69},
        {"symbol": "SGOV", "asset_type": "Pengemarkedsfond", "weight_pct": 12, "geography": "USA/Global", "foundation_score": 62},
        {"symbol": "SPY", "asset_type": "ETF", "weight_pct": 10, "sector": "Bred indeks", "geography": "USA/Global", "foundation_score": 78},
    ]


def test_portfolio_intelligence_has_optimizer_budget_and_regime():
    profile = build_portfolio_intelligence_profile(_rows(), regime="risk_off")
    assert profile["schema_version"] == PORTFOLIO_INTELLIGENCE_SCHEMA_VERSION
    assert profile["model"] == "Portfolio Intelligence Engine"
    assert profile["regime"] == "risk_off"
    assert profile["optimizer"]["model"] == "Portfolio Optimizer"
    assert profile["risk_budget_policy"]["model"] == "Risk Budget Policy"
    assert profile["core_risk_engine"]["model"] == "Core Risk Engine"


def test_optimizer_target_weights_sum_to_100_and_actions_exist():
    profile = build_portfolio_intelligence_profile(_rows(), regime="balanced")
    targets = profile["optimizer"]["target_weights"]
    total = sum(x["target_weight_pct"] for x in targets)
    assert 99.5 <= total <= 100.5
    assert all(x["action"] in {"increase", "reduce", "hold"} for x in targets)
    assert profile["optimizer"]["estimated_turnover_pct"] >= 0


def test_risk_off_reduces_tech_score_vs_risk_on():
    risk_on = build_portfolio_intelligence_profile(_rows(), regime="risk_on")
    risk_off = build_portfolio_intelligence_profile(_rows(), regime="risk_off")
    qqq_on = next(x for x in risk_on["ranked_candidates"] if x["symbol"] == "QQQ")
    qqq_off = next(x for x in risk_off["ranked_candidates"] if x["symbol"] == "QQQ")
    assert qqq_off["suggested_score"] < qqq_on["suggested_score"]


def test_constraints_are_respected_for_max_position():
    constraints = PortfolioConstraints(max_position_pct=35, target_position_count=5, max_turnover_pct=100)
    profile = build_portfolio_intelligence_profile(_rows(), constraints=constraints)
    targets = profile["optimizer"]["target_weights"]
    assert max(x["target_weight_pct"] for x in targets) <= 35.01
    assert len(targets) == 5
