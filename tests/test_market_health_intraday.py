from datetime import datetime, timezone
from market_health_intraday import in_session, update_intraday

def test_market_hours_and_closed_data_preserved():
    monday=datetime(2026,10,19,14,0,tzinfo=timezone.utc)
    sunday=datetime(2026,10,18,14,0,tzinfo=timezone.utc)
    assert in_session("us10y",monday)
    assert not in_session("us10y",sunday)
    row={"value":5.1,"observed_at":"2026-10-16T05:00:00+00:00","source":"daily"}
    saved={"indicators":{"us10y":{**row,"observations":[row]}}}
    result=update_intraday(saved,now=sunday,provider=lambda key,symbol:None)
    assert result["indicators"]["us10y"]["value"]==5.1
    assert result["intraday_status"]["us10y"]["state"]=="MARKET_CLOSED"

def test_no_provider_data_never_replaces_daily_value():
    monday=datetime(2026,10,19,14,0,tzinfo=timezone.utc)
    row={"value":5.1,"observed_at":"2026-10-16T05:00:00+00:00","source":"daily"}
    result=update_intraday({"indicators":{"us10y":{**row,"observations":[row]}}},
                           now=monday,provider=lambda key,symbol:None)
    assert result["indicators"]["us10y"]["value"]==5.1
    assert result["intraday_status"]["us10y"]["state"]=="UNAVAILABLE"
