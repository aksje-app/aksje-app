from datetime import datetime, timezone
from market_health_history import normalize
from market_health_backtest_readiness import assess_historical_feasibility

def test_monday_before_new_daily_close_keeps_friday_display():
    row={"value":19.99,"observed_at":"2026-10-16T05:00:00+00:00","source":"Yahoo"}
    assert normalize("vix",row,now=datetime(2026,10,19,13,49,tzinfo=timezone.utc))["status"]=="CURRENT"
    assert normalize("breadth",row,now=datetime(2026,10,19,13,49,tzinfo=timezone.utc))["status"]=="CURRENT"
    assert normalize("vix",row,now=datetime(2026,10,19,23,0,tzinfo=timezone.utc))["status"]=="STALE"

def test_readiness_never_claims_validation_from_sparse_observations():
    result=assess_historical_feasibility({"indicators":{"vix":{"observations":[{"value":20,"observed_at":"2011-10-17T00:00:00+00:00","source":"test"}]}}})
    assert result["validated"] is False
    assert result["historical_coverage"]["vix"]["count"]==1
    assert result["coverage_ready"] is False
