from datetime import datetime, timezone, timedelta
import pandas as pd
from market_health_collector import collect

def test_daily_history_backfills_and_current_value_matches():
    now=datetime.now(timezone.utc)
    idx=pd.date_range(end=now-timedelta(days=1),periods=230,freq="B")
    frame=pd.DataFrame({"Close":[100+i*.5 for i in range(len(idx))]},index=idx)
    result=collect({},history_provider=lambda symbol:frame,fred_provider=lambda series:[],cape_provider=lambda:[],now=now)
    for key in ("gold","dxy","us10y","trend"):
        records=result["indicators"][key]["observations"]
        assert len(records)>=20
        assert len({r["observed_at"] for r in records})==len(records)
        assert abs(records[-1]["value"]-result["indicators"][key]["value"])<.00001
    assert result["collection_status"]["history_schema"]==2

def test_history_backfill_does_not_invent_200d_trend():
    now=datetime.now(timezone.utc)
    idx=pd.date_range(end=now-timedelta(days=1),periods=30,freq="B")
    frame=pd.DataFrame({"Close":[100+i*.1 for i in range(30)]},index=idx)
    result=collect({},history_provider=lambda symbol:frame,fred_provider=lambda series:[],cape_provider=lambda:[],now=now)
    assert "trend" in result["collection_status"]["errors"]
    assert result["composite"]["validated"] is False
