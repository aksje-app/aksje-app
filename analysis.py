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

def get_history(ticker, period="1y"):
    try:
        return yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception:
        return pd.DataFrame()

def get_info(ticker):
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}

def calculate_metrics(hist):
    if hist is None or hist.empty or len(hist) < 60:
        return None

    close = hist["Close"].dropna()
    growth_1y = (close.iloc[-1] - close.iloc[0]) / close.iloc[0]
    momentum_30d = (close.tail(30).iloc[-1] - close.tail(30).iloc[0]) / close.tail(30).iloc[0]
    volatility = close.pct_change().dropna().std()
    ma50 = close.tail(50).mean()
    trend = (close.iloc[-1] - ma50) / ma50 if ma50 else 0

    return {
        "growth_1y": round(float(growth_1y), 4),
        "momentum_30d": round(float(momentum_30d), 4),
        "volatility": round(float(volatility), 4),
        "trend_vs_ma50": round(float(trend), 4),
    }

def calculate_score_from_hist(hist, sentiment=0.5, pe=None):
    metrics = calculate_metrics(hist)
    if not metrics:
        return None, None

    growth_score = clamp(metrics["growth_1y"] * 1.2 + 0.45)
    momentum_score = clamp(metrics["momentum_30d"] * 2.0 + 0.50)
    risk_score = clamp(1 - metrics["volatility"] * 18)
    trend_score = clamp(metrics["trend_vs_ma50"] * 2.0 + 0.50)

    if isinstance(pe, (int, float)) and pe > 0:
        value_score = clamp(1 - (pe / 60))
    else:
        value_score = 0.50

    total = (
        growth_score * 0.26 +
        momentum_score * 0.22 +
        risk_score * 0.18 +
        sentiment * 0.16 +
        trend_score * 0.10 +
        value_score * 0.08
    ) * 10

    return round(float(total), 2), metrics

def score_stock(ticker, use_news=True):
    hist = get_history(ticker)
    if hist.empty:
        return None

    articles, news_error = get_news(ticker.replace(".OL", ""), limit=6) if use_news else ([], None)
    sentiment = simple_finance_sentiment(articles)

    info = get_info(ticker)
    pe = info.get("forwardPE") or info.get("trailingPE")
    score, metrics = calculate_score_from_hist(hist, sentiment=sentiment, pe=pe)
    if score is None:
        return None

    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName") or ticker,
        "score": score,
        "sentiment": sentiment,
        "growth_1y": metrics["growth_1y"],
        "momentum_30d": metrics["momentum_30d"],
        "volatility": metrics["volatility"],
        "trend_vs_ma50": metrics["trend_vs_ma50"],
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
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

def simple_backtest(tickers, lookback_period="2y"):
    rows = []
    for ticker in tickers:
        hist = get_history(ticker, period=lookback_period)
        if hist.empty or len(hist) < 220:
            continue
        close = hist["Close"].dropna()
        ret = (close.iloc[-1] - close.iloc[0]) / close.iloc[0]
        vol = close.pct_change().dropna().std()
        sharpe_like = ret / (vol * (252 ** 0.5)) if vol else 0
        rows.append({
            "Ticker": ticker,
            "Return %": round(ret * 100, 1),
            "Volatility": round(float(vol), 4),
            "Simple Sharpe-ish": round(float(sharpe_like), 2),
        })
    return pd.DataFrame(rows).sort_values("Return %", ascending=False) if rows else pd.DataFrame()
