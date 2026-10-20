from datetime import datetime, timezone
from app_time_display import format_in_zone,age_hours

def test_norway_dst_and_fortaleza():
    ts="2026-10-20T19:00:00+00:00"
    assert "21:00" in format_in_zone(ts,"Europe/Oslo")
    assert "16:00" in format_in_zone(ts,"America/Fortaleza")
    ts="2026-10-26T20:00:00+00:00"
    assert "21:00" in format_in_zone(ts,"Europe/Oslo")
    assert "17:00" in format_in_zone(ts,"America/Fortaleza")

def test_naive_never_assumed_utc():
    assert "ukjent" in format_in_zone("2026-10-20T12:00:00","Europe/Oslo")
    assert age_hours("2026-10-20T12:00:00") is None

class _Browser:
    class context:
        timezone="America/Fortaleza"

def test_browser_timezone():
    from app_time_display import local_display,browser_timezone
    assert browser_timezone(_Browser)=="America/Fortaleza"
    assert "16:00" in local_display(_Browser,"2026-10-20T19:00:00+00:00")
