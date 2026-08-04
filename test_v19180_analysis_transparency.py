from analysis_transparency import attach_analysis_transparency, build_candidate_transparency


def _candidate():
    return {
        "ticker": "TEST.OL", "investment_score": 76.5, "confidence_score": 70,
        "confidence_before_evidence_policy": 88, "data_quality": 95,
        "evidence_valid_for_decision": False, "valid_for_decision": True,
        "positives": ["Sterk margin"], "risks": ["Syklisk risiko"],
        "raw": {"score_formula": {"weighted_contributions": {"quality": 22, "momentum": 18, "news": 4}}},
        "evidence_passport": {
            "areas": {
                "news": {"status": "VERIFIED_FACTS_FOUND", "ranking_contribution": 4,
                         "facts": [{"fact_id": "n1", "title": "Resultat over forventning", "source": "Oslo Bors", "source_url": "https://newsweb.no/x", "verification": "VERIFIED"}],
                         "sources": [{"source": "Oslo Bors", "url": "https://newsweb.no/x", "attempted": True, "status": "SUCCESS_WITH_RESULTS", "source_type": "OFFICIAL_EXCHANGE_FEED"}]},
                "insider": {"status": "NOT_SEARCHED", "facts": [], "sources": []},
            }
        },
        "confidence_profile": {"model_confidence": 88, "evidence_adjusted_model_confidence": 70, "market_data_coverage": 95, "evidence_coverage": 50, "source_confidence": 55},
    }


def test_candidate_transparency_separates_score_evidence_confidence():
    result = build_candidate_transparency(_candidate())
    assert result["ranking_explanation"]["total_score"] == 76.5
    assert result["claim_ledger"]["claim_count"] == 1
    assert result["confidence_breakdown"]["not_profit_probability"] is True
    assert result["confidence_breakdown"]["transparent_decision_confidence"] <= 69
    assert any(gap["area"] == "insider" for gap in result["critical_gaps"])


def test_attach_transparency_to_run_and_top3():
    candidate = _candidate()
    run = {"candidates": [candidate], "raw_top3": [dict(candidate)]}
    attach_analysis_transparency(run)
    assert run["analysis_transparency"]["candidate_count"] == 1
    assert run["raw_top3"][0]["analysis_transparency"]["ticker"] == "TEST.OL"
