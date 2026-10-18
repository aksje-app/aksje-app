"""Bounded market-health observation collector; no trades, scores or alerts.

Free daily bar feeds are explicitly labelled as daily, not intraday quotes.
Provider failures preserve prior evidence and are reported in status.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen
from csv import DictReader
from io import StringIO, BytesIO
from math import isfinite
from market_health_history import normalize
from market_health_ui import INDICATORS

FRED_SERIES = {"curve": "T10Y2Y", "credit": "BAMLH0A0HYM2"}


def fred_daily(series_id):
    """Public FRED CSV daily history; use date at UTC midnight, no invented quote time."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series_id + "&cosd=" + (datetime.now(timezone.utc) - timedelta(days=110)).date().isoformat()
    with urlopen(url, timeout=12) as response:
        payload = response.read(600000).decode("utf-8-sig")
    observations = []
    for row in DictReader(StringIO(payload)):
        raw = str(row.get(series_id) or "").strip()
        date = row.get("DATE") or row.get("observation_date")
        try:
            value = float(raw)
            at = datetime.fromisoformat(str(date)).replace(tzinfo=timezone.utc)
            if isfinite(value):
                observations.append({"value": value, "source": f"FRED daily series {series_id}", "observed_at": at.isoformat()})
        except (ValueError, TypeError):
            continue
    if not observations:
        raise ValueError("FRED series has no valid observations")
    return observations[-96:]



def shiller_cape_monthly():
    """Download Shiller's monthly CAPE series. The original workbook is the authority."""
    import pandas as pd
    source_url = "https://www.econ.yale.edu/~shiller/data/ie_data.xls"
    with urlopen(source_url, timeout=15) as response:
        workbook = response.read(4000000)
    frame = pd.read_excel(BytesIO(workbook), sheet_name=0, header=7)
    frame.columns = [str(c).strip().upper() for c in frame.columns]
    if "DATE" not in frame or "CAPE" not in frame:
        raise ValueError("Shiller workbook DATE/CAPE columns not found")
    records = []
    for _, row in frame.iterrows():
        try:
            date_code = f"{float(row['DATE']):.2f}"
            year_text, month_text = date_code.split(".")
            year, month = int(year_text), int(month_text)
            value = float(row["CAPE"])
            if not (1871 <= year <= datetime.now(timezone.utc).year and
                    1 <= month <= 12 and isfinite(value) and value > 0):
                continue
            observed = datetime(year, month, 1, tzinfo=timezone.utc)
            records.append({"value": value, "source": "Robert Shiller Yale monthly CAPE (ie_data.xls)",
                            "observed_at": observed.isoformat()})
        except (ValueError, TypeError, OverflowError):
            continue
    if not records:
        raise ValueError("Shiller workbook contains no valid CAPE observations")
    return sorted(records, key=lambda r: r["observed_at"])[-96:]


