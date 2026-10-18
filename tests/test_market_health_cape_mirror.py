from datetime import datetime,timezone
from market_health_collector import shiller_cape_mirror

def test_cape_mirror_parses_monthly_table_and_source():
    rows=[]
    for year in (2024,2025):
        for month in range(1,13):
            dt=datetime(year,month,1,tzinfo=timezone.utc)
            rows.append(f'<tr><td>{dt.strftime("%b %d, %Y")}</td><td>{30+month/10:.2f}</td></tr>')
    data=shiller_cape_mirror(html="<table>"+"".join(rows)+"</table>")
    assert len(data)==24
    assert data[-1]["value"]==31.2
    assert "secondary source" in data[-1]["source"]

def test_cape_mirror_rejects_missing_or_malformed_rows():
    try:
        shiller_cape_mirror(html="<table><tr><td>not-a-date</td><td>0</td></tr></table>")
        assert False
    except ValueError as exc:
        assert "fewer than 12" in str(exc)
