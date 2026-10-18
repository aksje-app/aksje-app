"""Annual shareholder payout yield from university-published S&P 500 data."""
from datetime import datetime, timezone
from math import isfinite
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

URL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/spearn.html"

def annual_shareholder_yield(html=None):
    if html is None:
        request = Request(URL, headers={"User-Agent":"Mozilla/5.0"})
        with urlopen(request, timeout=15) as response:
            html=response.read(1200000).decode("utf-8","replace")
    rows=[]
    for tr in BeautifulSoup(html,"html.parser").select("tr"):
        parts=[c.get_text(" ",strip=True).replace(",","") for c in tr.find_all(["td","th"])]
        if len(parts)<8: continue
        try:
            year=int(parts[0])
            sp500=float(parts[3])
            payout=float(parts[7])
            percent=100*payout/sp500
            if not(2001<=year<=datetime.now(timezone.utc).year and sp500>100 and
                   0<payout<sp500 and isfinite(percent) and percent<20):
                continue
            stamp=datetime(year,12,31,tzinfo=timezone.utc)
            rows.append({"value":round(percent,5),"observed_at":stamp.isoformat(),
                         "source":"NYU Stern Damodaran S&P 500 distributions (dividends + buybacks)/index; annual, latest year may include estimates"})
        except (ValueError,TypeError,ZeroDivisionError):
            continue
    records=sorted({r["observed_at"]:r for r in rows}.values(),key=lambda r:r["observed_at"])
    if len(records)<12: raise ValueError("Need 12 actual annual published distributions")
    return records[-96:]
