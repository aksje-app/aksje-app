from market_health_cockpit import dial_svg, historical_position, market_cards

def test_unrated_measure_with_history_has_cyan_needle_not_risk_color():
    obs=[{"value":float(i)} for i in range(20)]
    assert historical_position(10.0,obs) == 0.55
    html=dial_svg("gold",10.0,obs)
    assert "#29bb85" in html
    assert "L" in html

def test_unrated_measure_without_history_stays_neutral():
    assert "#29bb85" in dial_svg("gold",10.0,[])
    assert historical_position(10.0,[{"value":10.0}]*20) is None

def test_cockpit_avoids_false_risk_label():
    obs=[{"value":float(i)} for i in range(20)]
    html=market_cards([{"key":"gold","name":"Gull","value":10.0,"label":"10 USD","valid":True,"observations":obs,"observed":"18.10"}])
    assert "Lavt nivå" in html
    assert "Svært høy" not in html
