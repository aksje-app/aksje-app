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


def _dedupe(values):
    out, seen = [], set()
    for raw in values:
        ticker = str(raw or "").strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append(ticker)
    return out


US_FALLBACK = _dedupe(US_FALLBACK + [
    "TMO", "ABT", "ACN", "ISRG", "MCD", "GE", "CAT", "QCOM", "TXN", "INTU",
    "AMAT", "NOW", "BKNG", "SPGI", "GS", "RTX", "AXP", "PGR", "LOW", "NEE",
    "HON", "UNP", "BLK", "SYK", "TJX", "ETN", "VRTX", "LMT", "C", "ADP",
    "MDT", "CB", "ADI", "MMC", "DE", "PLD", "PANW", "KLAC", "AMT", "GILD",
    "SBUX", "MU", "FI", "BMY", "SO", "MO", "DUK", "ICE", "SHW", "MCK",
    "WM", "ZTS", "ELV", "EQIX", "APH", "CDNS", "REGN", "CI", "HCA", "SNPS",
    "CL", "ORLY", "PH", "CMG", "USB", "MCO", "GD", "EOG", "MAR", "AON",
    "NOC", "PNC", "ITW", "TDG", "APD", "MSI", "FDX", "ECL", "EMR", "ROP",
    "TGT", "PYPL", "FCX", "SLB", "CME", "NXPI", "MPC", "PSX", "AFL", "BDX",
    "CSX", "NSC", "GM", "F", "NKE", "LRCX", "MRVL", "WDAY", "TEAM", "DDOG",
])

NORWEGIAN_STOCKS = _dedupe(NORWEGIAN_STOCKS + [
    "AFG.OL", "AKAST.OL", "AKER.OL", "AKSO.OL", "AKH.OL", "ACC.OL", "ADE.OL",
    "AUSS.OL", "BELCO.OL", "BWLPG.OL", "CADLR.OL", "CRAYN.OL", "DOFG.OL",
    "ENTRA.OL", "EPR.OL", "FLNG.OL", "GOGL.OL", "GSF.OL", "HAVI.OL",
    "HBC.OL", "KID.OL", "LINK.OL", "MING.OL", "MOBA.OL", "NAPA.OL",
    "NOD.OL", "NORAM.OL", "NORBT.OL", "NRC.OL", "NSKOG.OL", "ODL.OL", "OLT.OL",
    "OTL.OL", "PEXIP.OL", "PROT.OL", "RECSI.OL", "SAGA.OL", "SATS.OL",
    "SCATC.OL", "SCHA.OL", "SNI.OL", "SOFF.OL", "SPOL.OL", "SRBNK.OL",
    "VEI.OL", "VISTN.OL", "WSTEP.OL", "WWI.OL", "ZAL.OL", "ZAP.OL", "ACR.OL",
])

SWEDISH_STOCKS = _dedupe(SWEDISH_STOCKS + [
    "INVE-A.ST", "AZA.ST", "BALD-B.ST", "BEIJ-B.ST", "BILL.ST", "CAST.ST",
    "DOM.ST", "EMBRAC-B.ST", "EPI-A.ST", "EPI-B.ST", "ESSITY-B.ST",
    "FABG.ST", "HEXA-B.ST", "HOLM-B.ST", "HUSQ-B.ST", "INDU-C.ST",
    "LIFCO-B.ST", "LUND-B.ST", "LUMI.ST", "MTRS.ST", "MYCR.ST", "PEAB-B.ST",
    "SECU-B.ST", "SOBI.ST", "TEL2-B.ST", "TREL-B.ST", "VITR.ST", "WIHL.ST",
    "ALIV-SDB.ST", "ARJO-B.ST", "BICO.ST", "BIOT.ST", "CATE.ST", "DUNI.ST",
    "EQT.ST", "FING-B.ST", "FOI-B.ST", "HMS.ST", "INTRUM.ST", "JM.ST",
    "LOOMIS.ST", "MIPS.ST", "NCC-B.ST", "NP3.ST", "RATO-B.ST", "SECT-B.ST",
    "SKA-B.ST", "STE-R.ST", "SWEC-B.ST", "VBG-B.ST", "VNV.ST",
])

FINNISH_STOCKS = _dedupe(FINNISH_STOCKS + [
    "AKTIA.HE", "ALMA.HE", "ANORA.HE", "ATRAV.HE", "BIOBV.HE", "CAPMAN.HE",
    "CTY1S.HE", "DIGIA.HE", "ENENTO.HE", "FIA1S.HE", "FSKRS.HE", "GOFORE.HE",
    "HARVIA.HE", "ICP1V.HE", "KEMPOWR.HE", "LEHTO.HE", "METSA.HE",
    "MUSTI.HE", "NOHO.HE", "OKDAV.HE", "OMASP.HE", "PON1V.HE", "RAIVV.HE",
    "REG1V.HE", "REMEDY.HE", "ROVIO.HE", "SCANFL.HE", "SSABAH.HE",
    "TIETO.HE", "TOKMAN.HE", "UPONOR.HE", "VAIAS.HE", "VERK.HE", "WETTERI.HE",
])

