"""Bounded live evidence retrieval for observational valuation screens."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import subprocess
import sys
from pathlib import Path
import time


def _annual_values(frame: Any, labels: tuple[str, ...]) -> list[float]:
    if frame is None or getattr(frame, "empty", True):
        return []
    for label in labels:
        if label in frame.index:
            values: list[float] = []
            for value in frame.loc[label].tolist():
                try:
                    number = float(value)
                    if number == number and abs(number) != float("inf"):
                        values.append(number)
                except (TypeError, ValueError):
                    pass
            return values
    return []


def _dated_values(frame: Any, labels: tuple[str, ...]) -> dict[str, float]:
    """Preserve fiscal dates so missing years cannot shift ROCE components."""
    if frame is None or getattr(frame, "empty", True):
        return {}
    for label in labels:
        if label not in frame.index:
            continue
        result = {}
        for date, value in frame.loc[label].items():
            try:
                number = float(value)
                if number == number and abs(number) != float("inf"):
                    result[str(date.date() if hasattr(date, "date") else date)[:10]] = number
            except (ValueError, TypeError):
                continue
        return result
    return {}


def live_financial_snapshot(ticker: str) -> dict[str, Any]:
    """Provider may fail or omit fields; caller must never invent missing EPS/ROCE.

    Yahoo Finance is a screening source, not a verified exchange filing. Users
    must check annual accounts before acting on any scenario price.
    """
    import yfinance as yf

    security = yf.Ticker(ticker)
    warnings: list[str] = []
    try:
        info = security.info or {}
    except Exception:
        info = {}
        warnings.append("Yahoo info utilgjengelig")
    try:
        annual = security.income_stmt
    except Exception:
        annual = None
        warnings.append("Resultatregnskap utilgjengelig")
    try:
        balance = security.balance_sheet
    except Exception:
        balance = None
        warnings.append("Balanse utilgjengelig")
    eps_by_year = _dated_values(annual, ("Diluted EPS", "Basic EPS"))
    ebit = _dated_values(annual, ("EBIT", "Operating Income"))
    assets = _dated_values(balance, ("Total Assets",))
    current_liabilities = _dated_values(balance, ("Current Liabilities", "Total Current Liabilities"))
    eps = [eps_by_year[year] for year in sorted(eps_by_year, reverse=True)][:5]
    roce_history = [ebit[year] / (assets[year] - current_liabilities[year])
                    for year in sorted(ebit.keys() & assets.keys() & current_liabilities.keys(), reverse=True)
                    if assets[year] > current_liabilities[year]][:5]
    sector = str(info.get("sector") or "")
    financial = [frame for frame in (annual, balance) if frame is not None and not getattr(frame, "empty", True)]
    period = max((year for year in ebit.keys() & assets.keys() & current_liabilities.keys()), default="") if len(financial) == 2 else ""
    # ROCE is not comparable for banks/insurers; never reinterpret ROE as ROCE.
    is_financial = "Financial" in sector or "Bank" in sector or "Insurance" in sector
    roce = roce_history[0] if not is_financial and roce_history else None
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not price:
        try:
            fast = security.fast_info
            price = fast.get("lastPrice") if fast else None
        except Exception:
            warnings.append("Fast kurs utilgjengelig")
    return {
        "ticker": ticker, "price": price, "trailing_eps": info.get("trailingEps"),
        "forward_eps": info.get("forwardEps"), "annual_eps": eps,
        "financial_date": period, "free_cash_flow": info.get("freeCashflow"),
        "roce": roce, "roce_history": [] if is_financial else roce_history[:5],
        "name": info.get("longName") or info.get("shortName") or ticker,
        "country": info.get("country"), "currency": info.get("currency"),
        "industry": info.get("industry") or sector,
        "source": "Yahoo Finance: aksjekurs, selskapets regnskap og nøkkeltall",
        "provider_warnings": warnings,
        "provider_partial": bool(warnings),
    }


def memory_budget_ok() -> bool:
    from runtime_memory import memory_snapshot
    snapshot = memory_snapshot()
    limit = float(snapshot.get("cgroup_memory_limit_mb") or 0)
    current = float(snapshot.get("cgroup_memory_current_mb") or snapshot.get("process_rss_mb") or 0)
    return not limit or current + 160 < limit


def isolated_financial_snapshot(ticker: str) -> dict[str, Any]:
    """Kill stalled providers and release memory between ticker fetches."""
    child = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("quality_valuation_worker.py")), ticker],
        cwd=str(Path(__file__).parent), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=15, check=False,
    )
    if child.returncode or len(child.stdout) > 32768:
        raise RuntimeError("Markedsdatakilde utilgjengelig")
    data = json.loads(child.stdout)
    if not isinstance(data, dict):
        raise ValueError("Ugyldige markedsdata")
    return data


PROXY_SYMBOLS = {"Brent": "BZ=F", "Kobber": "HG=F", "Gull": "GC=F"}
_PROXY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def live_proxy_snapshot(symbol: str) -> dict[str, Any]:
    """Daily futures proxy, not a company's contract or realized sales price."""
    import yfinance as yf
    prices = yf.Ticker(symbol).history(period="4mo", interval="1d", auto_adjust=True)
    if prices is None or getattr(prices, "empty", True):
        raise ValueError("Ingen markedskurser")
    close = [float(value) for value in prices["Close"].dropna().tolist()]
    if len(close) < 23 or close[-1] <= 0:
        raise ValueError("For kort prishistorikk")
    observed = prices.index[-1]
    return {"symbol": symbol, "last_price": round(close[-1], 3),
            "one_month_pct": round((close[-1] / close[-22] - 1) * 100, 2),
            "three_month_pct": round((close[-1] / close[-64] - 1) * 100, 2) if len(close) > 63 else None,
            "price_date": str(observed.date() if hasattr(observed, "date") else observed)[:10],
            "source": "Yahoo Finance futuresproxy, forsinket dagskurs"}


def observed_driver_prices(names: list[str]) -> dict[str, dict[str, Any]]:
    """At most three killable calls; unmapped regional prices remain missing."""
    result: dict[str, dict[str, Any]] = {}
    for name in dict.fromkeys(names):
        if name not in PROXY_SYMBOLS or len(result) >= 3:
            continue
        cached = _PROXY_CACHE.get(name)
        if cached and time.monotonic() - cached[0] < 6 * 3600:
            result[name] = dict(cached[1])
            continue
        child = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("quality_valuation_worker.py")), "--proxy", PROXY_SYMBOLS[name]],
            cwd=str(Path(__file__).parent), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=12, check=False,
        )
        if child.returncode or len(child.stdout) > 4096:
            result[name] = {"state": "MISSING", "reason": "Ingen bekreftet proxypris"}
            continue
        try:
            data = json.loads(child.stdout)
            if isinstance(data, dict) and data.get("last_price"):
                result[name] = data
                _PROXY_CACHE[name] = (time.monotonic(), data)
        except (ValueError, TypeError):
            result[name] = {"state": "MISSING", "reason": "Ugyldig kursgrunnlag"}
    return result
