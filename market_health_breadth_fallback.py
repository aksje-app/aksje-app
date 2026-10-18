"""Independent S&P 500 breadth fallback computed from constituent daily closes.

Returns a value only with sufficient coverage and dated prices. No proxy or trading effect.
"""
from datetime import datetime, timezone, timedelta
from io import StringIO
from math import isfinite
from urllib.request import Request, urlopen
import csv

CONSTITUENTS_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"

def compute_sp500_breadth(*, constituents_csv=None, history_provider=None, now=None):
    now = now or datetime.now(timezone.utc)
    if constituents_csv is None:
        with urlopen(Request(CONSTITUENTS_URL, headers={"User-Agent": "MarketHealth/1.0"}), timeout=12) as response:
            constituents_csv = response.read(300000).decode("utf-8-sig")
    reader = csv.DictReader(StringIO(constituents_csv))
    if not reader.fieldnames or "Symbol" not in reader.fieldnames:
        raise ValueError("S&P 500 constituent list missing Symbol")
    tickers = sorted({str(row.get("Symbol", "")).strip().replace(".", "-") for row in reader
                      if row.get("Symbol") and str(row.get("Symbol")).strip()})
    if not 450 <= len(tickers) <= 510:
        raise ValueError(f"S&P 500 constituent list invalid coverage: {len(tickers)}")
    if history_provider is None:
        import yfinance as yf
        def history_provider(batch):
            return yf.download(batch, period="15mo", interval="1d", auto_adjust=True,
                               progress=False, threads=8, group_by="column")
    positives = 0
    valid = 0
    last_dates = []
    for start in range(0, len(tickers), 60):
        batch = tickers[start:start + 60]
        frame = history_provider(batch)
        if frame is None or frame.empty:
            continue
        close = frame["Close"] if "Close" in frame else None
        if close is None:
            continue
        for ticker in batch:
            try:
                series = close[ticker].dropna() if hasattr(close, "columns") else close.dropna()
                if len(series) < 200:
                    continue
                observed = series.index[-1].to_pydatetime()
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
                observed = observed.astimezone(timezone.utc)
                if observed > now + timedelta(days=1) or now - observed > timedelta(days=5):
                    continue
                last = float(series.iloc[-1])
                baseline = float(series.iloc[-200:].mean())
                if not (isfinite(last) and isfinite(baseline) and baseline > 0):
                    continue
                valid += 1
                positives += int(last > baseline)
                last_dates.append(observed)
            except (KeyError, TypeError, ValueError, IndexError, AttributeError):
                continue
    if valid < 400 or valid < .80 * len(tickers):
        raise ValueError(f"Insufficient S&P 500 200-day bars: {valid}/{len(tickers)}")
    # The reported observation must not be more recent than an underlying price.
    observed = min(last_dates)
    if now - observed > timedelta(days=5):
        raise ValueError("Constituent coverage not current")
    return {
        "value": round(100 * positives / valid, 3),
        "observed_at": observed.isoformat(),
        "source": f"Constituent-based S&P500 breadth: {positives}/{valid} above 200-day average; Yahoo adjusted daily closes; {len(tickers)} tickers checked",
    }
