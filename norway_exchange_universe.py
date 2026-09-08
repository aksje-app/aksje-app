"""Authoritative Norway equity master from Euronext Oslo markets.

RC16.31bt hardens the live Norway-universe source for Render. Euronext's
current public product directory is the primary source. The legacy JSON data
endpoint remains as a compatibility fallback. A durable last-known-good
snapshot is retained so a temporary source/network failure cannot silently
shrink the production universe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re
from typing import Any, Iterable, Mapping
from urllib.parse import quote

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

EURONEXT_STOCKS_ENDPOINT = "https://live.euronext.com/en/pd/data/stocks"
EURONEXT_OSLO_LIST_URL = "https://live.euronext.com/en/markets/oslo/equities/list"
EURONEXT_PRODUCT_DIRECTORY_URL = (
    "https://live.euronext.com/en/pd_es/stocks/"
    "XOSL%2CMERK%2CXOAS/dp_stocks/df_stocks2/dt_stocks_osl"
)
NORWAY_EQUITY_MICS = ("XOSL", "MERK", "XOAS")
MIC_TO_MARKET = {
    "XOSL": "Oslo Børs",
    "MERK": "Euronext Growth Oslo",
    "XOAS": "Euronext Expand Oslo",
}
MARKET_TO_MIC = {value.casefold(): key for key, value in MIC_TO_MARKET.items()}
MASTER_KEY = "market_universe/norway_euronext_master.json"
MASTER_PATH = runtime_data_path("market_universe", "norway_euronext_master.json")
MASTER_SCHEMA_VERSION = "1.1"
REFRESH_SECONDS = 20 * 60 * 60
MIN_REASONABLE_OFFICIAL_ROWS = 150
MAX_DIRECTORY_PAGES = 80

_TAG_RE = re.compile(r"<[^>]+>")
_ATTR_TEXT_RE = re.compile(r"data-(?:title-hover|order)=['\"]([^'\"]+)['\"]", re.I)
_ISIN_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{10}\b")


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
    if "expand" in text or "axess" in text or "xoas" in text or "xoax" in text:
        return "XOAS"
    return "XOSL"


def _analysis_ticker(symbol: str) -> str:
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        return ""
    if symbol.endswith(".OL"):
        return symbol
    return re.sub(r"\s+", "", symbol) + ".OL"


def _instrument_row(name: str, isin: str, symbol: str, market_name: str) -> dict[str, Any] | None:
    name = _text(name)
    isin = _text(isin).upper()
    symbol = _text(symbol).upper()
    market_name = _text(market_name)
    if not symbol:
        return None
    mic = _mic_from_market(market_name)
    if mic not in NORWAY_EQUITY_MICS:
        return None
    return {
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
    }


def _dedupe_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in rows:
        row = dict(raw)
        key = (str(row.get("isin") or row.get("exchange_symbol") or ""), str(row.get("exchange_mic") or ""))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        output.append(row)
    output.sort(key=lambda row: (NORWAY_EQUITY_MICS.index(row["exchange_mic"]), row["exchange_symbol"]))
    return output


def _parse_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("aaData") or payload.get("data") or []
    parsed: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 4:
            continue
        row = _instrument_row(raw[0], raw[1], raw[2], raw[3])
        if row:
            parsed.append(row)
    return _dedupe_rows(parsed)


def _parse_product_directory_html(html: str) -> list[dict[str, Any]]:
    """Parse Euronext's current server-rendered product-directory table.

    The parser intentionally keys on ISIN + Oslo market text rather than CSS
    classes so routine Euronext markup changes do not break the master.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(str(html or ""), "lxml")
    parsed: list[dict[str, Any]] = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 4:
            continue
        texts = [_text(cell.get_text(" ", strip=True)) for cell in cells]
        joined = " | ".join(texts)
        isin_idx = next((i for i, text in enumerate(texts) if _ISIN_RE.search(text.upper())), None)
        market_idx = next((i for i, text in enumerate(texts) if any(label.casefold() in text.casefold() for label in MIC_TO_MARKET.values())), None)
        if isin_idx is None or market_idx is None:
            continue
        isin_match = _ISIN_RE.search(texts[isin_idx].upper())
        if not isin_match:
            continue
        isin = isin_match.group(0)
        # Euronext table contract is Name | ISIN | Symbol | Market | ... .
        # Prefer that exact relation, but retain a defensive fallback.
        symbol_idx = isin_idx + 1 if isin_idx + 1 < len(texts) else None
        name_idx = isin_idx - 1 if isin_idx > 0 else 0
        symbol = texts[symbol_idx] if symbol_idx is not None else ""
        if not symbol or " " in symbol and len(symbol) > 15:
            # Search nearby short non-numeric text if markup injected a column.
            candidates = [t for t in texts[max(0, isin_idx - 2):min(len(texts), market_idx + 1)] if t and not _ISIN_RE.search(t.upper())]
            symbol = next((t for t in candidates if re.fullmatch(r"[A-Za-z0-9.\- ]{1,12}", t) and "Oslo" not in t), symbol)
        row = _instrument_row(texts[name_idx], isin, symbol, texts[market_idx])
        if row:
            parsed.append(row)
    return _dedupe_rows(parsed)


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


