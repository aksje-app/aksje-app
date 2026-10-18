"""Point-in-time S&P 500 breadth backfill; offline and read-only.

Historical membership is necessary but never sufficient: unavailable or delisted
ticker histories must not be substituted by today's surviving constituents.
The caller supplies daily adjusted closes and archived membership CSV.
"""
from __future__ import annotations
from csv import DictReader
from datetime import date
from io import StringIO
from math import isfinite

def parse_membership_csv(csv_text):
    rows=[]
    for row in DictReader(StringIO(csv_text)):
        day=date.fromisoformat(str(row["date"]).strip())
        tickers={s.strip().replace(".", "-") for s in str(row["tickers"]).split(",") if s.strip()}
        if not 450 <= len(tickers) <= 510:
            continue
        rows.append((day,tickers))
    rows.sort(key=lambda x:x[0])
    return rows

def historical_breadth(memberships, adjusted_close_by_ticker, *, minimum_coverage=.8, min_constituents=400):
    """Returns only genuinely measurable session observations.

    adjusted_close_by_ticker[ticker][day] is an adjusted close from that day.
    200 observations up to the requested day are required; 200d averages
    include the current close, matching the production breadth convention.
    """
    if not 0.8 <= minimum_coverage <= 1:
        raise ValueError("coverage threshold must be at least 80%")
    results=[]
    for day, members in memberships:
        above=covered=0
        for ticker in members:
            prices=adjusted_close_by_ticker.get(ticker,{})
            if day not in prices:
                continue
            previous=sorted(d for d in prices if d<=day)
            if len(previous)<200:
                continue
            values=[float(prices[d]) for d in previous[-200:]]
            if not all(isfinite(x) and x>0 for x in values):
                continue
            covered+=1
            above+=int(values[-1] > sum(values)/200)
        if covered < min_constituents or covered < minimum_coverage*len(members):
            continue
        results.append({"observed_at":day.isoformat()+"T00:00:00+00:00",
                        "value":round(100*above/covered,3),
                        "source":f"Point-in-time S&P500 members and 200 adjusted daily closes ({above}/{covered}; {len(members)} members)"})
    return results
