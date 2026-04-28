import pandas as pd

US_FALLBACK = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMZN", "META", "AVGO", "JPM", "LLY"]

NORWEGIAN_STOCKS = [
    "EQNR.OL", "DNB.OL", "TEL.OL", "NHY.OL", "ORK.OL",
    "MOWI.OL", "AKRBP.OL", "YAR.OL", "KOG.OL", "TOM.OL",
    "SALM.OL", "GJF.OL", "SUBC.OL", "ATEA.OL", "FRO.OL",
    "NEL.OL", "VAR.OL", "BAKKA.OL", "WAWI.OL", "AUTO.OL",
    "SCHB.OL", "STB.OL", "HAFNI.OL", "BORR.OL", "MPCC.OL",
]

def get_sp500_tickers(limit=50):
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        df = tables[0]
        tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        return tickers[:limit]
    except Exception:
        return US_FALLBACK[:limit]

def get_norwegian_tickers():
    return NORWEGIAN_STOCKS
