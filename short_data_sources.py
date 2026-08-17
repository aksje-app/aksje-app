"""Bounded retrieval of reported short-interest data.

Official public registers are preferred.  A missing public register row means
"below the public threshold", never zero.  US exchange-reported fields exposed
through the structured provider are retained as verified secondary evidence;
daily short-sale volume is never used.
"""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from typing import Any, Mapping, Sequence

import requests

NORWAY_SOURCE = "Finanstilsynet Short Sale Register"
NORWAY_API = "https://ssr.finanstilsynet.no/api/v2/instruments"
SWEDEN_SOURCE = "Finansinspektionen Blankningsregister"
SWEDEN_URL = "https://www.fi.se/sv/vara-register/blankningsregistret/Positionsinnehavare"
CACHE_SECONDS = 12 * 60 * 60
_CACHE: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_name(value: Any) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).casefold()
    text = re.sub(r"\b(aktiebolag|ab|asa|publ|plc|inc|corp|corporation|group|holding)\b", " ", text)
    return re.sub(r"[^a-z0-9æøåäö]+", " ", text).strip()


def _matches(candidate: Mapping[str, Any], issuer: Any, isin: Any = "") -> bool:
    wanted_isin = str(candidate.get("isin") or candidate.get("ISIN") or "").upper().strip()
    if wanted_isin and wanted_isin == str(isin or "").upper().strip():
        return True
    issuer_clean = _clean_name(issuer)
    names = {
        _clean_name(candidate.get(key)) for key in ("longName", "shortName", "name", "company")
        if candidate.get(key)
    }
    ticker_root = str(candidate.get("ticker") or "").split(".", 1)[0].replace("-A", "").replace("-B", "").casefold()
    return bool(
        issuer_clean and (
            any(name and (name in issuer_clean or issuer_clean in name) for name in names)
            or (len(ticker_root) >= 3 and re.search(rf"\b{re.escape(ticker_root)}\b", issuer_clean))
        )
    )


