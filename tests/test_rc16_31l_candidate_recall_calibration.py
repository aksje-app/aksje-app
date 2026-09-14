from types import SimpleNamespace

from app_version import APP_VERSION, PREVIOUS_APP_VERSION, RANKING_MODEL_VERSION
from investment_pipeline import PipelineConfig
import market_intelligence as mi
from autonomi_core.portfolio_decisions.decision_funnel import (
    SHADOW_THRESHOLDS,
    build_decision_funnel,
)


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json


def test_legacy_top10_is_upgraded_to_global_top60():
    assert mi._effective_global_shortlist_size(10, 413) == 60
    assert mi._effective_global_shortlist_size(80, 413) == 80
    assert mi._effective_global_shortlist_size(10, 42) == 42


def test_calibration_thresholds_are_shadow_only():
    assert all(threshold in SHADOW_THRESHOLDS for threshold in (73.0, 70.0, 68.0, 65.0))
    params = SimpleNamespace(
        minimum_investment_score=73.0,
        minimum_data_quality=55.0,
        maximum_risk_score=65.0,
        maximum_open_positions=12,
        allow_additions=False,
    )
    candidate = {
        "ticker": "TEST.OL",
        "market": "Norge",
        "investment_score": 68.0,
        "data_quality": 90.0,
        "risk_score": 25.0,
        "price": 100.0,
        "mission_eligible": True,
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "portfolio_action": "REVIEW",
        "autonomy_outcome_code": "OVERVÅKES_AUTOMATISK",
    }
    result = build_decision_funnel(
        [candidate], parameters=params,
        portfolio={"status": "ACTIVE", "positions": {}}, trades=(),
    )
    shadows = {row["threshold"]: row for row in result["shadow_thresholds"]}
    assert result["production_threshold"] == 73.0
    assert result["production_threshold_changed"] is False
    assert shadows[68.0]["score_qualified_tickers"] == ["TEST.OL"]
    assert shadows[68.0]["changes_production"] is False
