from app_version import get_app_version
from fund_etf_analyzer import (
    build_unified_intelligence_profile,
    build_weight_governance_profile,
    build_confidence_profile,
    build_data_freshness_profile,
    build_standard_risk_flags,
    build_why_this_portfolio_profile,
)


def _row():
    return {
        "symbol": "MEGA",
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


def test_v18558_version():
    assert get_app_version() == "v18.5.62"


def test_unified_intelligence_schema_contains_governance_confidence_and_flags():
    profile = build_unified_intelligence_profile(_row())
    assert profile["model"] == "Unified Intelligence Model"
    assert profile["schema_version"] == 2
    assert profile["weight_governance"]["governed_score"] > 0
    assert profile["confidence"]["confidence_level"] in {"Lav", "Middels", "Høy"}
    flags = [x["flag"] for x in profile["risk_flags"]]
    assert "Concentration Risk" in flags
    assert "Insider Weakness" in flags


def test_weight_governance_renormalizes_missing_layers():
    row = _row()
    row["insider_holdings_profile"] = {"covered_top_holdings_weight_pct": 0}
    governance = build_weight_governance_profile(row)
    assert "insider" in governance["missing_layers"]
    assert abs(sum(governance["normalized_weights"].values()) - 1.0) < 0.01


def test_confidence_and_freshness_are_separate_from_score():
    freshness = build_data_freshness_profile(_row(), {"holdings_date": "2026-01-01T00:00:00+00:00"})
    confidence = build_confidence_profile(_row(), freshness)
    assert "freshness_score" in freshness
    assert "confidence_score" in confidence


def test_why_this_portfolio_engine_summarizes_selection():
    rows = [_row(), {**_row(), "symbol": "BOND", "portfolio_fit_score": 66, "confidence_score": 70}]
    profile = build_why_this_portfolio_profile(rows)
    assert profile["model"] == "Why This Portfolio Engine"
    assert profile["selected_count"] == 2
    assert profile["summary"]
