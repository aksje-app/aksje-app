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


def test_shadow_reports_low_pe_candidates_outside_existing_finalists(monkeypatch):
    import quality_market_prescreen as module
    candidates = {
        "VALUE.OL": {"ticker": "VALUE.OL", "last_price": 100, "trailing_pe": 7, "roe": 18, "debt_to_equity": 30},
        "GROWTH.OL": {"ticker": "GROWTH.OL", "last_price": 100, "trailing_pe": 16, "roe": 35, "debt_to_equity": 10},
    }
    monkeypatch.setattr(module, "enrich_candidate_rows", lambda rows, **kwargs: [dict(candidates[r["ticker"]]) for r in rows])
    import quality_turnaround
    monkeypatch.setattr(quality_turnaround, "reserve_watch_slots", lambda rows, limit, official: (rows[:limit], []))
    outcome = module.full_market_prescreen(["VALUE.OL", "GROWTH.OL"], finalist_limit=1)
    assert outcome["finalists"] == ["GROWTH.OL"]
    summary = outcome["deep_value_shadow_summary"]
    assert summary["qualified_count"] == 1
    assert summary["outside_finalists_tickers"] == ["VALUE.OL"]
    assert summary["can_authorize_buy"] is False


def test_low_pe_does_not_hide_missing_quality_or_poor_balance_sheet():
    missing = deep_value_evidence({"trailing_pe": 5.0, "roe": None, "debt_to_equity": None})
    assert missing["status"] == "INSUFFICIENT_EVIDENCE"
    assert set(missing["missing_fields"]) == {"roe", "debt_to_equity"}
    leveraged = deep_value_evidence({"trailing_pe": 5.0, "roe": 22, "debt_to_equity": 180})
    assert leveraged["status"] == "NOT_QUALIFIED"
    assert leveraged["flags"]["manageable_debt"] is False
    assert leveraged["can_authorize_buy"] is False


def test_shadow_preserves_existing_score_but_exposes_value_discount():
    low = {"trailing_pe": 6, "roe": 18, "debt_to_equity": 30}
    normal = {**low, "trailing_pe": 16}
    assert prescreen_score(low) < prescreen_score(normal)
    assert deep_value_evidence(low)["status"] == "DEEP_VALUE_WATCH"
    assert deep_value_evidence(normal)["status"] == "NOT_QUALIFIED"
