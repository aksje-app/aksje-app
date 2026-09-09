"""Authoritative Norway equity master from Euronext Oslo markets.

RC16.31bw closes the live Euronext parser gap observed on Render. The primary
CSV source is fetched per Oslo MIC (XOSL, MERK, XOAS), so exchange identity does
not depend on Euronext's display text. The current DataTables JSON parser also
accepts the real HTML-cell payload contract used by Euronext. RC16.31bu
observability is preserved end to end. A durable last-known-good snapshot is
retained so a temporary source/network failure cannot silently shrink the
production universe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from io import StringIO
import csv
import re
from typing import Any, Iterable, Mapping
from urllib.parse import quote
import json
import time

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

EURONEXT_STOCKS_ENDPOINT = "https://live.euronext.com/en/pd/data/stocks"
EURONEXT_STOCKS_ENDPOINT_CURRENT = "https://live.euronext.com/en/pd_es/data/stocks"
EURONEXT_STOCKS_DOWNLOAD_ENDPOINT = "https://live.euronext.com/en/pd_es/data/stocks/download"
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
MASTER_SCHEMA_VERSION = "1.3"
DIAGNOSTIC_KEY = "market_universe/norway_euronext_fetch_diagnostics.json"
DIAGNOSTIC_PATH = runtime_data_path("market_universe", "norway_euronext_fetch_diagnostics.json")
REFRESH_SECONDS = 20 * 60 * 60
MIN_REASONABLE_OFFICIAL_ROWS = 150
MAX_DIRECTORY_PAGES = 80

_TAG_RE = re.compile(r"<[^>]+>")
_ATTR_TEXT_RE = re.compile(r"data-(?:title-hover|order)=['\"]([^'\"]+)['\"]", re.I)
_ISIN_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{10}\b")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NorwayUniverseFetchError(RuntimeError):
    def __init__(self, message: str, *, attempts: Iterable[Mapping[str, Any]] = ()) -> None:
        super().__init__(message)
        self.attempts = [dict(row) for row in attempts if isinstance(row, Mapping)]


def _safe_response_meta(response: Any) -> dict[str, Any]:
    headers = getattr(response, "headers", {}) or {}
    text = str(getattr(response, "text", "") or "")
    content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")[:160]
    return {
        "http_status": int(getattr(response, "status_code", 0) or 0),
        "final_url": str(getattr(response, "url", "") or "")[:500],
        "content_type": content_type,
        "response_chars": len(text),
        "content_length": str(headers.get("content-length") or headers.get("Content-Length") or "")[:40],
    }


def _emit_attempt(row: Mapping[str, Any]) -> None:
    try:
        print("NORWAY_UNIVERSE_ATTEMPT " + json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str))
    except Exception:
        print(f"NORWAY_UNIVERSE_ATTEMPT strategy={row.get('strategy')} status={row.get('http_status')} rows={row.get('rows')} error={row.get('error')}")


def _add_attempt(attempts: list[dict[str, Any]], row: Mapping[str, Any]) -> dict[str, Any]:
    value = {**dict(row), "observed_at": _now_iso()}
    attempts.append(value)
    _emit_attempt(value)
    return value


def _persist_fetch_diagnostics(*, status: str, attempts: Iterable[Mapping[str, Any]], errors: Iterable[str] = (), parsed_count: int = 0, source: str = "", expected_count: int = 0) -> dict[str, Any]:
    value = {
        "schema_version": "1.0",
        "status": str(status),
        "updated_at": _now_iso(),
        "source": str(source or ""),
        "parsed_count": int(parsed_count or 0),
        "expected_count": int(expected_count or 0),
        "minimum_reasonable_rows": MIN_REASONABLE_OFFICIAL_ROWS,
        "attempts": [dict(row) for row in list(attempts)[-100:] if isinstance(row, Mapping)],
        "errors": [str(x)[:1000] for x in list(errors)[-20:]],
    }
    try:
        write_json(DIAGNOSTIC_KEY, DIAGNOSTIC_PATH, value)
    except Exception as exc:
        value["persistence_error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    return value


def load_norway_universe_fetch_diagnostics() -> dict[str, Any]:
    value = read_json(DIAGNOSTIC_KEY, DIAGNOSTIC_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


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
    if "oslo" in text or text == "xosl":
        return "XOSL"
    return ""


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




def _normalise_header(value: Any) -> str:
    text = _text(value).casefold()
    text = text.replace("ø", "o").replace("æ", "ae").replace("å", "a")
    return re.sub(r"[^a-z0-9]+", "", text)


def _decode_response_bytes(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)) and content:
        raw = bytes(content)
        for encoding in ("utf-8-sig", "utf-16", "latin-1"):
            try:
                return raw.decode(encoding)
            except Exception:
                pass
    return str(getattr(response, "text", "") or "")


def _parse_euronext_csv(text: str, *, mic_hint: str = "") -> list[dict[str, Any]]:
    """Parse Euronext CSV exports, optionally trusting the requested MIC.

    Euronext's export is authoritative for the request filter. Fetching one MIC at
    a time avoids depending on localized/abbreviated values in the ``Market``
    display column while still keeping the all-stocks parser strict.
    """
    raw = str(text or "").replace("\x00", "")
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return []

    hint = str(mic_hint or "").strip().upper()
    if hint and hint not in NORWAY_EQUITY_MICS:
        hint = ""

    header_idx = None
    delimiter = None
    for idx, line in enumerate(lines[:40]):
        for candidate in (";", "\t", ",", "|"):
            parts = [part.strip().strip('"') for part in line.split(candidate)]
            norms = {_normalise_header(part) for part in parts}
            has_isin = any(x == "isin" or x.endswith("isin") for x in norms)
            has_symbol = any(x in {"symbol", "ticker", "symbole"} or "ticker" in x for x in norms)
            has_market = any(x in {"market", "marked", "marche"} or "market" in x or "marked" in x for x in norms)
            if has_isin and has_symbol and (has_market or hint) and len(parts) >= 3:
                header_idx = idx
                delimiter = candidate
                break
        if delimiter:
            break
    if header_idx is None or delimiter is None:
        return []

    reader = csv.reader(StringIO("\n".join(lines[header_idx:])), delimiter=delimiter)
    try:
        headers = next(reader)
    except StopIteration:
        return []
    norms = [_normalise_header(h) for h in headers]

    def col(*names: str) -> int | None:
        wanted = {_normalise_header(n) for n in names}
        for i, value in enumerate(norms):
            if value in wanted:
                return i
        for i, value in enumerate(norms):
            if any(w and (value.endswith(w) or w in value) for w in wanted):
                return i
        return None

    name_i = col("Name", "Navn", "Nom", "Instrument name", "Issuer name")
    isin_i = col("ISIN")
    symbol_i = col("Symbol", "Ticker", "Symbole")
    market_i = col("Market", "Marked", "Marche", "Market name", "Trading location")
    mic_i = col("MIC", "Market MIC", "Mic code")
    if isin_i is None or symbol_i is None or (market_i is None and mic_i is None and not hint):
        return []

    parsed: list[dict[str, Any]] = []
    for values in reader:
        if not values or max(isin_i, symbol_i) >= len(values):
            continue
        isin = _text(values[isin_i]).upper()
        symbol = _text(values[symbol_i]).upper()
        if not symbol:
            continue
        mic = hint
        market = ""
        if mic_i is not None and mic_i < len(values):
            explicit_mic = _text(values[mic_i]).upper()
            if explicit_mic in NORWAY_EQUITY_MICS:
                mic = explicit_mic
        if market_i is not None and market_i < len(values):
            market = _text(values[market_i])
            market_mic = _mic_from_market(market)
            # A known explicit market must agree with the requested MIC. This
            # protects against an upstream endpoint silently ignoring its filter.
            if hint and market_mic and market_mic != hint:
                continue
            if not mic and market_mic:
                mic = market_mic
        if mic not in NORWAY_EQUITY_MICS:
            continue
        name = _text(values[name_i]) if name_i is not None and name_i < len(values) else symbol
        row = _instrument_row(name, isin, symbol, MIC_TO_MARKET[mic])
        if row:
            parsed.append(row)
    return _dedupe_rows(parsed)

def _fetch_official_csv(session: Any, timeout: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch Euronext CSV per MIC, then fall back to the all-stocks export."""
    attempts: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []

    # Request each Oslo market separately. The server-side filter is the source
    # of truth for market identity, so localized Market labels cannot zero the
    # parser or collapse the segment split.
    for mic in NORWAY_EQUITY_MICS:
        started = time.monotonic()
        response = None
        try:
            params = {
                "mics": mic,
                "initialLetter": "",
                "fe_type": "csv",
                "fe_decimal_separator": ".",
                "fe_date_format": "d/m/Y",
            }
            headers = {**_headers(), "Accept": "text/csv,text/plain,application/octet-stream,*/*;q=0.5"}
            response = session.get(EURONEXT_STOCKS_DOWNLOAD_ENDPOINT, params=params, headers=headers, timeout=timeout)
            meta = _safe_response_meta(response)
            response.raise_for_status()
            body = _decode_response_bytes(response)
            rows = _parse_euronext_csv(body, mic_hint=mic)
            _add_attempt(attempts, {
                "strategy": "OFFICIAL_CSV_EXPORT", "variant": f"MIC_{mic}", "method": "GET",
                "requested_url": EURONEXT_STOCKS_DOWNLOAD_ENDPOINT, **meta,
                "rows": len(rows), "parser": "euronext_csv_per_mic",
                "body_prefix": body[:160].replace("\n", " ").replace("\r", " "),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            })
            all_rows.extend(rows)
        except Exception as exc:
            row = {
                "strategy": "OFFICIAL_CSV_EXPORT", "variant": f"MIC_{mic}", "method": "GET",
                "requested_url": EURONEXT_STOCKS_DOWNLOAD_ENDPOINT,
                "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            }
            if response is not None:
                row.update(_safe_response_meta(response))
            _add_attempt(attempts, row)

    all_rows = _dedupe_rows(all_rows)
    if len(all_rows) >= MIN_REASONABLE_OFFICIAL_ROWS:
        return all_rows, attempts

    # Defensive fallback: all stocks export, where Market/MIC must identify Oslo.
    started = time.monotonic()
    response = None
    try:
        params = {
            "mics": "dm_all_stock", "initialLetter": "", "fe_type": "csv",
            "fe_decimal_separator": ".", "fe_date_format": "d/m/Y",
        }
        headers = {**_headers(), "Accept": "text/csv,text/plain,application/octet-stream,*/*;q=0.5"}
        response = session.get(EURONEXT_STOCKS_DOWNLOAD_ENDPOINT, params=params, headers=headers, timeout=timeout)
        meta = _safe_response_meta(response)
        response.raise_for_status()
        body = _decode_response_bytes(response)
        rows = _parse_euronext_csv(body)
        _add_attempt(attempts, {
            "strategy": "OFFICIAL_CSV_EXPORT", "variant": "ALL_STOCKS", "method": "GET",
            "requested_url": EURONEXT_STOCKS_DOWNLOAD_ENDPOINT, **meta,
            "rows": len(rows), "parser": "euronext_csv_header_map",
            "body_prefix": body[:160].replace("\n", " ").replace("\r", " "),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        })
        if len(rows) > len(all_rows):
            all_rows = rows
    except Exception as exc:
        row = {
            "strategy": "OFFICIAL_CSV_EXPORT", "variant": "ALL_STOCKS", "method": "GET",
            "requested_url": EURONEXT_STOCKS_DOWNLOAD_ENDPOINT,
            "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }
        if response is not None:
            row.update(_safe_response_meta(response))
        _add_attempt(attempts, row)
    return _dedupe_rows(all_rows), attempts

def _mic_from_raw_cells(raw_cells: Iterable[Any]) -> str:
    joined = " ".join(str(x or "") for x in raw_cells)
    upper = joined.upper()
    # Explicit MIC attributes / URL path segments are stronger than display text.
    for mic in NORWAY_EQUITY_MICS:
        if re.search(rf"(?:^|[^A-Z0-9]){re.escape(mic)}(?:[^A-Z0-9]|$)", upper):
            return mic
    return _mic_from_market(_text(joined))


def _parse_mapping_row(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    lower = {_normalise_header(k): v for k, v in raw.items()}
    def pick(*keys: str) -> Any:
        for key in keys:
            value = lower.get(_normalise_header(key))
            if value not in (None, ""):
                return value
        return ""
    name = pick("name", "instrumentname", "issuername")
    isin = pick("isin")
    symbol = pick("symbol", "ticker")
    market = pick("market", "marketname", "tradinglocation", "mic", "marketmic")
    mic = _mic_from_raw_cells(raw.values())
    if mic:
        market = MIC_TO_MARKET[mic]
    return _instrument_row(name, isin, symbol, market)


def _parse_sequence_row(raw: list[Any] | tuple[Any, ...]) -> dict[str, Any] | None:
    if len(raw) < 3:
        return None
    texts = [_text(value) for value in raw]
    mic = _mic_from_raw_cells(raw)

    isin_idx = None
    isin = ""
    for idx, text in enumerate(texts):
        match = _ISIN_RE.search(text.upper())
        if match:
            isin_idx, isin = idx, match.group(0)
            break

    # Euronext DataTables normally uses Name | ISIN | Symbol | Market, but the
    # cells may themselves be HTML. Keep that fast path, then locate by content.
    name = texts[0] if texts else ""
    symbol = texts[2] if len(texts) > 2 else ""
    market = texts[3] if len(texts) > 3 else ""
    if isin_idx is not None:
        if isin_idx > 0:
            name = texts[isin_idx - 1] or name
        if isin_idx + 1 < len(texts):
            symbol = texts[isin_idx + 1] or symbol

    if not mic:
        mic = _mic_from_market(market)
    if mic:
        market = MIC_TO_MARKET[mic]

    # If the symbol cell contains extra markup text, prefer a data-order/title
    # attribute or a short exchange-like token near the ISIN.
    raw_symbol = str(raw[isin_idx + 1] if isin_idx is not None and isin_idx + 1 < len(raw) else (raw[2] if len(raw) > 2 else ""))
    attr = _ATTR_TEXT_RE.search(raw_symbol)
    if attr:
        symbol = _text(attr.group(1)) or symbol
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-]{1,20}", symbol):
        nearby = texts[max(0, (isin_idx or 0) - 1):min(len(texts), (isin_idx or 1) + 4)]
        symbol = next((x.strip().upper() for x in nearby if re.fullmatch(r"[A-Za-z0-9.\-]{1,20}", x.strip()) and x.upper() not in NORWAY_EQUITY_MICS), symbol)

    return _instrument_row(name, isin, symbol, market)


def _parse_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("aaData") or payload.get("data") or []
    parsed: list[dict[str, Any]] = []
    for raw in raw_rows:
        row = None
        if isinstance(raw, Mapping):
            row = _parse_mapping_row(raw)
        elif isinstance(raw, (list, tuple)):
            row = _parse_sequence_row(raw)
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


def _request_payload_current() -> tuple[dict[str, str], dict[str, str]]:
    params, data = _request_payload()
    params = dict(params)
    params["display_filters"] = "df_stocks2"
    params["display_table"] = "dt_stocks_osl"
    return params, data


def _fetch_current_json(session: Any, timeout: float) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    params, data = _request_payload_current()
    attempts: list[dict[str, Any]] = []
    started = time.monotonic()
    response = None
    try:
        headers = {**_headers(), "Accept": "application/json,text/javascript,*/*;q=0.8",
                   "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        response = session.post(EURONEXT_STOCKS_ENDPOINT_CURRENT, params=params, data=data, headers=headers, timeout=timeout)
        meta = _safe_response_meta(response)
        response.raise_for_status()
        payload = response.json()
        rows = _parse_rows(payload)
        _add_attempt(attempts, {
            "strategy": "CURRENT_JSON_POST", "method": "POST",
            "requested_url": EURONEXT_STOCKS_ENDPOINT_CURRENT, **meta,
            "rows": len(rows),
            "records_filtered": int(payload.get("recordsFiltered") or payload.get("iTotalDisplayRecords") or 0),
            "raw_row_count": len(payload.get("aaData") or payload.get("data") or []),
            "raw_row_type": type((payload.get("aaData") or payload.get("data") or [None])[0]).__name__ if (payload.get("aaData") or payload.get("data")) else "",
            "parser": "json_html_cells_flexible",
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        })
        return rows, payload, attempts
    except Exception as exc:
        row = {
            "strategy": "CURRENT_JSON_POST", "method": "POST",
            "requested_url": EURONEXT_STOCKS_ENDPOINT_CURRENT,
            "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }
        if response is not None:
            row.update(_safe_response_meta(response))
        _add_attempt(attempts, row)
        raise NorwayUniverseFetchError(row["error"], attempts=attempts) from exc


def _headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (compatible; AI-Aksje-Analyzer/19.22; +Norway-equity-master)",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,nb;q=0.8",
        "Referer": EURONEXT_OSLO_LIST_URL,
        "Cache-Control": "no-cache",
        "X-Requested-With": "XMLHttpRequest",
    }


def _fetch_product_directory(session: Any, timeout: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    previous_signature: tuple[tuple[str, str], ...] | None = None
    empty_after_data = 0
    for page in range(MAX_DIRECTORY_PAGES):
        started = time.monotonic()
        try:
            requested_url = EURONEXT_PRODUCT_DIRECTORY_URL
            response = session.get(requested_url, params={"page": page}, headers=_headers(), timeout=timeout)
            meta = _safe_response_meta(response)
            response.raise_for_status()
            page_rows = _parse_product_directory_html(response.text)
            signature = tuple((str(r.get("isin") or ""), str(r.get("exchange_mic") or "")) for r in page_rows)
            _add_attempt(attempts, {
                "strategy": "PRODUCT_DIRECTORY_HTML", "method": "GET", "page": page,
                "requested_url": requested_url, **meta, "rows": len(page_rows),
                "parser": "beautifulsoup_table_isin_market",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            })
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
            row = {
                "strategy": "PRODUCT_DIRECTORY_HTML", "method": "GET", "page": page,
                "requested_url": EURONEXT_PRODUCT_DIRECTORY_URL,
                "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            }
            try:
                if 'response' in locals():
                    row.update(_safe_response_meta(response))
            except Exception:
                pass
            _add_attempt(attempts, row)
            if page == 0:
                raise NorwayUniverseFetchError(row["error"], attempts=attempts) from exc
            break
    return _dedupe_rows(all_rows), attempts

def _fetch_legacy_json(session: Any, timeout: float) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    params, data = _request_payload()
    attempts: list[dict[str, Any]] = []
    started = time.monotonic()
    response = None
    try:
        response = session.post(EURONEXT_STOCKS_ENDPOINT, params=params, data=data, headers=_headers(), timeout=timeout)
        meta = _safe_response_meta(response)
        response.raise_for_status()
        payload = response.json()
        rows = _parse_rows(payload)
        _add_attempt(attempts, {
            "strategy": "LEGACY_JSON_POST", "method": "POST", "requested_url": EURONEXT_STOCKS_ENDPOINT,
            **meta, "rows": len(rows), "records_filtered": int(payload.get("recordsFiltered") or payload.get("iTotalDisplayRecords") or 0),
            "parser": "json_aaData", "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        })
        return rows, payload, attempts
    except Exception as exc:
        row = {
            "strategy": "LEGACY_JSON_POST", "method": "POST", "requested_url": EURONEXT_STOCKS_ENDPOINT,
            "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }
        if response is not None:
            row.update(_safe_response_meta(response))
        _add_attempt(attempts, row)
        raise NorwayUniverseFetchError(row["error"], attempts=attempts) from exc

def fetch_official_norway_master(timeout: float = 12.0) -> dict[str, Any]:
    import requests

    session = requests.Session()
    attempts: list[dict[str, Any]] = []
    # Prime cookies / anti-bot edge state using the public Oslo list page.
    try:
        prime_started = time.monotonic()
        primed = session.get(EURONEXT_OSLO_LIST_URL, headers=_headers(), timeout=min(timeout, 8.0))
        _add_attempt(attempts, {"strategy": "PRIME_OSLO_LIST", "method": "GET", "requested_url": EURONEXT_OSLO_LIST_URL, **_safe_response_meta(primed), "elapsed_ms": round((time.monotonic() - prime_started) * 1000, 1)})
    except Exception as exc:
        _add_attempt(attempts, {"strategy": "PRIME_OSLO_LIST", "method": "GET", "requested_url": EURONEXT_OSLO_LIST_URL, "error": f"{type(exc).__name__}: {str(exc)[:1000]}"})

    rows: list[dict[str, Any]] = []
    source = ""
    expected = 0
    errors: list[str] = []

    # Primary: Euronext's own machine-readable CSV export used by the current
    # product directory download control. This avoids parsing the JS shell.
    try:
        csv_rows, csv_attempts = _fetch_official_csv(session, timeout)
        attempts.extend(csv_attempts)
        if len(csv_rows) > len(rows):
            rows = csv_rows
        if len(csv_rows) >= MIN_REASONABLE_OFFICIAL_ROWS:
            source = "Euronext official CSV export"
    except Exception as exc:
        errors.append(f"OFFICIAL_CSV_EXPORT: {type(exc).__name__}: {exc}")

    # Defensive fallback: server-rendered directory, should Euronext restore it.
    if len(rows) < MIN_REASONABLE_OFFICIAL_ROWS:
        if rows:
            errors.append(f"OFFICIAL_CSV_EXPORT: only {len(rows)} rows")
        try:
            html_rows, html_attempts = _fetch_product_directory(session, timeout)
            attempts.extend(html_attempts)
            if len(html_rows) > len(rows):
                rows = html_rows
            if len(html_rows) >= MIN_REASONABLE_OFFICIAL_ROWS:
                source = "Euronext product directory"
        except Exception as exc:
            if isinstance(exc, NorwayUniverseFetchError):
                attempts.extend(row for row in exc.attempts if row not in attempts)
            errors.append(f"PRODUCT_DIRECTORY_HTML: {type(exc).__name__}: {exc}")

    # Secondary machine-readable source: current pd_es DataTables endpoint.
    if len(rows) < MIN_REASONABLE_OFFICIAL_ROWS:
        try:
            current_rows, payload, current_attempts = _fetch_current_json(session, timeout)
            attempts.extend(current_attempts)
            current_expected = int(payload.get("recordsFiltered") or payload.get("iTotalDisplayRecords") or len(current_rows) or 0)
            if len(current_rows) > len(rows):
                rows = current_rows
                expected = current_expected
            if len(current_rows) >= MIN_REASONABLE_OFFICIAL_ROWS:
                source = "Euronext current stocks endpoint"
        except Exception as exc:
            if isinstance(exc, NorwayUniverseFetchError):
                attempts.extend(row for row in exc.attempts if row not in attempts)
            errors.append(f"CURRENT_JSON_POST: {type(exc).__name__}: {exc}")

    # Compatibility fallback: legacy DataTables JSON endpoint.
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
            if isinstance(exc, NorwayUniverseFetchError):
                attempts.extend(row for row in exc.attempts if row not in attempts)
            errors.append(f"LEGACY_JSON_POST: {type(exc).__name__}: {exc}")

    rows = _dedupe_rows(rows)
    if len(rows) < MIN_REASONABLE_OFFICIAL_ROWS:
        _persist_fetch_diagnostics(status="FAILED", attempts=attempts, errors=errors, parsed_count=len(rows), source=source, expected_count=expected)
        raise NorwayUniverseFetchError(
            f"Euronext official Norway master unavailable: parsed {len(rows)} rows; " + " | ".join(errors[-4:]), attempts=attempts
        )
    if expected and len(rows) < min(expected, 2000):
        errors.append(f"INCOMPLETE: parsed {len(rows)} of {expected}")
        _persist_fetch_diagnostics(status="FAILED_INCOMPLETE", attempts=attempts, errors=errors, parsed_count=len(rows), source=source, expected_count=expected)
        raise NorwayUniverseFetchError(f"Euronext universe incomplete: parsed {len(rows)} of {expected}", attempts=attempts)

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
        "source_url": (EURONEXT_STOCKS_DOWNLOAD_ENDPOINT if source == "Euronext official CSV export"
                       else EURONEXT_STOCKS_ENDPOINT_CURRENT if source == "Euronext current stocks endpoint"
                       else EURONEXT_PRODUCT_DIRECTORY_URL if source.startswith("Euronext product")
                       else EURONEXT_STOCKS_ENDPOINT),
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
    _persist_fetch_diagnostics(status="OFFICIAL_LIVE", attempts=attempts, errors=errors, parsed_count=len(rows), source=result["source"], expected_count=expected)
    print(f"NORWAY_UNIVERSE status=OFFICIAL_LIVE source={result['source']} count={len(rows)} by_exchange={by_exchange}")
    return result


def _load_durable() -> dict[str, Any]:
    value = read_json(MASTER_KEY, MASTER_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _save_durable(value: Mapping[str, Any]) -> None:
    write_json(MASTER_KEY, MASTER_PATH, dict(value))


def _fallback_master(fallback_tickers: Iterable[str], error: str = "", fetch_diagnostics: Mapping[str, Any] | None = None) -> dict[str, Any]:
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
        "fetch_diagnostics": dict(fetch_diagnostics or {}),
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
        diagnostics = load_norway_universe_fetch_diagnostics()
        return _fallback_master(fallback_tuple, error, diagnostics)


def get_norway_exchange_master(fallback_tickers: Iterable[str] = (), *, force_refresh: bool = False) -> dict[str, Any]:
    return get_norway_exchange_master_cached(tuple(fallback_tickers), bool(force_refresh))


def get_norway_exchange_master_snapshot() -> dict[str, Any]:
    """Return the durable authoritative master without making any network call.

    Report finalization uses this read-only snapshot so metadata rehydration can
    never delay or destabilize a completed analysis. The scanner/universe layer
    remains solely responsible for refreshing Euronext data.
    """
    durable = _load_durable()
    if durable.get("source_authoritative_exchange_master") and durable.get("instruments"):
        return dict(durable)
    return {}


def get_norway_instruments(fallback_tickers: Iterable[str] = (), *, force_refresh: bool = False) -> list[dict[str, Any]]:
    master = get_norway_exchange_master(fallback_tickers, force_refresh=force_refresh)
    return [dict(row) for row in master.get("instruments") or [] if isinstance(row, Mapping)]


def get_norway_tickers(fallback_tickers: Iterable[str] = (), *, force_refresh: bool = False) -> list[str]:
    return list(dict.fromkeys(str(row.get("ticker") or "").upper() for row in get_norway_instruments(fallback_tickers, force_refresh=force_refresh) if str(row.get("ticker") or "").strip()))
