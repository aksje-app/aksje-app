"""
fund_etf_analyzer.py

v18.5.43 Fund / ETF Analyzer with hardened Fund Decision Quality.

Pure helper layer for analysing funds and ETFs with a fund-specific decision
quality model. The module has no Streamlit dependency and does not fetch data by
itself; the UI passes data providers only when the user presses run.
"""

from __future__ import annotations
from utils import _safe_float, _now_iso, _clamp as _raw_clamp  # v18.6.3 centralized helpers

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app_version import get_app_version
from security_metadata import resolve_security_metadata, fund_display_label
from market_universe import BASE_MARKET_SCOPES, NORDIC_MARKET_SCOPES, market_scope_options


FundDataProvider = Callable[[str], Optional[Mapping[str, Any]]]
BenchmarkProvider = Callable[[str], Optional[Mapping[str, Any]]]
ProgressCallback = Callable[[Mapping[str, Any]], None]
StopCallback = Callable[[], bool]


def _clamp(value: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp fund scores, preserving older 0-100 shorthand used in this module."""
    return _raw_clamp(value, lo, hi)


FUND_TYPE_OPTIONS = [
    "Alle",
    "Indeksfond",
    "Aktivt fond",
    "ETF",
    "Rente-/obligasjonsfond",
    "High yield-fond",
    "Pengemarkedsfond",
    "Kombinasjonsfond",
    "Fond",
]

FIXED_INCOME_TYPES = {"Rente-/obligasjonsfond", "High yield-fond", "Pengemarkedsfond"}
DEFENSIVE_FIXED_INCOME_TYPES = {"Rente-/obligasjonsfond", "Pengemarkedsfond"}
HIGH_YIELD_TYPES = {"High yield-fond"}


FUND_TEST_MODE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "Rask": {
        "tests": ["Fondstype", "Kostnad", "Avkastning", "Risiko", "Datakvalitet"],
        "description": "Rask screening av kostnad, avkastning og risiko.",
        "api_multiplier": 1.0,
    },
    "Normal": {
        "tests": ["Fondstype", "Kostnad", "Avkastning", "Risiko", "Maks drawdown", "Benchmark", "Fondskvalitet", "Datakvalitet"],
        "description": "Anbefalt modus med benchmark og fondskvalitet.",
        "api_multiplier": 1.25,
    },
    "Grundig": {
        "tests": ["Fondstype", "Kostnad", "Avkastning", "Risiko", "Maks drawdown", "Benchmark", "Aktiv merverdi", "Fondskvalitet", "Forklaring", "Datakvalitet"],
        "description": "Grundigere vurdering med aktiv-vs-indeks og forklaring.",
        "api_multiplier": 1.55,
    },
}

OBJECTIVE_WEIGHTS = {
    "Balansert": {"cost": 0.22, "return": 0.20, "risk": 0.20, "benchmark": 0.18, "data": 0.12, "fit": 0.08},
    "Lav kostnad": {"cost": 0.38, "return": 0.14, "risk": 0.18, "benchmark": 0.14, "data": 0.10, "fit": 0.06},
    "Lav risiko": {"cost": 0.20, "return": 0.14, "risk": 0.34, "benchmark": 0.14, "data": 0.10, "fit": 0.08},
    "Best historikk": {"cost": 0.16, "return": 0.34, "risk": 0.18, "benchmark": 0.16, "data": 0.10, "fit": 0.06},
    "Grunnmur": {"cost": 0.30, "return": 0.16, "risk": 0.22, "benchmark": 0.12, "data": 0.10, "fit": 0.10},
}


# v18.5.39: Small curated starter universes. These are intentionally transparent
# and can be replaced by richer broker/fund feeds later. They use Yahoo symbols
# where possible and never fetch data until the user presses Run.
FUND_SELECTION_SOURCES = [
    "Manuell liste",
    "Auto-univers",
    "Auto indeksfond",
    "Auto ETF",
    "Auto aktive fond",
    "Auto rente-/obligasjonsfond",
    "Auto high yield-fond",
    "Auto pengemarkedsfond",
    "Alle / balansert miks",
]

FUND_EXTRA_MARKETS = ["Europa/UCITS"]
FUND_MARKET_OPTIONS = ["Alle"] + BASE_MARKET_SCOPES + ["Norden"] + FUND_EXTRA_MARKETS

FUND_UNIVERSES: Dict[str, List[Dict[str, str]]] = {
    "Indeksfond": [
        {"symbol": "VOO", "type": "ETF", "bucket": "USA bred indeks", "reason": "billig bred S&P 500-eksponering"},
        {"symbol": "VTI", "type": "ETF", "bucket": "USA totalmarked", "reason": "bred totalmarkedseksponering"},
        {"symbol": "ACWI", "type": "ETF", "bucket": "Global indeks", "reason": "global aksjeeksponering"},
        {"symbol": "VT", "type": "ETF", "bucket": "Global totalmarked", "reason": "globalt bredt aksjefond"},
        {"symbol": "VEA", "type": "ETF", "bucket": "Utviklede markeder", "reason": "eksponering utenfor USA"},
        {"symbol": "EEM", "type": "ETF", "bucket": "Emerging markets", "reason": "fremvoksende markeder"},
        {"symbol": "IEFA", "type": "ETF", "bucket": "Internasjonal indeks", "reason": "bred ikke-USA indeks"},
        {"symbol": "IUSQ.DE", "type": "ETF", "bucket": "Global UCITS", "reason": "global UCITS-lignende kandidat"},
        {"symbol": "SXR8.DE", "type": "ETF", "bucket": "S&P 500 UCITS", "reason": "europeisk S&P 500-kandidat"},
        {"symbol": "EUNL.DE", "type": "ETF", "bucket": "MSCI World UCITS", "reason": "bred world-kandidat"},
    ],
    "ETF": [
        {"symbol": "SPY", "type": "ETF", "bucket": "S&P 500", "reason": "stor og likvid benchmark-ETF"},
        {"symbol": "VOO", "type": "ETF", "bucket": "S&P 500", "reason": "lavkost S&P 500"},
        {"symbol": "VTI", "type": "ETF", "bucket": "USA totalmarked", "reason": "bred USA-eksponering"},
        {"symbol": "QQQ", "type": "ETF", "bucket": "Teknologi/vekst", "reason": "Nasdaq 100 / vekstprofil"},
        {"symbol": "ACWI", "type": "ETF", "bucket": "Global", "reason": "global aksjeeksponering"},
        {"symbol": "IWM", "type": "ETF", "bucket": "Small cap", "reason": "small-cap diversifisering"},
        {"symbol": "DIA", "type": "ETF", "bucket": "Dow", "reason": "stor verdi/blue-chip eksponering"},
        {"symbol": "EFA", "type": "ETF", "bucket": "Utviklede markeder", "reason": "ikke-USA utviklede markeder"},
        {"symbol": "EEM", "type": "ETF", "bucket": "Emerging markets", "reason": "fremvoksende markeder"},
        {"symbol": "XLK", "type": "ETF", "bucket": "Sektor teknologi", "reason": "sektor-satellitt teknologi"},
        {"symbol": "XLF", "type": "ETF", "bucket": "Sektor finans", "reason": "sektor-satellitt finans"},
        {"symbol": "XLV", "type": "ETF", "bucket": "Sektor helse", "reason": "defensiv/sektor helse"},
        {"symbol": "NORW", "type": "ETF", "bucket": "Norge ETF", "reason": "Norge-eksponering via ETF", "markets": ["Norge", "Norden"]},
        {"symbol": "EWD", "type": "ETF", "bucket": "Sverige ETF", "reason": "Sverige-eksponering via ETF", "markets": ["Sverige", "Norden"]},
        {"symbol": "EFNL", "type": "ETF", "bucket": "Finland ETF", "reason": "Finland-eksponering via ETF", "markets": ["Finland", "Norden"]},
        {"symbol": "EDEN", "type": "ETF", "bucket": "Danmark ETF", "reason": "Danmark-eksponering via ETF", "markets": ["Danmark", "Norden"]},
        {"symbol": "EWZ", "type": "ETF", "bucket": "Brasil ETF", "reason": "Brasil-eksponering via ETF", "markets": ["Brasil"]},
    ],
    "Aktivt fond": [
        {"symbol": "ARKK", "type": "Aktivt fond", "bucket": "Aktiv vekst", "reason": "aktiv/disruptiv vekstprofil, må bevise merverdi"},
        {"symbol": "ARKW", "type": "Aktivt fond", "bucket": "Aktiv teknologi", "reason": "aktiv teknologi/vekst, må testes mot benchmark"},
        {"symbol": "ARKF", "type": "Aktivt fond", "bucket": "Aktiv fintech", "reason": "aktiv tematisk kandidat"},
        {"symbol": "JEPI", "type": "Aktivt fond", "bucket": "Aktiv income", "reason": "aktiv income/covered-call ETF"},
        {"symbol": "JEPQ", "type": "Aktivt fond", "bucket": "Aktiv Nasdaq income", "reason": "aktiv Nasdaq/income-kandidat"},
        {"symbol": "TCAF", "type": "Aktivt fond", "bucket": "Aktiv kapitalallokering", "reason": "aktivt forvaltet ETF-kandidat"},
        {"symbol": "DYNF", "type": "Aktivt fond", "bucket": "Aktiv faktor", "reason": "aktiv faktor/rotasjon"},
        {"symbol": "AVGV", "type": "Aktivt fond", "bucket": "Aktiv verdi", "reason": "aktiv verdifaktor-kandidat"},
        {"symbol": "DNB_GLOBAL_INDEKS_A", "type": "Indeksfond", "bucket": "Norsk fondskatalog", "reason": "norsk indeksfond, krever NAV/ISIN-datakilde for full historikk", "markets": ["Norge", "Norden"]},
        {"symbol": "KLP_AKSJEGLOBAL_INDEKS_P", "type": "Indeksfond", "bucket": "Norsk fondskatalog", "reason": "norsk globalt indeksfond, lokal metadata/NAV-fallback", "markets": ["Norge", "Norden"]},
        {"symbol": "STOREBRAND_INDEKS_NORGE_A", "type": "Indeksfond", "bucket": "Norsk fondskatalog", "reason": "norsk indeksfond med Oslo-eksponering, krever NAV-kilde", "markets": ["Norge", "Norden"]},
        {"symbol": "AVANZA_GLOBAL", "type": "Indeksfond", "bucket": "Svensk fondskatalog", "reason": "svensk fondskandidat med lokal metadata/NAV-fallback", "markets": ["Sverige", "Norden"]},
        {"symbol": "SPILTAN_AKTIEFOND_INVESTMENTBOLAG", "type": "Aktivt fond", "bucket": "Svensk fondskatalog", "reason": "svensk aktiv fondskandidat, krever NAV-kilde", "markets": ["Sverige", "Norden"]},
    ],
    "Rente-/obligasjonsfond": [
        {"symbol": "BND", "type": "Rente-/obligasjonsfond", "bucket": "Bred obligasjon", "reason": "bred obligasjons-/renteeksponering"},
        {"symbol": "AGG", "type": "Rente-/obligasjonsfond", "bucket": "US aggregate bonds", "reason": "bred obligasjonsbenchmark"},
        {"symbol": "IEF", "type": "Rente-/obligasjonsfond", "bucket": "Mellomlang stat", "reason": "rentefølsom statsobligasjonseksponering"},
        {"symbol": "TLT", "type": "Rente-/obligasjonsfond", "bucket": "Lang stat", "reason": "lang durasjon, høyere rentefølsomhet"},
        {"symbol": "SHY", "type": "Rente-/obligasjonsfond", "bucket": "Kort stat", "reason": "kort durasjon, lavere rentefølsomhet"},
        {"symbol": "BSV", "type": "Rente-/obligasjonsfond", "bucket": "Kort obligasjon", "reason": "kort obligasjonsprofil"},
        {"symbol": "VCIT", "type": "Rente-/obligasjonsfond", "bucket": "Investment grade kreditt", "reason": "investment grade selskapsobligasjoner"},
        {"symbol": "LQD", "type": "Rente-/obligasjonsfond", "bucket": "Investment grade kreditt", "reason": "likvid IG-kredittbenchmark"},
        {"symbol": "VGIT", "type": "Rente-/obligasjonsfond", "bucket": "Mellomlang stat", "reason": "utvider startuniverset med stat/treasury"},
        {"symbol": "VGLT", "type": "Rente-/obligasjonsfond", "bucket": "Lang stat", "reason": "lang durasjon som sammenligningskandidat"},
        {"symbol": "GOVT", "type": "Rente-/obligasjonsfond", "bucket": "US Treasury bred", "reason": "bred statsobligasjonseksponering"},
        {"symbol": "IGSB", "type": "Rente-/obligasjonsfond", "bucket": "Kort IG kreditt", "reason": "kort investment grade-kreditt"},
        {"symbol": "SPSB", "type": "Rente-/obligasjonsfond", "bucket": "Kort corporate", "reason": "kort selskapsobligasjonsprofil"},
    ],
    "High yield-fond": [
        {"symbol": "HYG", "type": "High yield-fond", "bucket": "High yield", "reason": "stor high yield ETF, kredittrisiko må vurderes"},
        {"symbol": "JNK", "type": "High yield-fond", "bucket": "High yield", "reason": "likvid high yield-kandidat"},
        {"symbol": "ANGL", "type": "High yield-fond", "bucket": "Fallen angels", "reason": "fallen angels/high yield-segment"},
        {"symbol": "HYLB", "type": "High yield-fond", "bucket": "High yield lavkost", "reason": "lavkost high yield ETF-kandidat"},
        {"symbol": "USHY", "type": "High yield-fond", "bucket": "High yield bred", "reason": "bred high yield-eksponering"},
        {"symbol": "SJNK", "type": "High yield-fond", "bucket": "Kort high yield", "reason": "kortere high yield-profil"},
        {"symbol": "BKLN", "type": "High yield-fond", "bucket": "Bank loans", "reason": "flytende rente/kredittsatellitt"},
        {"symbol": "KRAFT_HIGH_YIELD_D", "type": "High yield-fond", "bucket": "Norsk high yield", "reason": "Kraft High Yield D-lignende kandidat; krever NAV/datakilde hvis Yahoo mangler"},
        {"symbol": "SHYG", "type": "High yield-fond", "bucket": "Kort high yield", "reason": "kortere high yield-kreditt"},
        {"symbol": "FALN", "type": "High yield-fond", "bucket": "Fallen angels", "reason": "fallen angels som high yield-satellitt"},
    ],
    "Pengemarkedsfond": [
        {"symbol": "SGOV", "type": "Pengemarkedsfond", "bucket": "T-bills", "reason": "kort stat/pengemarkedsnær eksponering"},
        {"symbol": "BIL", "type": "Pengemarkedsfond", "bucket": "T-bills", "reason": "svært kort rentepapir-eksponering"},
        {"symbol": "SHV", "type": "Pengemarkedsfond", "bucket": "Kort stat", "reason": "kort stat/pengemarkedsprofil"},
        {"symbol": "ICSH", "type": "Pengemarkedsfond", "bucket": "Ultra short", "reason": "ultrakort rente-ETF"},
        {"symbol": "MINT", "type": "Pengemarkedsfond", "bucket": "Ultra short aktiv", "reason": "ultrakort aktiv renteprofil"},
        {"symbol": "JPST", "type": "Pengemarkedsfond", "bucket": "Ultra short income", "reason": "ultrakort inntektsfond"},
        {"symbol": "NEAR", "type": "Pengemarkedsfond", "bucket": "Short duration", "reason": "kort rentefond/pengemarkedsnær"},
        {"symbol": "USFR", "type": "Pengemarkedsfond", "bucket": "Floating rate treasury", "reason": "flytende rente, kort stat"},
        {"symbol": "TFLO", "type": "Pengemarkedsfond", "bucket": "Treasury floating rate", "reason": "kort flytende statsrente"},
    ],
}

FUND_SYMBOL_ALIASES = {
    "KRAFTHIGHYIELDD": "KRAFT_HIGH_YIELD_D",
    "KRAFT-HIGH-YIELD-D": "KRAFT_HIGH_YIELD_D",
    "KRAFT_HIGH_YIELD_D": "KRAFT_HIGH_YIELD_D",
    "DNBGLOBALINDEKSA": "DNB_GLOBAL_INDEKS_A",
    "KLPAKSJEGLOBALINDEKSP": "KLP_AKSJEGLOBAL_INDEKS_P",
    "STOREBRANDINDEKSNORGEA": "STOREBRAND_INDEKS_NORGE_A",
    "AVANZAGLOBAL": "AVANZA_GLOBAL",
    "SPILTANAKTIEFONDINVESTMENTBOLAG": "SPILTAN_AKTIEFOND_INVESTMENTBOLAG",
}

# v18.5.47: shared display-name layer. Yahoo/metadata wins when present; this
# mapping is only fallback so UI never has to show ticker-only rows for known funds.
FUND_NAME_FALLBACKS: Dict[str, str] = {
    "SHY": "iShares 1-3 Year Treasury Bond ETF",
    "LQD": "iShares iBoxx $ Investment Grade Corporate Bond ETF",
    "IEF": "iShares 7-10 Year Treasury Bond ETF",
    "TLT": "iShares 20+ Year Treasury Bond ETF",
    "BSV": "Vanguard Short-Term Bond ETF",
    "VCIT": "Vanguard Intermediate-Term Corporate Bond ETF",
    "BND": "Vanguard Total Bond Market ETF",
    "AGG": "iShares Core U.S. Aggregate Bond ETF",
    "VGIT": "Vanguard Intermediate-Term Treasury ETF",
    "VGLT": "Vanguard Long-Term Treasury ETF",
    "GOVT": "iShares U.S. Treasury Bond ETF",
    "IGSB": "iShares 1-5 Year Investment Grade Corporate Bond ETF",
    "SPSB": "SPDR Portfolio Short Term Corporate Bond ETF",
    "HYG": "iShares iBoxx $ High Yield Corporate Bond ETF",
    "JNK": "SPDR Bloomberg High Yield Bond ETF",
    "ANGL": "VanEck Fallen Angel High Yield Bond ETF",
    "HYLB": "Xtrackers USD High Yield Corporate Bond ETF",
    "USHY": "iShares Broad USD High Yield Corporate Bond ETF",
    "SJNK": "SPDR Bloomberg Short Term High Yield Bond ETF",
    "BKLN": "Invesco Senior Loan ETF",
    "SHYG": "iShares 0-5 Year High Yield Corporate Bond ETF",
    "FALN": "iShares Fallen Angels USD Bond ETF",
    "KRAFT_HIGH_YIELD_D": "Kraft High Yield D",
    "SGOV": "iShares 0-3 Month Treasury Bond ETF",
    "BIL": "SPDR Bloomberg 1-3 Month T-Bill ETF",
    "SHV": "iShares Short Treasury Bond ETF",
    "ICSH": "iShares Ultra Short-Term Bond ETF",
    "MINT": "PIMCO Enhanced Short Maturity Active ETF",
    "JPST": "JPMorgan Ultra-Short Income ETF",
    "NEAR": "BlackRock Short Duration Bond ETF",
    "USFR": "WisdomTree Floating Rate Treasury Fund",
    "TFLO": "iShares Treasury Floating Rate Bond ETF",
    "VOO": "Vanguard S&P 500 ETF",
    "VTI": "Vanguard Total Stock Market ETF",
    "ACWI": "iShares MSCI ACWI ETF",
    "VT": "Vanguard Total World Stock ETF",
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust",
    "NORW": "Global X MSCI Norway ETF",
    "EWD": "iShares MSCI Sweden ETF",
    "EFNL": "iShares MSCI Finland ETF",
    "EDEN": "iShares MSCI Denmark ETF",
    "EWZ": "iShares MSCI Brazil ETF",
    "DNB_GLOBAL_INDEKS_A": "DNB Global Indeks A",
    "KLP_AKSJEGLOBAL_INDEKS_P": "KLP AksjeGlobal Indeks P",
    "STOREBRAND_INDEKS_NORGE_A": "Storebrand Indeks Norge A",
    "AVANZA_GLOBAL": "Avanza Global",
    "SPILTAN_AKTIEFOND_INVESTMENTBOLAG": "Spiltan Aktiefond Investmentbolag",
}

def get_fund_display_name(symbol: Any, data: Optional[Mapping[str, Any]] = None) -> str:
    """Return best available fund name: metadata/Yahoo -> fallback mapping -> not found."""
    sym = normalize_fund_symbol(symbol)
    meta = dict(data or {})
    for key in ("longName", "shortName", "name", "displayName", "fundName"):
        val = str(meta.get(key) or "").strip()
        if val and val.upper() != sym:
            return val
    return FUND_NAME_FALLBACKS.get(sym) or "Navn ikke funnet"


def enrich_fund_identity(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Attach consistent fund metadata without replacing fund_type with name."""
    out = dict(row or {})
    sym = normalize_fund_symbol(out.get("symbol") or out.get("ticker"))
    if sym:
        out["symbol"] = sym
        meta = resolve_security_metadata(sym, out)
        name = str(meta.get("name") or get_fund_display_name(sym, out) or "").strip()
        if name and name.upper().replace(" ", "") != sym.replace(" ", ""):
            out["name"] = name
            out["fund_name"] = name
            out["display_label"] = f"{sym} — {name}"
        else:
            out["display_label"] = sym
        out.setdefault("sector", meta.get("sector"))
        out.setdefault("risk", meta.get("risk"))
    return out

FIXED_INCOME_SYMBOLS = {row["symbol"] for key in ["Rente-/obligasjonsfond", "Pengemarkedsfond"] for row in FUND_UNIVERSES.get(key, [])}
HIGH_YIELD_SYMBOLS = {row["symbol"] for row in FUND_UNIVERSES.get("High yield-fond", [])}



def fund_selection_sources() -> List[str]:
    """Return UI-safe source options for fund selection."""
    return list(FUND_SELECTION_SOURCES)


def fund_type_options() -> List[str]:
    """Return UI-safe fund type options including fixed income/high yield. v18.5.46."""
    return list(FUND_TYPE_OPTIONS)


def fund_market_options() -> List[str]:
    """Return fund/ETF market choices aligned with the shared market engine."""
    options: List[str] = []
    for item in ["Alle"] + market_scope_options(include_aggregate=True) + FUND_EXTRA_MARKETS:
        if item not in options:
            options.append(item)
    return options


def _fund_market_tags(row: Mapping[str, Any]) -> List[str]:
    explicit = row.get("markets") or row.get("market") or []
    if isinstance(explicit, str):
        tags = [x.strip() for x in explicit.replace(";", ",").split(",") if x.strip()]
    else:
        try:
            tags = [str(x).strip() for x in explicit if str(x).strip()]
        except Exception:
            tags = []
    symbol = normalize_fund_symbol(row.get("symbol"))
    if symbol.endswith(".OL") or symbol in {"KRAFT_HIGH_YIELD_D", "DNB_GLOBAL_INDEKS_A", "KLP_AKSJEGLOBAL_INDEKS_P", "STOREBRAND_INDEKS_NORGE_A", "NORW"}:
        tags.extend(["Norge", "Norden"])
    elif symbol.endswith(".ST") or symbol in {"EWD", "AVANZA_GLOBAL", "SPILTAN_AKTIEFOND_INVESTMENTBOLAG"}:
        tags.extend(["Sverige", "Norden"])
    elif symbol.endswith(".HE") or symbol == "EFNL":
        tags.extend(["Finland", "Norden"])
    elif symbol.endswith(".CO") or symbol == "EDEN":
        tags.extend(["Danmark", "Norden"])
    elif symbol.endswith(".SA") or symbol == "EWZ":
        tags.append("Brasil")
    elif symbol.endswith(".DE"):
        tags.append("Europa/UCITS")
    elif symbol:
        tags.append("USA")
    out: List[str] = []
    for tag in tags:
        if tag and tag not in out:
            out.append(tag)
    return out or ["Ukjent"]


def _fund_row_matches_market(row: Mapping[str, Any], market_scope: str) -> bool:
    scope = str(market_scope or "Alle").strip()
    if scope in {"", "Alle"}:
        return True
    tags = set(_fund_market_tags(row))
    if scope == "Norden":
        return bool(tags.intersection(set(NORDIC_MARKET_SCOPES))) or "Norden" in tags
    return scope in tags


def default_fund_benchmark(fund_type: str = "Alle", market_scope: str = "Alle") -> str:
    """Pick a fund/region benchmark instead of always using SPY."""
    ftype = str(fund_type or "Alle")
    market = str(market_scope or "Alle")
    if ftype == "High yield-fond":
        return "HYG"
    if ftype == "Rente-/obligasjonsfond":
        return "BND"
    if ftype == "Pengemarkedsfond":
        return "SGOV"
    if market == "Norge":
        return "NORW"
    if market == "Sverige":
        return "EWD"
    if market == "Finland":
        return "EFNL"
    if market == "Danmark":
        return "EDEN"
    if market == "Brasil":
        return "EWZ"
    if market == "Europa/UCITS":
        return "EUNL.DE"
    if market == "Norden":
        return "EWD"
    return "SPY"


def _dedupe_symbols(items: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in items or []:
        symbol = normalize_fund_symbol(item.get("symbol"))
        if not symbol or symbol in seen:
            continue
        row = dict(item)
        row["symbol"] = symbol
        out.append(row)
        seen.add(symbol)
    return out


def _balanced_mix(max_funds: int | None = None) -> List[Dict[str, Any]]:
    """Create a balanced starter universe across fund categories.

    v18.5.49: `Maks fond` is no longer used to cut the universe before
    analysis. It only controls how many ranked results the UI shows after all
    available starter-universe candidates have been analyzed.
    """
    buckets = [
        FUND_UNIVERSES["Indeksfond"],
        FUND_UNIVERSES["ETF"],
        FUND_UNIVERSES["Rente-/obligasjonsfond"],
        FUND_UNIVERSES["High yield-fond"],
        FUND_UNIVERSES["Aktivt fond"],
        FUND_UNIVERSES["Pengemarkedsfond"],
    ]
    selected: List[Dict[str, Any]] = []
    seen = set()
    i = 0
    while any(i < len(bucket) for bucket in buckets):
        for bucket in buckets:
            if i < len(bucket):
                row = dict(bucket[i])
                symbol = normalize_fund_symbol(row.get("symbol"))
                if symbol and symbol not in seen:
                    row["symbol"] = symbol
                    selected.append(row)
                    seen.add(symbol)
        i += 1
    return selected


def select_fund_candidates(
    *,
    source: str = "Manuell liste",
    fund_type: str = "Alle",
    manual_symbols: Sequence[str] | None = None,
    max_funds: int = 8,
    market_scope: str = "Alle",
) -> Dict[str, Any]:
    """Resolve fund/ETF candidates from a source.

    v18.5.49 changes `Maks fond` from a pre-analysis cut-off to a post-ranking
    display limit. Auto sources now analyze the whole transparent starter
    universe first, rank all analyzed funds, and let the UI show top N/all.
    """
    source = str(source or "Manuell liste").strip()
    if source not in FUND_SELECTION_SOURCES:
        source = "Manuell liste"
    max_funds = max(1, int(max_funds or 8))
    manual = [normalize_fund_symbol(x) for x in (manual_symbols or []) if normalize_fund_symbol(x)]

    if source == "Manuell liste":
        rows = [
            {"symbol": sym, "type": fund_type if fund_type != "Alle" else "Manuell", "bucket": "Manuell", "reason": "valgt manuelt av bruker"}
            for sym in manual
        ]
    elif source in {"Auto-univers", "Alle / balansert miks"}:
        rows = _balanced_mix()
    elif source == "Auto indeksfond":
        rows = FUND_UNIVERSES["Indeksfond"]
    elif source == "Auto ETF":
        rows = FUND_UNIVERSES["ETF"]
    elif source == "Auto aktive fond":
        rows = FUND_UNIVERSES["Aktivt fond"]
    elif source == "Auto rente-/obligasjonsfond":
        rows = FUND_UNIVERSES["Rente-/obligasjonsfond"]
    elif source == "Auto high yield-fond":
        rows = FUND_UNIVERSES["High yield-fond"]
    elif source == "Auto pengemarkedsfond":
        rows = FUND_UNIVERSES["Pengemarkedsfond"]
    else:
        rows = _balanced_mix()

    # v18.5.49: Do not truncate the candidate list before scoring. `max_funds`
    # is kept as the user's desired result-display limit and is applied only
    # after ranking in the UI.
    selected = [
        dict(row, markets=_fund_market_tags(row))
        for row in _dedupe_symbols(rows)
        if _fund_row_matches_market(row, market_scope)
    ]

    symbols = [r["symbol"] for r in selected]
    return {
        "source": source,
        "fund_type": fund_type,
        "market_scope": market_scope,
        "max_funds": max_funds,
        "available_in_universe": len(_dedupe_symbols(rows)),
        "available_after_market_filter": len(selected),
        "symbols": symbols,
        "selected": selected,
        "selection_summary": f"{len(symbols)} fond/ETF i analyseunivers fra {source} / {market_scope}; viser maks {max_funds} etter rangering",
        "display_limit": max_funds,
        "universe_note": "Auto-universet er et starter-univers, ikke hele markedet. Hele starter-universet analyseres før resultatlisten kuttes. Vanlige nordiske fond kan kreve NAV/ISIN-kilde og vises med datastatus.",
    }








def normalize_fund_symbol(value: Any) -> str:
    raw = str(value or "").strip().upper().replace(" ", "")
    return FUND_SYMBOL_ALIASES.get(raw, raw)


def parse_fund_list(value: Any) -> List[str]:
    raw = str(value or "")
    for sep in [";", "\n", "\t"]:
        raw = raw.replace(sep, ",")
    out: List[str] = []
    seen = set()
    for part in raw.split(","):
        part_text = str(part or "").strip()
        phrase_symbol = normalize_fund_symbol(part_text)
        if phrase_symbol in FUND_SYMBOL_ALIASES.values() and phrase_symbol not in seen:
            out.append(phrase_symbol)
            seen.add(phrase_symbol)
            continue
        for token in part_text.split():
            symbol = normalize_fund_symbol(token)
            if symbol and symbol not in seen:
                out.append(symbol)
                seen.add(symbol)
    return out


def get_fund_test_mode_config(test_mode: str = "Normal") -> Dict[str, Any]:
    mode = str(test_mode or "Normal").strip()
    if mode not in FUND_TEST_MODE_CONFIGS:
        mode = "Normal"
    cfg = dict(FUND_TEST_MODE_CONFIGS[mode])
    cfg["mode"] = mode
    cfg["tests"] = list(cfg.get("tests") or FUND_TEST_MODE_CONFIGS["Normal"]["tests"])
    return cfg


def estimate_fund_etf_run(
    symbols: Sequence[str],
    *,
    test_mode: str = "Normal",
    include_benchmark: bool = True,
    fetch_costs: bool = True,
) -> Dict[str, Any]:
    clean: List[str] = []
    seen = set()
    for raw in symbols or []:
        symbol = normalize_fund_symbol(raw)
        if symbol and symbol not in seen:
            clean.append(symbol)
            seen.add(symbol)
    cfg = get_fund_test_mode_config(test_mode)
    tests = [t for t in cfg["tests"] if include_benchmark or t not in {"Benchmark", "Aktiv merverdi"}]
    total_tests = len(clean) * len(tests)
    price_calls = len(clean)
    benchmark_calls = 1 if include_benchmark and clean else 0
    metadata_calls = len(clean) if fetch_costs else 0
    load_score = int(math.ceil((price_calls + benchmark_calls + metadata_calls) * float(cfg.get("api_multiplier", 1.0))))
    if load_score <= 12:
        load_label = "Lav"
    elif load_score <= 45:
        load_label = "Medium"
    else:
        load_label = "Høy"
    return {
        "mode": cfg["mode"],
        "description": cfg.get("description", ""),
        "funds": len(clean),
        "tests": tests,
        "tests_per_fund": len(tests),
        "total_tests": total_tests,
        "price_calls": price_calls,
        "benchmark_calls": benchmark_calls,
        "metadata_calls": metadata_calls,
        "load_label": load_label,
    }


def _emit_progress(
    callback: Optional[ProgressCallback],
    *,
    symbol: str = "",
    fund_index: int = 0,
    fund_total: int = 0,
    test_name: str = "",
    test_index: int = 0,
    tests_per_fund: int = 0,
    completed_tests: int = 0,
    total_tests: int = 0,
    status: str = "running",
    message: str = "",
) -> None:
    if callback is None:
        return
    pct = 0.0 if total_tests <= 0 else _clamp((completed_tests / total_tests) * 100.0, 0.0, 100.0)
    callback({
        "status": status,
        "symbol": symbol,
        "fund_index": fund_index,
        "fund_total": fund_total,
        "test_name": test_name,
        "test_index": test_index,
        "tests_per_fund": tests_per_fund,
        "completed_tests": completed_tests,
        "total_tests": total_tests,
        "percent": round(pct, 1),
        "message": message,
        "updated_at": _now_iso(),
    })


def _prices_from_data(data: Optional[Mapping[str, Any]]) -> List[float]:
    if not data:
        return []
    raw = data.get("prices") or data.get("close") or data.get("closes") or []
    try:
        values = list(raw)
    except Exception:
        return []
    out: List[float] = []
    for value in values:
        val = _safe_float(value, None)
        if val is not None and val > 0:
            out.append(float(val))
    return out


def _period_return(prices: Sequence[float]) -> Optional[float]:
    vals = [float(x) for x in prices or [] if _safe_float(x, None) is not None and float(x) > 0]
    if len(vals) < 2:
        return None
    return (vals[-1] / vals[0] - 1.0) * 100.0


def _daily_returns(prices: Sequence[float]) -> List[float]:
    vals = [float(x) for x in prices or [] if _safe_float(x, None) is not None and float(x) > 0]
    out: List[float] = []
    for prev, cur in zip(vals, vals[1:]):
        if prev > 0:
            out.append((cur / prev) - 1.0)
    return out


def _annualized_volatility(prices: Sequence[float]) -> Optional[float]:
    rets = _daily_returns(prices)
    if len(rets) < 20:
        return None
    mean = sum(rets) / len(rets)
    variance = sum((x - mean) ** 2 for x in rets) / max(1, len(rets) - 1)
    return math.sqrt(variance) * math.sqrt(252.0) * 100.0


def _max_drawdown(prices: Sequence[float]) -> Optional[float]:
    vals = [float(x) for x in prices or [] if _safe_float(x, None) is not None and float(x) > 0]
    if len(vals) < 2:
        return None
    peak = vals[0]
    worst = 0.0
    for val in vals:
        peak = max(peak, val)
        if peak > 0:
            dd = (val / peak - 1.0) * 100.0
            worst = min(worst, dd)
    return worst


def _expense_ratio(data: Optional[Mapping[str, Any]]) -> Optional[float]:
    if not data:
        return None
    for key in ["expense_ratio", "expenseRatio", "annualReportExpenseRatio", "netExpenseRatio", "total_expense_ratio"]:
        val = _safe_float(data.get(key), None)
        if val is not None:
            # Some APIs return 0.002 for 0.20%, others 0.20.
            return val * 100.0 if 0 < val < 0.08 else val
    return None


def classify_fund(symbol: str, declared_type: str = "Alle", data: Optional[Mapping[str, Any]] = None) -> str:
    declared = str(declared_type or "Alle")
    if declared in set(FUND_TYPE_OPTIONS) - {"Alle"}:
        return declared
    if data:
        quote_type = str(data.get("quoteType") or data.get("type") or "").upper()
        category = str(data.get("category") or data.get("fundFamily") or "").upper()
        name = str(data.get("name") or data.get("longName") or "").upper()
        if any(x in category or x in name for x in ["HIGH YIELD", "HY", "KREDITT", "CREDIT"]):
            return "High yield-fond"
        if any(x in category or x in name for x in ["MONEY MARKET", "PENGEMARKED", "ULTRA SHORT", "T-BILL"]):
            return "Pengemarkedsfond"
        if any(x in category or x in name for x in ["BOND", "OBLIGASJON", "RENTE", "FIXED INCOME", "TREASURY"]):
            return "Rente-/obligasjonsfond"
        if any(x in category or x in name for x in ["BALANCED", "KOMBINASJON", "ALLOCATION"]):
            return "Kombinasjonsfond"
        if "ETF" in quote_type or " ETF" in name:
            return "ETF"
        if "INDEX" in category or "INDEKS" in category or "INDEX" in name or "INDEKS" in name:
            return "Indeksfond"
    s = str(symbol or "").upper()
    if s in HIGH_YIELD_SYMBOLS or any(tag in s for tag in ["HYG", "JNK", "HY", "HIGHYIELD"]):
        return "High yield-fond"
    if s in FIXED_INCOME_SYMBOLS or any(tag in s for tag in ["BND", "AGG", "IEF", "TLT", "SHY", "BIL", "SGOV", "MINT"]):
        return "Rente-/obligasjonsfond" if s not in {"BIL", "SGOV", "SHV", "ICSH", "MINT"} else "Pengemarkedsfond"
    if any(tag in s for tag in ["ETF", ".L", ".PA", ".DE"]):
        return "ETF"
    return "Fond"


def _score_cost(expense: Optional[float], fund_type: str) -> float:
    if expense is None:
        return 55.0
    # Thresholds are stricter for index funds/ETFs, more tolerant for active funds.
    if fund_type in {"Indeksfond", "ETF"}:
        return _clamp(100.0 - (expense / 0.80) * 75.0, 10.0, 100.0)
    if fund_type == "Pengemarkedsfond":
        return _clamp(100.0 - (expense / 0.60) * 78.0, 8.0, 100.0)
    if fund_type == "Rente-/obligasjonsfond":
        return _clamp(100.0 - (expense / 0.90) * 72.0, 8.0, 100.0)
    if fund_type == "High yield-fond":
        return _clamp(95.0 - (expense / 1.20) * 62.0, 8.0, 100.0)
    if fund_type == "Aktivt fond":
        return _clamp(100.0 - (expense / 1.80) * 65.0, 8.0, 100.0)
    return _clamp(100.0 - (expense / 1.20) * 70.0, 8.0, 100.0)


def _score_return(total_return: Optional[float]) -> float:
    if total_return is None:
        return 50.0
    # 5y/period return may vary, keep conservative.
    return _clamp(50.0 + total_return * 0.9, 5.0, 100.0)


def _score_risk(volatility: Optional[float], drawdown: Optional[float]) -> float:
    vol_score = 65.0 if volatility is None else _clamp(100.0 - volatility * 2.2, 5.0, 100.0)
    dd_score = 65.0 if drawdown is None else _clamp(100.0 + drawdown * 1.9, 5.0, 100.0)
    return round((vol_score * 0.55) + (dd_score * 0.45), 1)


def _score_benchmark(total_return: Optional[float], benchmark_return: Optional[float], expense: Optional[float], fund_type: str) -> float:
    if total_return is None or benchmark_return is None:
        return 55.0
    excess = total_return - benchmark_return
    fee_drag = expense or 0.0
    if fund_type == "Aktivt fond":
        # Active funds need excess return after fee drag to score high.
        return _clamp(55.0 + excess * 1.7 - fee_drag * 8.0, 5.0, 100.0)
    if fund_type == "High yield-fond":
        # High yield is a credit satellite; reward excess cautiously and penalize fees.
        return _clamp(55.0 + excess * 1.15 - fee_drag * 5.5, 5.0, 100.0)
    if fund_type in {"Rente-/obligasjonsfond", "Pengemarkedsfond"}:
        tracking_gap = abs(excess)
        return _clamp(90.0 - tracking_gap * 1.2 - fee_drag * 4.0, 10.0, 100.0)
    # Index/ETF should be close to benchmark, not necessarily beat it.
    tracking_gap = abs(excess)
    return _clamp(95.0 - tracking_gap * 1.4 - fee_drag * 3.0, 10.0, 100.0)


def _score_data_quality(prices: Sequence[float], expense: Optional[float], benchmark_return: Optional[float]) -> float:
    n = len(prices or [])
    score = 30.0
    if n >= 60:
        score += 20.0
    if n >= 250:
        score += 20.0
    if n >= 750:
        score += 10.0
    if expense is not None:
        score += 10.0
    if benchmark_return is not None:
        score += 10.0
    return _clamp(score, 5.0, 100.0)






# v18.5.50 / Layer 1: Base Fund Scoring.
# This profile is deliberately separated from the hardened decision profile so
# later explainability, holdings and insider layers can build on one stable
# numeric foundation instead of re-deriving scores in the UI.
def build_base_fund_score_profile(
    *,
    fund_type: str,
    objective: str,
    cost_score: float,
    return_score: float,
    risk_score: float,
    benchmark_score: float,
    data_score: float,
    fit_score: float,
    active_evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    weights = dict(OBJECTIVE_WEIGHTS.get(objective) or OBJECTIVE_WEIGHTS["Balansert"])
    components = {
        "cost": round(float(cost_score), 1),
        "return": round(float(return_score), 1),
        "risk": round(float(risk_score), 1),
        "benchmark": round(float(benchmark_score), 1),
        "data": round(float(data_score), 1),
        "fit": round(float(fit_score), 1),
    }
    raw = sum(float(components[k]) * float(weights.get(k, 0.0)) for k in components)
    adjustments: List[Dict[str, Any]] = []

    # Guardrails belong in layer 1 because they are not "AI opinion"; they are
    # conservative portfolio hygiene rules that prevent misleading high scores.
    if data_score < 45:
        raw = min(raw, 54.0)
        adjustments.append({"type": "cap", "label": "Svak datakvalitet", "effect": "score capped", "reason": "for lite pris-/kostnadsdata"})
    if fund_type == "Aktivt fond":
        evidence = dict(active_evidence or {})
        evidence_score = _safe_float(evidence.get("score"), 35.0) or 35.0
        if evidence.get("status") != "Godkjent" or evidence_score < 68:
            raw = min(raw, 58.0)
            adjustments.append({"type": "cap", "label": "Aktiv merverdi ikke bevist", "effect": "score capped", "reason": "aktivt fond må slå benchmark etter kostnad/risiko"})
    if fund_type == "High yield-fond" and risk_score < 60:
        raw = min(raw, 66.0)
        adjustments.append({"type": "cap", "label": "High yield-risiko", "effect": "score capped", "reason": "kredittrisiko/drawdown krever satellittbehandling"})

    score = round(_clamp(raw), 1)
    ranked_components = sorted(components.items(), key=lambda kv: kv[1], reverse=True)
    weakest_components = sorted(components.items(), key=lambda kv: kv[1])
    component_labels = {
        "cost": "kostnad",
        "return": "historikk/avkastning",
        "risk": "risiko/drawdown",
        "benchmark": "benchmark",
        "data": "datakvalitet",
        "fit": "mål/rolle-fit",
    }
    primary_driver = component_labels.get(ranked_components[0][0], ranked_components[0][0]) if ranked_components else "ukjent"
    primary_drag = component_labels.get(weakest_components[0][0], weakest_components[0][0]) if weakest_components else "ukjent"
    if score >= 75:
        verdict = "Sterk grunnscore"
    elif score >= 60:
        verdict = "Brukbar grunnscore"
    else:
        verdict = "Svak grunnscore"
    return {
        "layer": "Layer 1",
        "model": "Base Fund Scoring",
        "base_score": score,
        "verdict": verdict,
        "objective": objective,
        "fund_type": fund_type,
        "weights": {k: round(float(v), 3) for k, v in weights.items()},
        "components": components,
        "primary_driver": primary_driver,
        "primary_drag": primary_drag,
        "adjustments": adjustments,
        "explainable_ready": True,
        "holdings_ready": False,
        "insider_ready": False,
        "summary": f"{verdict}: sterkest på {primary_driver}, svakest på {primary_drag}.",
    }


# v18.5.51 / Layer 2: Explainable Fund Intelligence.
# Layer 2 turns the stable Layer 1 and Decision Quality numbers into plain
# Norwegian decision logic. It does not fetch holdings or insider data yet; it
# prepares clean explanation hooks for those later layers.
def build_fund_explainability_profile(row: Mapping[str, Any], *, peer_symbol: Optional[str] = None) -> Dict[str, Any]:
    r = dict(row or {})
    name = str(r.get("name") or r.get("symbol") or "Fondet")
    symbol = str(r.get("symbol") or "")
    fund_type = str(r.get("fund_type") or "Fond")
    quality = _safe_float(r.get("decision_quality"), 0.0) or 0.0
    base_score = _safe_float(r.get("base_score"), quality) or quality
    grade = str(r.get("grade") or "Ukjent")
    decision = str(r.get("decision") or "Vurder videre")
    role = str(r.get("recommended_role") or "Ukjent rolle")
    positives = [str(x) for x in (r.get("reasons_positive") or []) if str(x).strip()]
    cautions = [str(x) for x in (r.get("reasons_caution") or []) if str(x).strip()]
    why_not_100 = [str(x) for x in (r.get("why_not_100") or []) if str(x).strip()]
    base_profile = dict(r.get("base_score_profile") or {})
    components = dict(base_profile.get("components") or r.get("quality_breakdown") or {})

    strengths: List[str] = []
    weaknesses: List[str] = []
    triggers_positive: List[str] = []
    rejection_triggers: List[str] = []

    if positives:
        strengths.extend(positives[:3])
    if quality >= 72:
        strengths.append("helhetlig score er sterk nok til å vurderes som kandidat")
    if base_score >= 70:
        strengths.append("grunnscoren støtter beslutningen, ikke bare én enkelt faktor")
    if role and role != "Ukjent rolle":
        strengths.append(f"passer best som {role.lower()}")

    if cautions:
        weaknesses.extend(cautions[:3])
    if quality < 60:
        weaknesses.append("samlet beslutningskvalitet er for lav til automatisk favorisering")
    if base_score < 60:
        weaknesses.append("grunnscoren er svak og krever ekstra kontroll")
    if why_not_100:
        weaknesses.extend(why_not_100[:2])

    expense = r.get("expense_ratio_pct")
    excess = r.get("excess_return_pct")
    drawdown = r.get("max_drawdown_pct")
    risk_score = _safe_float(r.get("risk_score"), None)
    benchmark_score = _safe_float(r.get("benchmark_score"), None)
    cost_score = _safe_float(r.get("cost_score"), None)
    return_score = _safe_float(r.get("return_score"), None)

    if fund_type == "Aktivt fond":
        triggers_positive.append("tydelig meravkastning mot relevant benchmark etter kostnader")
        triggers_positive.append("stabil risikojustert avkastning over flere perioder")
        rejection_triggers.append("aktiv merverdi forsvinner etter kostnad og risiko")
        rejection_triggers.append("benchmark-gapet blir negativt over tid")
    elif fund_type in {"Indeksfond", "ETF"}:
        triggers_positive.append("lav kostnad, god tracking og høy datakvalitet består")
        rejection_triggers.append("kostnad eller tracking-feil øker uten bedre risikojustert avkastning")
    elif fund_type == "High yield-fond":
        triggers_positive.append("kredittspread faller uten at drawdown-risikoen øker")
        rejection_triggers.append("kredittspread utvider seg eller misligholdsrisiko stiger")
    elif fund_type in FIXED_INCOME_TYPES:
        triggers_positive.append("rentebildet og duration passer bedre med porteføljemålet")
        rejection_triggers.append("rente-/durationrisiko blir for høy for ønsket rolle")
    else:
        triggers_positive.append("fondet viser bedre kostnad, risiko og benchmark-bilde enn nærmeste alternativer")
        rejection_triggers.append("datakvalitet, kostnad eller risiko svekker beslutningsgrunnlaget")

    if cost_score is not None and cost_score < 65:
        triggers_positive.append("lavere løpende kostnad eller tydeligere kostnadsfordel")
    if benchmark_score is not None and benchmark_score < 65:
        triggers_positive.append("bedre benchmark-sammenligning i valgt periode")
    if risk_score is not None and risk_score < 60:
        triggers_positive.append("lavere drawdown eller mer stabil volatilitet")
        rejection_triggers.append("drawdown forverres uten kompenserende avkastning")
    if return_score is not None and return_score < 60:
        triggers_positive.append("sterkere historikk uten økt risiko")

    # keep lists concise and stable while preserving order
    def _uniq(items: Sequence[str], limit: int) -> List[str]:
        out: List[str] = []
        seen = set()
        for item in items:
            txt = str(item).strip()
            if not txt:
                continue
            key = txt.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(txt)
            if len(out) >= limit:
                break
        return out

    strengths = _uniq(strengths or ["ingen tydelig styrke funnet i tilgjengelige data"], 5)
    weaknesses = _uniq(weaknesses or ["ingen store røde flagg i tilgjengelige data"], 5)
    triggers_positive = _uniq(triggers_positive, 5)
    rejection_triggers = _uniq(rejection_triggers, 5)

    if quality >= 75:
        short = f"{name} rangeres høyt fordi flere uavhengige faktorer støtter samme konklusjon."
    elif quality >= 60:
        short = f"{name} er en brukbar kandidat, men bør sammenlignes mot alternativer før valg."
    else:
        short = f"{name} krever mer bevis før fondet bør prioriteres."

    if peer_symbol:
        competitor_note = f"Sammenlignes særlig mot {peer_symbol}: fondet må vinne på kostnad, risikojustert avkastning eller rolle-fit."
    else:
        competitor_note = "Sammenlign mot nærmeste alternativ: fondet bør vinne på kostnad, risikojustert avkastning eller porteføljerolle."

    return {
        "layer": "Layer 2",
        "model": "Explainable Fund Intelligence",
        "symbol": symbol,
        "name": name,
        "fund_type": fund_type,
        "decision_quality": round(quality, 1),
        "base_score": round(base_score, 1),
        "grade": grade,
        "decision": decision,
        "recommended_role": role,
        "short_explanation": short,
        "why_ranked_here": strengths,
        "what_holds_it_back": weaknesses,
        "what_would_make_it_selected": triggers_positive,
        "what_would_make_model_reject_it": rejection_triggers,
        "competitor_note": competitor_note,
        "metric_context": {
            "expense_ratio_pct": expense,
            "excess_return_pct": excess,
            "max_drawdown_pct": drawdown,
            "component_scores": components,
        },
        "holdings_ready": False,
        "insider_ready": False,
        "summary": f"{decision}. {strengths[0]} Svakeste punkt: {weaknesses[0]}",
    }



# v18.5.52 / Layer 3: Holdings-Aware Fund Analysis.
# Reads optional holdings from the fund data payload. No external call is made
# here, so the layer is deterministic, testable and safe for offline/demo data.
def build_holdings_aware_profile(data: Optional[Mapping[str, Any]], *, fund_symbol: str = "") -> Dict[str, Any]:
    raw_holdings = []
    if data:
        raw_holdings = data.get("holdings") or data.get("top_holdings") or data.get("portfolio") or []
    holdings: List[Dict[str, Any]] = []
    for item in raw_holdings or []:
        if not isinstance(item, Mapping):
            continue
        sym = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
        name = str(item.get("name") or item.get("company") or sym or "Ukjent").strip()
        weight = _safe_float(item.get("weight_pct") or item.get("weight") or item.get("pct"), None)
        if weight is not None and 0 < weight <= 1.0:
            weight *= 100.0
        sector = str(item.get("sector") or item.get("industry") or "Ukjent").strip()
        geography = str(item.get("geography") or item.get("country") or item.get("region") or "Ukjent").strip()
        market_cap = str(item.get("market_cap") or item.get("market_cap_category") or item.get("size") or "Ukjent").strip()
        if not sym and not name:
            continue
        holdings.append({
            "symbol": sym,
            "name": name,
            "weight_pct": None if weight is None else round(float(weight), 3),
            "sector": sector or "Ukjent",
            "geography": geography or "Ukjent",
            "market_cap_category": market_cap or "Ukjent",
        })
    holdings = sorted(holdings, key=lambda h: _safe_float(h.get("weight_pct"), 0.0) or 0.0, reverse=True)
    top10 = holdings[:10]
    top10_weight = round(sum(_safe_float(h.get("weight_pct"), 0.0) or 0.0 for h in top10), 2)
    top3_weight = round(sum(_safe_float(h.get("weight_pct"), 0.0) or 0.0 for h in top10[:3]), 2)

    sector_weights: Dict[str, float] = {}
    geography_weights: Dict[str, float] = {}
    megacap_weight = 0.0
    for h in holdings:
        w = _safe_float(h.get("weight_pct"), 0.0) or 0.0
        sector_weights[h.get("sector") or "Ukjent"] = sector_weights.get(h.get("sector") or "Ukjent", 0.0) + w
        geography_weights[h.get("geography") or "Ukjent"] = geography_weights.get(h.get("geography") or "Ukjent", 0.0) + w
        mcap = str(h.get("market_cap_category") or "").lower()
        if any(x in mcap for x in ["mega", "large", "stor"]):
            megacap_weight += w

    sector_weights = {k: round(v, 2) for k, v in sorted(sector_weights.items(), key=lambda kv: kv[1], reverse=True)}
    geography_weights = {k: round(v, 2) for k, v in sorted(geography_weights.items(), key=lambda kv: kv[1], reverse=True)}
    largest_sector = next(iter(sector_weights.items()), ("Ukjent", 0.0))
    largest_geo = next(iter(geography_weights.items()), ("Ukjent", 0.0))

    vulnerabilities: List[str] = []
    strengths: List[str] = []
    if not holdings:
        vulnerabilities.append("holdings-data mangler; porteføljen kan ikke sårbarhetsvurderes")
        concentration_score = 50.0
    else:
        if top10_weight >= 55:
            vulnerabilities.append("høy konsentrasjon i topp 10-posisjoner")
        elif top10_weight <= 30:
            strengths.append("topp-posisjonene er relativt spredt")
        if top3_weight >= 25:
            vulnerabilities.append("stor avhengighet av de tre største posisjonene")
        if largest_sector[1] >= 35:
            vulnerabilities.append(f"sektorkonsentrasjon mot {largest_sector[0]}")
        if largest_geo[1] >= 70:
            vulnerabilities.append(f"geografisk konsentrasjon mot {largest_geo[0]}")
        if megacap_weight >= 45:
            vulnerabilities.append("betydelig megacap-avhengighet")
        concentration_score = _clamp(100.0 - top10_weight * 0.75 - top3_weight * 0.55, 5.0, 100.0)
        if not vulnerabilities:
            strengths.append("ingen tydelig enkeltsårbarhet i tilgjengelige topp-holdings")

    if concentration_score >= 70:
        risk_label = "Lav/middels"
    elif concentration_score >= 50:
        risk_label = "Middels"
    else:
        risk_label = "Høy"
    summary = "Holdings-data mangler." if not holdings else f"Topp 10 utgjør {top10_weight}% av kjente holdings; største sektor er {largest_sector[0]} ({largest_sector[1]}%)."
    return {
        "layer": "Layer 3",
        "model": "Holdings-Aware Fund Analysis",
        "fund_symbol": fund_symbol,
        "holdings_available": bool(holdings),
        "holdings_count": len(holdings),
        "top_holdings": top10,
        "top10_weight_pct": top10_weight,
        "top3_weight_pct": top3_weight,
        "sector_weights": sector_weights,
        "geography_weights": geography_weights,
        "megacap_weight_pct": round(megacap_weight, 2),
        "concentration_score": round(concentration_score, 1),
        "concentration_risk": risk_label,
        "strengths": strengths,
        "vulnerabilities": vulnerabilities,
        "summary": summary,
    }


# v18.5.53 / Layer 4: Insider Intelligence for top holdings.
# The layer accepts optional per-holding insider events in the same data payload:
# insider_events={"AAPL":[{"type":"buy","role":"CEO","value":...}, ...]}.
def build_holdings_insider_profile(holdings_profile: Mapping[str, Any], data: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    events_by_symbol = {}
    if data:
        events_by_symbol = data.get("insider_events") or data.get("insider") or data.get("insider_signals") or {}
    if not isinstance(events_by_symbol, Mapping):
        events_by_symbol = {}

    rows: List[Dict[str, Any]] = []
    score_points = 0.0
    weighted_signal = 0.0
    covered_weight = 0.0
    for h in (holdings_profile.get("top_holdings") or [])[:10]:
        sym = str(h.get("symbol") or "").upper()
        weight = _safe_float(h.get("weight_pct"), 0.0) or 0.0
        raw_events = events_by_symbol.get(sym) or events_by_symbol.get(sym.lower()) or []
        if isinstance(raw_events, Mapping):
            raw_events = [raw_events]
        buys = sells = neutral = 0
        exec_weight = 0.0
        notes: List[str] = []
        for ev in raw_events or []:
            if not isinstance(ev, Mapping):
                continue
            typ = str(ev.get("type") or ev.get("transaction_type") or ev.get("side") or "").lower()
            role = str(ev.get("role") or ev.get("insider_role") or "").lower()
            val = _safe_float(ev.get("value") or ev.get("shares") or ev.get("amount"), 1.0) or 1.0
            role_boost = 1.35 if any(x in role for x in ["ceo", "cfo", "chair", "styreleder"]) else 1.0
            magnitude = min(3.0, max(0.5, math.log10(abs(val) + 10.0) / 3.0)) * role_boost
            if "buy" in typ or "kjøp" in typ or typ == "purchase":
                buys += 1
                exec_weight += magnitude
            elif "sell" in typ or "salg" in typ or typ == "sale":
                sells += 1
                exec_weight -= magnitude
            else:
                neutral += 1
        if buys >= 2 and sells == 0:
            notes.append("cluster buying")
        if sells >= 2 and buys == 0:
            notes.append("cluster selling")
        if exec_weight > 0.75:
            direction = "Positiv"
            contribution = min(1.0, exec_weight / 4.0)
        elif exec_weight < -0.75:
            direction = "Negativ"
            contribution = max(-1.0, exec_weight / 4.0)
        else:
            direction = "Nøytral"
            contribution = 0.0
        if raw_events:
            covered_weight += weight
            weighted_signal += contribution * weight
        rows.append({
            "symbol": sym,
            "name": h.get("name"),
            "weight_pct": weight,
            "buy_count": buys,
            "sell_count": sells,
            "neutral_count": neutral,
            "direction": direction,
            "signal_strength": round(contribution, 3),
            "notes": notes,
        })
        score_points += contribution

    if covered_weight > 0:
        net = weighted_signal / covered_weight
    else:
        net = 0.0
    if net >= 0.18:
        direction = "Positiv"
    elif net <= -0.18:
        direction = "Negativ"
    else:
        direction = "Nøytral"
    score = round(_clamp(50.0 + net * 45.0, 0.0, 100.0), 1)
    positives = [r for r in rows if r.get("direction") == "Positiv"]
    negatives = [r for r in rows if r.get("direction") == "Negativ"]
    summary = "Ingen insiderdata for topp-posisjonene." if covered_weight <= 0 else f"Insiderbildet peker {direction.lower()} for de største posisjonene med {round(covered_weight, 1)}% dekket vekt."
    return {
        "layer": "Layer 4",
        "model": "Insider Intelligence Layer",
        "direction": direction,
        "insider_score": score,
        "covered_top_holdings_weight_pct": round(covered_weight, 2),
        "positive_holdings": [r.get("symbol") for r in positives],
        "negative_holdings": [r.get("symbol") for r in negatives],
        "rows": rows,
        "summary": summary,
    }


# v18.5.54 / Layer 5: Composite Intelligence Score.
# This is the orchestration layer. It combines Layer 1 base score, decision
# quality, Layer 3 holdings and Layer 4 insider direction into one transparent
# score while keeping every subscore visible for debugging and UI explanation.
def build_composite_fund_intelligence_profile(
    row: Mapping[str, Any],
    holdings_profile: Optional[Mapping[str, Any]] = None,
    insider_profile: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    r = dict(row or {})
    holdings = dict(holdings_profile or r.get("holdings_profile") or {})
    insider = dict(insider_profile or r.get("insider_holdings_profile") or {})

    base = _safe_float(r.get("base_score"), None)
    decision = _safe_float(r.get("decision_quality"), None)
    holdings_score = _safe_float(holdings.get("concentration_score"), None) if holdings.get("holdings_available") else None
    insider_score = _safe_float(insider.get("insider_score"), None) if (insider.get("covered_top_holdings_weight_pct") or 0) > 0 else None

    candidates = {
        "base": {"score": base, "weight": 0.35, "label": "grunnscore"},
        "decision": {"score": decision, "weight": 0.30, "label": "beslutningskvalitet"},
        "holdings": {"score": holdings_score, "weight": 0.20, "label": "holdings-kvalitet"},
        "insider": {"score": insider_score, "weight": 0.15, "label": "insiderbilde"},
    }
    available = {k: v for k, v in candidates.items() if v["score"] is not None}
    weight_sum = sum(float(v["weight"]) for v in available.values()) or 1.0
    normalized_weights = {k: round(float(v["weight"]) / weight_sum, 3) for k, v in available.items()}
    raw = sum(float(v["score"]) * normalized_weights[k] for k, v in available.items()) if available else 0.0

    adjustments: List[str] = []
    if holdings.get("holdings_available"):
        conc = _safe_float(holdings.get("concentration_score"), 50.0) or 50.0
        if conc < 45:
            adjustments.append("holdings-konsentrasjon trekker ned")
        elif conc > 70:
            adjustments.append("spredte holdings støtter scoren")
    else:
        adjustments.append("holdings-data mangler og vekten fordeles på andre lag")

    if insider_score is not None:
        if insider.get("direction") == "Positiv":
            adjustments.append("insiderbildet i topp-posisjoner peker positivt")
        elif insider.get("direction") == "Negativ":
            adjustments.append("insiderbildet i topp-posisjoner peker negativt")
        else:
            adjustments.append("insiderbildet i topp-posisjoner er nøytralt/blandet")
    else:
        adjustments.append("insiderdata mangler og vekten fordeles på andre lag")

    data_score = _safe_float(r.get("data_quality"), 50.0) or 50.0
    if data_score < 45:
        raw = min(raw, 55.0)
        adjustments.append("svak datakvalitet begrenser composite score")

    score = round(_clamp(raw), 1)
    if score >= 75:
        verdict = "Sterk samlet fondsintelligens"
    elif score >= 60:
        verdict = "Brukbar samlet fondsintelligens"
    else:
        verdict = "Svak samlet fondsintelligens"

    strongest = None
    weakest = None
    if available:
        strongest = max(available.items(), key=lambda kv: float(kv[1]["score"]))[1]["label"]
        weakest = min(available.items(), key=lambda kv: float(kv[1]["score"]))[1]["label"]
    summary = f"{verdict}: sterkest på {strongest or 'ukjent'}, svakest på {weakest or 'ukjent'}."
    coverage = {
        "base": base is not None,
        "decision": decision is not None,
        "holdings": holdings_score is not None,
        "insider": insider_score is not None,
    }
    return {
        "layer": "Layer 5",
        "model": "Composite Fund Intelligence Score",
        "fund_intelligence_score": score,
        "composite_score": score,
        "verdict": verdict,
        "summary": summary,
        "components": {
            "base_score": None if base is None else round(base, 1),
            "decision_quality": None if decision is None else round(decision, 1),
            "holdings_score": None if holdings_score is None else round(holdings_score, 1),
            "insider_score": None if insider_score is None else round(insider_score, 1),
        },
        "weights": normalized_weights,
        "coverage": coverage,
        "adjustments": adjustments,
        "strongest_layer": strongest,
        "weakest_layer": weakest,
    }


def apply_holdings_and_insider_adjustment(row: Dict[str, Any], data: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    holdings = build_holdings_aware_profile(data, fund_symbol=str(row.get("symbol") or ""))
    insider = build_holdings_insider_profile(holdings, data)
    composite = build_composite_fund_intelligence_profile(row, holdings, insider)
    row["holdings_profile"] = holdings
    row["insider_holdings_profile"] = insider
    row["composite_intelligence_profile"] = composite
    row["fund_intelligence_score"] = composite.get("fund_intelligence_score")
    row["composite_score"] = composite.get("composite_score")
    row["intelligence_adjustments"] = list(composite.get("adjustments") or [])
    row["holdings_summary"] = holdings.get("summary")
    row["insider_summary"] = insider.get("summary")
    row["composite_summary"] = composite.get("summary")
    # Layer 7 scenario/regime is derived after Layer 5, so it can reuse the full
    # row context without altering the core composite score yet.
    row = apply_scenario_regime_layer(row)
    if row["intelligence_adjustments"]:
        row.setdefault("reasons_caution", [])
        if insider.get("direction") == "Negativ":
            row["reasons_caution"].append("negativt insiderbilde i topp-posisjoner")
        row.setdefault("reasons_positive", [])
        if insider.get("direction") == "Positiv":
            row["reasons_positive"].append("positivt insiderbilde i topp-posisjoner")
    return row


# v18.5.56 / Layer 7: Scenario & Regime Engine.
# Scores how each fund may behave under common market regimes. This is not a
# forecast; it is a sensitivity map based on fund type, duration, risk, holdings
# concentration and insider/credit context.
SCENARIO_REGIMES: Dict[str, Dict[str, Any]] = {
    "rentefall": {"label": "Rentefall", "description": "Fallende renter / lavere lange renter."},
    "renteokning": {"label": "Renteøkning", "description": "Stigende renter / høyere lange renter."},
    "resesjon": {"label": "Resesjon", "description": "Svak vekst, høyere krav til kvalitet og lavere risikovilje."},
    "inflasjon": {"label": "Inflasjon", "description": "Vedvarende prispress og press på rentekurven."},
    "kredittstress": {"label": "Kredittstress", "description": "Spread-utvidelse, likviditetsstress og høyere misligholdsrisiko."},
    "tech_ai_selloff": {"label": "Tech/AI-selloff", "description": "Fall i teknologi-, AI- og megacap-ledere."},
    "risk_on": {"label": "Risk-on", "description": "Bedre risikovilje og jakt på avkastning."},
}


def _scenario_band(score: float) -> str:
    if score >= 70:
        return "Robust/positiv"
    if score >= 52:
        return "Nøytral/blandet"
    return "Sårbar"


def _scenario_add(base: float, points: float, reason: str, reasons: List[str]) -> float:
    reasons.append(reason)
    return base + points


def build_scenario_regime_profile(row: Mapping[str, Any]) -> Dict[str, Any]:
    r = dict(row or {})
    ftype = str(r.get("fund_type") or "")
    duration = _safe_float(r.get("duration"), None)
    vol = _safe_float(r.get("volatility_pct"), None)
    dd = _safe_float(r.get("max_drawdown_pct"), None)
    risk_score = _safe_float(r.get("risk_score"), 50.0) or 50.0
    holdings = dict(r.get("holdings_profile") or {})
    insider = dict(r.get("insider_holdings_profile") or {})
    sector_weights = dict(holdings.get("sector_weights") or {})
    megacap_weight = _safe_float(holdings.get("megacap_weight_pct"), 0.0) or 0.0
    concentration = _safe_float(holdings.get("concentration_score"), None)
    tech_weight = 0.0
    for k, v in sector_weights.items():
        name = str(k).lower()
        if any(x in name for x in ["tech", "teknologi", "information technology", "kommunikasjon", "communication"]):
            tech_weight += _safe_float(v, 0.0) or 0.0
    insider_dir = str(insider.get("direction") or "Nøytral")

    rows: Dict[str, Dict[str, Any]] = {}
    for key, meta in SCENARIO_REGIMES.items():
        score = 55.0
        reasons: List[str] = []
        if key == "rentefall":
            if ftype in DEFENSIVE_FIXED_INCOME_TYPES and duration is not None and duration >= 6:
                score = _scenario_add(score, 22, "lang durasjon kan få medvind ved rentefall", reasons)
            elif ftype in DEFENSIVE_FIXED_INCOME_TYPES:
                score = _scenario_add(score, 10, "rente-/obligasjonsprofil kan støttes av lavere renter", reasons)
            if ftype == "High yield-fond":
                score = _scenario_add(score, 3, "lavere renter hjelper, men kredittrisiko dominerer fortsatt", reasons)
        elif key == "renteokning":
            if ftype in DEFENSIVE_FIXED_INCOME_TYPES and duration is not None and duration >= 6:
                score = _scenario_add(score, -24, "lang durasjon er sårbar ved renteøkning", reasons)
            elif ftype == "Pengemarkedsfond":
                score = _scenario_add(score, 18, "kort pengemarkedsprofil er normalt mer robust ved renteøkning", reasons)
            elif ftype in DEFENSIVE_FIXED_INCOME_TYPES:
                score = _scenario_add(score, -8, "renteeksponering kan trekke ned", reasons)
        elif key == "resesjon":
            if ftype == "High yield-fond":
                score = _scenario_add(score, -24, "high yield er sårbart når misligholdsrisiko og spreads øker", reasons)
            if ftype == "Pengemarkedsfond":
                score = _scenario_add(score, 20, "likviditetsnær profil er defensiv i resesjon", reasons)
            if risk_score >= 70:
                score = _scenario_add(score, 8, "historisk risiko/drawdown ser relativt kontrollert ut", reasons)
            elif risk_score < 45:
                score = _scenario_add(score, -12, "svak risikoscore gjør fondet mer sårbart i resesjon", reasons)
        elif key == "inflasjon":
            if ftype in DEFENSIVE_FIXED_INCOME_TYPES and duration is not None and duration >= 6:
                score = _scenario_add(score, -18, "lang durasjon presses ofte av inflasjon/renteuro", reasons)
            if ftype == "Pengemarkedsfond":
                score = _scenario_add(score, 10, "kort renteprofil repriser raskere", reasons)
            if ftype in {"ETF", "Indeksfond", "Fond", "Aktivt fond"}:
                score = _scenario_add(score, -4, "bred aksjeeksponering kan være blandet ved inflasjon", reasons)
        elif key == "kredittstress":
            if ftype == "High yield-fond":
                score = _scenario_add(score, -32, "high yield er direkte utsatt for spread-utvidelse", reasons)
            elif ftype == "Rente-/obligasjonsfond":
                score = _scenario_add(score, -10, "kredittdelen i obligasjoner kan presses", reasons)
            elif ftype == "Pengemarkedsfond":
                score = _scenario_add(score, 8, "kort likviditetsnær profil kan dempe kredittstress", reasons)
        elif key == "tech_ai_selloff":
            if tech_weight >= 30 or megacap_weight >= 45:
                score = _scenario_add(score, -24, "stor teknologi/megacap-avhengighet gir selloff-sårbarhet", reasons)
            elif tech_weight >= 15:
                score = _scenario_add(score, -10, "noe teknologieksponering kan trekke ned", reasons)
            else:
                score = _scenario_add(score, 6, "lav kjent teknologi/megacap-konsentrasjon demper scenarioet", reasons)
        elif key == "risk_on":
            if ftype == "High yield-fond":
                score = _scenario_add(score, 18, "risk-on kan gi støtte til high yield-spreads", reasons)
            if ftype in {"ETF", "Indeksfond", "Fond", "Aktivt fond"} and risk_score >= 55:
                score = _scenario_add(score, 8, "risikoaktiva kan få medvind når risikoviljen bedres", reasons)
            if ftype == "Pengemarkedsfond":
                score = _scenario_add(score, -6, "likviditetsbuffer kan henge etter i risk-on", reasons)

        if concentration is not None and concentration < 45 and key in {"resesjon", "tech_ai_selloff", "kredittstress"}:
            score = _scenario_add(score, -7, "holdings-konsentrasjon øker sårbarheten i stress-scenario", reasons)
        if dd is not None and dd < -20 and key in {"resesjon", "kredittstress", "tech_ai_selloff"}:
            score = _scenario_add(score, -6, "historisk drawdown tyder på svakere stressrobusthet", reasons)
        if vol is not None and vol > 20 and key in {"resesjon", "kredittstress"}:
            score = _scenario_add(score, -5, "høy volatilitet øker stressrisiko", reasons)
        if insider_dir == "Positiv" and key in {"risk_on", "resesjon"}:
            score = _scenario_add(score, 4, "positivt insiderbilde i topp-posisjoner gir litt støtte", reasons)
        elif insider_dir == "Negativ" and key in {"risk_on", "resesjon", "tech_ai_selloff"}:
            score = _scenario_add(score, -5, "negativt insiderbilde i topp-posisjoner trekker ned", reasons)

        score = round(_clamp(score, 0.0, 100.0), 1)
        rows[key] = {
            "scenario": key,
            "label": meta["label"],
            "description": meta["description"],
            "score": score,
            "band": _scenario_band(score),
            "drivers": reasons[:5] or ["ingen tydelig scenario-driver i tilgjengelige data"],
        }

    best = max(rows.values(), key=lambda x: float(x["score"])) if rows else None
    worst = min(rows.values(), key=lambda x: float(x["score"])) if rows else None
    scenario_score = round(sum(float(x["score"]) for x in rows.values()) / max(1, len(rows)), 1)
    summary = f"Mest robust i {best['label']} og mest sårbar i {worst['label']}." if best and worst else "Scenarioanalyse mangler."
    return {
        "layer": "Layer 7",
        "model": "Scenario & Regime Engine",
        "scenario_score": scenario_score,
        "best_scenario": None if not best else {"key": best["scenario"], "label": best["label"], "score": best["score"]},
        "worst_scenario": None if not worst else {"key": worst["scenario"], "label": worst["label"], "score": worst["score"]},
        "scenarios": rows,
        "summary": summary,
    }


def apply_scenario_regime_layer(row: Dict[str, Any]) -> Dict[str, Any]:
    scenario = build_scenario_regime_profile(row)
    row["scenario_regime_profile"] = scenario
    row["scenario_score"] = scenario.get("scenario_score")
    row["scenario_summary"] = scenario.get("summary")
    worst = scenario.get("worst_scenario") or {}
    best = scenario.get("best_scenario") or {}
    if worst:
        row.setdefault("reasons_caution", [])
        caution = f"mest sårbar i scenario: {worst.get('label')}"
        if caution not in row["reasons_caution"]:
            row["reasons_caution"].append(caution)
    if best:
        row.setdefault("reasons_positive", [])
        pos = f"mest robust i scenario: {best.get('label')}"
        if pos not in row["reasons_positive"]:
            row["reasons_positive"].append(pos)
    return row


# v18.5.55 / Layer 6: What Changed Intelligence.
# Stores compact run snapshots and compares the current analysis against the
# most recent comparable run. This makes the fund screener behave like a living
# research assistant: it can explain what changed since last time, not just what
# ranks highest now.
SNAPSHOT_DIR = Path("storage") / "analysis_snapshots"
SNAPSHOT_SCHEMA_VERSION = 1


def _slug_part(value: Any, fallback: str = "all") -> str:
    raw = str(value or fallback).strip().lower()
    out = []
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_", "/"}:
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or fallback


def _snapshot_context_key(fund_type: str, objective: str, symbols: Sequence[str]) -> str:
    universe_sig = "_".join(sorted(str(s).upper() for s in (symbols or []) if s))[:64] or "manual"
    return f"{_slug_part(fund_type)}__{_slug_part(objective)}__{_slug_part(universe_sig, 'universe')}"


def _compact_fund_snapshot_row(row: Mapping[str, Any], rank: int) -> Dict[str, Any]:
    holdings = dict(row.get("holdings_profile") or {})
    insider = dict(row.get("insider_holdings_profile") or {})
    explain = dict(row.get("explainability_profile") or {})
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "name": row.get("name"),
        "rank": rank,
        "fund_type": row.get("fund_type"),
        "decision": row.get("decision"),
        "grade": row.get("grade"),
        "fund_intelligence_score": row.get("fund_intelligence_score"),
        "decision_quality": row.get("decision_quality"),
        "base_score": row.get("base_score"),
        "data_quality": row.get("data_quality"),
        "holdings_score": holdings.get("concentration_score"),
        "insider_direction": insider.get("direction"),
        "insider_score": insider.get("insider_score"),
        "scenario_score": row.get("scenario_score"),
        "worst_scenario": (row.get("scenario_regime_profile") or {}).get("worst_scenario"),
        "positive_drivers": list((explain.get("why_ranked_here") or row.get("reasons_positive") or [])[:5]),
        "risk_flags": list((explain.get("what_holds_it_back") or row.get("reasons_caution") or [])[:6]),
        "summary": row.get("composite_summary") or row.get("explainability_summary") or row.get("base_score_summary"),
    }


def build_fund_analysis_snapshot(result: Mapping[str, Any]) -> Dict[str, Any]:
    ranked = list(result.get("ranked") or [])
    symbols = list(result.get("symbols") or [r.get("symbol") for r in ranked])
    context_key = _snapshot_context_key(str(result.get("fund_type") or "Alle"), str(result.get("objective") or "Balansert"), symbols)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "version": get_app_version(),
        "created_at": _now_iso(),
        "context_key": context_key,
        "fund_type": result.get("fund_type"),
        "objective": result.get("objective"),
        "test_mode": result.get("test_mode"),
        "benchmark_symbol": result.get("benchmark_symbol"),
        "symbols": symbols,
        "summary": dict(result.get("summary") or {}),
        "ranked": [_compact_fund_snapshot_row(row, idx) for idx, row in enumerate(ranked, start=1)],
    }


def _snapshot_path(snapshot: Mapping[str, Any]) -> Path:
    created = str(snapshot.get("created_at") or _now_iso()).replace(":", "").replace("+", "_").replace(".", "_")
    return SNAPSHOT_DIR / f"fund_analysis__{snapshot.get('context_key') or 'context'}__{created}.json"


def save_fund_analysis_snapshot(result: Mapping[str, Any], *, snapshot_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    try:
        snap = build_fund_analysis_snapshot(result)
        directory = Path(snapshot_dir) if snapshot_dir else SNAPSHOT_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / _snapshot_path(snap).name
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {"path": str(path), "snapshot": snap}
    except Exception as exc:
        return {"error": str(exc)[:200]}


def load_latest_fund_analysis_snapshot(context_key: str, *, snapshot_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    try:
        directory = Path(snapshot_dir) if snapshot_dir else SNAPSHOT_DIR
        if not directory.exists():
            return None
        files = sorted(directory.glob(f"fund_analysis__{context_key}__*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    except Exception:
        return None
    return None


def _delta_label(delta: float, positive_word: str = "opp", negative_word: str = "ned") -> str:
    if delta > 0:
        return f"{positive_word} {round(abs(delta), 1)}"
    if delta < 0:
        return f"{negative_word} {round(abs(delta), 1)}"
    return "uendret"


def build_what_changed_profile(current_result: Mapping[str, Any], previous_snapshot: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    current_rows = [_compact_fund_snapshot_row(row, idx) for idx, row in enumerate(list(current_result.get("ranked") or []), start=1)]
    if not previous_snapshot:
        return {
            "layer": "Layer 6",
            "model": "What Changed Intelligence",
            "has_previous": False,
            "summary": "Ingen tidligere sammenlignbar analyse funnet. Denne kjøringen lagres som første snapshot.",
            "rank_movers": [],
            "score_movers": [],
            "new_funds": [r.get("symbol") for r in current_rows[:10]],
            "removed_funds": [],
            "risk_flag_changes": [],
            "insider_direction_changes": [],
        }

    prev_rows = {str(r.get("symbol") or "").upper(): dict(r) for r in (previous_snapshot.get("ranked") or [])}
    cur_rows = {str(r.get("symbol") or "").upper(): dict(r) for r in current_rows}
    rank_movers: List[Dict[str, Any]] = []
    score_movers: List[Dict[str, Any]] = []
    risk_flag_changes: List[Dict[str, Any]] = []
    insider_changes: List[Dict[str, Any]] = []

    for sym, cur in cur_rows.items():
        prev = prev_rows.get(sym)
        if not prev:
            continue
        cur_rank = int(cur.get("rank") or 0)
        prev_rank = int(prev.get("rank") or 0)
        rank_delta = prev_rank - cur_rank  # positive means improved rank
        cur_score = _safe_float(cur.get("fund_intelligence_score"), None)
        prev_score = _safe_float(prev.get("fund_intelligence_score"), None)
        score_delta = None if cur_score is None or prev_score is None else round(cur_score - prev_score, 1)
        if abs(rank_delta) >= 1:
            rank_movers.append({
                "symbol": sym,
                "name": cur.get("name"),
                "previous_rank": prev_rank,
                "current_rank": cur_rank,
                "rank_delta": rank_delta,
                "direction": "opp" if rank_delta > 0 else "ned",
                "explanation": f"{sym} gikk {'opp' if rank_delta > 0 else 'ned'} fra rang {prev_rank} til {cur_rank}.",
            })
        if score_delta is not None and abs(score_delta) >= 3:
            score_movers.append({
                "symbol": sym,
                "name": cur.get("name"),
                "previous_score": prev_score,
                "current_score": cur_score,
                "score_delta": score_delta,
                "explanation": f"Intelligensscore {_delta_label(score_delta)} poeng siden sist.",
            })
        prev_flags = set(str(x) for x in (prev.get("risk_flags") or []))
        cur_flags = set(str(x) for x in (cur.get("risk_flags") or []))
        added = sorted(cur_flags - prev_flags)[:4]
        removed = sorted(prev_flags - cur_flags)[:4]
        if added or removed:
            risk_flag_changes.append({"symbol": sym, "name": cur.get("name"), "added": added, "removed": removed})
        if prev.get("insider_direction") != cur.get("insider_direction"):
            insider_changes.append({
                "symbol": sym,
                "name": cur.get("name"),
                "previous_direction": prev.get("insider_direction"),
                "current_direction": cur.get("insider_direction"),
                "explanation": f"Insiderbildet endret seg fra {prev.get('insider_direction') or 'ukjent'} til {cur.get('insider_direction') or 'ukjent'}.",
            })

    rank_movers.sort(key=lambda r: abs(int(r.get("rank_delta") or 0)), reverse=True)
    score_movers.sort(key=lambda r: abs(float(r.get("score_delta") or 0)), reverse=True)
    new_funds = sorted(set(cur_rows) - set(prev_rows))
    removed_funds = sorted(set(prev_rows) - set(cur_rows))
    pieces = []
    if rank_movers:
        top = rank_movers[0]
        pieces.append(top.get("explanation"))
    if score_movers:
        top = score_movers[0]
        pieces.append(f"Største scoreendring: {top.get('symbol')} {top.get('explanation')}")
    if insider_changes:
        pieces.append(f"{len(insider_changes)} fond fikk endret insiderretning.")
    if risk_flag_changes:
        pieces.append(f"{len(risk_flag_changes)} fond fikk endrede risikoflagg.")
    summary = " ".join(pieces) if pieces else "Ingen store endringer siden forrige sammenlignbare analyse."
    return {
        "layer": "Layer 6",
        "model": "What Changed Intelligence",
        "has_previous": True,
        "previous_created_at": previous_snapshot.get("created_at"),
        "summary": summary,
        "rank_movers": rank_movers[:10],
        "score_movers": score_movers[:10],
        "new_funds": new_funds[:20],
        "removed_funds": removed_funds[:20],
        "risk_flag_changes": risk_flag_changes[:10],
        "insider_direction_changes": insider_changes[:10],
    }


def attach_and_store_what_changed(result: Dict[str, Any], *, snapshot_dir: Optional[Path] = None) -> Dict[str, Any]:
    try:
        snapshot = build_fund_analysis_snapshot(result)
        previous = load_latest_fund_analysis_snapshot(str(snapshot.get("context_key") or ""), snapshot_dir=snapshot_dir)
        profile = build_what_changed_profile(result, previous)
        result["what_changed_profile"] = profile
        result["what_changed_summary"] = profile.get("summary")
        stored = save_fund_analysis_snapshot(result, snapshot_dir=snapshot_dir)
        result["snapshot_storage"] = {"stored": bool(stored and not stored.get("error")), **(stored or {})}
    except Exception as exc:
        result["what_changed_profile"] = {"layer": "Layer 6", "model": "What Changed Intelligence", "has_previous": False, "summary": "What Changed kunne ikke beregnes.", "error": str(exc)[:200]}
        result["what_changed_summary"] = result["what_changed_profile"].get("summary")
    return result

def _active_evidence_test(
    *,
    fund_type: str,
    total_return: Optional[float],
    benchmark_return: Optional[float],
    expense: Optional[float],
    volatility: Optional[float],
    benchmark_volatility: Optional[float] = None,
) -> Dict[str, Any]:
    """Assess whether an active fund has proven enough value after costs.

    This is intentionally conservative: active funds should not score highly just
    because absolute return is positive. They need acceptable excess return vs a
    relevant benchmark, after considering fee drag and extra risk.
    """
    if fund_type != "Aktivt fond":
        return {
            "status": "Ikke relevant",
            "score": None,
            "excess_return_pct": None if total_return is None or benchmark_return is None else round(total_return - benchmark_return, 2),
            "risk_penalty_pct": 0.0,
            "fee_drag_pct": None if expense is None else round(expense, 3),
            "message": "Ikke aktivt fond/aktiv ETF.",
        }
    if total_return is None or benchmark_return is None:
        return {
            "status": "Mangler data",
            "score": 35.0,
            "excess_return_pct": None,
            "risk_penalty_pct": None,
            "fee_drag_pct": None if expense is None else round(expense, 3),
            "message": "Mangler historikk eller benchmark for å bevise aktiv merverdi.",
        }
    excess = float(total_return) - float(benchmark_return)
    fee_drag = float(expense or 0.0)
    risk_penalty = 0.0
    if volatility is not None and benchmark_volatility is not None:
        risk_penalty = max(0.0, float(volatility) - float(benchmark_volatility)) * 0.20
    # Conservative evidence score. Need positive excess above fees and not too much extra risk.
    evidence_score = _clamp(50.0 + (excess * 2.0) - (fee_drag * 10.0) - risk_penalty, 0.0, 100.0)
    net_edge = excess - fee_drag - risk_penalty
    if evidence_score >= 68.0 and net_edge > 0.5:
        status = "Godkjent"
        msg = "Har foreløpig bevist aktiv merverdi mot benchmark etter kostnad/riskojustering."
    elif evidence_score >= 52.0 and net_edge > -1.0:
        status = "Usikker"
        msg = "Noe aktiv merverdi, men ikke sterkt nok til høy tillit."
    else:
        status = "Ikke bevist"
        msg = "Har ikke bevist nok merverdi til å forsvare aktiv kostnad/risiko."
    return {
        "status": status,
        "score": round(evidence_score, 1),
        "excess_return_pct": round(excess, 2),
        "risk_penalty_pct": round(risk_penalty, 2),
        "fee_drag_pct": round(fee_drag, 3),
        "message": msg,
    }




def _fixed_income_profile(
    *,
    fund_type: str,
    data: Optional[Mapping[str, Any]],
    volatility: Optional[float],
    drawdown: Optional[float],
    expense: Optional[float],
) -> Dict[str, Any]:
    """Return a conservative profile for rente-, obligasjons- and high yield funds.

    The goal is to avoid treating high yield as ordinary low-risk bonds. Fields
    are best-effort: many free data sources lack yield/duration, so the profile
    exposes missing data instead of guessing.
    """
    if fund_type not in FIXED_INCOME_TYPES:
        return {"is_fixed_income": False, "category": "Ikke relevant"}
    data = data or {}
    duration = _safe_float(data.get("duration") or data.get("effectiveDuration") or data.get("averageDuration"), None)
    yield_pct = _safe_float(data.get("yield") or data.get("yield_pct") or data.get("trailingAnnualDividendYield") or data.get("annualYield"), None)
    if yield_pct is not None and 0 < yield_pct < 0.25:
        yield_pct *= 100.0
    credit = str(data.get("credit_quality") or data.get("creditQuality") or data.get("category") or "").upper()

    if fund_type == "Pengemarkedsfond":
        risk_level = "Lav"
        role = "Likviditetsbuffer"
        reason = "Kort rente-/pengemarkedsprofil; vurderes primært som kontant-/likviditetsnær plassering."
    elif fund_type == "Rente-/obligasjonsfond":
        if duration is not None and duration >= 7:
            risk_level = "Middels/høy"
            role = "Defensiv satellitt"
            reason = "Obligasjonsfond med høyere rentefølsomhet/durasjon."
        else:
            risk_level = "Lav/middels"
            role = "Defensiv komponent"
            reason = "Rente-/obligasjonsfond; vurderes mot durasjon, rente- og kredittrisiko."
    else:
        risk_level = "Høy kredittrisiko"
        role = "Kredittsatellitt"
        reason = "High yield bør ikke behandles som trygt rentefond; kredittrisiko og drawdown må vurderes særskilt."

    warnings: List[str] = []
    if fund_type == "High yield-fond":
        warnings.append("high yield er kredittsatellitt, ikke lavrisiko-grunnmur")
    if duration is None and fund_type != "High yield-fond":
        warnings.append("durasjon/rentefølsomhet mangler")
    if yield_pct is None:
        warnings.append("yield/løpende rente mangler")
    if volatility is not None and volatility > (12.0 if fund_type != "High yield-fond" else 18.0):
        warnings.append("volatilitet er høy for fondstypen")
    if drawdown is not None and drawdown < (-10.0 if fund_type != "High yield-fond" else -18.0):
        warnings.append("historisk drawdown er betydelig")
    if expense is not None and expense > (0.80 if fund_type != "High yield-fond" else 1.20):
        warnings.append("kostnaden er høy for rente-/kredittfond")

    return {
        "is_fixed_income": True,
        "category": fund_type,
        "risk_level": risk_level,
        "recommended_role": role,
        "reason": reason,
        "duration": None if duration is None else round(duration, 2),
        "yield_pct": None if yield_pct is None else round(yield_pct, 3),
        "credit_quality_hint": credit or None,
        "warnings": warnings,
    }


def build_fund_comparator(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build a compact fund-vs-fund comparison summary."""
    valid = [enrich_fund_identity(dict(r)) for r in (rows or []) if r]
    if not valid:
        return {"count": 0, "leaders": {}, "rows": [], "active_evidence": []}

    def _min_by(key: str):
        candidates = [r for r in valid if _safe_float(r.get(key), None) is not None]
        return min(candidates, key=lambda r: float(r.get(key))) if candidates else None

    def _max_by(key: str):
        candidates = [r for r in valid if _safe_float(r.get(key), None) is not None]
        return max(candidates, key=lambda r: float(r.get(key))) if candidates else None

    def _risk_adjusted(row: Mapping[str, Any]) -> float:
        ret = _safe_float(row.get("period_return_pct"), 0.0) or 0.0
        vol = _safe_float(row.get("volatility_pct"), None)
        dd = abs(_safe_float(row.get("max_drawdown_pct"), 0.0) or 0.0)
        risk = (vol if vol is not None else 18.0) + (dd * 0.35)
        return ret / max(1.0, risk)

    def _after_cost(row: Mapping[str, Any]) -> float:
        ret = _safe_float(row.get("period_return_pct"), 0.0) or 0.0
        fee = _safe_float(row.get("expense_ratio_pct"), 0.0) or 0.0
        return ret - fee

    cheapest = _min_by("expense_ratio_pct")
    best_quality = _max_by("decision_quality")
    best_after_cost = max(valid, key=_after_cost)
    best_risk_adjusted = max(valid, key=_risk_adjusted)
    foundation_candidates = [r for r in valid if r.get("fund_type") in {"Indeksfond", "ETF", "Rente-/obligasjonsfond", "Pengemarkedsfond"}]
    fixed_income_candidates = [r for r in valid if r.get("fund_type") in FIXED_INCOME_TYPES]
    high_yield_candidates = [r for r in valid if r.get("fund_type") == "High yield-fond"]
    best_foundation = max(foundation_candidates or valid, key=lambda r: (float(r.get("fit_score") or 0), float(r.get("decision_quality") or 0)))
    best_fixed_income = max(fixed_income_candidates, key=lambda r: float(r.get("decision_quality") or 0)) if fixed_income_candidates else None
    best_high_yield = max(high_yield_candidates, key=lambda r: float(r.get("decision_quality") or 0)) if high_yield_candidates else None

    rows_out: List[Dict[str, Any]] = []
    for r in valid:
        rows_out.append({
            "symbol": r.get("symbol"),
            "name": r.get("name"),
            "fund_type": r.get("fund_type"),
            "decision_quality": r.get("decision_quality"),
            "expense_ratio_pct": r.get("expense_ratio_pct"),
            "period_return_pct": r.get("period_return_pct"),
            "volatility_pct": r.get("volatility_pct"),
            "max_drawdown_pct": r.get("max_drawdown_pct"),
            "excess_return_pct": r.get("excess_return_pct"),
            "active_evidence_status": r.get("active_evidence_status"),
            "active_evidence_score": r.get("active_evidence_score"),
            "decision": r.get("decision"),
            "display_label": r.get("display_label") or fund_display_label(r.get("symbol"), r),
        })

    active = [r for r in valid if r.get("fund_type") == "Aktivt fond"]
    active_evidence = sorted(active, key=lambda r: float(r.get("active_evidence_score") or 0), reverse=True)
    return {
        "count": len(valid),
        "leaders": {
            "billigst": cheapest.get("symbol") if cheapest else "-",
            "best_kvalitet": best_quality.get("symbol") if best_quality else "-",
            "best_etter_kostnad": best_after_cost.get("symbol") if best_after_cost else "-",
            "best_risikojustert": best_risk_adjusted.get("symbol") if best_risk_adjusted else "-",
            "best_grunnmur": best_foundation.get("symbol") if best_foundation else "-",
            "best_rente_obligasjon": best_fixed_income.get("symbol") if best_fixed_income else "-",
            "best_high_yield": best_high_yield.get("symbol") if best_high_yield else "-",
        },
        "rows": rows_out,
        "active_evidence": active_evidence,
    }



BROAD_CORE_HINTS = [
    "GLOBAL", "WORLD", "TOTALMARKED", "TOTAL MARKET", "S&P 500", "SP 500",
    "MSCI", "BRED", "BROAD", "UTVIKLEDE", "INDEKS", "INDEX",
]
SATELLITE_HINTS = [
    "TEKNOLOGI", "TECH", "SEKTOR", "SECTOR", "SMALL", "EMERGING", "VEKST",
    "GROWTH", "FINTECH", "INCOME", "NASDAQ", "FAKTOR", "FACTOR", "VERDI", "VALUE",
    "HIGH YIELD", "KREDITT", "CREDIT", "BANK LOAN", "HY",
]
BROAD_CORE_SYMBOLS = {"SPY", "VOO", "VTI", "VT", "ACWI", "EUNL.DE", "IUSQ.DE", "SXR8.DE", "VEA", "IEFA", "BND", "AGG", "SHY", "BSV", "SGOV", "BIL", "SHV"}
SATELLITE_SYMBOLS = {"QQQ", "XLK", "XLF", "XLV", "IWM", "EEM", "ARKK", "ARKW", "ARKF", "JEPI", "JEPQ", "TCAF", "DYNF", "AVGV", "HYG", "JNK", "ANGL", "HYLB", "USHY", "SJNK", "BKLN", "KRAFT_HIGH_YIELD_D"}

CORE_SATELLITE_PROFILES: Dict[str, Dict[str, Any]] = {
    "Lav kostnad": {"core_pct": 90, "satellite_pct": 10, "max_core": 3, "max_satellite": 2, "description": "Lav kostnad: mest mulig bred grunnmur, få satellitter."},
    "Lav risiko": {"core_pct": 85, "satellite_pct": 15, "max_core": 3, "max_satellite": 2, "description": "Lav risiko: bred grunnmur og begrenset satellittandel."},
    "Grunnmur": {"core_pct": 90, "satellite_pct": 10, "max_core": 3, "max_satellite": 2, "description": "Grunnmur: prioriterer brede indeks-/ETF-kandidater."},
    "Best historikk": {"core_pct": 65, "satellite_pct": 35, "max_core": 3, "max_satellite": 4, "description": "Best historikk: mer rom for satellitter med god kvalitet."},
    "Balansert": {"core_pct": 75, "satellite_pct": 25, "max_core": 3, "max_satellite": 3, "description": "Balansert: bred grunnmur med kontrollerte satellitter."},
}


def _text_has_any(value: Any, hints: Sequence[str]) -> bool:
    text = str(value or "").upper()
    return any(h in text for h in hints)


def _is_broad_core_candidate(row: Mapping[str, Any]) -> bool:
    symbol = str(row.get("symbol") or "").upper()
    ftype = str(row.get("fund_type") or "")
    bucket = row.get("bucket") or row.get("category") or row.get("name") or ""
    if ftype in {"Rente-/obligasjonsfond", "Pengemarkedsfond"}:
        return symbol in BROAD_CORE_SYMBOLS or ftype == "Pengemarkedsfond"
    if ftype == "High yield-fond":
        return False
    if ftype not in {"Indeksfond", "ETF"}:
        return False
    if symbol in BROAD_CORE_SYMBOLS:
        return True
    if _text_has_any(bucket, BROAD_CORE_HINTS) and not _text_has_any(bucket, SATELLITE_HINTS):
        return True
    return False


def _is_satellite_candidate(row: Mapping[str, Any]) -> bool:
    symbol = str(row.get("symbol") or "").upper()
    ftype = str(row.get("fund_type") or "")
    bucket = row.get("bucket") or row.get("category") or row.get("name") or ""
    if symbol in SATELLITE_SYMBOLS:
        return True
    if ftype == "High yield-fond":
        return True
    if ftype == "Aktivt fond":
        return True
    if _text_has_any(bucket, SATELLITE_HINTS):
        return True
    return False


def _role_reason(row: Mapping[str, Any], role: str) -> str:
    ftype = str(row.get("fund_type") or "")
    cost = row.get("expense_ratio_pct")
    quality = row.get("decision_quality")
    evidence = row.get("active_evidence_status")
    if role == "Grunnmur":
        return "Bred/lavkost indeks- eller ETF-kandidat med egnet kvalitet som porteføljegrunnmur."
    if role == "Satellitt":
        if ftype == "High yield-fond":
            return "High yield/kredittsatellitt med høyere kredittrisiko; bør ikke brukes som trygg rentebase."
        if ftype == "Aktivt fond":
            return f"Aktiv kandidat med {evidence or 'ukjent'} merverdibevis; bør brukes som mindre satellitt, ikke grunnmur."
        return "Mer spisset/sektor-/temaeksponering; kan brukes som kontrollert satellitt rundt grunnmuren."
    if role in {"Defensiv komponent", "Likviditetsbuffer", "Kredittsatellitt"}:
        return str((row.get("fixed_income_profile") or {}).get("reason") or "Rente-/kredittfond med egen risikoprofil.")
    if role == "Krever mer bevis":
        return "Mangler sterk nok dokumentasjon, datakvalitet eller aktiv merverdi til å få plass i forslag nå."
    return "Lav kvalitet, mangelfulle data eller for svak kostnad/risiko-profil for valgt mål."


def classify_core_satellite_role(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Assign a portfolio role to one analysed fund row."""
    r = dict(row or {})
    quality = _safe_float(r.get("decision_quality"), 0.0) or 0.0
    data_q = _safe_float(r.get("data_quality"), 0.0) or 0.0
    cost_score = _safe_float(r.get("cost_score"), 55.0) or 55.0
    decision = str(r.get("decision") or "")
    ftype = str(r.get("fund_type") or "")
    evidence = str(r.get("active_evidence_status") or "")

    if decision in {"Mangler data", "Vent / forkast"} or quality < 50 or data_q < 35:
        role = "Unngå"
    elif ftype == "Aktivt fond" and evidence != "Godkjent":
        role = "Krever mer bevis"
    elif decision == "Krever mer bevis":
        role = "Krever mer bevis"
    elif _is_broad_core_candidate(r) and quality >= 60 and cost_score >= 55 and data_q >= 45:
        role = "Grunnmur"
    elif quality >= 58 and (_is_satellite_candidate(r) or ftype in {"ETF", "Aktivt fond"}):
        role = "Satellitt"
    elif quality >= 62 and ftype in {"Indeksfond", "ETF"}:
        role = "Grunnmur"
    else:
        role = "Krever mer bevis"

    return {
        "symbol": r.get("symbol"),
        "name": r.get("name"),
        "fund_type": ftype,
        "role": role,
        "decision_quality": r.get("decision_quality"),
        "expense_ratio_pct": r.get("expense_ratio_pct"),
        "period_return_pct": r.get("period_return_pct"),
        "volatility_pct": r.get("volatility_pct"),
        "max_drawdown_pct": r.get("max_drawdown_pct"),
        "active_evidence_status": r.get("active_evidence_status"),
        "reason": _role_reason(r, role),
        "cautions": list(r.get("reasons_caution") or [])[:3],
    }


def _allocate_weights(candidates: Sequence[Mapping[str, Any]], total_weight: float) -> List[float]:
    n = len(candidates or [])
    if n <= 0 or total_weight <= 0:
        return []
    scores = [max(20.0, _safe_float(c.get("decision_quality"), 50.0) or 50.0) for c in candidates]
    total_score = sum(scores) or float(n)
    raw = [(s / total_score) * float(total_weight) for s in scores]
    rounded = [round(x, 1) for x in raw]
    drift = round(float(total_weight) - sum(rounded), 1)
    if rounded:
        rounded[0] = round(rounded[0] + drift, 1)
    return rounded


def build_core_satellite_portfolio(
    rows: Sequence[Mapping[str, Any]],
    *,
    profile: str = "Balansert",
    max_positions: int = 8,
) -> Dict[str, Any]:
    """Create a simple core/satellite fund proposal from analysed fund rows.

    The function is deliberately conservative: broad, low-cost index/ETF rows are
    preferred as core. Active funds are only eligible as satellites when their
    active evidence test is approved. Everything else is labelled as needing more
    proof or avoid.
    """
    profile_key = str(profile or "Balansert")
    cfg = CORE_SATELLITE_PROFILES.get(profile_key) or CORE_SATELLITE_PROFILES["Balansert"]
    max_positions = max(1, int(max_positions or 8))
    valid = [dict(r) for r in (rows or []) if r]
    if not valid:
        return {
            "profile": profile_key,
            "status": "Ingen data",
            "allocation": [],
            "core": [],
            "satellites": [],
            "needs_proof": [],
            "avoid": [],
            "warnings": ["Kjør Fond / ETF-analyse først."],
            "summary": "Ingen fond/ETF-data å bygge forslag fra.",
        }

    roles = [classify_core_satellite_role(r) for r in valid]
    by_symbol = {str(r.get("symbol")): dict(r) for r in valid}
    core = [r for r in roles if r.get("role") == "Grunnmur"]
    satellites = [r for r in roles if r.get("role") == "Satellitt"]
    needs = [r for r in roles if r.get("role") == "Krever mer bevis"]
    avoid = [r for r in roles if r.get("role") == "Unngå"]

    def _sort_key(role_row: Mapping[str, Any]) -> Tuple[float, float]:
        full = by_symbol.get(str(role_row.get("symbol")), {})
        return (_safe_float(full.get("decision_quality"), 0.0) or 0.0, _safe_float(full.get("data_quality"), 0.0) or 0.0)

    core = sorted(core, key=_sort_key, reverse=True)[: int(cfg.get("max_core") or 3)]
    remaining_slots = max(0, max_positions - len(core))
    satellites = sorted(satellites, key=_sort_key, reverse=True)[: min(remaining_slots, int(cfg.get("max_satellite") or 3))]

    warnings: List[str] = []
    if not core:
        warnings.append("Fant ingen tydelig grunnmur. Vurder bredt/lavkost indeksfond før satellitter.")
        # Emergency fallback: allow best broad-ish ETF/index candidate if available.
        fallback = sorted([r for r in roles if r.get("fund_type") in {"Indeksfond", "ETF"} and r.get("role") != "Unngå"], key=_sort_key, reverse=True)[:1]
        if fallback:
            fallback[0]["role"] = "Grunnmur"
            fallback[0]["reason"] = "Beste tilgjengelige indeks/ETF-kandidat, men bør valideres som grunnmur."
            core = fallback
            satellites = [s for s in satellites if s.get("symbol") != core[0].get("symbol")]
    if not satellites:
        warnings.append("Ingen klare satellitter valgt; grunnmur kan stå alene.")

    core_pct = float(cfg.get("core_pct") or 75)
    sat_pct = float(cfg.get("satellite_pct") or 25)
    if not satellites:
        core_pct, sat_pct = 100.0, 0.0
    if not core:
        core_pct, sat_pct = 0.0, 100.0 if satellites else 0.0

    allocation: List[Dict[str, Any]] = []
    for role_row, weight in zip(core, _allocate_weights(core, core_pct)):
        row = dict(role_row)
        row["weight_pct"] = weight
        allocation.append(row)
    for role_row, weight in zip(satellites, _allocate_weights(satellites, sat_pct)):
        row = dict(role_row)
        row["weight_pct"] = weight
        allocation.append(row)

    if allocation:
        total = round(sum(float(a.get("weight_pct") or 0.0) for a in allocation), 1)
        drift = round(100.0 - total, 1)
        allocation[0]["weight_pct"] = round(float(allocation[0].get("weight_pct") or 0.0) + drift, 1)

    avg_quality = None
    if allocation:
        avg_quality = round(sum((_safe_float(a.get("decision_quality"), 0.0) or 0.0) * (float(a.get("weight_pct") or 0.0) / 100.0) for a in allocation), 1)

    summary = "Forslag laget med bred grunnmur og kontrollerte satellitter." if allocation else "Ingen allokering foreslått."
    return {
        "profile": profile_key,
        "status": "OK" if allocation else "Mangler kandidater",
        "description": cfg.get("description"),
        "target_core_pct": core_pct,
        "target_satellite_pct": sat_pct,
        "average_quality": avg_quality,
        "allocation": allocation,
        "core": core,
        "satellites": satellites,
        "needs_proof": needs,
        "avoid": avoid,
        "warnings": warnings,
        "summary": summary,
        "role_counts": {
            "grunnmur": len(core),
            "satellitt": len(satellites),
            "krever_mer_bevis": len(needs),
            "unngå": len(avoid),
        },
    }


# v18.5.42: Cost impact over time -------------------------------------------------
DEFAULT_COST_IMPACT_FEES = [0.18, 0.50, 1.00, 1.50]


def future_value_after_costs(
    *,
    start_amount: float = 100_000.0,
    monthly_saving: float = 2_000.0,
    annual_return_pct: float = 7.0,
    annual_fee_pct: float = 0.18,
    years: int = 20,
) -> float:
    """Estimate ending value after annual fund costs using monthly compounding.

    The model is intentionally simple and transparent. It is not a promise of
    future return; it shows how different expense ratios can compound into a
    large value difference over time.
    """
    start = max(0.0, float(start_amount or 0.0))
    saving = max(0.0, float(monthly_saving or 0.0))
    years_i = max(1, int(years or 1))
    gross = float(annual_return_pct or 0.0) / 100.0
    fee = max(0.0, float(annual_fee_pct or 0.0)) / 100.0
    # Conservative: subtract fee from gross annual return before monthly compounding.
    net_annual = max(-0.95, gross - fee)
    monthly_rate = (1.0 + net_annual) ** (1.0 / 12.0) - 1.0
    value = start
    for _ in range(years_i * 12):
        value = value * (1.0 + monthly_rate) + saving
    return round(value, 2)


def _format_cost_label(symbol: str, fee: float) -> str:
    sym = str(symbol or "").strip()
    return f"{sym} · {fee:.2f}%" if sym else f"Kostnad {fee:.2f}%"


def build_cost_impact_table(
    fee_rows: Sequence[Mapping[str, Any]],
    *,
    start_amount: float = 100_000.0,
    monthly_saving: float = 2_000.0,
    annual_return_pct: float = 7.0,
    years: int = 20,
    baseline_fee_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Build cost-impact rows for actual fund fees or generic fee levels.

    `fee_rows` accepts mappings with `label`, `symbol` and `expense_ratio_pct`.
    The output is UI-ready and deterministic so tests can verify the math.
    """
    clean: List[Dict[str, Any]] = []
    for raw in fee_rows or []:
        fee = _safe_float(raw.get("expense_ratio_pct"), None)
        if fee is None or fee < 0:
            continue
        symbol = str(raw.get("symbol") or "").strip()
        label = str(raw.get("label") or raw.get("display_label") or raw.get("name") or fund_display_label(symbol, raw) or _format_cost_label(symbol, fee)).strip()
        clean.append({
            "symbol": symbol,
            "label": label,
            "expense_ratio_pct": round(float(fee), 3),
        })

    if not clean:
        clean = [
            {"symbol": "", "label": f"Standard {fee:.2f}%", "expense_ratio_pct": float(fee)}
            for fee in DEFAULT_COST_IMPACT_FEES
        ]

    # Keep unique symbol+fee/label rows while preserving order.
    unique: List[Dict[str, Any]] = []
    seen = set()
    for row in clean:
        key = (row.get("symbol"), row.get("label"), row.get("expense_ratio_pct"))
        if key not in seen:
            unique.append(row)
            seen.add(key)

    fees = [float(r["expense_ratio_pct"]) for r in unique]
    baseline_fee = _safe_float(baseline_fee_pct, None)
    if baseline_fee is None:
        baseline_fee = min(fees) if fees else min(DEFAULT_COST_IMPACT_FEES)
    baseline_fee = max(0.0, float(baseline_fee))
    no_fee_value = future_value_after_costs(
        start_amount=start_amount,
        monthly_saving=monthly_saving,
        annual_return_pct=annual_return_pct,
        annual_fee_pct=0.0,
        years=years,
    )
    baseline_value = future_value_after_costs(
        start_amount=start_amount,
        monthly_saving=monthly_saving,
        annual_return_pct=annual_return_pct,
        annual_fee_pct=baseline_fee,
        years=years,
    )

    out_rows: List[Dict[str, Any]] = []
    for row in unique:
        fee = float(row["expense_ratio_pct"])
        ending = future_value_after_costs(
            start_amount=start_amount,
            monthly_saving=monthly_saving,
            annual_return_pct=annual_return_pct,
            annual_fee_pct=fee,
            years=years,
        )
        out_rows.append({
            "symbol": row.get("symbol") or "",
            "label": row.get("label") or fund_display_label(row.get("symbol", ""), row) or _format_cost_label(row.get("symbol", ""), fee),
            "expense_ratio_pct": round(fee, 3),
            "ending_value": round(ending, 2),
            "vs_baseline": round(ending - baseline_value, 2),
            "cost_drag_vs_no_fee": round(no_fee_value - ending, 2),
            "baseline_fee_pct": round(baseline_fee, 3),
        })

    out_rows = sorted(out_rows, key=lambda r: (float(r.get("expense_ratio_pct") or 0.0), str(r.get("label") or "")))
    best = out_rows[0] if out_rows else {}
    worst = out_rows[-1] if out_rows else {}
    difference_best_worst = None
    if best and worst:
        difference_best_worst = round(float(best.get("ending_value") or 0.0) - float(worst.get("ending_value") or 0.0), 2)
    return {
        "version": get_app_version(),
        "created_at": _now_iso(),
        "start_amount": round(max(0.0, float(start_amount or 0.0)), 2),
        "monthly_saving": round(max(0.0, float(monthly_saving or 0.0)), 2),
        "annual_return_pct": round(float(annual_return_pct or 0.0), 3),
        "years": max(1, int(years or 1)),
        "baseline_fee_pct": round(baseline_fee, 3),
        "no_fee_value": no_fee_value,
        "baseline_value": baseline_value,
        "rows": out_rows,
        "summary": {
            "cheapest_label": best.get("label") if best else "",
            "highest_cost_label": worst.get("label") if worst else "",
            "difference_best_worst": difference_best_worst,
            "count": len(out_rows),
        },
    }


def build_fund_cost_impact(
    analysed_rows: Sequence[Mapping[str, Any]],
    *,
    start_amount: float = 100_000.0,
    monthly_saving: float = 2_000.0,
    annual_return_pct: float = 7.0,
    years: int = 20,
    include_standard_levels: bool = True,
) -> Dict[str, Any]:
    """Create a cost-impact scenario from analysed fund/ETF rows.

    Actual fund rows are used when expense ratios exist. Standard levels are
    added as reference points so users can see the long-term effect even when a
    data provider lacks expense data.
    """
    fee_rows: List[Dict[str, Any]] = []
    for row in analysed_rows or []:
        fee = _safe_float(row.get("expense_ratio_pct"), None)
        if fee is None:
            continue
        symbol = str(row.get("symbol") or row.get("ticker") or "").strip()
        name = get_fund_display_name(symbol, row) if symbol else str(row.get("name") or "Fond")
        label = f"{symbol} — {name}" if symbol and name and name != "Navn ikke funnet" else (symbol or name or "Fond")
        fee_rows.append({"symbol": symbol, "label": label, "expense_ratio_pct": fee})

    if include_standard_levels:
        for fee in DEFAULT_COST_IMPACT_FEES:
            fee_rows.append({"symbol": "", "label": f"Referanse {fee:.2f}%", "expense_ratio_pct": fee})

    return build_cost_impact_table(
        fee_rows,
        start_amount=start_amount,
        monthly_saving=monthly_saving,
        annual_return_pct=annual_return_pct,
        years=years,
    )



# v18.5.42: Hardened Fund Decision Quality --------------------------------------
FUND_DECISION_COMPONENT_LABELS = {
    "cost": "Kostnad",
    "return": "Avkastning",
    "risk": "Risiko",
    "benchmark": "Benchmark",
    "data": "Datakvalitet",
    "fit": "Rolle/egnethet",
    "cost_impact": "Kostnadseffekt over tid",
    "active_evidence": "Aktiv merverdi",
}


def _score_cost_impact(expense: Optional[float], fund_type: str) -> float:
    """Score long-term cost drag on a 0-100 scale.

    This is deliberately stricter than the simple cost score because a small fee
    difference compounds over decades. Active funds are allowed a higher fee only
    when the active evidence test later supports it.
    """
    if expense is None:
        return 52.0
    fee = max(0.0, float(expense))
    if fund_type in {"Indeksfond", "ETF"}:
        # 0.10-0.25% should score very highly; 1.50% should be a serious warning.
        return _clamp(100.0 - fee * 42.0, 5.0, 100.0)
    if fund_type == "Pengemarkedsfond":
        return _clamp(100.0 - fee * 48.0, 5.0, 100.0)
    if fund_type == "Rente-/obligasjonsfond":
        return _clamp(98.0 - fee * 44.0, 5.0, 100.0)
    if fund_type == "High yield-fond":
        return _clamp(90.0 - fee * 32.0, 5.0, 100.0)
    if fund_type == "Aktivt fond":
        return _clamp(92.0 - fee * 33.0, 5.0, 100.0)
    return _clamp(95.0 - fee * 38.0, 5.0, 100.0)


def _score_foundation_fit(*, fund_type: str, cost_score: float, benchmark_score: float, data_score: float, risk_score: float, fit_score: float) -> float:
    if fund_type in DEFENSIVE_FIXED_INCOME_TYPES:
        return _clamp((risk_score * 0.30) + (cost_score * 0.24) + (data_score * 0.20) + (benchmark_score * 0.16) + (fit_score * 0.10))
    if fund_type == "High yield-fond":
        return _clamp((fit_score * 0.25) + (data_score * 0.25) + (risk_score * 0.20) + (cost_score * 0.15) + (benchmark_score * 0.15) - 25.0)
    if fund_type not in {"Indeksfond", "ETF"}:
        return _clamp((fit_score * 0.30) + (data_score * 0.25) + (risk_score * 0.20) + (cost_score * 0.15) + (benchmark_score * 0.10) - 18.0)
    return _clamp((cost_score * 0.30) + (benchmark_score * 0.22) + (data_score * 0.20) + (risk_score * 0.18) + (fit_score * 0.10))


def _score_satellite_fit(*, fund_type: str, return_score: float, risk_score: float, benchmark_score: float, active_evidence: Mapping[str, Any]) -> float:
    evidence = _safe_float(active_evidence.get("score"), 58.0) or 58.0
    if fund_type == "Aktivt fond":
        return _clamp((evidence * 0.45) + (return_score * 0.25) + (risk_score * 0.20) + (benchmark_score * 0.10))
    if fund_type == "High yield-fond":
        return _clamp((return_score * 0.28) + (risk_score * 0.30) + (benchmark_score * 0.22) + 8.0)
    return _clamp((return_score * 0.35) + (risk_score * 0.25) + (benchmark_score * 0.20) + 12.0)


def build_fund_decision_quality_profile(
    *,
    fund_type: str,
    objective: str,
    expense: Optional[float],
    total_return: Optional[float],
    benchmark_return: Optional[float],
    volatility: Optional[float],
    drawdown: Optional[float],
    cost_score: float,
    return_score: float,
    risk_score: float,
    benchmark_score: float,
    data_score: float,
    fit_score: float,
    active_evidence: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return a stricter, explainable Fund Decision Quality profile.

    v18.5.42 changes Fund Decision Quality from a single weighted number into a
    conservative decision profile. The profile keeps a numeric score, but also
    exposes component scores, role scores, reason codes and guardrails. This
    makes it easier for the UI to explain why a low-cost index fund can be a
    strong core holding and why an active fund must prove value after costs.
    """
    weights = OBJECTIVE_WEIGHTS.get(objective) or OBJECTIVE_WEIGHTS["Balansert"]
    base_quality = (
        cost_score * weights["cost"]
        + return_score * weights["return"]
        + risk_score * weights["risk"]
        + benchmark_score * weights["benchmark"]
        + data_score * weights["data"]
        + fit_score * weights["fit"]
    )
    cost_impact_score = _score_cost_impact(expense, fund_type)
    active_score = active_evidence.get("score") if fund_type == "Aktivt fond" else None
    active_score_num = _safe_float(active_score, 60.0) or 60.0
    risk_adjusted_quality = _clamp((return_score * 0.42) + (risk_score * 0.43) + (benchmark_score * 0.15))
    foundation_score = _score_foundation_fit(
        fund_type=fund_type,
        cost_score=cost_score,
        benchmark_score=benchmark_score,
        data_score=data_score,
        risk_score=risk_score,
        fit_score=fit_score,
    )
    satellite_score = _score_satellite_fit(
        fund_type=fund_type,
        return_score=return_score,
        risk_score=risk_score,
        benchmark_score=benchmark_score,
        active_evidence=active_evidence,
    )

    # Blend in the long-term fee effect and role quality without letting them
    # overpower the underlying risk/return/data scores.
    hardened = (base_quality * 0.72) + (cost_impact_score * 0.12) + (risk_adjusted_quality * 0.08) + (max(foundation_score, satellite_score) * 0.08)

    drivers: List[str] = []
    cautions: List[str] = []
    why_not_100: List[str] = []

    if cost_score >= 78 and cost_impact_score >= 78:
        drivers.append("lav kostnad og god kostnadseffekt over tid")
    elif expense is None:
        cautions.append("kostnad mangler")
        why_not_100.append("mangler kostnadsdata")
    else:
        cautions.append("kostnad trekker ned kvaliteten")
        why_not_100.append("kostnadseffekt over tid er ikke optimal")

    if return_score >= 68:
        drivers.append("god historisk avkastning i dataperioden")
    elif total_return is None:
        cautions.append("historisk avkastning mangler")
        why_not_100.append("mangler nok prisdata")
    else:
        why_not_100.append("avkastningen er ikke tydelig sterk")

    if risk_score >= 72:
        drivers.append("akseptabel risiko og drawdown")
    elif risk_score < 48:
        cautions.append("høy risiko eller drawdown")
        why_not_100.append("risiko/drawdown trekker ned")

    if benchmark_score >= 72:
        drivers.append("sterk benchmark-vurdering")
    elif benchmark_return is None:
        cautions.append("benchmark mangler")
        why_not_100.append("benchmark-data mangler")
    else:
        why_not_100.append("benchmark-gap eller tracking avviker")

    if data_score >= 70:
        drivers.append("god datakvalitet")
    elif data_score < 55:
        cautions.append("svak datakvalitet")
        why_not_100.append("datakvalitet er for svak")

    evidence_status = str(active_evidence.get("status") or "")
    if fund_type == "Aktivt fond":
        if evidence_status == "Godkjent" and active_score_num >= 68:
            drivers.append("aktiv merverdi er bevist mot benchmark")
        elif evidence_status == "Usikker":
            cautions.append("aktiv merverdi er usikker")
            why_not_100.append("aktiv merverdi er ikke stabil nok")
            hardened = min(hardened, 68.0)
        else:
            cautions.append("aktiv merverdi er ikke bevist")
            why_not_100.append("aktivt fond må bevise merverdi etter kostnader")
            hardened = min(hardened, 56.0)
        if expense is not None and expense > 1.20 and active_score_num < 75:
            cautions.append("høy aktiv kostnad uten sterk nok merverdi")
            hardened = min(hardened, 54.0)
    else:
        if fund_type in DEFENSIVE_FIXED_INCOME_TYPES and foundation_score >= 66:
            drivers.append("egnet som defensiv rente-/likviditetskomponent")
        elif fund_type == "High yield-fond":
            cautions.append("high yield har høyere kredittrisiko enn vanlige rentefond")
            why_not_100.append("high yield bør vurderes som kredittsatellitt")
            hardened = min(hardened, 72.0)
        elif foundation_score >= 70:
            drivers.append("egnet som mulig grunnmur")

    if data_score < 40:
        hardened = min(hardened, 52.0)
    if expense is not None and expense > 1.50 and fund_type != "Aktivt fond":
        hardened = min(hardened, 55.0)
        cautions.append("svært høy kostnad for indeks/ETF-kandidat")

    quality = round(_clamp(hardened), 1)
    if quality >= 78:
        grade = "Høy"
    elif quality >= 60:
        grade = "Middels"
    else:
        grade = "Lav"

    if fund_type == "High yield-fond":
        decision = "Kan vurderes" if quality >= 60 and data_score >= 55 else "Vurder videre"
        recommended_role = "Kredittsatellitt" if quality >= 55 else "Krever mer bevis"
    elif fund_type == "Pengemarkedsfond":
        decision = "God kandidat" if quality >= 66 else "Kan vurderes"
        recommended_role = "Likviditetsbuffer"
    elif fund_type == "Rente-/obligasjonsfond":
        decision = "God kandidat" if quality >= 70 else ("Kan vurderes" if quality >= 58 else "Vurder videre")
        recommended_role = "Defensiv komponent" if quality >= 58 else "Krever mer bevis"
    elif fund_type == "Aktivt fond" and (evidence_status != "Godkjent" or active_score_num < 68):
        decision = "Krever mer bevis"
        recommended_role = "Krever mer bevis"
    elif quality >= 76 and foundation_score >= satellite_score and fund_type in {"Indeksfond", "ETF"}:
        decision = "God kandidat"
        recommended_role = "Grunnmur"
    elif quality >= 66:
        decision = "Kan vurderes"
        recommended_role = "Grunnmur" if foundation_score >= satellite_score and fund_type in {"Indeksfond", "ETF"} else "Satellitt"
    elif quality >= 54:
        decision = "Vurder videre"
        recommended_role = "Krever mer bevis"
    else:
        decision = "Vent / forkast"
        recommended_role = "Unngå"

    if not drivers:
        drivers.append("ingen tydelig hoveddriver funnet")
    if not why_not_100:
        why_not_100.append("ingen fond er risikofritt; score holdes konservativ")

    components = {
        "cost": round(cost_score, 1),
        "return": round(return_score, 1),
        "risk": round(risk_score, 1),
        "benchmark": round(benchmark_score, 1),
        "data": round(data_score, 1),
        "fit": round(fit_score, 1),
        "cost_impact": round(cost_impact_score, 1),
        "active_evidence": None if active_score is None else round(active_score_num, 1),
    }
    role_scores = {
        "grunnmur_score": round(foundation_score, 1),
        "satellitt_score": round(satellite_score, 1),
        "cost_efficiency_score": round(cost_impact_score, 1),
        "risk_adjusted_quality": round(risk_adjusted_quality, 1),
        "active_evidence_score": None if active_score is None else round(active_score_num, 1),
    }
    return {
        "decision_quality": quality,
        "grade": grade,
        "decision": decision,
        "recommended_role": recommended_role,
        "component_scores": components,
        "role_scores": role_scores,
        "drivers": drivers[:5],
        "cautions": cautions[:5],
        "why_not_100": why_not_100[:5],
        "summary": f"{grade} fondskvalitet · {decision} · rolle: {recommended_role}",
    }

def analyze_fund_record(
    symbol: str,
    data: Optional[Mapping[str, Any]],
    *,
    fund_type: str = "Alle",
    objective: str = "Balansert",
    benchmark_data: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    symbol = normalize_fund_symbol(symbol)
    data = data or {}
    prices = _prices_from_data(data)
    benchmark_prices = _prices_from_data(benchmark_data)
    detected_type = classify_fund(symbol, fund_type, data)
    expense = _expense_ratio(data)
    total_return = _period_return(prices)
    benchmark_return = _period_return(benchmark_prices)
    volatility = _annualized_volatility(prices)
    benchmark_volatility = _annualized_volatility(benchmark_prices)
    drawdown = _max_drawdown(prices)
    fixed_income_profile = _fixed_income_profile(
        fund_type=detected_type,
        data=data,
        volatility=volatility,
        drawdown=drawdown,
        expense=expense,
    )

    active_evidence = _active_evidence_test(
        fund_type=detected_type,
        total_return=total_return,
        benchmark_return=benchmark_return,
        expense=expense,
        volatility=volatility,
        benchmark_volatility=benchmark_volatility,
    )

    cost_score = _score_cost(expense, detected_type)
    return_score = _score_return(total_return)
    risk_score = _score_risk(volatility, drawdown)
    benchmark_score = _score_benchmark(total_return, benchmark_return, expense, detected_type)
    data_score = _score_data_quality(prices, expense, benchmark_return)
    fit_score = 86.0 if detected_type in {"Indeksfond", "ETF"} and objective in {"Grunnmur", "Lav kostnad", "Balansert"} else 68.0
    if detected_type in DEFENSIVE_FIXED_INCOME_TYPES:
        fit_score = 82.0 if objective in {"Lav risiko", "Balansert", "Grunnmur"} else 72.0
    elif detected_type == "High yield-fond":
        fit_score = 58.0 if objective in {"Lav risiko", "Grunnmur"} else 68.0
    if detected_type == "Aktivt fond":
        evidence_score = _safe_float(active_evidence.get("score"), 35.0) or 35.0
        if benchmark_score < 55 or evidence_score < 52:
            fit_score -= 18.0
        elif evidence_score >= 68:
            fit_score += 6.0
    fit_score = _clamp(fit_score, 5.0, 100.0)

    base_score_profile = build_base_fund_score_profile(
        fund_type=detected_type,
        objective=objective,
        cost_score=cost_score,
        return_score=return_score,
        risk_score=risk_score,
        benchmark_score=benchmark_score,
        data_score=data_score,
        fit_score=fit_score,
        active_evidence=active_evidence,
    )

    quality_profile = build_fund_decision_quality_profile(
        fund_type=detected_type,
        objective=objective,
        expense=expense,
        total_return=total_return,
        benchmark_return=benchmark_return,
        volatility=volatility,
        drawdown=drawdown,
        cost_score=cost_score,
        return_score=return_score,
        risk_score=risk_score,
        benchmark_score=benchmark_score,
        data_score=data_score,
        fit_score=fit_score,
        active_evidence=active_evidence,
    )
    quality = float(quality_profile.get("decision_quality") or 0.0)
    grade = str(quality_profile.get("grade") or "Lav")

    positives: List[str] = []
    cautions: List[str] = []
    if cost_score >= 78:
        positives.append("lav kostnad")
    elif expense is None:
        cautions.append("kostnad mangler")
    else:
        cautions.append("kostnad bør vurderes")
    if return_score >= 65:
        positives.append("god historikk i perioden")
    elif total_return is None:
        cautions.append("mangler nok prisdata")
    if risk_score >= 70:
        positives.append("akseptabel risiko/drawdown")
    elif risk_score < 45:
        cautions.append("høy risiko eller drawdown")
    if detected_type == "Aktivt fond":
        if active_evidence.get("status") == "Godkjent":
            positives.append("aktiv merverdi bevist mot benchmark")
        elif active_evidence.get("status") == "Usikker":
            cautions.append("aktiv merverdi er usikker")
        else:
            cautions.append("aktiv merverdi ikke godt nok bevist")
    elif detected_type in FIXED_INCOME_TYPES:
        fi_warnings = list((fixed_income_profile or {}).get("warnings") or [])
        if detected_type in DEFENSIVE_FIXED_INCOME_TYPES:
            positives.append("rente-/likviditetskomponent med egen risikoprofil")
        if detected_type == "High yield-fond":
            cautions.append("high yield er kredittrisiko, ikke trygg rente")
        for warning in fi_warnings[:2]:
            if warning not in cautions:
                cautions.append(warning)
    elif benchmark_score >= 70:
        positives.append("følger benchmark godt")
    if data_score < 55:
        cautions.append("svak datakvalitet")

    decision = str(quality_profile.get("decision") or "Vurder videre")
    # Keep older reason lists, but enrich them with the hardened profile so the
    # UI can explain Decision Quality without guessing.
    for reason in quality_profile.get("drivers") or []:
        if reason not in positives:
            positives.append(reason)
    for reason in quality_profile.get("cautions") or []:
        if reason not in cautions:
            cautions.append(reason)

    row = {
        "symbol": symbol,
        "name": get_fund_display_name(symbol, data),
        "fund_type": detected_type,
        "objective": objective,
        "decision_quality": quality,
        "base_score": base_score_profile.get("base_score"),
        "base_score_profile": base_score_profile,
        "base_score_summary": base_score_profile.get("summary"),
        "grade": grade,
        "decision": decision,
        "expense_ratio_pct": None if expense is None else round(expense, 3),
        "period_return_pct": None if total_return is None else round(total_return, 2),
        "benchmark_return_pct": None if benchmark_return is None else round(benchmark_return, 2),
        "excess_return_pct": None if total_return is None or benchmark_return is None else round(total_return - benchmark_return, 2),
        "volatility_pct": None if volatility is None else round(volatility, 2),
        "benchmark_volatility_pct": None if benchmark_volatility is None else round(benchmark_volatility, 2),
        "max_drawdown_pct": None if drawdown is None else round(drawdown, 2),
        "cost_score": round(cost_score, 1),
        "return_score": round(return_score, 1),
        "risk_score": round(risk_score, 1),
        "benchmark_score": round(benchmark_score, 1),
        "data_quality": round(data_score, 1),
        "fit_score": round(fit_score, 1),
        "fund_decision_quality": quality_profile,
        "quality_breakdown": quality_profile.get("component_scores"),
        "role_scores": quality_profile.get("role_scores"),
        "recommended_role": quality_profile.get("recommended_role"),
        "quality_verdict": quality_profile.get("summary"),
        "why_not_100": quality_profile.get("why_not_100"),
        "active_evidence_status": active_evidence.get("status"),
        "active_evidence_score": active_evidence.get("score"),
        "active_evidence_message": active_evidence.get("message"),
        "active_evidence": active_evidence,
        "fixed_income_profile": fixed_income_profile,
        "fixed_income_risk_level": fixed_income_profile.get("risk_level") if fixed_income_profile.get("is_fixed_income") else None,
        "fixed_income_role": fixed_income_profile.get("recommended_role") if fixed_income_profile.get("is_fixed_income") else None,
        "duration": fixed_income_profile.get("duration") if fixed_income_profile.get("is_fixed_income") else None,
        "yield_pct": fixed_income_profile.get("yield_pct") if fixed_income_profile.get("is_fixed_income") else None,
        "reasons_positive": positives[:4],
        "reasons_caution": cautions[:4],
        "data_points": len(prices),
        "datastatus": "Pris/NAV funnet" if len(prices) >= 2 else "Mangler pris/NAV-historikk",
        "data_quality_label": "Høy" if data_score >= 75 else ("Middels" if data_score >= 55 else "Lav"),
        "version": get_app_version(),
        "created_at": _now_iso(),
    }
    row = enrich_fund_identity(row)
    # Layer 3 + Layer 4 are applied before Layer 2 explanation so the plain-language
    # explanation can include holdings/insider context in later UI surfaces.
    row = apply_holdings_and_insider_adjustment(row, data)
    row["explainability_profile"] = build_fund_explainability_profile(row)
    row["explainability_summary"] = row["explainability_profile"].get("summary")
    row["why_ranked_here"] = row["explainability_profile"].get("why_ranked_here")
    row["what_holds_it_back"] = row["explainability_profile"].get("what_holds_it_back")
    row["what_would_make_it_selected"] = row["explainability_profile"].get("what_would_make_it_selected")
    row["what_would_make_model_reject_it"] = row["explainability_profile"].get("what_would_make_model_reject_it")
    return row




# v18.5.57 / Layer 8: Portfolio Fit Engine.
# This layer scores a fund as an addition to a portfolio, not only as an
# isolated candidate. It rewards true diversification, gap filling and lower
# overlap with existing holdings while keeping Layer 1-7 signals visible.
def _holding_symbol_weights_from_any(value: Any) -> Dict[str, float]:
    rows: List[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        if value.get("holdings") or value.get("top_holdings") or value.get("portfolio"):
            raw = value.get("holdings") or value.get("top_holdings") or value.get("portfolio") or []
            rows = [x for x in raw if isinstance(x, Mapping)]
        else:
            rows = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        rows = [x for x in value if isinstance(x, Mapping)]
    out: Dict[str, float] = {}
    for item in rows:
        sym = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
        if not sym:
            continue
        w = _safe_float(item.get("weight_pct") or item.get("weight") or item.get("pct"), None)
        if w is None:
            w = 0.0
        if 0 < w <= 1:
            w *= 100.0
        out[sym] = out.get(sym, 0.0) + float(w)
    return out


def _sector_weights_from_profile(profile: Mapping[str, Any]) -> Dict[str, float]:
    sectors = profile.get("sector_weights") or {}
    if isinstance(sectors, Mapping):
        return {str(k): float(_safe_float(v, 0.0) or 0.0) for k, v in sectors.items()}
    return {}


def _existing_portfolio_from_selection(selection_info: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    info = dict(selection_info or {})
    raw = (
        info.get("existing_portfolio")
        or info.get("current_portfolio")
        or info.get("portfolio")
        or info.get("portfolio_holdings")
        or []
    )
    symbol_weights = _holding_symbol_weights_from_any(raw)
    sector_weights: Dict[str, float] = {}
    rows = raw if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, Mapping)) else [raw]
    for item in rows or []:
        if not isinstance(item, Mapping):
            continue
        sector = str(item.get("sector") or item.get("industry") or "").strip()
        if not sector:
            continue
        w = _safe_float(item.get("weight_pct") or item.get("weight") or item.get("pct"), 0.0) or 0.0
        if 0 < w <= 1:
            w *= 100.0
        sector_weights[sector] = sector_weights.get(sector, 0.0) + float(w)
    return {"symbol_weights": symbol_weights, "sector_weights": sector_weights, "has_existing": bool(symbol_weights or sector_weights)}


def _overlap_pct(candidate_weights: Mapping[str, float], existing_weights: Mapping[str, float]) -> float:
    if not candidate_weights or not existing_weights:
        return 0.0
    total = sum(max(0.0, float(v)) for v in candidate_weights.values()) or 1.0
    overlap = 0.0
    for sym, w in candidate_weights.items():
        if sym in existing_weights:
            overlap += max(0.0, float(w))
    return round(min(100.0, (overlap / total) * 100.0), 2)


def build_portfolio_fit_profile(row: Mapping[str, Any], *, existing_portfolio: Optional[Mapping[str, Any]] = None, peer_rows: Optional[Sequence[Mapping[str, Any]]] = None) -> Dict[str, Any]:
    r = dict(row or {})
    holdings = dict(r.get("holdings_profile") or {})
    top_holdings = holdings.get("top_holdings") or []
    candidate_weights = _holding_symbol_weights_from_any(top_holdings)
    existing = dict(existing_portfolio or {})
    existing_weights = dict(existing.get("symbol_weights") or {})
    existing_sectors = dict(existing.get("sector_weights") or {})
    has_existing = bool(existing.get("has_existing") or existing_weights or existing_sectors)

    overlap = _overlap_pct(candidate_weights, existing_weights)
    diversification_score = 72.0 if not has_existing else _clamp(100.0 - overlap * 1.15, 5.0, 100.0)

    candidate_sectors = _sector_weights_from_profile(holdings)
    largest_sector = next(iter(candidate_sectors.items()), ("Ukjent", 0.0)) if candidate_sectors else ("Ukjent", 0.0)
    gap_fill_score = 60.0
    gap_notes: List[str] = []
    if candidate_sectors and existing_sectors:
        # Reward sectors the current portfolio does not already lean heavily on.
        weighted_underrep = 0.0
        sector_total = sum(max(0.0, float(v)) for v in candidate_sectors.values()) or 1.0
        for sector, weight in candidate_sectors.items():
            existing_w = float(_safe_float(existing_sectors.get(sector), 0.0) or 0.0)
            underrep = max(0.0, 25.0 - existing_w) / 25.0
            weighted_underrep += (float(weight) / sector_total) * underrep
            if weight >= 15 and existing_w < 10:
                gap_notes.append(f"fyller porteføljehull i {sector}")
        gap_fill_score = _clamp(45.0 + weighted_underrep * 45.0, 5.0, 100.0)
    elif candidate_sectors and not has_existing:
        gap_fill_score = 62.0
        gap_notes.append("ingen eksisterende portefølje lagt inn; vurderes mot generell diversifisering")

    concentration_score = _safe_float(holdings.get("concentration_score"), 55.0) or 55.0
    scenario_score = _safe_float(r.get("scenario_score"), 55.0) or 55.0
    intelligence = _safe_float(r.get("fund_intelligence_score"), _safe_float(r.get("decision_quality"), 55.0)) or 55.0
    data_quality = _safe_float(r.get("data_quality"), 50.0) or 50.0

    raw = (
        intelligence * 0.34
        + scenario_score * 0.16
        + diversification_score * 0.22
        + gap_fill_score * 0.18
        + concentration_score * 0.06
        + data_quality * 0.04
    )
    fit_score = round(_clamp(raw), 1)

    strengths: List[str] = []
    cautions: List[str] = []
    if not has_existing:
        strengths.append("kan vurderes som porteføljebyggestein, men eksisterende portefølje mangler")
    elif overlap <= 10:
        strengths.append("lav overlapp mot eksisterende portefølje")
    elif overlap >= 35:
        cautions.append("høy overlapp mot eksisterende portefølje")
    else:
        strengths.append("moderat overlapp mot eksisterende portefølje")
    strengths.extend(gap_notes[:2])
    if concentration_score < 45:
        cautions.append("fondets egne holdings er konsentrerte")
    worst = (r.get("scenario_regime_profile") or {}).get("worst_scenario") or {}
    if worst and _safe_float(worst.get("score"), 100.0) < 45:
        cautions.append(f"svakt fit i scenario: {worst.get('label')}")

    if fit_score >= 75:
        verdict = "Sterk portefølje-fit"
    elif fit_score >= 60:
        verdict = "Brukbar portefølje-fit"
    else:
        verdict = "Svak portefølje-fit"
    summary = f"{verdict}: overlap {overlap}% og største sektor {largest_sector[0]} ({round(float(largest_sector[1] or 0), 1)}%)."
    return {
        "layer": "Layer 8",
        "model": "Portfolio Fit Engine",
        "portfolio_fit_score": fit_score,
        "verdict": verdict,
        "has_existing_portfolio": has_existing,
        "overlap_pct": overlap,
        "diversification_score": round(diversification_score, 1),
        "gap_fill_score": round(gap_fill_score, 1),
        "largest_candidate_sector": {"name": largest_sector[0], "weight_pct": round(float(largest_sector[1] or 0), 2)},
        "strengths": strengths or ["ingen tydelig porteføljefordel funnet"],
        "cautions": cautions or ["ingen tydelig porteføljeadvarsel"],
        "summary": summary,
    }


def attach_portfolio_fit_layer(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    existing = _existing_portfolio_from_selection(selection_info)
    enhanced: List[Dict[str, Any]] = []
    for row in rows or []:
        r = dict(row or {})
        profile = build_portfolio_fit_profile(r, existing_portfolio=existing, peer_rows=rows)
        r["portfolio_fit_profile"] = profile
        r["portfolio_fit_score"] = profile.get("portfolio_fit_score")
        r["portfolio_fit_summary"] = profile.get("summary")
        enhanced.append(r)
    ranked = sorted(enhanced, key=lambda x: (float(x.get("portfolio_fit_score") or 0), float(x.get("fund_intelligence_score") or 0), float(x.get("data_quality") or 0)), reverse=True)
    best = ranked[0] if ranked else {}
    return {
        "layer": "Layer 8",
        "model": "Portfolio Fit Engine",
        "has_existing_portfolio": bool(existing.get("has_existing")),
        "best_symbol": best.get("symbol") or "",
        "best_name": best.get("name") or "",
        "best_score": best.get("portfolio_fit_score"),
        "ranked": ranked,
        "summary": "Portefølje-fit vurderer overlapp, hull, scenario og eksisterende eksponering før endelig rangering.",
    }




# v18.5.58 / Foundation Stabilization & Architecture Cleanup.
# This layer standardizes Layer 1-8 outputs into one governed intelligence
# envelope. It adds weight governance, confidence/freshness, standardized risk
# flags, overlap cache hooks and a first "Why this portfolio?" reasoning block.
FOUNDATION_SCHEMA_VERSION = 2
FOUNDATION_LAYER_WEIGHTS = {
    "base": 0.18,
    "decision_quality": 0.18,
    "explainability": 0.08,
    "holdings": 0.14,
    "insider": 0.10,
    "scenario": 0.14,
    "portfolio_fit": 0.18,
}
OVERLAP_CACHE_DIR = Path("storage") / "portfolio_overlap_cache"
PORTFOLIO_INTELLIGENCE_DIR = Path("storage") / "portfolio_intelligence_foundation"
REGIME_MEMORY_DIR = PORTFOLIO_INTELLIGENCE_DIR / "regime_memory"


def _data_age_days(value: Any) -> Optional[int]:
    if not value:
        return None
    try:
        txt = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0, int((now - dt.astimezone(timezone.utc)).total_seconds() // 86400))
    except Exception:
        return None


def build_weight_governance_profile(row: Mapping[str, Any]) -> Dict[str, Any]:
    r = dict(row or {})
    raw_scores = {
        "base": _safe_float(r.get("base_score"), None),
        "decision_quality": _safe_float(r.get("decision_quality"), None),
        "explainability": _safe_float((r.get("explainability_profile") or {}).get("explainability_score"), None),
        "holdings": _safe_float((r.get("holdings_profile") or {}).get("concentration_score"), None) if (r.get("holdings_profile") or {}).get("holdings_available") else None,
        "insider": _safe_float((r.get("insider_holdings_profile") or {}).get("insider_score"), None) if ((r.get("insider_holdings_profile") or {}).get("covered_top_holdings_weight_pct") or 0) > 0 else None,
        "scenario": _safe_float(r.get("scenario_score"), None),
        "portfolio_fit": _safe_float(r.get("portfolio_fit_score"), None),
    }
    available = {k: v for k, v in raw_scores.items() if v is not None}
    total_weight = sum(FOUNDATION_LAYER_WEIGHTS.get(k, 0.0) for k in available) or 1.0
    normalized = {k: round(FOUNDATION_LAYER_WEIGHTS.get(k, 0.0) / total_weight, 4) for k in available}
    missing = [k for k, v in raw_scores.items() if v is None]
    governed = sum(float(available[k]) * normalized[k] for k in available) if available else 0.0
    return {
        "schema_version": FOUNDATION_SCHEMA_VERSION,
        "model": "Weight Governance System",
        "default_weights": {k: round(float(v), 4) for k, v in FOUNDATION_LAYER_WEIGHTS.items()},
        "normalized_weights": normalized,
        "available_layers": sorted(available.keys()),
        "missing_layers": missing,
        "scores": {k: None if v is None else round(float(v), 1) for k, v in raw_scores.items()},
        "governed_score": round(_clamp(governed), 1),
        "summary": "Vekter re-normaliseres når holdings/insider eller andre datalag mangler.",
    }


def build_data_freshness_profile(row: Mapping[str, Any], data: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    d = dict(data or {})
    r = dict(row or {})
    price_age = _data_age_days(d.get("price_updated_at") or d.get("prices_updated_at") or d.get("updated_at") or r.get("created_at"))
    holdings_age = _data_age_days(d.get("holdings_updated_at") or d.get("portfolio_date") or d.get("holdings_date"))
    insider_age = _data_age_days(d.get("insider_updated_at") or d.get("insider_date"))
    ages = [x for x in [price_age, holdings_age, insider_age] if x is not None]
    oldest = max(ages) if ages else None
    warnings: List[str] = []
    if holdings_age is None and (r.get("holdings_profile") or {}).get("holdings_available"):
        warnings.append("holdings finnes, men oppdateringsdato mangler")
    if holdings_age is not None and holdings_age > 45:
        warnings.append(f"holdings-data er {holdings_age} dager gammel")
    if insider_age is not None and insider_age > 30:
        warnings.append(f"insiderdata er {insider_age} dager gammel")
    if price_age is not None and price_age > 7:
        warnings.append(f"prisdata er {price_age} dager gammel")
    if oldest is None:
        freshness_score = 55.0
        status = "Ukjent"
    else:
        freshness_score = _clamp(100.0 - min(80.0, oldest * 1.2), 5.0, 100.0)
        status = "Fersk" if freshness_score >= 75 else "Middels" if freshness_score >= 55 else "Gammel"
    return {
        "model": "Data Freshness Layer",
        "status": status,
        "freshness_score": round(freshness_score, 1),
        "price_age_days": price_age,
        "holdings_age_days": holdings_age,
        "insider_age_days": insider_age,
        "warnings": warnings,
        "summary": "Datoferskhet vurderes per pris, holdings og insider der kilden oppgir dato.",
    }


def build_confidence_profile(row: Mapping[str, Any], freshness: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    r = dict(row or {})
    f = dict(freshness or {})
    data_quality = _safe_float(r.get("data_quality"), 50.0) or 50.0
    holdings_available = bool((r.get("holdings_profile") or {}).get("holdings_available"))
    insider_covered = _safe_float((r.get("insider_holdings_profile") or {}).get("covered_top_holdings_weight_pct"), 0.0) or 0.0
    freshness_score = _safe_float(f.get("freshness_score"), 55.0) or 55.0
    layer_count = len([x for x in [r.get("base_score"), r.get("decision_quality"), r.get("fund_intelligence_score"), r.get("scenario_score"), r.get("portfolio_fit_score")] if x is not None])
    score = data_quality * 0.32 + freshness_score * 0.22 + min(100.0, layer_count * 18.0) * 0.20
    score += (85.0 if holdings_available else 45.0) * 0.16
    score += min(100.0, insider_covered * 2.0) * 0.10
    score = round(_clamp(score), 1)
    level = "Høy" if score >= 75 else "Middels" if score >= 55 else "Lav"
    drivers: List[str] = []
    cautions: List[str] = []
    if data_quality >= 70:
        drivers.append("god datakvalitet")
    else:
        cautions.append("datakvalitet begrenser tillit")
    if holdings_available:
        drivers.append("holdings-laget er tilgjengelig")
    else:
        cautions.append("holdings mangler")
    if insider_covered > 0:
        drivers.append("insiderdekning finnes for topp-posisjoner")
    else:
        cautions.append("insiderdekning mangler")
    cautions.extend(list(f.get("warnings") or [])[:3])
    return {
        "model": "Confidence Engine",
        "confidence_score": score,
        "confidence_level": level,
        "drivers": drivers,
        "cautions": cautions,
        "summary": f"Tillit: {level} ({score}/100).",
    }


def build_standard_risk_flags(row: Mapping[str, Any]) -> List[Dict[str, Any]]:
    r = dict(row or {})
    holdings = dict(r.get("holdings_profile") or {})
    insider = dict(r.get("insider_holdings_profile") or {})
    scenario = dict(r.get("scenario_regime_profile") or {})
    flags: List[Dict[str, Any]] = []
    def add(flag: str, severity: str, reason: str) -> None:
        if not any(x.get("flag") == flag for x in flags):
            flags.append({"flag": flag, "severity": severity, "reason": reason})
    if _safe_float(holdings.get("top10_weight_pct"), 0.0) and (_safe_float(holdings.get("top10_weight_pct"), 0.0) or 0) >= 55:
        add("Concentration Risk", "Høy", "topp 10 holdings utgjør stor andel")
    if (_safe_float(holdings.get("megacap_weight_pct"), 0.0) or 0) >= 35:
        add("Megacap Dependency", "Middels", "stor avhengighet av megacaps")
    sectors = dict(holdings.get("sector_weights") or {})
    tech = max([float(_safe_float(v, 0.0) or 0.0) for k, v in sectors.items() if "tech" in str(k).lower() or "tekn" in str(k).lower()] or [0.0])
    if tech >= 30:
        add("AI/Technology Concentration", "Middels", "stor teknologi-/AI-relatert eksponering")
    if str(insider.get("direction") or "") == "Negativ":
        add("Insider Weakness", "Middels", "insiderbildet i topp-posisjoner peker negativt")
    worst = scenario.get("worst_scenario") or {}
    if _safe_float(worst.get("score"), 100.0) is not None and (_safe_float(worst.get("score"), 100.0) or 100) < 45:
        add("Regime Fragility", "Middels", f"svak i scenario: {worst.get('label')}")
    if str(r.get("fund_type") or "") == "High yield-fond":
        add("Credit Fragility", "Høy", "high yield er sårbart ved kredittstress")
    if _safe_float(r.get("duration"), 0.0) and (_safe_float(r.get("duration"), 0.0) or 0) >= 7:
        add("Duration Sensitivity", "Middels", "høy durasjon gir rentefølsomhet")
    if not flags:
        add("No Major Standard Flag", "Lav", "ingen standardisert hovedrisiko funnet i tilgjengelige data")
    return flags


def _portfolio_overlap_cache_key(rows: Sequence[Mapping[str, Any]], selection_info: Optional[Mapping[str, Any]] = None) -> str:
    payload = {
        "symbols": sorted(str(r.get("symbol") or "").upper() for r in rows or []),
        "selection": selection_info or {},
        "schema": FOUNDATION_SCHEMA_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]


def write_portfolio_overlap_cache(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    try:
        OVERLAP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = _portfolio_overlap_cache_key(rows, selection_info)
        payload = {
            "schema_version": FOUNDATION_SCHEMA_VERSION,
            "created_at": _now_iso(),
            "key": key,
            "rows": [{"symbol": r.get("symbol"), "overlap_pct": (r.get("portfolio_fit_profile") or {}).get("overlap_pct"), "portfolio_fit_score": r.get("portfolio_fit_score")} for r in rows or []],
        }
        path = OVERLAP_CACHE_DIR / f"overlap__{key}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {"enabled": True, "key": key, "path": str(path), "rows": len(payload["rows"])}
    except Exception as exc:
        return {"enabled": False, "error": str(exc)[:200]}




# v18.5.59 / Consolidated Intelligence Modules.
# The previous foundation pieces are kept for backward compatibility, but the
# app now exposes three clearer modules: Intelligence Core, Explanation & Risk
# Engine, and Portfolio Intelligence Foundation.
def build_intelligence_core_profile(row: Mapping[str, Any], *, data: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    r = dict(row or {})
    freshness = build_data_freshness_profile(r, data)
    confidence = build_confidence_profile(r, freshness)
    governance = build_weight_governance_profile(r)
    governed_score = _safe_float(governance.get("governed_score"), 0.0) or 0.0
    confidence_score = _safe_float(confidence.get("confidence_score"), 50.0) or 50.0
    core_score = round(_clamp(governed_score * 0.88 + confidence_score * 0.12), 1)
    return {
        "module": "A",
        "model": "Intelligence Core",
        "schema_version": FOUNDATION_SCHEMA_VERSION,
        "core_score": core_score,
        "unified_schema": {
            "base_score": r.get("base_score_profile") or {"base_score": r.get("base_score")},
            "decision_quality": r.get("fund_decision_quality") or {"decision_quality": r.get("decision_quality")},
            "explainability": r.get("explainability_profile") or {},
            "holdings": r.get("holdings_profile") or {},
            "insider": r.get("insider_holdings_profile") or {},
            "scenario": r.get("scenario_regime_profile") or {},
            "portfolio_fit": r.get("portfolio_fit_profile") or {},
            "composite": r.get("composite_intelligence_profile") or {},
        },
        "weight_governance": governance,
        "confidence": confidence,
        "freshness": freshness,
        "summary": f"Intelligence Core samler schema, vekter, confidence og freshness i én styrt kjerne ({core_score}/100).",
    }


def build_explanation_risk_engine_profile(row: Mapping[str, Any], *, core: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    r = dict(row or {})
    c = dict(core or {})
    flags = build_standard_risk_flags(r)
    explain = dict(r.get("explainability_profile") or {})
    confidence = dict(c.get("confidence") or r.get("confidence_profile") or {})
    positives = list(explain.get("strengths") or r.get("reasons_positive") or [])[:4]
    negatives = list(explain.get("weaknesses") or r.get("reasons_caution") or [])[:4]
    if confidence.get("confidence_level") == "Lav":
        negatives.append("lav confidence gjør konklusjonen mindre sikker")
    return {
        "module": "B",
        "model": "Explanation & Risk Engine",
        "positives": positives,
        "negatives": negatives,
        "risk_flags": flags,
        "confidence_level": confidence.get("confidence_level"),
        "summary": "Forklaring og risiko er samlet i ett lag slik at UI bruker samme språk og samme flagg overalt.",
    }


def _selection_context_key(selection_info: Optional[Mapping[str, Any]] = None) -> str:
    info = dict(selection_info or {})
    raw = "|".join([
        str(info.get("fund_type") or info.get("type") or "all"),
        str(info.get("objective") or info.get("profile") or "general"),
        str(info.get("source") or info.get("mode") or "auto"),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _holding_symbols(row: Mapping[str, Any]) -> set[str]:
    holdings = (row.get("holdings_profile") or {}).get("top_holdings") or []
    symbols: set[str] = set()
    for item in holdings:
        if not isinstance(item, Mapping):
            continue
        sym = str(item.get("symbol") or item.get("ticker") or "").upper().strip()
        if sym:
            symbols.add(sym)
    return symbols


def build_portfolio_overlap_matrix(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    ranked = [dict(r or {}) for r in rows or []]
    symbols = [str(r.get("symbol") or "").upper() for r in ranked]
    holding_sets = {str(r.get("symbol") or "").upper(): _holding_symbols(r) for r in ranked}
    pairs: List[Dict[str, Any]] = []
    for i, a in enumerate(symbols):
        for b in symbols[i + 1:]:
            a_set, b_set = holding_sets.get(a, set()), holding_sets.get(b, set())
            if a_set and b_set:
                union = len(a_set | b_set) or 1
                overlap = round(100.0 * len(a_set & b_set) / union, 2)
                method = "holdings_jaccard"
            else:
                overlap = 0.0
                method = "no_holdings"
            if overlap > 0:
                pairs.append({"a": a, "b": b, "overlap_pct": overlap, "method": method})
    pairs.sort(key=lambda x: float(x.get("overlap_pct") or 0), reverse=True)
    return {
        "model": "Portfolio Overlap Matrix",
        "fund_count": len(symbols),
        "pair_count": len(pairs),
        "highest_overlaps": pairs[:10],
        "summary": "Overlap-cache bruker holdings når tilgjengelig, og holder parvis overlapp klar for porteføljeanalyse.",
    }


def write_portfolio_intelligence_cache(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    try:
        PORTFOLIO_INTELLIGENCE_DIR.mkdir(parents=True, exist_ok=True)
        key = _portfolio_overlap_cache_key(rows, selection_info)
        matrix = build_portfolio_overlap_matrix(rows)
        payload = {
            "schema_version": FOUNDATION_SCHEMA_VERSION,
            "created_at": _now_iso(),
            "key": key,
            "context_key": _selection_context_key(selection_info),
            "overlap_matrix": matrix,
            "funds": [str(r.get("symbol") or "").upper() for r in rows or []],
        }
        path = PORTFOLIO_INTELLIGENCE_DIR / f"portfolio_foundation__{key}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {"enabled": True, "key": key, "path": str(path), "overlap_matrix": matrix}
    except Exception as exc:
        return {"enabled": False, "error": str(exc)[:200]}


def _regime_memory_payload(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    ranked = [dict(r or {}) for r in rows or []]
    best: Dict[str, int] = {}
    worst: Dict[str, int] = {}
    fragile: List[str] = []
    for r in ranked:
        scenario = dict(r.get("scenario_regime_profile") or {})
        b = ((scenario.get("best_scenario") or {}).get("label") or "Ukjent")
        w = ((scenario.get("worst_scenario") or {}).get("label") or "Ukjent")
        best[b] = best.get(b, 0) + 1
        worst[w] = worst.get(w, 0) + 1
        if _safe_float(((scenario.get("worst_scenario") or {}).get("score")), 100.0) < 45:
            fragile.append(str(r.get("symbol") or "").upper())
    return {
        "schema_version": FOUNDATION_SCHEMA_VERSION,
        "created_at": _now_iso(),
        "context_key": _selection_context_key(selection_info),
        "fund_count": len(ranked),
        "best_scenario_counts": best,
        "worst_scenario_counts": worst,
        "fragile_symbols": fragile,
        "average_scenario_score": round(sum(_safe_float(r.get("scenario_score"), 0.0) or 0.0 for r in ranked) / max(1, len(ranked)), 1),
    }


def _load_previous_regime_memory(context_key: str) -> Optional[Dict[str, Any]]:
    try:
        if not REGIME_MEMORY_DIR.exists():
            return None
        files = sorted(REGIME_MEMORY_DIR.glob(f"regime__{context_key}__*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not files:
            return None
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def build_regime_memory_profile(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    context_key = _selection_context_key(selection_info)
    current = _regime_memory_payload(rows, selection_info=selection_info)
    previous = _load_previous_regime_memory(context_key)
    changes: List[str] = []
    if previous:
        delta = round(float(current.get("average_scenario_score") or 0) - float(previous.get("average_scenario_score") or 0), 1)
        if abs(delta) >= 3:
            changes.append(f"scenario-score endret {delta:+.1f} poeng siden forrige sammenlignbare kjøring")
        new_fragile = sorted(set(current.get("fragile_symbols") or []) - set(previous.get("fragile_symbols") or []))
        if new_fragile:
            changes.append(f"nye regimesårbare fond: {', '.join(new_fragile[:5])}")
    else:
        changes.append("første regime-memory for dette universet; brukes som baseline")
    try:
        REGIME_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = REGIME_MEMORY_DIR / f"regime__{context_key}__{stamp}.json"
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        stored = str(path)
    except Exception as exc:
        stored = f"ikke lagret: {str(exc)[:160]}"
    return {
        "model": "Regime Memory",
        "context_key": context_key,
        "current": current,
        "previous_available": bool(previous),
        "changes": changes,
        "stored_path": stored,
        "summary": "Regime Memory husker hvordan dette universet reagerte i forrige sammenlignbare analyse.",
    }


def build_portfolio_construction_reasoning(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    why = build_why_this_portfolio_profile(rows, selection_info=selection_info)
    matrix = build_portfolio_overlap_matrix(rows)
    ranked = [dict(r or {}) for r in rows or []]
    top = ranked[: max(1, min(8, len(ranked)))]
    diversifiers = [str(r.get("symbol") or "").upper() for r in top if (_safe_float((r.get("portfolio_fit_profile") or {}).get("overlap_pct"), 0.0) or 0.0) <= 10]
    weak_links = [str(r.get("symbol") or "").upper() for r in top if (_safe_float(r.get("confidence_score"), 100.0) or 100.0) < 55]
    reasons = list(why.get("reasons") or [])
    if diversifiers:
        reasons.append(f"ekte diversifisering fra {', '.join(diversifiers[:5])}")
    cautions = list(why.get("cautions") or [])
    if weak_links:
        cautions.append(f"svakt datagrunnlag i {', '.join(weak_links[:5])}")
    if matrix.get("highest_overlaps"):
        worst = matrix["highest_overlaps"][0]
        if float(worst.get("overlap_pct") or 0) >= 40:
            cautions.append(f"høy intern overlapp mellom {worst.get('a')} og {worst.get('b')}")
    return {
        "model": "Why This Portfolio?",
        "selected_count": len(top),
        "reasons": reasons or ["kombinasjonen er valgt ut fra score, portefølje-fit og datakvalitet"],
        "cautions": cautions or ["ingen samlet porteføljeadvarsel funnet"],
        "diversifier_symbols": diversifiers,
        "summary": "Forklarer hvorfor kombinasjonen av fond gir mening sammen, ikke bare hvorfor hvert fond er godt alene.",
    }


def build_portfolio_intelligence_foundation_profile(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    ranked = [dict(r or {}) for r in rows or []]
    legacy_cache = write_portfolio_overlap_cache(ranked, selection_info=selection_info)
    intelligence_cache = write_portfolio_intelligence_cache(ranked, selection_info=selection_info)
    regime_memory = build_regime_memory_profile(ranked, selection_info=selection_info)
    why = build_portfolio_construction_reasoning(ranked, selection_info=selection_info)
    avg_fit = None
    if ranked:
        avg_fit = round(sum(_safe_float(r.get("portfolio_fit_score"), 0.0) or 0.0 for r in ranked) / len(ranked), 1)
    return {
        "module": "C",
        "model": "Portfolio Intelligence Foundation",
        "average_portfolio_fit": avg_fit,
        "portfolio_overlap_cache": legacy_cache,
        "portfolio_intelligence_cache": intelligence_cache,
        "overlap_matrix": (intelligence_cache.get("overlap_matrix") if isinstance(intelligence_cache, Mapping) else None),
        "regime_memory": regime_memory,
        "why_this_portfolio": why,
        "components": ["Portfolio Overlap Cache", "Regime Memory", "Why this portfolio?"],
        "summary": "Portfolio Intelligence Foundation samler overlap-cache, regime memory og hvorfor-porteføljen-logikk som grunnmur for full Portfolio Intelligence Engine.",
    }

def build_unified_intelligence_profile(row: Mapping[str, Any], *, data: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    r = dict(row or {})
    intelligence_core = build_intelligence_core_profile(r, data=data)
    explanation_risk = build_explanation_risk_engine_profile(r, core=intelligence_core)
    weights = dict(intelligence_core.get("weight_governance") or {})
    confidence = dict(intelligence_core.get("confidence") or {})
    freshness = dict(intelligence_core.get("freshness") or {})
    flags = list(explanation_risk.get("risk_flags") or [])
    foundation_score = _safe_float(intelligence_core.get("core_score"), 0.0) or 0.0
    return {
        "schema_version": FOUNDATION_SCHEMA_VERSION,
        "version": get_app_version(),
        "model": "Unified Intelligence Model",
        "foundation_score": round(_clamp(foundation_score), 1),
        "modules": {
            "intelligence_core": intelligence_core,
            "explanation_risk_engine": explanation_risk,
        },
        "intelligence_core": intelligence_core,
        "explanation_risk_engine": explanation_risk,
        "layers": intelligence_core.get("unified_schema") or {},
        "weight_governance": weights,
        "confidence": confidence,
        "freshness": freshness,
        "risk_flags": flags,
        "summary": f"Unified score {round(_clamp(foundation_score), 1)}/100 med {confidence.get('confidence_level')} tillit.",
    }


def attach_foundation_stabilization(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    enhanced: List[Dict[str, Any]] = []
    for row in rows or []:
        r = dict(row or {})
        unified = build_unified_intelligence_profile(r)
        r["unified_intelligence_profile"] = unified
        r["foundation_score"] = unified.get("foundation_score")
        r["confidence_profile"] = unified.get("confidence")
        r["confidence_score"] = (unified.get("confidence") or {}).get("confidence_score")
        r["confidence_level"] = (unified.get("confidence") or {}).get("confidence_level")
        r["freshness_profile"] = unified.get("freshness")
        r["standard_risk_flags"] = unified.get("risk_flags") or []
        r["weight_governance_profile"] = unified.get("weight_governance")
        r["intelligence_core_profile"] = unified.get("intelligence_core")
        r["explanation_risk_engine_profile"] = unified.get("explanation_risk_engine")
        enhanced.append(r)
    ranked = sorted(enhanced, key=lambda x: (float(x.get("foundation_score") or 0), float(x.get("portfolio_fit_score") or 0), float(x.get("fund_intelligence_score") or 0)), reverse=True)
    portfolio_foundation = build_portfolio_intelligence_foundation_profile(ranked, selection_info=selection_info)
    cache = portfolio_foundation.get("portfolio_overlap_cache") or {}
    return {
        "schema_version": FOUNDATION_SCHEMA_VERSION,
        "model": "Consolidated Intelligence Architecture",
        "ranked": ranked,
        "modules": {
            "intelligence_core": "per fund",
            "explanation_risk_engine": "per fund",
            "portfolio_intelligence_foundation": portfolio_foundation,
        },
        "portfolio_intelligence_foundation": portfolio_foundation,
        "overlap_cache": cache,
        "summary": "Foundation er samlet i tre moduler: Intelligence Core, Explanation & Risk Engine og Portfolio Intelligence Foundation.",
    }


def build_why_this_portfolio_profile(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    ranked = [dict(r) for r in (rows or [])]
    selected = ranked[: max(1, min(8, len(ranked)))]
    reasons: List[str] = []
    cautions: List[str] = []
    if not selected:
        return {"model": "Why This Portfolio Engine", "summary": "Ingen portefølje å forklare.", "reasons": [], "cautions": []}
    avg_fit = round(sum(_safe_float(r.get("portfolio_fit_score"), 0.0) or 0.0 for r in selected) / len(selected), 1)
    avg_conf = round(sum(_safe_float(r.get("confidence_score"), 0.0) or 0.0 for r in selected) / len(selected), 1)
    low_overlap = [r.get("symbol") for r in selected if ((r.get("portfolio_fit_profile") or {}).get("overlap_pct") or 0) <= 10]
    if low_overlap:
        reasons.append(f"lav overlapp i {len(low_overlap)} av toppkandidatene")
    scenarios = [((r.get("scenario_regime_profile") or {}).get("best_scenario") or {}).get("label") for r in selected]
    scenarios = [s for s in scenarios if s]
    if scenarios:
        reasons.append("scenario-balanse vurdert på tvers av kandidatene")
    flags = []
    for r in selected:
        flags.extend([f.get("flag") for f in (r.get("standard_risk_flags") or []) if f.get("severity") in {"Høy", "Middels"}])
    if flags:
        cautions.append(f"{len(flags)} standardiserte risikoflagg må overvåkes i topputvalget")
    if avg_conf < 60:
        cautions.append("gjennomsnittlig confidence er bare middels/lav")
    summary = f"Porteføljen forklares med gj.snittlig portefølje-fit {avg_fit}/100 og confidence {avg_conf}/100."
    return {
        "model": "Why This Portfolio Engine",
        "selected_count": len(selected),
        "average_portfolio_fit": avg_fit,
        "average_confidence": avg_conf,
        "reasons": reasons or ["beste kombinasjon ut fra score, fit og tilgjengelig datagrunnlag"],
        "cautions": cautions or ["ingen samlet hovedadvarsel i topputvalget"],
        "summary": summary,
    }

def build_fund_decision_quality_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build a UI-ready summary for hardened Fund Decision Quality."""
    valid = [dict(r) for r in (rows or []) if r]
    if not valid:
        return {
            "count": 0,
            "average_quality": None,
            "grade_counts": {},
            "role_counts": {},
            "decision_counts": {},
            "best_symbol": "",
            "rows": [],
            "warnings": ["Ingen fondskvalitet beregnet ennå."],
        }
    avg = round(sum(_safe_float(r.get("decision_quality"), 0.0) or 0.0 for r in valid) / max(1, len(valid)), 1)
    avg_base = round(sum(_safe_float(r.get("base_score"), 0.0) or 0.0 for r in valid) / max(1, len(valid)), 1)
    grade_counts: Dict[str, int] = {}
    role_counts: Dict[str, int] = {}
    decision_counts: Dict[str, int] = {}
    out_rows: List[Dict[str, Any]] = []
    for row in valid:
        grade = str(row.get("grade") or "Ukjent")
        role = str(row.get("recommended_role") or "Ukjent")
        decision = str(row.get("decision") or "Ukjent")
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
        role_counts[role] = role_counts.get(role, 0) + 1
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        profile = dict(row.get("fund_decision_quality") or {})
        out_rows.append({
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "fund_type": row.get("fund_type"),
            "decision_quality": row.get("decision_quality"),
            "grade": grade,
            "decision": decision,
            "recommended_role": role,
            "base_score": row.get("base_score"),
            "base_score_profile": row.get("base_score_profile") or {},
            "base_score_summary": row.get("base_score_summary"),
            "component_scores": row.get("quality_breakdown") or profile.get("component_scores") or {},
            "role_scores": row.get("role_scores") or profile.get("role_scores") or {},
            "drivers": profile.get("drivers") or row.get("reasons_positive") or [],
            "cautions": profile.get("cautions") or row.get("reasons_caution") or [],
            "why_not_100": row.get("why_not_100") or profile.get("why_not_100") or [],
            "fixed_income_profile": row.get("fixed_income_profile") or {},
            "explainability_profile": row.get("explainability_profile") or {},
            "explainability_summary": row.get("explainability_summary"),
            "holdings_profile": row.get("holdings_profile") or {},
            "insider_holdings_profile": row.get("insider_holdings_profile") or {},
            "fund_intelligence_score": row.get("fund_intelligence_score"),
            "scenario_score": row.get("scenario_score"),
            "scenario_regime_profile": row.get("scenario_regime_profile") or {},
            "scenario_summary": row.get("scenario_summary"),
            "portfolio_fit_score": row.get("portfolio_fit_score"),
            "portfolio_fit_profile": row.get("portfolio_fit_profile") or {},
            "portfolio_fit_summary": row.get("portfolio_fit_summary"),
            "foundation_score": row.get("foundation_score"),
            "unified_intelligence_profile": row.get("unified_intelligence_profile") or {},
            "confidence_profile": row.get("confidence_profile") or {},
            "confidence_score": row.get("confidence_score"),
            "confidence_level": row.get("confidence_level"),
            "freshness_profile": row.get("freshness_profile") or {},
            "standard_risk_flags": row.get("standard_risk_flags") or [],
            "weight_governance_profile": row.get("weight_governance_profile") or {},
            "holdings_summary": row.get("holdings_summary"),
            "insider_summary": row.get("insider_summary"),
            "why_ranked_here": row.get("why_ranked_here") or [],
            "what_holds_it_back": row.get("what_holds_it_back") or [],
            "what_would_make_it_selected": row.get("what_would_make_it_selected") or [],
            "what_would_make_model_reject_it": row.get("what_would_make_model_reject_it") or [],
        })
    out_rows = sorted(out_rows, key=lambda r: _safe_float(r.get("decision_quality"), 0.0) or 0.0, reverse=True)
    warnings = []
    if decision_counts.get("Krever mer bevis", 0):
        warnings.append("Noen fond krever mer bevis før de bør brukes i forslag.")
    if role_counts.get("Grunnmur", 0) == 0:
        warnings.append("Ingen tydelig grunnmur-kandidat funnet.")
    return {
        "count": len(valid),
        "average_quality": avg,
        "average_base_score": avg_base,
        "average_portfolio_fit_score": round(sum(_safe_float(r.get("portfolio_fit_score"), 0.0) or 0.0 for r in valid) / max(1, len(valid)), 1),
        "grade_counts": grade_counts,
        "role_counts": role_counts,
        "decision_counts": decision_counts,
        "best_symbol": out_rows[0].get("symbol") if out_rows else "",
        "rows": out_rows,
        "warnings": warnings,
    }

def run_fund_etf_lab(
    symbols: Sequence[str],
    *,
    data_provider: FundDataProvider,
    benchmark_provider: Optional[BenchmarkProvider] = None,
    benchmark_symbol: str = "SPY",
    fund_type: str = "Alle",
    objective: str = "Balansert",
    test_mode: str = "Normal",
    progress_callback: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
    max_funds: int = 40,
    selection_info: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    clean: List[str] = []
    seen = set()
    for raw in symbols or []:
        symbol = normalize_fund_symbol(raw)
        if symbol and symbol not in seen:
            clean.append(symbol)
            seen.add(symbol)
        # v18.5.49: keep all supplied universe symbols. `max_funds` is a
        # display/result limit, not an analysis limit.
    display_limit = max(1, int(max_funds or 8))
    budget = estimate_fund_etf_run(clean, test_mode=test_mode, include_benchmark=bool(benchmark_provider), fetch_costs=True)
    tests = list(budget.get("tests") or [])
    total_tests = int(budget.get("total_tests") or 0)
    completed = 0
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    interrupted = False

    benchmark_data: Optional[Mapping[str, Any]] = None
    if benchmark_provider and benchmark_symbol:
        try:
            benchmark_data = benchmark_provider(benchmark_symbol)
        except Exception as exc:
            errors.append({"symbol": benchmark_symbol, "test": "Benchmark", "error": str(exc)[:200]})
            benchmark_data = None

    _emit_progress(progress_callback, completed_tests=0, total_tests=total_tests, status="starting", message="Starter Fond / ETF-analyse")

    for fund_idx, symbol in enumerate(clean, start=1):
        if should_stop and should_stop():
            interrupted = True
            break
        data: Optional[Mapping[str, Any]] = None
        for test_idx, test_name in enumerate(tests, start=1):
            if should_stop and should_stop():
                interrupted = True
                break
            _emit_progress(
                progress_callback,
                symbol=symbol,
                fund_index=fund_idx,
                fund_total=len(clean),
                test_name=test_name,
                test_index=test_idx,
                tests_per_fund=len(tests),
                completed_tests=completed,
                total_tests=total_tests,
                status="running",
            )
            try:
                # Fetch once at first test. Subsequent tests reuse same data.
                if data is None:
                    data = data_provider(symbol)
                # Computation happens after all named checks have been displayed.
            except Exception as exc:
                errors.append({"symbol": symbol, "test": test_name, "error": str(exc)[:200]})
                data = None
            completed += 1
            _emit_progress(
                progress_callback,
                symbol=symbol,
                fund_index=fund_idx,
                fund_total=len(clean),
                test_name=test_name,
                test_index=test_idx,
                tests_per_fund=len(tests),
                completed_tests=completed,
                total_tests=total_tests,
                status="running",
            )
        if interrupted:
            break
        try:
            row = analyze_fund_record(symbol, data, fund_type=fund_type, objective=objective, benchmark_data=benchmark_data)
            if row.get("data_points", 0) < 2:
                row["decision"] = "Mangler data"
                row.setdefault("reasons_caution", []).append("ingen prisserie funnet")
            results.append(row)
        except Exception as exc:
            errors.append({"symbol": symbol, "test": "Analyse", "error": str(exc)[:200]})

    ranked = sorted(results, key=lambda x: (float(x.get("fund_intelligence_score") or x.get("decision_quality") or 0), float(x.get("data_quality") or 0)), reverse=True)
    portfolio_fit = attach_portfolio_fit_layer(ranked, selection_info=selection_info)
    ranked = list(portfolio_fit.get("ranked") or ranked)
    foundation = attach_foundation_stabilization(ranked, selection_info=selection_info)
    ranked = list(foundation.get("ranked") or ranked)
    why_this_portfolio = (foundation.get("portfolio_intelligence_foundation") or {}).get("why_this_portfolio") or build_why_this_portfolio_profile(ranked, selection_info=selection_info)
    index_candidates = [r for r in ranked if r.get("fund_type") in {"Indeksfond", "ETF"}]
    active_candidates = [r for r in ranked if r.get("fund_type") == "Aktivt fond"]
    fixed_income_candidates = [r for r in ranked if r.get("fund_type") in FIXED_INCOME_TYPES]
    high_yield_candidates = [r for r in ranked if r.get("fund_type") == "High yield-fond"]
    needs_proof = [r for r in ranked if r.get("decision") in {"Krever mer bevis", "Vent / forkast", "Mangler data"}]
    comparator = build_fund_comparator(ranked)
    decision_quality_summary = build_fund_decision_quality_summary(ranked)
    core_satellite = build_core_satellite_portfolio(ranked, profile=objective, max_positions=min(display_limit, 8))
    cost_impact = build_fund_cost_impact(ranked)
    summary = {
        "best_symbol": ranked[0].get("symbol") if ranked else "",
        "best_quality": ranked[0].get("decision_quality") if ranked else None,
        "best_base_score": ranked[0].get("base_score") if ranked else None,
        "best_portfolio_fit_score": ranked[0].get("portfolio_fit_score") if ranked else None,
        "best_foundation_score": ranked[0].get("foundation_score") if ranked else None,
        "best_confidence_level": ranked[0].get("confidence_level") if ranked else None,
        "analyzed": len(results),
        "errors": len(errors),
        "interrupted": interrupted,
        "selected_max": display_limit,
        "actual_analyzed": len(results),
        "available_in_universe": (selection_info or {}).get("available_in_universe"),
    }
    result_payload = {
        "version": get_app_version(),
        "created_at": _now_iso(),
        "fund_type": fund_type,
        "objective": objective,
        "test_mode": test_mode,
        "benchmark_symbol": benchmark_symbol,
        "symbols": clean,
        "selection": dict(selection_info or {}),
        "budget": budget,
        "completed_tests": completed,
        "total_tests": total_tests,
        "interrupted": interrupted,
        "summary": summary,
        "ranked": ranked,
        "index_candidates": index_candidates,
        "active_candidates": active_candidates,
        "fixed_income_candidates": fixed_income_candidates,
        "high_yield_candidates": high_yield_candidates,
        "needs_proof": needs_proof,
        "comparator": comparator,
        "decision_quality_summary": decision_quality_summary,
        "active_evidence": comparator.get("active_evidence", []),
        "core_satellite": core_satellite,
        "cost_impact": cost_impact,
        "portfolio_fit": portfolio_fit,
        "foundation": foundation,
        "why_this_portfolio": why_this_portfolio,
        "errors": errors,
    }
    return attach_and_store_what_changed(result_payload)
