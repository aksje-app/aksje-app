from datetime import datetime,timezone
from market_health_preliminary_composite import preliminary_composite,RISK_KEYS
from market_health_composite_gauge import composite_gauge

NOW=datetime(2026,10,16,20,tzinfo=timezone.utc)

def test_missing_inputs_never_produce_score():
    x=preliminary_composite({"indicators":{}},now=NOW)
    assert x["risk_score"] is None
    assert x["validated"] is False

def test_dated_readings_produce_explicit_provisional_needle():
    rows={}
    for key in RISK_KEYS:
        rows[key]={"value":{"cape":40,"equity_yield":1.7,"ttf":87,"us10y":5.1,"us30y":5.4,"breadth":55,"vix":20,"trend":5,"credit":3.2,"curve":.35}[key],"source":"Test verified source","observed_at":"2026-10-16T00:00:00Z"}
    x=preliminary_composite({"indicators":rows},now=NOW)
    assert x["validated"] is False
    assert x["provisional"] is True
    assert 0<=x["risk_score"]<=100
    assert x["trade_signals_enabled"] is False
    html=composite_gauge(x)
    assert "FORELØPIG" in html and "<line" in html
