from copy import deepcopy

from report_integrity import canonical_report_view, validate_report_integrity


def _candidate(ticker="AAA.OL", action="SKIP", code="AUTOMATISK_AVVIST"):
    return {
        "ticker": ticker, "name": "Alpha ASA", "market": "Norge", "rank": 1,
        "investment_score": 70, "confidence_score": 80, "risk_score": 30,
        "valid_for_decision": True, "evidence_valid_for_decision": False,
        "autonomy_outcome_code": code, "autonomy_outcome_reason": "Evidensport lukket",
        "portfolio_action": action,
        "decision_readiness": {"market_data": "VALID", "news": "NOT_SEARCHED", "insider": "NOT_SEARCHED"},
        "evidence_coverage": {"news": {"status": "NOT_SEARCHED"}, "insider": {"status": "NOT_SEARCHED"}},
        "raw": {
            "news_intelligence": {"coverage": "NOT_SEARCHED", "events": []},
            "insider_intelligence": {"coverage": "NOT_SEARCHED", "evidence": []},
        },
    }


def _run():
    c = _candidate()
    return {
        "version": "v19.17.0-rc6", "app_version": "v19.17.0-rc6", "report_schema_version": "1.6",
        "version_contract": {"app_version": "v19.17.0-rc6", "report_schema_version": "1.6"},
        "report_identity": {"type": "UTKAST", "label": "Utkast"},
        "report_status": {"state": "DRAFT", "label": "UTKAST – IKKE ENDELIG"},
        "candidates": [c], "markets": ["Norge", "Sverige", "USA"],
        "market_profile": {"profile_id": "CORE", "label": "Kjernemarkeder", "expanded_markets": ["Norge", "Sverige", "USA"]},
        "summary": {"scanned": 1, "proposals": 1},
        "portfolio_decisions": {"portfolio_context": {"active": False}, "decisions": [{"ticker": "AAA.OL", "action": "REVIEW", "reason": "gammel"}], "actions": {"REVIEW": 1}},
        "portfolio_proposal": {"actions": {"REVIEW": 1}, "allocations": [{"ticker": "AAA.OL"}], "positions": []},
        "market_runs": [{"candidates": [{"ticker": "AAA.OL", "status": "KREVER MANUELL VURDERING", "portfolio_action": "REVIEW"}], "proposals": [{"ticker": "AAA.OL", "status": "KREVER MANUELL VURDERING", "portfolio_action": "REVIEW"}]}],
        "changes": {"new": [{"ticker": "AAA.OL", "status": "KREVER MANUELL VURDERING", "portfolio_action": "REVIEW", "reason": "gammel"}]},
        "combined_data_quality": {"evaluated": 1, "market_data_valid": 1},
        "data_quality": {"score": 100},
    }


def test_all_derived_candidate_views_are_synchronised():
    out = canonical_report_view(_run())
    assert out["portfolio_proposal"]["actions"]["SKIP"] == 1
    assert out["portfolio_proposal"]["actions"]["REVIEW"] == 0
    assert out["portfolio_proposal"]["allocations"] == []
    assert out["market_runs"][0]["candidates"][0]["portfolio_action"] == "SKIP"
    assert out["market_runs"][0]["proposals"][0]["status"] == "Automatisk avvist"
    assert out["changes"]["new"][0]["portfolio_action"] == "SKIP"
    assert out["report_integrity"]["ok"] is True


def test_integrity_rejects_parallel_portfolio_truths():
    out = canonical_report_view(_run())
    broken = deepcopy(out)
    broken["portfolio_proposal"]["actions"]["REVIEW"] = 1
    broken["portfolio_proposal"]["actions"]["SKIP"] = 0
    result = validate_report_integrity(broken)
    assert result["ok"] is False
    assert any("portfolio_proposal.actions" in error for error in result["errors"])


def test_documentation_coverage_never_exceeds_evidence_coverage():
    out = canonical_report_view(_run())
    profile = out["candidates"][0]["confidence_profile"]
    assert profile["documentation_coverage"] <= profile["evidence_coverage"]


def test_invalid_direct_news_source_is_rejected():
    run = _run()
    run["candidates"][0]["raw"]["news_intelligence"] = {
        "coverage": "VERIFIED_FACTS_FOUND", "verified_fact_count": 1,
        "events": [{"title": "Alpha ASA wins contract", "company_relevant": True, "source_url": "not-a-url"}],
    }
    run["candidates"][0]["decision_readiness"]["news"] = "VERIFIED_FACTS_FOUND"
    out = canonical_report_view(run)
    assert out["report_integrity"]["ok"] is True
    assert any("ekskludert fra verifisert evidens" in warning for warning in out["report_integrity"]["warnings"])
