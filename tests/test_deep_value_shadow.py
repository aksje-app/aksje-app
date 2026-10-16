from services.deep_value_shadow_service import deep_value_evidence
from quality_market_prescreen import prescreen_score


def test_deep_value_shadow_classification_does_not_authorize_trades():
    good = {"trailing_pe": 7.5, "roe": 17, "debt_to_equity": 42}
    evidence = deep_value_evidence(good)
    assert evidence["status"] == "DEEP_VALUE_WATCH"
    assert evidence["can_authorize_buy"] is False
    assert evidence["shadow_only"] is True
    assert deep_value_evidence({"trailing_pe": -3, "roe": 17, "debt_to_equity": 42})["status"] == "NOT_QUALIFIED"
    assert deep_value_evidence({"trailing_pe": 7.5})["status"] == "INSUFFICIENT_EVIDENCE"


def test_legacy_prescreen_score_remains_unchanged():
    data = {"trailing_pe": 7.5, "roe": 17, "debt_to_equity": 42, "earnings_growth": 8, "revenue_growth": 6}
    score_before = prescreen_score(data)
    deep_value_evidence(data)
    assert prescreen_score(data) == score_before
