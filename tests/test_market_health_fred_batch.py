from datetime import datetime, timezone, timedelta
import pandas as pd
from market_health_collector import collect, FRED_SERIES
from market_health_gauges import display_gauge

def test_fred_series_are_timestamped_and_do_not_touch_trading():
    now=datetime.now(timezone.utc)
    ix=pd.DatetimeIndex([now-timedelta(days=i) for i in (2,1)])
    def yahoo(symbol):
        return pd.DataFrame({"Close": [100.,101.]},index=ix)
    def fred(series):
        value=4.2 if series=="BAMLH0A0HYM2" else -0.35
        return [{"value":value,"source":"FRED daily "+series,"observed_at":(now-timedelta(days=1)).isoformat()}]
    output=collect({},history_provider=yahoo,fred_provider=fred,now=now)
    assert output["indicators"]["credit"]["value"]==4.2
    assert output["indicators"]["curve"]["value"]==-0.35
    assert "credit" in output["collection_status"]["updated"]
    assert "curve" in output["collection_status"]["updated"]
    assert output["composite"]["validated"] is False

def test_fred_failure_preserves_last_known_value_and_reports_error():
    now=datetime.now(timezone.utc)
    prior={"indicators":{"credit":{"value":4.8,"source":"FRED historical","observed_at":(now-timedelta(days=1)).isoformat()}}}
    def yahoo(symbol):
        raise ValueError("not available")
    def fred(series):
        raise RuntimeError("source unreachable")
    output=collect(prior,history_provider=yahoo,fred_provider=fred,now=now)
    assert output["indicators"]["credit"]["value"]==4.8
    assert "credit" in output["collection_status"]["errors"]

def test_new_scales_are_explicitly_provisional():
    assert display_gauge("credit",6)["status"]=="DISPLAY_ONLY"
    assert display_gauge("curve",-1.5)["reverse_risk"] is True
    for key in ("gold","brent","us10y","us30y","dxy","eurusd"):
        assert display_gauge(key,5)["status"]=="DISPLAY_ONLY"
