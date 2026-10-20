from superfund_fmp_history import approved_symbol,fetch_history
def test_verified_mapping_only():
    entry={"LU0154236417":{"isin":"LU0154236417","kind":"fond","symbol":"FOO","verified":True,"evidence_url":"https://example.org/source"}}
    assert approved_symbol("LU0154236417","fond",entry)=="FOO"
    assert approved_symbol("LU0154236417","etf",entry) is None
def test_no_fake_history_without_provider_key():
    try:fetch_history("FOO","fond",api_key="")
    except ValueError as exc:assert str(exc)=="FMP_API_KEY_MISSING"
    else:assert False
