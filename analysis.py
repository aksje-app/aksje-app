import math
import os
import time
from typing import Any, Dict, Mapping, Optional, Sequence

import pandas as pd
import yfinance as yf
from alpha_radar_currency import market_cap_fields
from news import get_news, simple_finance_sentiment

FAST_CACHE_TTL_SECONDS = int(os.getenv("APP_SCORE_FAST_CACHE_TTL_SECONDS", "900") or 900)
INSIDER_SCORE_MAX_ADJUSTMENT = float(os.getenv("APP_INSIDER_SCORE_MAX_ADJUSTMENT", "0.6") or 0.6)
INSIDER_RANKING_LIMIT = int(os.getenv("APP_INSIDER_RANKING_LIMIT", "12") or 12)

_HISTORY_CACHE: Dict[tuple, tuple[float, pd.DataFrame]] = {}
_INFO_CACHE: Dict[str, tuple[float, dict]] = {}
_INSIDER_CACHE: Dict[str, tuple[float, dict]] = {}

def clamp(x, low=0.0, high=1.0):
    try:
        if x is None or math.isnan(float(x)):
            return 0.5
        return max(low, min(high, float(x)))
    except Exception:
        return 0.5

def _fresh(cache_row):
    try:
        ts, value = cache_row
        return (time.time() - float(ts)) <= FAST_CACHE_TTL_SECONDS, value
    except Exception:
        return False, None

def get_history(ticker, period="2y"):
    key = (str(ticker).upper(), str(period))
    ok, cached = _fresh(_HISTORY_CACHE.get(key))
    if ok:
        return cached.copy()
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if hist is not None and not hist.empty:
            _HISTORY_CACHE[key] = (time.time(), hist.copy())
        return hist
    except Exception:
        return pd.DataFrame()

def get_histories(tickers: Sequence[str], period="2y") -> Dict[str, pd.DataFrame]:
    clean = []
    seen = set()
    for raw in tickers or []:
        ticker = str(raw or "").strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            clean.append(ticker)
    out: Dict[str, pd.DataFrame] = {}
    missing = []
    for ticker in clean:
        key = (ticker, str(period))
        ok, cached = _fresh(_HISTORY_CACHE.get(key))
        if ok:
            out[ticker] = cached.copy()
        else:
            missing.append(ticker)
    if not missing:
        return out
    try:
        raw = yf.download(
            tickers=missing,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=True,
            group_by="ticker",
        )
        for ticker in missing:
            hist = pd.DataFrame()
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    if ticker in raw.columns.get_level_values(0):
                        hist = raw[ticker].dropna(how="all")
                    elif ticker in raw.columns.get_level_values(-1):
                        hist = raw.xs(ticker, axis=1, level=-1).dropna(how="all")
                else:
                    hist = raw.dropna(how="all")
            except Exception:
                hist = pd.DataFrame()
            if hist is not None and not hist.empty:
                _HISTORY_CACHE[(ticker, str(period))] = (time.time(), hist.copy())
                out[ticker] = hist
    except Exception:
        pass
    for ticker in missing:
        if ticker not in out:
            hist = get_history(ticker, period=period)
            if hist is not None and not hist.empty:
                out[ticker] = hist
    return out

def get_info(ticker):
    key = str(ticker or "").strip().upper()
    ok, cached = _fresh(_INFO_CACHE.get(key))
    if ok:
        return dict(cached or {})
    try:
        info = yf.Ticker(ticker).info or {}
        _INFO_CACHE[key] = (time.time(), dict(info or {}))
        return info
    except Exception:
        return {}

def calc_return(close, days):
    if len(close) <= days:
        return 0.0
    return float((close.iloc[-1] - close.iloc[-days]) / close.iloc[-days])

def calculate_metrics(hist):
    if hist is None or hist.empty or len(hist) < 120:
        return None

    close = hist["Close"].dropna()
    volume = hist["Volume"].dropna() if "Volume" in hist else pd.Series(dtype=float)

    ret_1y = calc_return(close, min(252, len(close)-1))
    ret_6m = calc_return(close, min(126, len(close)-1))
    ret_3m = calc_return(close, min(63, len(close)-1))
    ret_1m = calc_return(close, min(21, len(close)-1))

    daily = close.pct_change().dropna()
    volatility = float(daily.std())
    downside = daily[daily < 0]
    downside_vol = float(downside.std()) if len(downside) else volatility

    ma50 = close.tail(50).mean()
    ma200 = close.tail(min(200, len(close))).mean()
    trend_50 = float((close.iloc[-1] - ma50) / ma50) if ma50 else 0
    trend_200 = float((close.iloc[-1] - ma200) / ma200) if ma200 else 0

    peak = close.cummax()
    drawdown = ((close - peak) / peak).min()

    vol_trend = 0.5
    if len(volume) >= 60:
        recent_vol = volume.tail(20).mean()
        old_vol = volume.tail(60).head(40).mean()
        if old_vol:
            vol_trend = clamp((recent_vol / old_vol - 1) * 0.5 + 0.5)

    return {
        "ret_1y": round(ret_1y, 4),
        "ret_6m": round(ret_6m, 4),
        "ret_3m": round(ret_3m, 4),
        "ret_1m": round(ret_1m, 4),
        "volatility": round(volatility, 4),
        "downside_vol": round(downside_vol, 4),
        "trend_50": round(trend_50, 4),
        "trend_200": round(trend_200, 4),
        "max_drawdown": round(float(drawdown), 4),
        "volume_trend_score": round(float(vol_trend), 3),
    }

