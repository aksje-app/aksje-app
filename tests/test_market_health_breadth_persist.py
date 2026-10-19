from datetime import datetime,timezone
from market_health_breadth_persist import apply_verified_backfill

NOW=datetime(2026,10,18,22,tzinfo=timezone.utc)

def test_no_prices_do_not_replace_live_breadth():
    row={"value":51.2,"observed_at":"2026-10-16T00:00:00+00:00","source":"live"}
    input_={"indicators":{"breadth":{**row,"observations":[row]}}}
    members=",".join("T%03d"%i for i in range(500))
    result=apply_verified_backfill(input_,now=NOW,fetch_csv=lambda:"date,tickers\n2026-09-30,\""+members+"\"\n",
        fetch_prices=lambda tickers,years:{})
    assert result["breadth_backfill_status"]["state"]=="FAILED"
    assert result["indicators"]["breadth"]["value"]==51.2
    assert len(result["indicators"]["breadth"]["observations"])==1
    assert apply_verified_backfill(result,now=NOW,fetch_csv=lambda:1)==result

def test_approved_historical_rows_are_merged_without_changing_live_value():
    from datetime import date,timedelta
    friday=date(2026,9,30)
    tickers=["T%03d"%i for i in range(500)]
    dates=[friday-timedelta(days=i) for i in range(199,-1,-1)]
    prices={ticker:{day:float(j+1) for j,day in enumerate(dates)} for ticker in tickers[:400]}
    csv="date,tickers\n2026-09-30,\""+",".join(tickers)+"\"\n"
    latest={"value":52.0,"observed_at":"2026-10-16T00:00:00+00:00","source":"live"}
    result=apply_verified_backfill({"indicators":{"breadth":{**latest,"observations":[latest]}}},
        now=NOW,fetch_csv=lambda:csv,fetch_prices=lambda tickers,years:prices)
    assert result["breadth_backfill_status"]["state"]=="COMPLETED"
    assert len(result["indicators"]["breadth"]["observations"])==2
    assert result["indicators"]["breadth"]["value"]==52.0
    assert result.get("composite",{}).get("validated") is not True
