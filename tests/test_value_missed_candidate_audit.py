from services.value_missed_candidate_audit import missed_value_candidate_audit


def test_missed_cheap_quality_and_value_trap_separated():
    rows = [
        {"ticker": "CHEAP.OL", "trailing_pe": 6, "roe": 19, "debt_to_equity": 25,
         "pe_source": "trailingPE", "earnings_growth": 6, "quality_prescreen_score": 65},
        {"ticker": "TRAP.OL", "trailing_pe": 4, "roe": 12, "debt_to_equity": 70,
         "pe_source": "forwardPE_fallback", "earnings_growth": -35,
         "free_cash_flow": -100, "quality_prescreen_score": 58},
        {"ticker": "GROWTH.OL", "trailing_pe": 20, "roe": 25, "debt_to_equity": 20},
        {"ticker": "BROKEN.OL", "trailing_pe": 4, "roe": 21,
         "debt_to_equity": 20, "data_fetch_status": "QUARANTINED"},
    ]
    out = missed_value_candidate_audit(rows, ["GROWTH.OL"])
    assert out["counts"] == {"qualified": 2, "missed": 2, "pe_forward_fallback": 1,
                              "pe_unverified": 0, "possible_value_trap": 1}
    indexed = {r["ticker"]: r for r in out["missed_candidates"]}
    assert indexed["CHEAP.OL"]["risk_signals"] == []
    assert indexed["CHEAP.OL"]["needs_review"] is False
    assert set(indexed["TRAP.OL"]["risk_signals"]) == {"earnings_growth_negative", "free_cash_flow_negative"}
    assert indexed["TRAP.OL"]["needs_review"] is True
    assert out["can_authorize_buy"] is False


def test_missing_valuation_provenance_is_explicit():
    rows = [{"ticker": "UNKNOWN.OL", "trailing_pe": 7, "roe": 20, "debt_to_equity": 30}]
    out = missed_value_candidate_audit(rows, [])
    assert out["counts"]["pe_unverified"] == 1
    assert out["missed_candidates"][0]["needs_review"] is True