def _number(value: Any) -> float | None:
    text = str(value or "").replace("\xa0", "").replace(" ", "").replace("%", "")
    if not text or text.startswith("<"):
        return None
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _walk_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        if any(str(key).casefold() in {"issuer", "issuername", "companyname", "instrumentname", "isin"} for key in value):
            rows.append(dict(value))
        for child in value.values():
            rows.extend(_walk_rows(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            rows.extend(_walk_rows(child))
    return rows


def _field(row: Mapping[str, Any], *tokens: str) -> Any:
    for key, value in row.items():
        normal = re.sub(r"[^a-z0-9]", "", str(key).casefold())
        if any(re.sub(r"[^a-z0-9]", "", token.casefold()) in normal for token in tokens):
            return value
    return None


def fetch_norway(candidate: Mapping[str, Any], session: Any = None) -> dict[str, Any]:
    client = session or requests.Session()
    base = {"source": NORWAY_SOURCE, "as_of": _now()[:10], "published_at": _now(), "status": "OFFICIAL"}
    try:
        response = client.get(NORWAY_API, timeout=20, headers={"User-Agent": "AI-Aksje-Analyzer-Pro/19.22"})
        response.raise_for_status()
        payload = response.json()
        instruments = [dict(row) for row in payload if isinstance(row, Mapping)] if isinstance(payload, list) else []
        matched = [row for row in instruments if _matches(candidate, row.get("issuerName"), row.get("isin"))]
        if matched:
            events = [dict(event) for event in matched[0].get("events") or [] if isinstance(event, Mapping)]
            events.sort(key=lambda event: str(event.get("date") or ""), reverse=True)
            latest = events[0] if events else {}
            pct = _number(latest.get("shortPercent"))
            if pct is not None and pct >= 0.5:
                return {
                    **base, "short_interest_pct_outstanding": pct,
                    "shares_short": _number(latest.get("shares")),
                    "as_of": str(latest.get("date") or base["as_of"]),
                    "coverage_status": "VERIFIED_PUBLIC_POSITION", "results": 1,
                }
        return {**base, "coverage_status": "NO_PUBLIC_POSITION_AT_OR_ABOVE_0_5", "public_threshold_pct": 0.5, "results": 0}
    except Exception as exc:
        return {**base, "status": "SOURCE_ERROR", "coverage_status": "SOURCE_ERROR", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def _html_rows(text: str) -> list[list[str]]:
    rows = []
    for block in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, flags=re.I | re.S):
        cells = [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", cell))).strip()
                 for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", block, flags=re.I | re.S)]
        if cells:
            rows.append(cells)
    return rows


def fetch_sweden(candidate: Mapping[str, Any], session: Any = None) -> dict[str, Any]:
    client = session or requests.Session()
    base = {"source": SWEDEN_SOURCE, "as_of": _now()[:10], "published_at": _now(), "status": "OFFICIAL"}
    try:
        response = client.get(SWEDEN_URL, timeout=20, headers={"User-Agent": "AI-Aksje-Analyzer-Pro/19.22"})
        response.raise_for_status()
        for cells in _html_rows(response.text):
            if len(cells) >= 4 and _matches(candidate, cells[0], cells[1]):
                pct = _number(cells[-1])
                if pct is not None:
                    return {**base, "short_interest_pct_outstanding": pct, "as_of": cells[-2] or base["as_of"], "coverage_status": "VERIFIED_PUBLIC_AGGREGATE", "results": 1}
        return {**base, "coverage_status": "NO_REPORTED_AGGREGATE_AT_OR_ABOVE_0_1", "public_threshold_pct": 0.1, "results": 0}
    except Exception as exc:
        return {**base, "status": "SOURCE_ERROR", "coverage_status": "SOURCE_ERROR", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def _date_from_epoch(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def fetch_usa(candidate: Mapping[str, Any]) -> dict[str, Any]:
    ticker = str(candidate.get("ticker") or "").upper().strip()
    base = {"source": "US exchange-reported short interest via yfinance", "published_at": _now(), "status": "VERIFIED_SECONDARY"}
    try:
        import yfinance as yf
        info = dict(yf.Ticker(ticker).info or {})
        as_of = _date_from_epoch(info.get("dateShortInterest") or info.get("sharesShortPreviousMonthDate"))
        values = {
            "short_interest_pct_float": _number(info.get("shortPercentOfFloat")),
            "short_interest_pct_outstanding": _number(info.get("sharesPercentSharesOut")),
            "shares_short": _number(info.get("sharesShort")),
            "days_to_cover": _number(info.get("shortRatio")),
        }
        # yfinance fractions are expressed as 0..1; the report contract uses percent.
        for key in ("short_interest_pct_float", "short_interest_pct_outstanding"):
            if values[key] is not None and values[key] <= 1.0:
                values[key] = round(values[key] * 100.0, 4)
        if as_of and any(value is not None for value in values.values()):
            return {**base, **values, "as_of": as_of, "coverage_status": "VERIFIED_EXCHANGE_REPORTED"}
        return {**base, "status": "NO_DATA", "as_of": as_of or None, "coverage_status": "NO_REPORTED_DATA"}
    except Exception as exc:
        return {**base, "status": "SOURCE_ERROR", "as_of": None, "coverage_status": "SOURCE_ERROR", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def fetch_short_data(candidate: Mapping[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
    ticker = str(candidate.get("ticker") or "").upper().strip()
    market = str(candidate.get("market") or "").strip()
    cache_key = f"{market}|{ticker}"
    with _LOCK:
        cached = _CACHE.get(cache_key)
        if cached and not force_refresh and time.time() - float(cached.get("cached_at") or 0) < CACHE_SECONDS:
            return dict(cached["value"])
    if market == "Norge":
        value = fetch_norway(candidate)
    elif market == "Sverige":
        value = fetch_sweden(candidate)
    elif market == "USA":
        value = fetch_usa(candidate)
    else:
        value = {"source": None, "as_of": None, "status": "NOT_SUPPORTED", "coverage_status": "NOT_SUPPORTED", "market": market}
    with _LOCK:
        _CACHE[cache_key] = {"cached_at": time.time(), "value": dict(value)}
    return value


def enrich_rows(rows: Sequence[Mapping[str, Any]], *, force_refresh: bool = False, progress_callback: Any = None) -> list[dict[str, Any]]:
    source = [dict(row) for row in rows]
    ordered: list[dict[str, Any] | None] = [None] * len(source)
    def one(index: int, row: dict[str, Any]):
        row["short_data"] = fetch_short_data(row, force_refresh=force_refresh)
        return index, row
    with ThreadPoolExecutor(max_workers=max(1, min(4, len(source) or 1))) as pool:
        futures = [pool.submit(one, index, row) for index, row in enumerate(source)]
        done = 0
        for future in as_completed(futures):
            index, row = future.result(); ordered[index] = row; done += 1
            if progress_callback:
                progress_callback(done, len(source), str(row.get("ticker") or ""))
    return [row for row in ordered if row is not None]


__all__ = ["fetch_short_data", "fetch_norway", "fetch_sweden", "fetch_usa", "enrich_rows"]
