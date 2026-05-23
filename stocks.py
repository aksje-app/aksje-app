from functools import lru_cache
from io import StringIO

try:
    import pandas as pd
except Exception:
    pd = None

try:
    import requests
except Exception:
    requests = None

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

FINNISH_STOCKS = [
    "NOKIA.HE", "NESTE.HE", "KNEBV.HE", "SAMPO.HE", "UPM.HE",
    "FORTUM.HE", "WRT1V.HE", "ELISA.HE", "METSO.HE", "VALMT.HE",
    "ORNAV.HE", "ORNBV.HE", "KESKOB.HE", "HUH1V.HE", "KCR.HE",
    "TYRES.HE", "STERV.HE", "OUT1V.HE", "QTCOM.HE", "PUUILO.HE",
    "KOJAMO.HE", "MEKKO.HE", "KEMIRA.HE", "CGCBV.HE", "MANTA.HE"
]

DANISH_STOCKS = [
    "NOVO-B.CO", "MAERSK-B.CO", "DSV.CO", "ORSTED.CO", "CARL-B.CO",
    "PNDORA.CO", "NZYM-B.CO", "VWS.CO", "COLO-B.CO", "GMAB.CO",
    "DANSKE.CO", "TRYG.CO", "ROCK-B.CO", "JYSK.CO", "AMBU-B.CO",
    "DEMANT.CO", "GN.CO", "ISS.CO", "RBREW.CO", "FLS.CO",
    "BAVA.CO", "NETC.CO", "ALK-B.CO", "NKT.CO", "TOP.CO"
]

BRAZILIAN_STOCKS = [
    "PETR4.SA", "VALE3.SA", "ITUB4.SA", "BBDC4.SA", "ABEV3.SA",
    "B3SA3.SA", "WEGE3.SA", "BBAS3.SA", "RENT3.SA", "PRIO3.SA",
    "ITSA4.SA", "ELET3.SA", "SUZB3.SA", "GGBR4.SA", "JBSS3.SA",
    "RAIL3.SA", "LREN3.SA", "HAPV3.SA", "RADL3.SA", "CSNA3.SA",
    "EMBR3.SA", "EQTL3.SA", "CMIG4.SA", "VIVT3.SA", "SBSP3.SA",
    "PETR3.SA", "ITUB3.SA", "BBDC3.SA", "ELET6.SA", "CMIG3.SA",
    "UGPA3.SA", "BRFS3.SA", "KLBN11.SA", "TIMS3.SA", "SANB11.SA",
    "BPAC11.SA", "RDOR3.SA", "YDUQ3.SA", "CPLE6.SA", "CPLE3.SA",
    "BEEF3.SA", "MRFG3.SA", "TOTS3.SA", "CYRE3.SA", "MULT3.SA",
    "BRKM5.SA", "CSAN3.SA", "SLCE3.SA", "VBBR3.SA", "ENEV3.SA",
    "TAEE11.SA", "EGIE3.SA", "CPFE3.SA", "GOAU4.SA", "PSSA3.SA",
    "BBSE3.SA", "ASAI3.SA", "CRFB3.SA", "PCAR3.SA", "HYPE3.SA",
    "NTCO3.SA", "PETZ3.SA", "CASH3.SA", "LWSA3.SA", "MGLU3.SA"
]

@lru_cache(maxsize=8)
def _get_sp500_tickers_cached(limit=150):
    """Fetch S&P 500 with a short timeout and cache it for fast reruns."""
    if pd is None or requests is None:
        return tuple(US_FALLBACK[:limit])
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

def get_finnish_tickers(limit=None):
    return FINNISH_STOCKS[:limit] if limit else FINNISH_STOCKS

def get_danish_tickers(limit=None):
    return DANISH_STOCKS[:limit] if limit else DANISH_STOCKS

def get_brazilian_tickers(limit=None):
    return BRAZILIAN_STOCKS[:limit] if limit else BRAZILIAN_STOCKS

def get_all_tickers(limit_per_market=50):
    return (
        get_sp500_tickers(limit_per_market) +
        get_norwegian_tickers(limit_per_market) +
        get_swedish_tickers(limit_per_market) +
        get_finnish_tickers(limit_per_market) +
        get_danish_tickers(limit_per_market) +
        get_brazilian_tickers(limit_per_market)
    )