def _headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (compatible; AI-Aksje-Analyzer/19.22; +Norway-equity-master)",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,nb;q=0.8",
        "Referer": EURONEXT_OSLO_LIST_URL,
        "Cache-Control": "no-cache",
    }


def _fetch_product_directory(session: Any, timeout: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    previous_signature: tuple[tuple[str, str], ...] | None = None
    empty_after_data = 0
    for page in range(MAX_DIRECTORY_PAGES):
        try:
            response = session.get(EURONEXT_PRODUCT_DIRECTORY_URL, params={"page": page}, headers=_headers(), timeout=timeout)
            status_code = int(getattr(response, "status_code", 0) or 0)
            response.raise_for_status()
            page_rows = _parse_product_directory_html(response.text)
            signature = tuple((str(r.get("isin") or ""), str(r.get("exchange_mic") or "")) for r in page_rows)
            attempts.append({"strategy": "PRODUCT_DIRECTORY_HTML", "page": page, "http_status": status_code, "rows": len(page_rows), "url": str(getattr(response, "url", EURONEXT_PRODUCT_DIRECTORY_URL))})
            if page_rows and signature == previous_signature:
                break
            previous_signature = signature if page_rows else previous_signature
            if page_rows:
                all_rows.extend(page_rows)
                empty_after_data = 0
            elif all_rows:
                empty_after_data += 1
                if empty_after_data >= 2:
                    break
            elif page >= 2:
                break
        except Exception as exc:
            attempts.append({"strategy": "PRODUCT_DIRECTORY_HTML", "page": page, "error": f"{type(exc).__name__}: {exc}"})
            if page == 0:
                raise RuntimeError(attempts[-1]["error"]) from exc
            break
    return _dedupe_rows(all_rows), attempts


def _fetch_legacy_json(session: Any, timeout: float) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    params, data = _request_payload()
    attempts: list[dict[str, Any]] = []
    response = session.post(EURONEXT_STOCKS_ENDPOINT, params=params, data=data, headers=_headers(), timeout=timeout)
    status_code = int(getattr(response, "status_code", 0) or 0)
    response.raise_for_status()
    payload = response.json()
    rows = _parse_rows(payload)
    attempts.append({"strategy": "LEGACY_JSON_POST", "http_status": status_code, "rows": len(rows), "url": str(getattr(response, "url", EURONEXT_STOCKS_ENDPOINT))})
    return rows, payload, attempts


def fetch_official_norway_master(timeout: float = 12.0) -> dict[str, Any]:
    import requests

    session = requests.Session()
    attempts: list[dict[str, Any]] = []
    # Prime cookies / anti-bot edge state using the public Oslo list page.
    try:
        primed = session.get(EURONEXT_OSLO_LIST_URL, headers=_headers(), timeout=min(timeout, 8.0))
        attempts.append({"strategy": "PRIME_OSLO_LIST", "http_status": int(getattr(primed, "status_code", 0) or 0), "url": str(getattr(primed, "url", EURONEXT_OSLO_LIST_URL))})
    except Exception as exc:
        attempts.append({"strategy": "PRIME_OSLO_LIST", "error": f"{type(exc).__name__}: {exc}"})

    rows: list[dict[str, Any]] = []
    source = ""
    expected = 0
    errors: list[str] = []

    try:
        rows, html_attempts = _fetch_product_directory(session, timeout)
        attempts.extend(html_attempts)
        if len(rows) >= MIN_REASONABLE_OFFICIAL_ROWS:
            source = "Euronext product directory"
    except Exception as exc:
        errors.append(f"PRODUCT_DIRECTORY_HTML: {type(exc).__name__}: {exc}")

    if len(rows) < MIN_REASONABLE_OFFICIAL_ROWS:
        if rows:
            errors.append(f"PRODUCT_DIRECTORY_HTML: only {len(rows)} rows")
        try:
            legacy_rows, payload, legacy_attempts = _fetch_legacy_json(session, timeout)
            attempts.extend(legacy_attempts)
            legacy_expected = int(payload.get("recordsFiltered") or payload.get("iTotalDisplayRecords") or len(legacy_rows) or 0)
            if len(legacy_rows) > len(rows):
                rows = legacy_rows
                expected = legacy_expected
            if len(legacy_rows) >= MIN_REASONABLE_OFFICIAL_ROWS:
                source = "Euronext legacy stocks endpoint"
        except Exception as exc:
            errors.append(f"LEGACY_JSON_POST: {type(exc).__name__}: {exc}")

    rows = _dedupe_rows(rows)
    if len(rows) < MIN_REASONABLE_OFFICIAL_ROWS:
        raise RuntimeError(
            f"Euronext official Norway master unavailable: parsed {len(rows)} rows; "
            + " | ".join(errors[-4:])
        )
    if expected and len(rows) < min(expected, 2000):
        raise RuntimeError(f"Euronext universe incomplete: parsed {len(rows)} of {expected}")

    now = _now_iso()
    by_exchange: dict[str, int] = {}
    for row in rows:
        by_exchange[row["exchange_name"]] = by_exchange.get(row["exchange_name"], 0) + 1
        row["last_verified_at"] = now
    result = {
        "schema_version": MASTER_SCHEMA_VERSION,
        "status": "OFFICIAL_LIVE",
        "source_authoritative_exchange_master": True,
        "source": source or "Euronext official Norway equity master",
        "source_url": EURONEXT_PRODUCT_DIRECTORY_URL if source.startswith("Euronext product") else EURONEXT_STOCKS_ENDPOINT,
        "list_url": EURONEXT_OSLO_LIST_URL,
        "mics": list(NORWAY_EQUITY_MICS),
        "fetched_at": now,
        "verified_at": now,
        "count": len(rows),
        "by_exchange": by_exchange,
        "instruments": rows,
        "fetch_attempts": attempts[-20:],
        "error": "",
    }
    print(f"NORWAY_UNIVERSE status=OFFICIAL_LIVE source={result['source']} count={len(rows)} by_exchange={by_exchange}")
    return result


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
    result = {
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
    print(f"NORWAY_UNIVERSE status=FALLBACK_UNVERIFIED count={len(instruments)} error={result['error']}")
    return result


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
        error = f"{type(exc).__name__}: {exc}"
        if durable.get("source_authoritative_exchange_master") and durable.get("instruments"):
            value = dict(durable)
            value["status"] = "OFFICIAL_LAST_KNOWN_GOOD_STALE"
            value["refresh_error"] = error
            value["age_seconds"] = _age_seconds(value.get("verified_at") or value.get("fetched_at"))
            print(f"NORWAY_UNIVERSE status=OFFICIAL_LAST_KNOWN_GOOD_STALE count={len(value.get('instruments') or [])} refresh_error={error}")
            return value
        return _fallback_master(fallback_tuple, error)


def get_norway_exchange_master(fallback_tickers: Iterable[str] = (), *, force_refresh: bool = False) -> dict[str, Any]:
    return get_norway_exchange_master_cached(tuple(fallback_tickers), bool(force_refresh))


def get_norway_instruments(fallback_tickers: Iterable[str] = (), *, force_refresh: bool = False) -> list[dict[str, Any]]:
    master = get_norway_exchange_master(fallback_tickers, force_refresh=force_refresh)
    return [dict(row) for row in master.get("instruments") or [] if isinstance(row, Mapping)]


def get_norway_tickers(fallback_tickers: Iterable[str] = (), *, force_refresh: bool = False) -> list[str]:
    return list(dict.fromkeys(str(row.get("ticker") or "").upper() for row in get_norway_instruments(fallback_tickers, force_refresh=force_refresh) if str(row.get("ticker") or "").strip()))
