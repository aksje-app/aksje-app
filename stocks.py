from functools import lru_cache
from io import StringIO

import pandas as pd
import requests

US_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "LLY", "JPM",
    "V", "UNH", "XOM", "MA", "COST", "NFLX", "WMT", "HD", "PG", "JNJ",
    "AMD", "CRM", "BAC", "ORCL", "KO", "PEP", "ADBE", "CSCO", "MRK", "ABBV",
    "PLTR", "COIN", "SHOP", "UBER", "SNOW"
]

NORWEGIAN_STOCKS = [
    "EQNR.OL", "DNB.OL", "TEL.OL", "NHY.OL", "ORK.OL",
    "MOWI.OL", "AKRBP.OL", "YAR.OL", "KOG.OL", "TOM.OL",
    "SALM.OL", "GJF.OL", "SUBC.OL", "ATEA.OL", "FRO.OL",
    "NEL.OL", "VAR.OL", "BAKKA.OL", "WAWI.OL", "AUTO.OL",
    "SCHB.OL", "STB.OL", "HAFNI.OL", "BORR.OL", "MPCC.OL",
    "LSG.OL", "ELK.OL", "NAS.OL", "KIT.OL", "XXL.OL"
]

SWEDISH_STOCKS = [
    "VOLV-B.ST", "ERIC-B.ST", "HM-B.ST", "ATCO-A.ST", "ATCO-B.ST",
    "ABB.ST", "SAND.ST", "SEB-A.ST", "SWED-A.ST", "TELIA.ST",
    "SKF-B.ST", "ASSA-B.ST", "INVE-B.ST", "EVO.ST", "SINCH.ST",
    "NDA-SE.ST", "SHB-A.ST", "ALFA.ST", "SAAB-B.ST", "SCA-B.ST",
    "BOL.ST", "ELUX-B.ST", "GETI-B.ST", "KINV-B.ST", "LATO-B.ST",
    "NIBE-B.ST", "SBB-B.ST", "SSAB-A.ST", "THULE.ST", "AZN.ST"
]

@lru_cache(maxsize=8)
def _get_sp500_tickers_cached(limit=150):
    """Fetch S&P 500 with a short timeout and cache it for fast reruns."""
    try:
        response = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            timeout=6,
            headers={"User-Agent": "smart-ai-trading-app/1.0"},
        )
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        df = tables[0]
        tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        return tuple(tickers[:limit])
    except Exception:
        return tuple(US_FALLBACK[:limit])


def get_sp500_tickers(limit=150):
    """Henter S&P 500 automatisk fra Wikipedia. Fallback hvis nettet feiler."""
    return list(_get_sp500_tickers_cached(int(limit or 150)))

def get_norwegian_tickers(limit=None):
    return NORWEGIAN_STOCKS[:limit] if limit else NORWEGIAN_STOCKS

def get_swedish_tickers(limit=None):
    return SWEDISH_STOCKS[:limit] if limit else SWEDISH_STOCKS

def get_all_tickers(limit_per_market=50):
    return (
        get_sp500_tickers(limit_per_market) +
        get_norwegian_tickers(limit_per_market) +
        get_swedish_tickers(limit_per_market)
    )
