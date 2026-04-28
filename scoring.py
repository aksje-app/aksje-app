import numpy as np
import pandas as pd

def clamp(x, low=0, high=1):
    try:
        if x is None or np.isnan(x):
            return 0.5
        return max(low, min(high, x))
    except Exception:
        return 0.5

def pct_change(hist, days=None):
    if hist is None or hist.empty or len(hist) < 2:
        return 0
    close = hist["Close"].dropna()
    if days and len(close) > days:
        close = close.tail(days)
    if len(close) < 2 or close.iloc[0] == 0:
        return 0
    return (close.iloc[-1] - close.iloc[0]) / close.iloc[0]

def volatility(hist):
    if hist is None or hist.empty:
        return 0.04
    returns = hist["Close"].pct_change().dropna()
    if returns.empty:
        return 0.04
    return float(returns.std())

def max_drawdown(hist):
    if hist is None or hist.empty:
        return 0
    close = hist["Close"].dropna()
    peak = close.cummax()
    dd = (close - peak) / peak
    return float(dd.min())

def score_stock(hist, sentiment=0.5, fundamentals=None):
    fundamentals = fundamentals or {}
    growth_1y = pct_change(hist)
    momentum_3m = pct_change(hist, 63)
    vol = volatility(hist)
    dd = max_drawdown(hist)

    growth_score = clamp((growth_1y + 0.15) / 0.60)
    momentum_score = clamp((momentum_3m + 0.05) / 0.30)
    risk_score = clamp(1 - (vol / 0.045))
    drawdown_score = clamp(1 + dd)  # dd is negative

    pe = fundamentals.get("pe")
    rev_growth = fundamentals.get("revenue_growth")
    margins = fundamentals.get("profit_margins")

    pe_score = 0.5 if not pe or pe <= 0 else clamp(1 - ((pe - 15) / 70))
    rev_score = 0.5 if rev_growth is None else clamp((rev_growth + 0.05) / 0.35)
    margin_score = 0.5 if margins is None else clamp((margins + 0.05) / 0.35)
    fundamental_score = (pe_score * 0.35 + rev_score * 0.4 + margin_score * 0.25)

    final = (
        growth_score * 0.24 +
        momentum_score * 0.20 +
        risk_score * 0.16 +
        drawdown_score * 0.08 +
        sentiment * 0.14 +
        fundamental_score * 0.18
    ) * 10

    return {
        "score": round(float(final), 2),
        "growth_1y": float(growth_1y),
        "momentum_3m": float(momentum_3m),
        "volatility": float(vol),
        "drawdown": float(dd),
        "sentiment": float(sentiment),
        "fundamental_score": round(float(fundamental_score), 3),
        "risk_score": round(float(risk_score), 3),
    }
