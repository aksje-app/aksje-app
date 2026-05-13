"""Security metadata resolver.

v18.5.72: One shared resolver for ticker -> display name, sector and risk.
This is intentionally lightweight/offline first so picker tables do not show
NAVN=ticker, SEKTOR=Unknown, RISIKO=Ukjent when common metadata is available.
Live/API data can still override these fallbacks through normal row fields.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping
import re

APP_SECURITY_METADATA_VERSION = "v18.5.73"

_STOCKS: Dict[str, Dict[str, str]] = {
    "AAPL": {"name": "Apple Inc.", "sector": "Technology", "risk": "Lav"},
    "MSFT": {"name": "Microsoft Corporation", "sector": "Technology", "risk": "Lav"},
    "NVDA": {"name": "NVIDIA Corporation", "sector": "Technology", "risk": "Middels"},
    "AMZN": {"name": "Amazon.com, Inc.", "sector": "Consumer", "risk": "Middels"},
    "META": {"name": "Meta Platforms, Inc.", "sector": "Communication", "risk": "Middels"},
    "GOOGL": {"name": "Alphabet Inc.", "sector": "Communication", "risk": "Lav"},
    "GOOG": {"name": "Alphabet Inc.", "sector": "Communication", "risk": "Lav"},
    "AVGO": {"name": "Broadcom Inc.", "sector": "Technology", "risk": "Middels"},
    "TSLA": {"name": "Tesla, Inc.", "sector": "Consumer", "risk": "Høy"},
    "LLY": {"name": "Eli Lilly and Company", "sector": "Healthcare", "risk": "Middels"},
    "JPM": {"name": "JPMorgan Chase & Co.", "sector": "Financials", "risk": "Lav"},
    "V": {"name": "Visa Inc.", "sector": "Financials", "risk": "Lav"},
    "UNH": {"name": "UnitedHealth Group Incorporated", "sector": "Healthcare", "risk": "Middels"},
    "NFLX": {"name": "Netflix, Inc.", "sector": "Communication", "risk": "Middels"},
    "MA": {"name": "Mastercard Incorporated", "sector": "Financials", "risk": "Lav"},
    "XOM": {"name": "Exxon Mobil Corporation", "sector": "Energy", "risk": "Middels"},
    "COST": {"name": "Costco Wholesale Corporation", "sector": "Consumer", "risk": "Lav"},
    "ORCL": {"name": "Oracle Corporation", "sector": "Technology", "risk": "Middels"},
    "WMT": {"name": "Walmart Inc.", "sector": "Consumer", "risk": "Lav"},
    "HD": {"name": "The Home Depot, Inc.", "sector": "Consumer", "risk": "Middels"},
    "PG": {"name": "Procter & Gamble Company", "sector": "Consumer", "risk": "Lav"},
    "AMD": {"name": "Advanced Micro Devices, Inc.", "sector": "Technology", "risk": "Høy"},
    "EQNR.OL": {"name": "Equinor ASA", "sector": "Energy", "risk": "Middels"},
    "DNB.OL": {"name": "DNB Bank ASA", "sector": "Financials", "risk": "Lav"},
    "STB.OL": {"name": "Storebrand ASA", "sector": "Financials", "risk": "Middels"},
    "NHY.OL": {"name": "Norsk Hydro ASA", "sector": "Materials", "risk": "Middels"},
    "YAR.OL": {"name": "Yara International ASA", "sector": "Materials", "risk": "Middels"},
    "NOVO-B.CO": {"name": "Novo Nordisk A/S", "sector": "Healthcare", "risk": "Middels"},
    "VOLV-B.ST": {"name": "Volvo AB B", "sector": "Industrials", "risk": "Middels"},
    "ERIC-B.ST": {"name": "Ericsson B", "sector": "Communication", "risk": "Middels"},
    "ABB.ST": {"name": "ABB Ltd", "sector": "Industrials", "risk": "Middels"},
    "ATCO-A.ST": {"name": "Atlas Copco AB A", "sector": "Industrials", "risk": "Lav"},
}

_FUNDS: Dict[str, Dict[str, str]] = {
    "SHYG": {"name": "iShares 0-5 Year High Yield Corporate Bond ETF", "sector": "High yield credit", "risk": "Høy"},
    "USHY": {"name": "iShares Broad USD High Yield Corporate Bond ETF", "sector": "High yield credit", "risk": "Høy"},
    "SJNK": {"name": "SPDR Bloomberg Short Term High Yield Bond ETF", "sector": "High yield credit", "risk": "Høy"},
    "FALN": {"name": "iShares Fallen Angels USD Bond ETF", "sector": "High yield credit", "risk": "Høy"},
    "ANGL": {"name": "VanEck Fallen Angel High Yield Bond ETF", "sector": "High yield credit", "risk": "Høy"},
    "BKLN": {"name": "Invesco Senior Loan ETF", "sector": "Senior loans", "risk": "Høy"},
    "JNK": {"name": "SPDR Bloomberg High Yield Bond ETF", "sector": "High yield credit", "risk": "Høy"},
    "HYG": {"name": "iShares iBoxx $ High Yield Corporate Bond ETF", "sector": "High yield credit", "risk": "Høy"},
    "BND": {"name": "Vanguard Total Bond Market ETF", "sector": "Investment grade bonds", "risk": "Middels"},
    "TLT": {"name": "iShares 20+ Year Treasury Bond ETF", "sector": "Treasury bonds", "risk": "Middels"},
    "SHY": {"name": "iShares 1-3 Year Treasury Bond ETF", "sector": "Treasury bonds", "risk": "Lav"},
    "VOO": {"name": "Vanguard S&P 500 ETF", "sector": "Broad equity", "risk": "Middels"},
    "SPY": {"name": "SPDR S&P 500 ETF Trust", "sector": "Broad equity", "risk": "Middels"},
    "QQQ": {"name": "Invesco QQQ Trust", "sector": "Technology growth", "risk": "Middels"},
    "ARKK": {"name": "ARK Innovation ETF", "sector": "Innovation growth", "risk": "Høy"},
    "HYLB": {"name": "Xtrackers USD High Yield Corporate Bond ETF", "sector": "High yield credit", "risk": "Høy"},
    "LQD": {"name": "iShares iBoxx $ Investment Grade Corporate Bond ETF", "sector": "Investment grade bonds", "risk": "Middels"},
    "IEF": {"name": "iShares 7-10 Year Treasury Bond ETF", "sector": "Treasury bonds", "risk": "Middels"},
    "AGG": {"name": "iShares Core U.S. Aggregate Bond ETF", "sector": "Investment grade bonds", "risk": "Middels"},
    "BSV": {"name": "Vanguard Short-Term Bond ETF", "sector": "Investment grade bonds", "risk": "Lav"},
    "VCIT": {"name": "Vanguard Intermediate-Term Corporate Bond ETF", "sector": "Investment grade bonds", "risk": "Middels"},
    "KRAFT_HIGH_YIELD_D": {"name": "Kraft High Yield D", "sector": "Norwegian high yield credit", "risk": "Høy"},
    "SGOV": {"name": "iShares 0-3 Month Treasury Bond ETF", "sector": "Money market", "risk": "Lav"},
    "BIL": {"name": "SPDR Bloomberg 1-3 Month T-Bill ETF", "sector": "Money market", "risk": "Lav"},
    "SHV": {"name": "iShares Short Treasury Bond ETF", "sector": "Money market", "risk": "Lav"},
    "ICSH": {"name": "iShares Ultra Short-Term Bond ETF", "sector": "Money market", "risk": "Lav"},
    "MINT": {"name": "PIMCO Enhanced Short Maturity Active ETF", "sector": "Money market", "risk": "Lav"},
    "JPST": {"name": "JPMorgan Ultra-Short Income ETF", "sector": "Money market", "risk": "Lav"},
}

_BAD_NAME_VALUES = {"", "UNKNOWN", "UKJENT", "N/A", "NA", "NONE", "NULL", "-"}


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _compact(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def is_weak_name(name: Any, symbol: Any) -> bool:
    n = str(name or "").strip()
    s = normalize_symbol(symbol)
    if n.upper() in _BAD_NAME_VALUES:
        return True
    return _compact(n) == _compact(s)


def _source_meta(symbol: str) -> Dict[str, str]:
    return dict(_STOCKS.get(symbol) or _FUNDS.get(symbol) or {})


def resolve_security_metadata(symbol: Any, row: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    row = row or {}
    sym = normalize_symbol(row.get("ticker") or row.get("symbol") or row.get("Symbol") or symbol)
    meta = _source_meta(sym)

    name = ""
    for key in ("fund_name", "fundName", "longName", "companyName", "shortName", "displayName", "name", "Navn", "NAVN"):
        val = str(row.get(key) or "").strip()
        if val and not is_weak_name(val, sym):
            name = val
            break
    if not name:
        name = meta.get("name", "")

    sector = ""
    for key in ("sector", "Sector", "industry", "Industry"):
        val = str(row.get(key) or "").strip()
        if val and val not in {"Unknown", "Ukjent"}:
            sector = val
            break
    if not sector:
        sector = meta.get("sector", "Unknown")

    risk = str(row.get("risk") or row.get("risk_label") or "").strip()
    if not risk or risk in {"Unknown", "Ukjent"}:
        risk = meta.get("risk", "Ukjent")

    out = dict(row)
    out.update({
        "ticker": sym,
        "symbol": sym,
        "name": name or sym,
        "longName": name or sym,
        "display_label": f"{sym} — {name}" if sym and name and not is_weak_name(name, sym) else sym,
        "sector": sector,
        "risk": risk,
        "metadata_version": APP_SECURITY_METADATA_VERSION,
    })
    return out


def fund_display_label(symbol: Any, row: Mapping[str, Any] | None = None) -> str:
    """Return consistent fund label: TICKER — Fund name when known."""
    meta = resolve_security_metadata(symbol, row)
    sym = normalize_symbol(meta.get("symbol") or symbol)
    name = str(meta.get("name") or "").strip()
    if sym and name and not is_weak_name(name, sym):
        return f"{sym} — {name}"
    return sym or name or "-"


def display_label(symbol: Any, row: Mapping[str, Any] | None = None) -> str:
    return str(resolve_security_metadata(symbol, row).get("display_label") or normalize_symbol(symbol))


def enrich_security_rows(rows: Any) -> Any:
    if not isinstance(rows, list):
        return rows
    out = []
    for row in rows:
        if isinstance(row, Mapping):
            out.append(resolve_security_metadata(row.get("ticker") or row.get("symbol"), row))
        else:
            sym = normalize_symbol(row)
            out.append(resolve_security_metadata(sym, {"ticker": sym}))
    return out
