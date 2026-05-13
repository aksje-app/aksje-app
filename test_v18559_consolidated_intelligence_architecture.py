from app_version import get_app_version
from fund_etf_analyzer import (
    build_intelligence_core_profile,
    build_explanation_risk_engine_profile,
    build_portfolio_intelligence_foundation_profile,
    build_unified_intelligence_profile,
)


def _row(symbol="MEGA"):
    return {
        "symbol": symbol,
        "name": "Mega Cap Test ETF",
        "fund_type": "ETF",
        "base_score": 74,
        "decision_quality": 78,
        "data_quality": 82,
        "fund_intelligence_score": 76,
        "scenario_score": 62,
        "portfolio_fit_score": 71,
        "holdings_profile": {
            "holdings_available": True,
            "concentration_score": 42,
            "top10_weight_pct": 61,
            "megacap_weight_pct": 44,
            "sector_weights": {"Technology": 38, "Health Care": 12},
        },
        "insider_holdings_profile": {
            "covered_top_holdings_weight_pct": 21,
            "insider_score": 39,
            "direction": "Negativ",
        },
        "scenario_regime_profile": {"worst_scenario": {"label": "Tech/AI-selloff", "score": 38}},
        "portfolio_fit_profile": {"overlap_pct": 8},
    }


def test_v18559_version():
    assert get_app_version() == "v18.5.73"


def test_intelligence_core_collects_schema_weights_confidence_and_freshness():
    core = build_intelligence_core_profile(_row())
    assert core["model"] == "Intelligence Core"
    assert core["core_score"] > 0
    assert "unified_schema" in core
    assert "weight_governance" in core
    assert "confidence" in core
    assert "freshness" in core


def test_explanation_risk_engine_collects_flags_and_plain_language():
    core = build_intelligence_core_profile(_row())
    risk = build_explanation_risk_engine_profile(_row(), core=core)
    assert risk["model"] == "Explanation & Risk Engine"
    flags = [x["flag"] for x in risk["risk_flags"]]
    assert "Concentration Risk" in flags
    assert "Insider Weakness" in flags


def test_portfolio_intelligence_foundation_wraps_cache_and_why_this_portfolio():
    foundation = build_portfolio_intelligence_foundation_profile([_row("A"), _row("B")])
    assert foundation["model"] == "Portfolio Intelligence Foundation"
    assert "portfolio_overlap_cache" in foundation
    assert foundation["why_this_portfolio"]["selected_count"] == 2


def test_unified_profile_exposes_three_module_architecture():
    profile = build_unified_intelligence_profile(_row())
    assert profile["modules"]["intelligence_core"]["model"] == "Intelligence Core"
    assert profile["modules"]["explanation_risk_engine"]["model"] == "Explanation & Risk Engine"
    assert profile["foundation_score"] > 0
