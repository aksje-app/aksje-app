from datetime import datetime, timezone
from market_health_shareholder_yield import annual_shareholder_yield
from market_health_history import normalize

def test_annual_payout_yield_uses_dividends_plus_buybacks_not_earnings():
    rows=[]
    for year in range(2011,2026):
        rows.append(f"<tr><td>{year}</td><td>5%</td><td>1%</td><td>1000</td><td>50</td><td>10</td><td>20%</td><td>30</td><td>60%</td></tr>")
    result=annual_shareholder_yield("<table>"+"".join(rows)+"</table>")
    assert len(result)==15
    assert result[-1]["value"]==3.
    assert result[-1]["observed_at"]=="2025-12-31T00:00:00+00:00"
    assert "annual" in result[-1]["source"]
    assert normalize("equity_yield",result[-1],now=datetime(2026,10,18,tzinfo=timezone.utc))["status"]=="CURRENT"

def test_unverifiable_distribution_table_is_rejected():
    try:
        annual_shareholder_yield("<table><tr><td>2025</td><td>BAD</td></tr></table>")
        assert False
    except ValueError:
        pass
