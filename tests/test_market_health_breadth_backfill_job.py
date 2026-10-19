from datetime import date, timedelta
from market_health_breadth_backfill_job import monthly_snapshots, prepare_backfill

def test_monthly_memberships_and_rejected_missing_prices():
    members={f"T{i:03d}" for i in range(500)}
    rows=[(date(2025,1,2),members),(date(2025,1,31),members),(date(2025,2,28),members)]
    assert [day for day,_ in monthly_snapshots(rows,start=date(2025,1,1),end=date(2025,2,28))]==[date(2025,1,31),date(2025,2,28)]
    csv="date,tickers\n2025-01-31,\""+",".join(sorted(members))+"\"\n2025-02-28,\""+",".join(sorted(members))+"\"\n"
    result=prepare_backfill(membership_csv=csv,prices={},start=date(2025,1,1),end=date(2025,2,28))
    assert result["candidate_months"]==2
    assert result["accepted_months"]==0
    assert result["validated_composite"] is False
    assert result["observations"]==[]
