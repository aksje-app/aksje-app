from datetime import datetime, timezone, timedelta
from market_health_cockpit import historical_position, dial_svg, market_cards

def test_historical_needle_requires_actual_dispersion_and_sample_count():
    assert historical_position(5,[]) is None
    assert historical_position(5,[{"value":5}]*20) is None
    obs=[{"value":i} for i in range(20)]
    assert historical_position(10,obs)==.55
    svg=dial_svg("gold",10,obs)
    assert "#5ac6da" in svg
    assert "L" in svg

def test_no_risk_claim_for_descriptive_needle():
    obs=[{"value":i} for i in range(20)]
    html=market_cards([{"key":"gold","name":"Gull","valid":True,"value":10,"label":"10 USD","observed":"18.10","observations":obs}])
    assert "Historisk nivå" in html
    assert "Skala ikke kalibrert" not in html
    assert "mh-cockpit-grid" in html

def test_missing_data_remain_neutral():
    html=market_cards([{"key":"ttf","name":"TTF","valid":False,"label":"Mangler data"}])
    assert "#5ac6da" not in html
