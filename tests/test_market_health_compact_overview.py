from pathlib import Path
from market_health_gauges import display_gauge

def test_overview_hides_unvalidated_oversized_dial():
    source=Path("market_health_ui.py").read_text(encoding="utf-8")
    assert 'st.markdown(dial("Samlet markedsrisiko", score)' in source
    assert 'and overall.get("validated") is True' in source
    assert "av {len(INDICATORS)} indikatorer har målte verdier" in source

def test_all_observed_measures_have_explicit_preliminary_display_scale():
    assert display_gauge("vix",19.99)["label"] == "Moderat"
    for key in ("us10y","us30y","gold","dxy","brent","eurusd"):
        assert display_gauge(key,3)["status"] == "DISPLAY_ONLY"
