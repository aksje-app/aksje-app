from datetime import datetime, timezone, timedelta
import pandas as pd
from market_health_collector import collect


def test_collector_uses_real_dated_close_and_does_not_fake_composite():
    idx = pd.date_range(end=datetime.now(timezone.utc)-timedelta(days=1), periods=205, freq="B")
    frame = pd.DataFrame({"Close": [100+i*.1 for i in range(205)]}, index=idx)
    snap = collect({}, history_provider=lambda symbol: frame, fred_provider=lambda series: [], cape_provider=lambda: [])
    assert snap["composite"]["validated"] is False
    assert snap["indicators"]["trend"]["value"] > 0
    assert "Yahoo Finance daily" in snap["indicators"]["vix"]["source"]
    assert snap["indicators"]["us10y"]["value"] == frame["Close"].iloc[-1]
    assert "cape" not in snap["indicators"]


def test_collection_failure_never_turns_into_zero_price():
    def fail(_symbol):
        raise RuntimeError("provider unavailable")
    snap = collect({}, history_provider=fail, fred_provider=lambda series: [])
    assert "vix" in snap["collection_status"]["errors"]
    assert "vix" not in snap["indicators"]
