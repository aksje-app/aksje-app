import math
import pandas as pd
import yfinance as yf
from news import get_news, simple_finance_sentiment

def clamp(x, low=0.0, high=1.0):
    try:
        if x is None or math.isnan(float(x)):
            return 0.5
        return max(low, min(high, float(x)))
    except Exception:
        return 0.5

def get_history(ticker, period="2y"):
    try:
        return yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception:
        return pd.DataFrame()

def get_info(ticker):
    try:
        return yf.Ticker(ticker).info or {}
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

def score_from_metrics(metrics, sentiment=0.5, pe=None, profit_margin=None, revenue_growth=None, debt_to_equity=None):
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

    return round(float(total), 2), {k: round(float(v), 3) for k, v in parts.items()}

def score_stock(ticker, use_news=True):
    hist = get_history(ticker, period="2y")
    metrics = calculate_metrics(hist)
    if not metrics:
        return None

    articles, news_error = get_news(ticker.replace(".OL", ""), limit=6, source="score_stock") if use_news else ([], None)
    sentiment = simple_finance_sentiment(articles)

    info = get_info(ticker)
    pe = info.get("forwardPE") or info.get("trailingPE")
    score, parts = score_from_metrics(
        metrics,
        sentiment=sentiment,
        pe=pe,
        profit_margin=info.get("profitMargins"),
        revenue_growth=info.get("revenueGrowth"),
        debt_to_equity=info.get("debtToEquity"),
    )
    if score is None:
        return None

    return {
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
        "articles": articles,
        "news_error": news_error,
        "hist": hist,
    }

def rank_stocks(tickers, max_count=25, use_news=True):
    results = []
    for ticker in tickers[:max_count]:
        item = score_stock(ticker, use_news=use_news)
        if item:
            results.append(item)
    return sorted(results, key=lambda x: x["score"], reverse=True)
