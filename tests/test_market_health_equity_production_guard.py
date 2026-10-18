from market_health_collector import collect
from datetime import datetime, timezone

def test_production_annual_source_not_disabled_by_auto_created_yahoo_provider(monkeypatch):
    import market_health_shareholder_yield
    from unittest.mock import patch
    row={"value":3.2,"observed_at":"2025-12-31T00:00:00+00:00","source":"NYU Stern annual"}
    calls=[]
    def annual():
        calls.append(True)
        return [row]
    with patch.object(market_health_shareholder_yield,"annual_shareholder_yield",annual),patch("yfinance.Ticker") as ticker:
        ticker.return_value.history.return_value.empty=True
        result=collect({},fred_provider=lambda _:[],cape_provider=lambda:[],breadth_provider=lambda: (_ for _ in ()).throw(ValueError("offline")))
    assert calls
    assert result["indicators"]["equity_yield"]["value"]==3.2
    assert "equity_yield" not in result["collection_status"]["errors"]
