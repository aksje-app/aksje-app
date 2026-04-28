from __future__ import annotations

import pandas as pd
import yfinance as yf


def get_sp500_tickers() -> list[str]:
    """Fetch current S&P 500 tickers from Wikipedia.

    Yahoo Finance uses '-' instead of '.' for some tickers, e.g. BRK.B -> BRK-B.
    """
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        df = tables[0]
        tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        return sorted(tickers)
    except Exception as e:
        print("Kunne ikke hente S&P 500-listen:", e)
        return ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]


def get_price_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period, auto_adjust=True)
        return hist.dropna()
    except Exception as e:
        print(f"Kunne ikke hente data for {ticker}:", e)
        return pd.DataFrame()


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def calculate_components(hist: pd.DataFrame, sentiment: float = 0.5) -> dict | None:
    if hist.empty or "Close" not in hist or len(hist) < 40:
        return None

    close = hist["Close"]
    growth = (close.iloc[-1] - close.iloc[0]) / close.iloc[0]
    momentum = (close.tail(30).iloc[-1] - close.tail(30).iloc[0]) / close.tail(30).iloc[0]
    volatility = close.pct_change().dropna().std()

    growth_score = clamp(growth * 2)
    momentum_score = clamp(momentum * 3)
    risk_score = 1 - clamp(volatility * 5)
    sentiment_score = clamp(sentiment)

    final_score = (
        growth_score * 0.40
        + momentum_score * 0.20
        + risk_score * 0.20
        + sentiment_score * 0.20
    ) * 10

    return {
        "growth": growth,
        "momentum": momentum,
        "volatility": volatility,
        "growth_score": growth_score,
        "momentum_score": momentum_score,
        "risk_score": risk_score,
        "sentiment": sentiment_score,
        "score": round(final_score, 2),
    }
