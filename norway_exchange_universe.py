"""Authoritative Norway equity master from Euronext Oslo markets.

RC16.31br centralises the Norway instrument universe for reports, Fresh Trend,
learning and Paper Trade.  The live source is Euronext's stock data endpoint
for XOSL (Oslo Bors), MERK (Euronext Growth Oslo) and XOAS (Euronext Expand
Oslo).  A durable last-known-good snapshot is retained so a temporary network
failure cannot silently shrink the production universe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re
from typing import Any, Iterable, Mapping

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

EURONEXT_STOCKS_ENDPOINT = "https://live.euronext.com/en/pd/data/stocks"
EURONEXT_OSLO_LIST_URL = "https://live.euronext.com/en/markets/oslo/equities/list"
NORWAY_EQUITY_MICS = ("XOSL", "MERK", "XOAS")
MIC_TO_MARKET = {
    "XOSL": "Oslo Børs",
    "MERK": "Euronext Growth Oslo",
    "XOAS": "Euronext Expand Oslo",
}
MARKET_TO_MIC = {value.casefold(): key for key, value in MIC_TO_MARKET.items()}
MASTER_KEY = "market_universe/norway_euronext_master.json"
MASTER_PATH = runtime_data_path("market_universe", "norway_euronext_master.json")
MASTER_SCHEMA_VERSION = "1.0"
REFRESH_SECONDS = 20 * 60 * 60
MIN_REASONABLE_OFFICIAL_ROWS = 150

_TAG_RE = re.compile(r"<[^>]+>")
_ATTR_TEXT_RE = re.compile(r"data-(?:title-hover|order)=['\"]([^'\"]+)['\"]", re.I)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any) -> str:
    raw = str(value or "")
    match = _ATTR_TEXT_RE.search(raw)
    if match and not _TAG_RE.sub("", raw).strip():
        raw = match.group(1)
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", raw))).strip()


def _age_seconds(value: Any) -> float | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _mic_from_market(value: str) -> str:
    text = str(value or "").strip().casefold()
    if text in MARKET_TO_MIC:
        return MARKET_TO_MIC[text]
    if "growth" in text or "merk" in text:
        return "MERK"
    if "expand" in text or "axess" in text or "xoas" in text:
        return "XOAS"
    return "XOSL"


def _analysis_ticker(symbol: str) -> str:
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        return ""
    if symbol.endswith(".OL"):
        return symbol
    # Euronext symbols can contain spaces in display text. Yahoo Oslo symbols
    # use the exchange symbol plus .OL; stripping display whitespace is safer
    # than inventing another alias. Missing Yahoo coverage remains auditable.
    return re.sub(r"\s+", "", symbol) + ".OL"


def _parse_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("aaData") or payload.get("data") or []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 4:
            continue
        name = _text(raw[0])
        isin = _text(raw[1]).upper()
        symbol = _text(raw[2]).upper()
        market_name = _text(raw[3])
        if not symbol:
            continue
        mic = _mic_from_market(market_name)
        if mic not in NORWAY_EQUITY_MICS:
            continue
        key = (isin or symbol, mic)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "ticker": _analysis_ticker(symbol),
            "analysis_ticker": _analysis_ticker(symbol),
            "exchange_symbol": symbol,
            "symbol": symbol,
            "isin": isin,
            "name": name or symbol,
            "company_name": name or symbol,
            "market": "Norge",
            "country": "Norge",
            "currency": "NOK",
            "exchange_name": MIC_TO_MARKET[mic],
            "market_segment": MIC_TO_MARKET[mic],
            "exchange_mic": mic,
            "listing_status": "ACTIVE",
            "universe_source": "EURONEXT_OFFICIAL",
            "source": "Euronext official Norway equity master",
            "source_url": EURONEXT_OSLO_LIST_URL,
        })
    rows.sort(key=lambda row: (NORWAY_EQUITY_MICS.index(row["exchange_mic"]), row["exchange_symbol"]))
    return rows


def _request_payload() -> tuple[dict[str, str], dict[str, str]]:
    params = {
        "mics": ",".join(NORWAY_EQUITY_MICS),
        "display_datapoints": "dp_stocks",
        "display_filters": "df_stocks",
    }
    data = {"draw": "1", "start": "0", "length": "2000", "search[value]": "", "search[regex]": "false",
            "iDisplayLength": "2000", "iDisplayStart": "0", "sSortDir_0": "asc", "order[0][column]": "0", "order[0][dir]": "asc"}
    for idx in range(7):
        data[f"columns[{idx}][data]"] = str(idx)
        data[f"columns[{idx}][name]"] = ""
        data[f"columns[{idx}][searchable]"] = "true"
        data[f"columns[{idx}][orderable]"] = "true" if idx == 0 else "false"
        data[f"columns[{idx}][search][value]"] = ""
        data[f"columns[{idx}][search][regex]"] = "false"
    return params, data


def fetch_official_norway_master(timeout: float = 12.0) -> dict[str, Any]:
    import requests
    params, data = _request_payload()
    session = requests.Session()
    headers = {
        "User-Agent": "AI-Aksje-Analyzer/19.22 Norway-universe (+Euronext official equity master)",
        "Accept": "application/json,text/plain,*/*",
        "Referer": EURONEXT_OSLO_LIST_URL,
    }
    # Euronext may bind the data endpoint to cookies established by the public
    # list page. Prime the session first; failure here is non-fatal because the
    # endpoint can also answer directly in some deployments.
    try:
        session.get(EURONEXT_OSLO_LIST_URL, headers=headers, timeout=min(timeout, 8.0))
    except Exception:
        pass
    response = session.post(EURONEXT_STOCKS_ENDPOINT, params=params, data=data, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    rows = _parse_rows(payload)
    expected = int(payload.get("recordsFiltered") or payload.get("iTotalDisplayRecords") or len(rows) or 0)
    if len(rows) < MIN_REASONABLE_OFFICIAL_ROWS:
        raise RuntimeError(f"Euronext returned only {len(rows)} Norway equity rows; refusing to replace last-known-good master")
    if expected and len(rows) < min(expected, 2000):
        raise RuntimeError(f"Euronext universe incomplete: parsed {len(rows)} of {expected}")
    now = _now_iso()
    by_exchange: dict[str, int] = {}
    for row in rows:
        by_exchange[row["exchange_name"]] = by_exchange.get(row["exchange_name"], 0) + 1
        row["last_verified_at"] = now
    return {
        "schema_version": MASTER_SCHEMA_VERSION,
        "status": "OFFICIAL_LIVE",
        "source_authoritative_exchange_master": True,
        "source": "Euronext official stocks endpoint",
        "source_url": EURONEXT_STOCKS_ENDPOINT,
        "list_url": EURONEXT_OSLO_LIST_URL,
        "mics": list(NORWAY_EQUITY_MICS),
        "fetched_at": now,
        "verified_at": now,
        "count": len(rows),
        "by_exchange": by_exchange,
        "instruments": rows,
        "error": "",
    }


def _load_durable() -> dict[str, Any]:
    value = read_json(MASTER_KEY, MASTER_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _save_durable(value: Mapping[str, Any]) -> None:
    write_json(MASTER_KEY, MASTER_PATH, dict(value))


def _fallback_master(fallback_tickers: Iterable[str], error: str = "") -> dict[str, Any]:
    now = _now_iso()
    instruments = []
    for ticker in dict.fromkeys(str(x or "").strip().upper() for x in fallback_tickers if str(x or "").strip()):
        symbol = ticker[:-3] if ticker.endswith(".OL") else ticker
        instruments.append({
            "ticker": ticker if ticker.endswith(".OL") else _analysis_ticker(ticker),
            "analysis_ticker": ticker if ticker.endswith(".OL") else _analysis_ticker(ticker),
            "exchange_symbol": symbol,
            "symbol": symbol,
            "isin": "",
            "name": symbol,
            "company_name": symbol,
            "market": "Norge",
            "country": "Norge",
            "currency": "NOK",
            "exchange_name": "Ukjent Oslo-markedsplass",
            "market_segment": "Ukjent Oslo-markedsplass",
            "exchange_mic": "",
            "listing_status": "FALLBACK_UNVERIFIED",
            "universe_source": "PACKAGED_FALLBACK",
            "source": "Packaged Norway fallback",
            "source_url": "",
            "last_verified_at": "",
        })
    return {
        "schema_version": MASTER_SCHEMA_VERSION,
        "status": "FALLBACK_UNVERIFIED",
        "source_authoritative_exchange_master": False,
        "source": "Packaged Norway fallback",
        "source_url": "",
        "list_url": EURONEXT_OSLO_LIST_URL,
        "mics": list(NORWAY_EQUITY_MICS),
        "fetched_at": now,
        "verified_at": "",
        "count": len(instruments),
        "by_exchange": {"Ukjent Oslo-markedsplass": len(instruments)},
        "instruments": instruments,
        "error": str(error or "Official Euronext master unavailable"),
    }


def get_norway_exchange_master_cached(fallback_tuple: tuple[str, ...], force_refresh: bool = False) -> dict[str, Any]:
    durable = _load_durable()
    age = _age_seconds(durable.get("verified_at") or durable.get("fetched_at"))
    if not force_refresh and durable.get("source_authoritative_exchange_master") and age is not None and age < REFRESH_SECONDS and durable.get("instruments"):
        value = dict(durable)
        value["status"] = "OFFICIAL_LAST_KNOWN_GOOD"
        value["age_seconds"] = round(age, 1)
        return value
    try:
        fresh = fetch_official_norway_master()
        previous = {str(x.get("isin") or x.get("exchange_symbol") or ""): x for x in durable.get("instruments") or [] if isinstance(x, Mapping)}
        for row in fresh["instruments"]:
            old = previous.get(str(row.get("isin") or row.get("exchange_symbol") or ""), {})
            row["first_seen_at"] = str(old.get("first_seen_at") or fresh["verified_at"])
        _save_durable(fresh)
        return fresh
    except Exception as exc:
        if durable.get("source_authoritative_exchange_master") and durable.get("instruments"):
            value = dict(durable)
            value["status"] = "OFFICIAL_LAST_KNOWN_GOOD_STALE"
            value["refresh_error"] = f"{type(exc).__name__}: {exc}"
            value["age_seconds"] = _age_seconds(value.get("verified_at") or value.get("fetched_at"))
            return value
        return _fallback_master(fallback_tuple, f"{type(exc).__name__}: {exc}")


def get_norway_exchange_master(fallback_tickers: Iterable[str] = (), *, force_refresh: bool = False) -> dict[str, Any]:
    return get_norway_exchange_master_cached(tuple(fallback_tickers), bool(force_refresh))


def get_norway_instruments(fallback_tickers: Iterable[str] = (), *, force_refresh: bool = False) -> list[dict[str, Any]]:
    master = get_norway_exchange_master(fallback_tickers, force_refresh=force_refresh)
    return [dict(row) for row in master.get("instruments") or [] if isinstance(row, Mapping)]


def get_norway_tickers(fallback_tickers: Iterable[str] = (), *, force_refresh: bool = False) -> list[str]:
    return list(dict.fromkeys(str(row.get("ticker") or "").upper() for row in get_norway_instruments(fallback_tickers, force_refresh=force_refresh) if str(row.get("ticker") or "").strip()))


def lookup_norway_instrument(ticker: str, fallback_tickers: Iterable[str] = ()) -> dict[str, Any]:
    wanted = str(ticker or "").strip().upper()
    for row in get_norway_instruments(fallback_tickers):
        if str(row.get("ticker") or "").upper() == wanted:
            return dict(row)
    return {}
