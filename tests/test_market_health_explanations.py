from market_health_explanations import GAUGE_GUIDE, explain
from market_health_ui import INDICATORS
from market_health_cockpit import market_cards

def test_all_fourteen_have_plain_explanations():
    assert set(GAUGE_GUIDE) == set(INDICATORS)
    for key in INDICATORS:
        guide = explain(key)
        assert all(guide[field] for field in ("question","meaning","caution","note"))

def test_gauges_have_accessible_explanations():
    cards = [{"key":key,"name":meta[0],"valid":False,"label":"Mangler data",
              "status":"Mangler data","observed":""} for key,meta in INDICATORS.items()]
    html = market_cards(cards)
    assert html.count("Hva betyr måleren?") == 14
    assert "Gullpris" in html
    assert "Markedsbredde" in html
