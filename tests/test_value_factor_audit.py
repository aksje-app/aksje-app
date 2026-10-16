from services.value_factor_audit import extended_value_factors


def test_extended_factor_audit_does_not_invent_missing_data():
    audit = extended_value_factors({"trailing_pe": 7.5, "roe": 16, "fcf_yield": float("nan")})
    assert audit["groups"]["valuation"]["trailing_pe"] == 7.5
    assert audit["groups"]["valuation"]["fcf_yield"] is None
    assert "roic" in audit["missing_by_group"]["profitability"]
    assert audit["pe_provenance"] == "UNVERIFIED_TRAILING_OR_FORWARD_FALLBACK"
    assert audit["can_authorize_buy"] is False


def test_extended_audit_preserves_explicit_pe_source():
    audit = extended_value_factors({"trailing_pe": 8, "pe_source": "trailingPE", "price_to_book": 1.2})
    assert audit["pe_provenance"] == "trailingPE"
    assert audit["groups"]["valuation"]["price_to_book"] == 1.2
    assert audit["shadow_only"] is True
