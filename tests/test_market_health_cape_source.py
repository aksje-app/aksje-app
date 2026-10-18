from datetime import datetime, timezone, timedelta
from market_health_collector import collect

def test_cape_collects_monthly_observation_without_fabrication():
    now=datetime.now(timezone.utc)
    month_start=datetime(now.year,now.month,1,tzinfo=timezone.utc)
    records=[{"value":36.5,"source":"Robert Shiller Yale monthly CAPE (ie_data.xls)","observed_at":month_start.isoformat()}]
    def fail(symbol):
        raise RuntimeError("provider disabled in test")
    out=collect({}, history_provider=fail, fred_provider=lambda series: [], cape_provider=lambda: records, now=now)
    assert out["indicators"]["cape"]["value"]==36.5
    assert "cape" in out["collection_status"]["updated"]
    assert out["composite"]["validated"] is False

def test_cape_provider_failure_preserves_prior_observation():
    now=datetime.now(timezone.utc)
    previous={"indicators":{"cape":{"value":30.,"source":"Yale monthly CAPE","observed_at":(now-timedelta(days=8)).isoformat()}}}
    def fail(*_):
        raise RuntimeError("unavailable")
    out=collect(previous,history_provider=fail,fred_provider=fail,cape_provider=fail,now=now)
    assert out["indicators"]["cape"]["value"]==30.
    assert "cape" in out["collection_status"]["errors"]
