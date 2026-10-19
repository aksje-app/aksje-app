from datetime import datetime,timezone
from market_health_history import normalize

def test_friday_market_bars_stay_current_early_utc_monday():
    row={"value":19.99,"source":"Friday daily close","observed_at":"2026-10-16T05:00:00+00:00"}
    monday=datetime(2026,10,19,2,6,tzinfo=timezone.utc)
    assert normalize("vix",row,now=monday)["status"]=="CURRENT"
    assert normalize("breadth",row,now=monday)["status"]=="CURRENT"
    later=datetime(2026,10,19,23,0,tzinfo=timezone.utc)
    assert normalize("vix",row,now=later)["status"]=="STALE"

def test_old_thursday_quote_not_revived_on_monday():
    row={"value":19.99,"source":"daily close","observed_at":"2026-10-15T05:00:00+00:00"}
    assert normalize("vix",row,now=datetime(2026,10,19,2,6,tzinfo=timezone.utc))["status"]=="STALE"