def _safe_number(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default

def _normalize_insider_score(insider) -> Optional[float]:
    if insider is None:
        return None
    if isinstance(insider, Mapping):
        value = insider.get("score")
    else:
        value = insider
    score = _safe_number(value, None)
    if score is None:
        return None
    if score > 1 and score <= 100:
        score = score / 100.0
    if score > 10:
        score = score / 100.0
    elif score > 1:
        score = score / 10.0
    return clamp(score)

def _insider_adjustment(insider_score: Optional[float]) -> float:
    if insider_score is None:
        return 0.0
    return round((float(insider_score) - 0.5) * (INSIDER_SCORE_MAX_ADJUSTMENT * 2.0), 3)

def get_cached_insider_signal(ticker, provider=None, ttl_seconds=6 * 60 * 60):
    key = str(ticker or "").strip().upper()
    row = _INSIDER_CACHE.get(key)
    try:
        if row and (time.time() - float(row[0])) <= ttl_seconds:
            return dict(row[1] or {})
    except Exception:
        pass
    try:
        if provider is None:
            from insider import get_insider_data as provider
        data = provider(key)
        if isinstance(data, Mapping):
            data = dict(data)
        else:
            data = {"score": data}
    except Exception as exc:
        data = {"score": 0.5, "label": "Ingen insiderdata", "error": str(exc)}
    _INSIDER_CACHE[key] = (time.time(), dict(data or {}))
    return dict(data or {})

def apply_insider_adjustment(item: Optional[Mapping[str, Any]], insider=None, insider_provider=None) -> Optional[dict]:
    if not item:
        return None
    row = dict(item)
    ticker = str(row.get("ticker") or "").strip().upper()
    if insider is None and ticker:
        insider = get_cached_insider_signal(ticker, provider=insider_provider)
    insider_score = _normalize_insider_score(insider)
    if insider_score is None:
        insider_score = 0.5
    adjustment = _insider_adjustment(insider_score)
    base_score = _safe_number(row.get("score"), 0.0) or 0.0
    row["base_score_before_insider"] = round(base_score, 2)
    row["score"] = round(max(0.0, min(10.0, base_score + adjustment)), 2)
    row["insider_score"] = round(float(insider_score), 3)
    row["insider_adjustment"] = adjustment
    if isinstance(insider, Mapping):
        row["insider_label"] = insider.get("label") or insider.get("direction") or "Insiderdata"
        row["insider_transactions"] = insider.get("transactions")
        row["insider_latest_type"] = insider.get("latest_type")
        row["insider_latest_date"] = insider.get("latest_date")
        row["insider_error"] = insider.get("error")
    parts = dict(row.get("score_parts") or {})
    parts["insider"] = round(float(insider_score), 3)
    row["score_parts"] = parts
    return row

def score_from_metrics(metrics, sentiment=0.5, pe=None, profit_margin=None, revenue_growth=None, debt_to_equity=None, insider_score=None):
    if not metrics:
        return None, {}

    momentum_score = clamp(metrics["ret_6m"] * 0.9 + metrics["ret_3m"] * 1.2 + metrics["ret_1m"] * 0.8 + 0.45)
    trend_score = clamp(metrics["trend_50"] * 1.2 + metrics["trend_200"] * 0.8 + 0.50)
    risk_score = clamp(1 - metrics["volatility"] * 14 - abs(min(metrics["max_drawdown"], 0)) * 0.55)
    downside_score = clamp(1 - metrics["downside_vol"] * 18)

    if isinstance(pe, (int, float)) and pe > 0:
        value_score = clamp(1 - (pe / 55))
    else:
        value_score = 0.50

    if isinstance(profit_margin, (int, float)):
        quality_score = clamp(profit_margin * 2.5 + 0.45)
    else:
        quality_score = 0.50

    if isinstance(revenue_growth, (int, float)):
        fundamental_growth_score = clamp(revenue_growth * 2.0 + 0.45)
    else:
        fundamental_growth_score = 0.50

    if isinstance(debt_to_equity, (int, float)):
        debt_score = clamp(1 - debt_to_equity / 250)
    else:
        debt_score = 0.50

    volume_score = metrics.get("volume_trend_score", 0.5)

    normalized_insider = _normalize_insider_score(insider_score)
    insider_adjustment = _insider_adjustment(normalized_insider)

    parts = {
        "momentum": momentum_score,
        "trend": trend_score,
        "risk": risk_score,
        "downside": downside_score,
        "value": value_score,
        "quality": quality_score,
        "fundamental_growth": fundamental_growth_score,
        "debt": debt_score,
        "volume": volume_score,
        "sentiment": sentiment,
        "insider": 0.5 if normalized_insider is None else normalized_insider,
    }

    total = (
        momentum_score * 0.20 +
        trend_score * 0.13 +
        risk_score * 0.14 +
        downside_score * 0.08 +
        value_score * 0.09 +
        quality_score * 0.10 +
        fundamental_growth_score * 0.10 +
        debt_score * 0.05 +
        volume_score * 0.04 +
        sentiment * 0.07
    ) * 10
    total = max(0.0, min(10.0, total + insider_adjustment))

    return round(float(total), 2), {k: round(float(v), 3) for k, v in parts.items()}

def score_stock(ticker, use_news=True, include_insider=False, insider_provider=None, hist=None, info=None):
    hist = hist if hist is not None else get_history(ticker, period="2y")
    metrics = calculate_metrics(hist)
    if not metrics:
        return None

    articles, news_error = get_news(ticker.replace(".OL", ""), limit=6, source="score_stock") if use_news else ([], None)
    sentiment = simple_finance_sentiment(articles)

    info = dict(info or get_info(ticker) or {})
    pe = info.get("forwardPE") or info.get("trailingPE")
    insider = get_cached_insider_signal(ticker, provider=insider_provider) if include_insider else None
    insider_score = _normalize_insider_score(insider)
    score, parts = score_from_metrics(
        metrics,
        sentiment=sentiment,
        pe=pe,
        profit_margin=info.get("profitMargins"),
        revenue_growth=info.get("revenueGrowth"),
        debt_to_equity=info.get("debtToEquity"),
        insider_score=insider_score,
    )
    if score is None:
        return None

    item = {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName") or ticker,
        "score": score,
        "score_parts": parts,
        "sentiment": sentiment,
        "ret_1y": metrics["ret_1y"],
        "ret_6m": metrics["ret_6m"],
        "ret_3m": metrics["ret_3m"],
        "ret_1m": metrics["ret_1m"],
        "volatility": metrics["volatility"],
        "max_drawdown": metrics["max_drawdown"],
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "profit_margin": info.get("profitMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "debt_to_equity": info.get("debtToEquity"),
        "market_cap": info.get("marketCap"),
        "market_cap_currency": info.get("currency") or info.get("financialCurrency"),
        "articles": articles,
        "news_error": news_error,
        "hist": hist,
    }
    item.update(market_cap_fields(ticker, item))
    if include_insider:
        item["insider_score"] = round(float(insider_score if insider_score is not None else 0.5), 3)
        item["insider_adjustment"] = _insider_adjustment(insider_score)
        if isinstance(insider, Mapping):
            item["insider_label"] = insider.get("label") or "Insiderdata"
            item["insider_transactions"] = insider.get("transactions")
            item["insider_latest_type"] = insider.get("latest_type")
            item["insider_latest_date"] = insider.get("latest_date")
            item["insider_error"] = insider.get("error")
    return item

def rank_stocks(tickers, max_count=25, use_news=True, include_insider=False, insider_limit=None, use_batch=True):
    results = []
    selected = [str(t or "").strip().upper() for t in (tickers or []) if str(t or "").strip()][:max_count]
    histories = get_histories(selected, period="2y") if use_batch and selected else {}
    for ticker in selected:
        item = score_stock(ticker, use_news=use_news, include_insider=False, hist=histories.get(ticker))
        if item:
            results.append(item)
    results = sorted(results, key=lambda x: x["score"], reverse=True)
    if include_insider and results:
        limit = INSIDER_RANKING_LIMIT if insider_limit is None else int(insider_limit or 0)
        limit = max(0, min(limit, len(results)))
        enriched = []
        for idx, item in enumerate(results):
            if idx < limit:
                enriched.append(apply_insider_adjustment(item) or item)
            else:
                enriched.append(item)
        results = enriched
    return sorted(results, key=lambda x: x["score"], reverse=True)
