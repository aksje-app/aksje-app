from market_health_gauges import display_gauge
from market_health_cockpit import dial_svg

def test_all_eight_yahoo_observed_gauges_have_colored_zone_and_needle():
    examples={"vix":19.99,"trend":5.34,"us10y":5.10,"us30y":5.44,"dxy":101.84,
              "brent":109.86,"gold":4181.10,"eurusd":1.12}
    for key,value in examples.items():
        result=display_gauge(key,value)
        assert result["status"]=="DISPLAY_ONLY"
        assert result["percent"] is not None
        svg=dial_svg(key,value)
        assert "#f4fafc" in svg and "#29bb85" in svg

def test_ten_year_boundary_and_thirty_year_distinct_threshold():
    assert display_gauge("us10y",5.10)["label"]=="Høy"
    assert display_gauge("us10y",5.30)["label"]=="Svært høy"
    assert display_gauge("us30y",5.44)["label"]=="Høy"
    assert display_gauge("us30y",5.50)["label"]=="Svært høy"

def test_nonrisk_price_colors_have_explicit_descriptive_labels():
    for key,val in (("gold",4181),("brent",110),("dxy",102),("eurusd",1.12)):
        result=display_gauge(key,val)
        assert "nivå" in result["label"]
        assert "ikke" in result["method"].lower() or "IKKE" in result["method"]

def test_unavailable_sources_stay_unrated_and_gray():
    for key in ("cape","breadth","ttf","equity_yield"):
        assert display_gauge(key,100)["percent"] is None
        assert "#718899" in dial_svg(key,None)
