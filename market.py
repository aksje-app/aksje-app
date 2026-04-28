import pandas as pd
import yfinance as yf

DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]

def get_sp500_tickers(limit=50):
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        return tickers[:limit]
    except Exception:
        return DEFAULT_TICKERS

def get_history(ticker, period="1y"):
    try:
        return yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception:
        return pd.DataFrame()

def get_info(ticker):
    try:
        info = yf.Ticker(ticker).get_info()
        return {
            "name": info.get("shortName") or info.get("longName") or ticker,
            "sector": info.get("sector", "Ukjent"),
            "pe": info.get("trailingPE"),
            "market_cap": info.get("marketCap"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margins": info.get("profitMargins"),
        }
    except Exception:
        return {"name": ticker, "sector": "Ukjent", "pe": None, "market_cap": None, "revenue_growth": None, "profit_margins": None}
