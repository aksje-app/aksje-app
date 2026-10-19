from datetime import datetime, timezone
from market_health_vix_intraday import us_regular_session, update_vix_intraday

def test_us_session_uses_new_york_time():
    assert us_regular_session(datetime(2026,10,19,14,0,tzinfo=timezone.utc))
    assert not us_regular_session(datetime(2026,10,19,12,0,tzinfo=timezone.utc))
    assert not us_regular_session(datetime(2026,10,18,14,0,tzinfo=timezone.utc))

def test_failed_quote_preserves_daily_close_and_history():
    row={"value":19.99,"observed_at":"2026-10-16T05:00:00+00:00","source":"daily"}
    now=datetime(2026,10,19,14,0,tzinfo=timezone.utc)
    state=update_vix_intraday({"indicators":{"vix":{**row,"observations":[row]}}},
        now=now, provider=lambda:None)
    assert state["indicators"]["vix"]["value"]==19.99
    assert state["vix_intraday_status"]["state"]=="UNAVAILABLE"
    assert len(state["indicators"]["vix"]["observations"])==1