DANISH_STOCKS = _dedupe(DANISH_STOCKS + [
    "MAERSK-A.CO", "ALMB.CO", "BO.CO", "DFDS.CO", "DRLCO.CO", "FLUG-B.CO",
    "GUBRA.CO", "HUSCO.CO", "MATAS.CO", "MT-B.CO", "NTG.CO", "RIAS-B.CO",
    "SCHOU.CO", "SOLAR-B.CO", "SPNO.CO", "SYDB.CO", "TORM.CO", "UIE.CO",
    "ZEAL.CO", "AOJ-B.CO", "CBRAIN.CO", "CHEMM.CO", "DAB.CO", "DJUR.CO",
    "FASTPC.CO", "HH.CO", "KRE.CO", "LASP.CO", "LUXOR-B.CO", "MONSO.CO",
    "NORTHM.CO", "PARKEN.CO", "RILBA.CO", "RTX.CO", "SKAKO.CO", "TRIFOR.CO",
    "VJBA.CO", "AGILC.CO", "AQUA.CO", "GREENM.CO", "HARB-B.CO", "HOVE.CO",
    "KONSOL.CO", "LEDIBOND.CO", "MAPS.CO", "MTHH.CO", "NORD.CO", "NTR-B.CO",
    "ORDERYOYO.CO", "ORPHA.CO", "PAAL-B.CO", "PENNEO.CO", "RISMA.CO",
])

BRAZILIAN_STOCKS = _dedupe(BRAZILIAN_STOCKS + [
    "ALOS3.SA", "ALPA4.SA", "ARZZ3.SA", "AZUL4.SA", "BHIA3.SA", "BRAP4.SA",
    "BRAV3.SA", "CCRO3.SA", "CEAB3.SA", "CIEL3.SA", "COGN3.SA", "CPLE11.SA",
    "DXCO3.SA", "ECOR3.SA", "ENAT3.SA", "EZTC3.SA", "FLRY3.SA", "GFSA3.SA",
    "IGTI11.SA", "IRBR3.SA", "LJQQ3.SA", "MRVE3.SA", "QUAL3.SA", "RECV3.SA",
    "SMTO3.SA", "SOMA3.SA", "TEND3.SA", "TRPL4.SA", "USIM5.SA", "VAMO3.SA",
    "VIVA3.SA", "VULC3.SA",
])

