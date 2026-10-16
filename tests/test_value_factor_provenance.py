from candidate_market_data import _fundamental_fields
from services.value_factor_audit import extended_value_factors


def test_trailing_pe_source_is_recorded():
    fields, trace = _fundamental_fields({"trailingPE": 9, "forwardPE": 6, "priceToBook": 1.4, "operatingMargins": .21})
    assert fields["trailing_pe"] == 9
    assert fields["forward_pe"] == 6
    assert fields["pe_source"] == "trailingPE"
    assert fields["price_to_book"] == 1.4
    assert fields["operating_margin"] == 21
    assert any(item["step"] == "pe_source" for item in trace)


def test_forward_fallback_is_explicit_and_not_hidden():
    fields, _ = _fundamental_fields({"forwardPE": 7})
    assert fields["trailing_pe"] == 7  # current legacy ranking is unchanged
    assert fields["pe_source"] == "forwardPE_fallback"
    evidence = extended_value_factors(fields)
    assert evidence["pe_provenance"] == "forwardPE_fallback"
    assert evidence["can_authorize_buy"] is False


def test_missing_and_nonfinite_fundamentals():
    fields, _ = _fundamental_fields({"trailingPE": float("nan"), "forwardPE": None})
    assert fields["pe_source"] == "MISSING"
    assert "trailing_pe" not in fields


def test_factor_observation_does_not_change_legacy_ranking():
    from quality_market_prescreen import prescreen_score
    fields, _ = _fundamental_fields({"trailingPE": 8, "returnOnEquity": .17, "debtToEquity": 35})
    before = prescreen_score(fields)
    extended_value_factors(fields)
    assert prescreen_score(fields) == before
