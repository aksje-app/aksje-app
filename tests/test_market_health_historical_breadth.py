from datetime import date,timedelta
from market_health_historical_breadth import parse_membership_csv,historical_breadth

def test_wrong_member_count_is_not_accepted():
    assert parse_membership_csv("date,tickers\n2024-01-02,AAPL,MSFT\n")==[]

def test_no_survivorship_substitutions_or_fabricated_breadth():
    day=date(2026,10,16)
    members={"T%03d"%i for i in range(500)}
    assert historical_breadth([(day,members)],{})==[]
    dates=[day-timedelta(days=j) for j in range(199,-1,-1)]
    prices={t:{d:float(i+1) for i,d in enumerate(dates)} for t in sorted(members)[:399]}
    assert historical_breadth([(day,members)],prices)==[]
    prices["T399"]={d:float(i+1) for i,d in enumerate(dates)}
    result=historical_breadth([(day,members)],prices)
    assert len(result)==1 and result[0]["value"]==100
    assert "400" in result[0]["source"]

def test_weekend_member_snapshot_uses_next_real_trading_session():
    from datetime import date, timedelta
    saturday=date(2026,10,17)
    monday=date(2026,10,19)
    members={f"T{i:03d}" for i in range(500)}
    sessions=[monday-timedelta(days=j) for j in range(199,-1,-1)]
    prices={ticker:{day:float(i+1) for i,day in enumerate(sessions)}
            for ticker in sorted(members)[:400]}
    result=historical_breadth([(saturday,members)],prices)
    assert result and result[0]["observed_at"].startswith("2026-10-19")
