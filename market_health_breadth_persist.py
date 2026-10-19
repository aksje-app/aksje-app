"""One-time verified historical breadth import into the existing market snapshot.

Runs at most once per UTC day when not successfully completed. Strictly
informational: never mutates trade state or validates the composite.
"""
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from market_health_breadth_backfill_job import (
    MEMBERSHIP_URL, parse_membership_csv, monthly_snapshots,
    download_adjusted_prices, prepare_backfill,
)

def apply_verified_backfill(snapshot, *, now=None, fetch_csv=None, fetch_prices=None):
    now = now or datetime.now(timezone.utc)
    snapshot = dict(snapshot or {})
    status = dict(snapshot.get("breadth_backfill_status") or {})
    if status.get("state") == "COMPLETED":
        return snapshot
    if status.get("attempt_date") == now.date().isoformat():
        return snapshot
    status = {"state":"RUNNING","attempt_date":now.date().isoformat(),"at":now.isoformat()}
    snapshot["breadth_backfill_status"] = status
    try:
        if fetch_csv is None:
            def fetch_csv():
                req=Request(MEMBERSHIP_URL,headers={"User-Agent":"MarketHealthHistory/1.0"})
                with urlopen(req,timeout=30) as response:
                    return response.read(12000000).decode("utf-8-sig")
        text=fetch_csv()
        start=now.date()-timedelta(days=31*18)
        snapshots=monthly_snapshots(parse_membership_csv(text),start=start,end=now.date())
        tickers=sorted(set().union(*(members for _,members in snapshots))) if snapshots else []
        if fetch_prices is None:
            fetch_prices=download_adjusted_prices
        prices=fetch_prices(tickers,years=5) if tickers else {}
        proposal=prepare_backfill(membership_csv=text,prices=prices,start=start,end=now.date())
        accepted=proposal["observations"]
        if not accepted:
            raise ValueError("Ingen historiske datoer oppfylte 80 prosent kursdekning")
        indicators=dict(snapshot.get("indicators") or {})
        old=dict(indicators.get("breadth") or {})
        existing=list(old.get("observations") or [])
        joined={row["observed_at"]:row for row in existing+accepted if isinstance(row,dict) and row.get("observed_at")}
        history=sorted(joined.values(),key=lambda r:r["observed_at"])[-4000:]
        indicators["breadth"]={**old,"observations":history}
        snapshot["indicators"]=indicators
        status.update({"state":"COMPLETED","accepted_months":len(accepted),
                       "rejected_months":proposal["rejected_months"],
                       "total_observations":len(history),"minimum_coverage":0.8})
    except Exception as exc:
        status.update({"state":"FAILED","error":str(exc)[:300]})
    return snapshot
