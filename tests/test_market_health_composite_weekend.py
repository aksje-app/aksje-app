from datetime import datetime, timezone
from market_health_composite_gauge import composite_gauge
from market_health_history import normalize

def test_composite_unvalidated_has_no_pointer_or_score():
    html = composite_gauge({"risk_score": 82, "validated": False})
    assert "IKKE BEREGNET" in html
    assert "<line" not in html
    assert "82 / 100" not in html

def test_composite_validated_displays_score():
    html = composite_gauge({"risk_score": 42, "validated": True})
    assert "42 / 100" in html
    assert "<line" in html

def test_friday_breadth_remains_current_sunday():
    observation = {"value": 55.152, "observed_at": "2026-10-16T00:00:00+00:00", "source":"Dated genuine closes"}
    result = normalize("breadth", observation, now=datetime(2026,10,18,19,tzinfo=timezone.utc))
    assert result["status"] == "CURRENT"

def test_old_breadth_is_stale():
    observation = {"value": 55.152, "observed_at": "2026-10-12T00:00:00+00:00", "source":"Dated genuine closes"}
    result = normalize("breadth", observation, now=datetime(2026,10,18,19,tzinfo=timezone.utc))
    assert result["status"] == "STALE"