def shiller_cape_mirror(*, html=None):
    """Secondary monthly CAPE data when Yale host refuses connections."""
    from bs4 import BeautifulSoup
    from urllib.request import Request
    if html is None:
        req = Request("https://www.multpl.com/shiller-pe/table/by-month",
                      headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=12) as response:
            html = response.read(1200000).decode("utf-8", "replace")
    monthly = {}
    for tr in BeautifulSoup(html, "html.parser").select("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        try:
            date = datetime.strptime(cells[0].get_text(" ", strip=True), "%b %d, %Y").replace(tzinfo=timezone.utc)
            value = float(cells[1].get_text(" ", strip=True).replace(",", ""))
            if not (1871 <= date.year <= datetime.now(timezone.utc).year and
                    isfinite(value) and 0 < value < 200):
                continue
            k = (date.year, date.month)
            if k not in monthly or date > monthly[k][0]:
                monthly[k] = (date, value)
        except (ValueError, TypeError):
            continue
    if len(monthly) < 12:
        raise ValueError("Secondary CAPE source has fewer than 12 valid monthly observations")
    return [{"observed_at": date.isoformat(), "value": value,
             "source": "Multpl Shiller CAPE monthly table (secondary source)"}
            for date, value in sorted(monthly.values())[-96:]]


SYMBOLS = {"vix": "^VIX", "us10y": "^TNX", "us30y": "^TYX",
           "brent": "BZ=F", "gold": "GC=F", "dxy": "DX-Y.NYB",
           "eurusd": "EURUSD=X", "trend": "^GSPC"}


def collect(snapshot=None, *, history_provider=None, fred_provider=None, cape_provider=None, now=None):
    now = now or datetime.now(timezone.utc)
    saved = dict(snapshot or {})
    previous = saved.get("indicators") or {}
    previous = previous if isinstance(previous, dict) else {}
    result = dict(previous)
    errors = {}
    if history_provider is None:
        import yfinance as yf
        history_provider = lambda symbol: yf.Ticker(symbol).history(period="1y" if symbol == "^GSPC" else "35d", interval="1d", auto_adjust=False)
    for key, symbol in SYMBOLS.items():
        try:
            frame = history_provider(symbol)
            if frame is None or frame.empty:
                raise ValueError("empty daily price history")
            if "Close" not in frame:
                raise ValueError("missing Close")
            series = frame["Close"].dropna()
            if series.empty:
                raise ValueError("no finite closing price")
            last_time = series.index[-1]
            if getattr(last_time, "tzinfo", None) is None:
                raise ValueError("unqualified timestamp")
            observed = last_time.to_pydatetime().astimezone(timezone.utc)
            value = float(series.iloc[-1])
            # Yahoo ^TNX/^TYX responses observed in production are already percent yields.
            # Do not divide a percent yield by ten without an independently verified unit contract.
            if key == "trend":
                if len(series) < 200:
                    raise ValueError("200-day baseline unavailable")
                avg = float(series.iloc[-200:].mean())
                if avg <= 0:
                    raise ValueError("invalid 200-day baseline")
                value = (value / avg - 1.0) * 100.0
            row = {"value": value, "source": f"Yahoo Finance daily observation ({symbol})",
                   "observed_at": observed.isoformat()}
            checked = normalize(key, row, now=now)
            if not checked:
                raise ValueError("invalid dated observation")
            old = result.get(key) or {}
            historical = list(old.get("observations") or []) if isinstance(old, dict) else []
            closes = series if key != "trend" else (series / series.rolling(200).mean() - 1.0) * 100.0
            for time_index, close in closes.iloc[-96:].items():
                if getattr(time_index, "tzinfo", None) is None:
                    continue
                stamp = time_index.to_pydatetime().astimezone(timezone.utc)
                numeric = float(close)
                if not (isfinite(numeric) and stamp <= now + timedelta(seconds=60)):
                    continue
                historical.append({"value": numeric, "source": row["source"],
                                   "observed_at": stamp.isoformat()})
            by_date = {o["observed_at"]: o for o in historical
                       if isinstance(o, dict) and o.get("observed_at") and
                       isfinite(float(o.get("value", float("nan"))))}
            observations = sorted(by_date.values(), key=lambda o: o["observed_at"])[-96:]
            result[key] = {**row, "observations": observations}
        except Exception as exc:
            errors[key] = str(exc)[:180]
    fred_provider = fred_provider or fred_daily
    for key, series_id in FRED_SERIES.items():
        try:
            records = fred_provider(series_id)
            row = records[-1]
            if not normalize(key, row, now=now):
                raise ValueError("invalid FRED date/source")
            old = result.get(key) or {}
            combined = list(old.get("observations") or []) if isinstance(old, dict) else []
            unique = {r["observed_at"]: r for r in combined + records if isinstance(r, dict) and r.get("observed_at")}
            result[key] = {**row, "observations": sorted(unique.values(), key=lambda r: r["observed_at"])[-96:]}
        except Exception as exc:
            errors[key] = str(exc)[:180]
    try:
        if cape_provider is not None:
            cape_records = cape_provider()
        else:
            try:
                cape_records = shiller_cape_monthly()
            except Exception:
                cape_records = shiller_cape_mirror()
        cape_row = cape_records[-1]
        if not normalize("cape", cape_row, now=now):
            raise ValueError("invalid Shiller CAPE source or timestamp")
        result["cape"] = {**cape_row, "observations": cape_records[-96:]}
    except Exception as exc:
        errors["cape"] = str(exc)[:180]
    return {"indicators": result, "composite": {"validated": False},
            "collection_status": {"at": now.isoformat(), "updated": [k for k in (*SYMBOLS, *FRED_SERIES, "cape") if k in result and k not in errors],
                                  "errors": errors, "cadence": "4h poll / daily bar publication",
                                  "mode": "READ_ONLY", "history_schema": 2}}