TICKER_NAME_ALIASES = {
    "AAPL": ["Apple", "Apple Inc"],
    "MSFT": ["Microsoft", "Microsoft Corp"],
    "NVDA": ["NVIDIA", "NVIDIA Corp"],
    "AMZN": ["Amazon", "Amazon.com", "Amazon.com Inc"],
    "META": ["Meta Platforms", "Meta Platforms Inc"],
    "GOOGL": ["Alphabet", "Alphabet Inc", "Google"],
    "GOOG": ["Alphabet", "Alphabet Inc", "Google"],
    "AVGO": ["Broadcom", "Broadcom Inc"],
    "TSLA": ["Tesla", "Tesla Inc"],
    "LLY": ["Eli Lilly", "Eli Lilly and Co"],
    "JPM": ["JPMorgan Chase", "JPMorgan Chase & Co"],
    "V": ["Visa", "Visa Inc"],
    "UNH": ["UnitedHealth", "UnitedHealth Group"],
    "XOM": ["Exxon Mobil", "Exxon Mobil Corp"],
    "MA": ["Mastercard", "Mastercard Inc"],
    "COST": ["Costco", "Costco Wholesale"],
    "NFLX": ["Netflix", "Netflix Inc"],
    "WMT": ["Walmart", "Walmart Inc"],
    "HD": ["Home Depot", "The Home Depot"],
    "PG": ["Procter & Gamble", "Procter and Gamble"],
    "JNJ": ["Johnson & Johnson", "Johnson and Johnson"],
    "AMD": ["Advanced Micro Devices", "AMD"],
    "CRM": ["Salesforce", "Salesforce Inc"],
    "BAC": ["Bank of America", "Bank of America Corp"],
    "ORCL": ["Oracle", "Oracle Corp"],
    "KO": ["Coca-Cola", "The Coca-Cola Co"],
    "PEP": ["PepsiCo", "PepsiCo Inc"],
    "ADBE": ["Adobe", "Adobe Inc"],
    "CSCO": ["Cisco", "Cisco Systems"],
    "MRK": ["Merck", "Merck & Co"],
    "ABBV": ["AbbVie", "AbbVie Inc"],
    "CAT": ["Caterpillar", "Caterpillar Inc"],
    "SLB": ["SLB", "SLB Ltd", "Schlumberger"],
    "EQNR.OL": ["Equinor"],
    "DNB.OL": ["DNB Bank", "DNB Bank ASA"],
    "NHY.OL": ["Norsk Hydro"],
    "TEL.OL": ["Telenor"],
    "ORK.OL": ["Orkla"],
    "MOWI.OL": ["Mowi"],
    "AKRBP.OL": ["Aker BP"],
    "YAR.OL": ["Yara International"],
    "KOG.OL": ["Kongsberg Gruppen"],
    "TOM.OL": ["Tomra Systems"],
    "SALM.OL": ["SalMar"],
    "GJF.OL": ["Gjensidige Forsikring"],
    "SUBC.OL": ["Subsea 7"],
    "FRO.OL": ["Frontline"],
    "STB.OL": ["Storebrand"],
    "LSG.OL": ["Leroy Seafood", "Lerøy Seafood"],
    "ELK.OL": ["Elkem"],
    "NAS.OL": ["Norwegian Air Shuttle"],
    "NORBT.OL": ["NORBIT", "Norbit ASA"],
    "AFG.OL": ["AF Gruppen"],
    "ZAP.OL": ["Zaptec"],
    "ACR.OL": ["Axactor"],
    "VOLV-B.ST": ["Volvo AB"],
    "VOLV-A.ST": ["Volvo AB"],
    "ERIC-B.ST": ["Telefonaktiebolaget LM Ericsson", "Ericsson"],
    "HM-B.ST": ["H & M Hennes & Mauritz", "Hennes & Mauritz"],
    "ATCO-A.ST": ["Atlas Copco"],
    "ATCO-B.ST": ["Atlas Copco"],
    "ABB.ST": ["ABB Ltd"],
    "SAND.ST": ["Sandvik"],
    "SEB-A.ST": ["Skandinaviska Enskilda Banken", "SEB"],
    "SWED-A.ST": ["Swedbank"],
    "TELIA.ST": ["Telia Co", "Telia Company"],
    "SKF-B.ST": ["SKF AB"],
    "ASSA-B.ST": ["Assa Abloy"],
    "INVE-B.ST": ["Investor AB"],
    "INVE-A.ST": ["Investor AB"],
    "EVO.ST": ["Evolution AB"],
    "SAAB-B.ST": ["Saab AB"],
    "NIBE-B.ST": ["NIBE Industrier"],
    "NOKIA.HE": ["Nokia Oyj"],
    "NESTE.HE": ["Neste Oyj"],
    "KNEBV.HE": ["Kone Oyj"],
    "SAMPO.HE": ["Sampo Oyj"],
    "UPM.HE": ["UPM-Kymmene"],
    "FORTUM.HE": ["Fortum"],
    "WRT1V.HE": ["Wartsila", "Wärtsilä"],
    "ELISA.HE": ["Elisa Oyj"],
    "METSO.HE": ["Metso"],
    "VALMT.HE": ["Valmet"],
    "KESKOB.HE": ["Kesko"],
    "TYRES.HE": ["Nokian Renkaat"],
    "NOVO-B.CO": ["Novo Nordisk"],
    "MAERSK-B.CO": ["AP Moller - Maersk", "A.P. Moller - Maersk", "Maersk"],
    "MAERSK-A.CO": ["AP Moller - Maersk", "A.P. Moller - Maersk", "Maersk"],
    "DSV.CO": ["DSV"],
    "ORSTED.CO": ["Orsted", "Ørsted"],
    "CARL-B.CO": ["Carlsberg"],
    "PNDORA.CO": ["Pandora"],
    "NZYM-B.CO": ["Novozymes"],
    "VWS.CO": ["Vestas Wind Systems", "Vestas"],
    "COLO-B.CO": ["Coloplast"],
    "GMAB.CO": ["Genmab"],
    "DANSKE.CO": ["Danske Bank"],
    "TRYG.CO": ["Tryg"],
    "ROCK-B.CO": ["Rockwool"],
    "AMBU-B.CO": ["Ambu"],
    "DEMANT.CO": ["Demant"],
    "GN.CO": ["GN Store Nord"],
    "ISS.CO": ["ISS"],
    "RBREW.CO": ["Royal Unibrew"],
    "FLS.CO": ["FLSmidth"],
    "BAVA.CO": ["Bavarian Nordic"],
    "ALK-B.CO": ["ALK-Abello", "ALK-Abelló"],
    "NKT.CO": ["NKT"],
    "TOP.CO": ["Topdanmark"],
    "PETR4.SA": ["Petroleo Brasileiro", "Petrobras"],
    "PETR3.SA": ["Petroleo Brasileiro", "Petrobras"],
    "VALE3.SA": ["Vale SA"],
    "ITUB4.SA": ["Itau Unibanco", "Itaú Unibanco"],
    "BBDC4.SA": ["Banco Bradesco"],
    "ABEV3.SA": ["Ambev"],
    "B3SA3.SA": ["B3 SA"],
    "WEGE3.SA": ["WEG SA"],
    "BBAS3.SA": ["Banco do Brasil"],
    "RENT3.SA": ["Localiza"],
    "PRIO3.SA": ["PRIO SA", "Petro Rio"],
}


def get_ticker_name_aliases():
    aliases = {ticker: list(TICKER_NAME_ALIASES.get(ticker, [])) for ticker in get_all_tickers(limit_per_market=250)}
    for ticker in list(aliases):
        root = ticker.split(".", 1)[0].replace("-", " ")
        if root and root not in aliases[ticker]:
            aliases[ticker].append(root)
    return aliases


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
