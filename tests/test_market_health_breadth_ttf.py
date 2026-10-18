from datetime import datetime,timezone
import pandas as pd
from market_health_collector import collect, sp500_breadth_daily, SYMBOLS

def test_breadth_validates_published_count_and_date():
    html="<h1>51.5% of S&P 500 stocks (256 of 497) are above their 200-day moving average</h1><p>Last updated: Oct 17, 2026, 12:56 AM UTC</p>"
    result=sp500_breadth_daily(html=html)
    assert result["value"]==51.5
    assert "256/497" in result["source"]
    assert result["observed_at"].startswith("2026-10-17")
    assert SYMBOLS["ttf"]=="TTF=F"

def test_breadth_rejects_conflicting_numerator_and_percent():
    html="<p>95% of S&P 500 stocks (256 of 497) are above their 200-day moving average</p><p>Last updated: Oct 17, 2026, 12:56 AM UTC</p>"
    try:
        sp500_breadth_daily(html=html)
        assert False, "must reject incompatible counts"
    except ValueError:
        pass

def test_mock_collector_stores_breadth_with_real_timestamp():
    now=datetime.now(timezone.utc)
    row={"value":51.5,"source":"TradingTwoHundred S&P500 above 200d (256/497 stocks)","observed_at":now.isoformat()}
    def fail(_): raise RuntimeError("offline")
    result=collect({},history_provider=fail,fred_provider=fail,cape_provider=fail,breadth_provider=lambda:row,now=now)
    assert result["indicators"]["breadth"]["value"]==51.5
    assert result["composite"]["validated"] is False
