from pathlib import Path
from market_health_gauges import display_gauge


def test_vix_needle_and_risk_zones_agree_at_boundaries():
    assert display_gauge("vix", 15)["percent"] == 16.67
    assert display_gauge("vix", 20)["percent"] == 33.33
    assert display_gauge("vix", 30)["percent"] == 66.67
    assert display_gauge("vix", 19.99)["label"] == "Moderat"


def test_display_only_indicators_do_not_affect_trading():
    for key in ("dxy", "us10y", "brent", "eurusd"):
        assert display_gauge(key, 100)["status"] == "DISPLAY_ONLY"


def test_css_segments_follow_vix_display_breakpoints():
    source = Path("market_health_cockpit.py").read_text(encoding="utf-8")
    assert "spec = DISPLAY_SCALES.get(key" in source
    assert "segments = list(zip([0.0] + cut, cut + [1.0]))" in source
    assert "COLORS" in source
    assert "opacity=" in source
    assert "if gauge.get(\"reverse_risk\")" in source
