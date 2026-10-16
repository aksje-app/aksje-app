from services.shadow_mark_integrity import audit_shadow_daily_marks


def _mark(day="2026-10-14"):
    return {"market_date":day,"price":101.0,"benchmark_price":220.0,
            "return_pct":1.0,"benchmark_return_pct":0.4,"excess_return_pct":0.6}


def test_real_mark_shape_is_supported():
    result = audit_shadow_daily_marks([{"daily_marks":[_mark()]}])
    assert result["status"] == "DATA_INTEGRITY_OK"
    assert result["can_authorize_buy"] is False


def test_duplicate_and_missing_values_fail_closed():
    dup = audit_shadow_daily_marks([{"daily_marks":[_mark(), _mark()]}])
    assert dup["duplicate_observation_dates"] == 1
    assert dup["status"] == "DATA_INTEGRITY_FAILED"
    bad = _mark()
    bad.pop("benchmark_price")
    assert audit_shadow_daily_marks([{"daily_marks":[bad]}])["invalid_marks"] == 1
