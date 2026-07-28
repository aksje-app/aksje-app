"""Direct official insider/manager-transaction sources for v19.14.1.

The functions are intentionally fail-closed. A successful source check with no
matching disclosure is represented as SUCCESS_NO_RESULTS. Network, parsing or
access failures are recorded as SOURCE_ERROR and may trigger a documented
fallback; they are never converted into a fabricated transaction.
"""
from __future__ import annotations

import csv
import html
import io
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from xml.etree import ElementTree

import requests

from app_version import APP_VERSION

VERSION = APP_VERSION
DEFAULT_TIMEOUT_SECONDS = 15
NASDAQ_MAIN_RSS = "https://api.news.eu.nasdaq.com/news/rss/mainMarketNotices"
NASDAQ_FIRST_NORTH_RSS = "https://api.news.eu.nasdaq.com/news/rss/firstNorthNotices"
SWEDEN_FI_EXPORT = "https://marknadssok.fi.se/Publiceringsklient/sv-SE/Search/Search"
EURONEXT_OSLO_NEWS = "https://live.euronext.com/en/markets/oslo/equities/company-news"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ticker_root(ticker: str) -> str:
    return str(ticker or "").upper().split(".", 1)[0].replace("-A", "").replace("-B", "")


def _normalise_text(value: Any) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _terms(ticker: str, company: str) -> list[str]:
    values = [_ticker_root(ticker), str(company or "").strip()]
    company_clean = re.sub(r"\b(ASA|AB|OYJ|A/S|AS|PLC|INC\.?|CORP\.?)\b", "", values[1], flags=re.I).strip()
    if company_clean:
        values.append(company_clean)
    out: list[str] = []
    for value in values:
        if value and len(value) >= 2 and value.lower() not in {x.lower() for x in out}:
            out.append(value)
    return out


def _number(value: Any) -> float:
    text = str(value or "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _pick(row: Mapping[str, Any], *tokens: str) -> Any:
    for key, value in row.items():
        normal = re.sub(r"[^a-z0-9]", "", str(key).lower())
        if any(re.sub(r"[^a-z0-9]", "", token.lower()) in normal for token in tokens):
            return value
    return None


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "cp1252", "latin-1"):
        try:
            text = content.decode(encoding)
            if text.strip():
                return text
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _swedish_transaction(row: Mapping[str, Any], url: str) -> dict[str, Any]:
    kind = str(_pick(row, "karaktar", "transaktionstyp", "transaction") or "")
    shares = _number(_pick(row, "volym", "antal"))
    price = _number(_pick(row, "pris"))
    return {
        "date": str(_pick(row, "transaktionsdatum", "datum") or "")[:10],
        "transaction": kind,
        "insider": str(_pick(row, "personiledandestallningnamn", "person", "namn") or "Ukjent"),
        "position": str(_pick(row, "befattning", "position") or "Ukjent rolle"),
        "shares": shares,
        "price": price,
        "value": shares * price if shares and price else 0.0,
        "currency": str(_pick(row, "valuta") or "SEK"),
        "source": "Finansinspektionens insynsregister",
        "source_url": url,
        "verification": "OFFICIAL_PRIMARY",
        "published_at": str(_pick(row, "publiceringsdatum") or ""),
        "retrieved_at": _now(),
        "document_id": str(_pick(row, "publiceringsid", "id") or ""),
    }


def fetch_sweden_fi(ticker: str, company: str, *, lookback_days: int = 90,
                     session: requests.Session | None = None) -> dict[str, Any]:
    client = session or requests.Session()
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=max(1, int(lookback_days)))
    issuer = str(company or _ticker_root(ticker)).strip()
    params = {
        "SearchFunctionType": "Insyn",
        "Utgivare": issuer,
        "PersonILedandeStällningNamn": "",
        "Transaktionsdatum.From": start.isoformat(),
        "Transaktionsdatum.To": today.isoformat(),
        "Publiceringsdatum.From": start.isoformat(),
        "Publiceringsdatum.To": today.isoformat(),
        "button": "export",
        "Page": "1",
    }
    base = {
        "source": "Finansinspektionens insynsregister",
        "source_type": "OFFICIAL_PRIMARY",
        "attempted": True,
        "checked_at": _now(),
        "url": "https://marknadssok.fi.se/publiceringsklient",
        "direct_primary_source_checked": True,
        "transactions": [],
    }
    try:
        response = client.get(SWEDEN_FI_EXPORT, params=params, timeout=DEFAULT_TIMEOUT_SECONDS,
                              headers={"User-Agent": "AI-Aksje-Analyzer-Pro/19.14.1"})
        response.raise_for_status()
        text = _decode_csv(response.content)
        delimiter = ";" if text.count(";") >= text.count(",") else ","
        rows = [dict(row) for row in csv.DictReader(io.StringIO(text), delimiter=delimiter)]
        transactions = [_swedish_transaction(row, response.url) for row in rows if any(str(value or "").strip() for value in row.values())]
        transactions = [row for row in transactions if row.get("date") or row.get("insider") != "Ukjent"]
        base.update({
            "status": "SUCCESS_WITH_RESULTS" if transactions else "SUCCESS_NO_RESULTS",
            "results": len(transactions), "transactions": transactions,
            "url": response.url, "error": "",
        })
    except Exception as exc:
        base.update({"status": "SOURCE_ERROR", "results": 0, "error": f"{type(exc).__name__}: {str(exc)[:400]}"})
    return base


def _parse_date(value: str) -> str:
    text = str(value or "").strip()
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(text)
        return dt.astimezone(timezone.utc).date().isoformat()
    except Exception:
        return text[:10]


def _field(text: str, *labels: str) -> str:
    for label in labels:
        pattern = re.compile(rf"(?:^|[\n;])\s*{re.escape(label)}\s*[:\-]\s*([^\n;]+)", re.I)
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return ""


def _nasdaq_transaction(item: Mapping[str, Any], source_name: str) -> dict[str, Any] | None:
    text = _normalise_text("\n".join(str(item.get(key) or "") for key in ("title", "description", "content")))
    kind = _field(text, "Nature of transaction", "Transaction type", "Liiketoimen luonne", "Transaktionens art")
    if not kind:
        low = text.lower()
        kind = "BUY" if any(token in low for token in ("acquisition", "purchase", "hankinta", "förvärv")) else "SELL" if any(token in low for token in ("disposal", "sale", "luovutus", "avyttring")) else ""
    if not kind:
        return None
    shares = _number(_field(text, "Volume", "Aggregated volume", "Volyymi", "Volym"))
    price = _number(_field(text, "Unit price", "Price", "Yksikköhinta", "Pris"))
    return {
        "date": _field(text, "Transaction date", "Date", "Liiketoimen päivämäärä", "Transaktionsdatum") or _parse_date(str(item.get("pubDate") or "")),
        "transaction": kind,
        "insider": _field(text, "Name", "Person discharging managerial responsibilities", "Nimi", "Namn") or "Ukjent",
        "position": _field(text, "Position/status", "Position", "Asema", "Befattning") or "Ledende person",
        "shares": shares, "price": price, "value": shares * price if shares and price else 0.0,
        "currency": _field(text, "Currency", "Valuutta", "Valuta"),
        "source": source_name, "source_url": str(item.get("link") or ""),
        "verification": "OFFICIAL_EXCHANGE_FEED", "published_at": str(item.get("pubDate") or ""),
        "retrieved_at": _now(), "document_id": str(item.get("guid") or item.get("link") or ""),
    }


def fetch_nasdaq_nordic(ticker: str, company: str, market: str, *, lookback_days: int = 90,
                         session: requests.Session | None = None) -> dict[str, Any]:
    client = session or requests.Session()
    terms = [term.lower() for term in _terms(ticker, company)]
    source_name = f"Nasdaq {market} – offisielle selskapsmeldinger"
    attempts, matched, transactions, errors = 0, 0, [], []
    links = []
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=max(1, int(lookback_days)))
    for url in (NASDAQ_MAIN_RSS, NASDAQ_FIRST_NORTH_RSS):
        try:
            response = client.get(url, timeout=DEFAULT_TIMEOUT_SECONDS,
                                  headers={"User-Agent": "AI-Aksje-Analyzer-Pro/19.14.1"})
            response.raise_for_status(); attempts += 1
            root = ElementTree.fromstring(response.content)
            for node in root.findall(".//item"):
                item = {child.tag.split("}")[-1]: (child.text or "") for child in list(node)}
                text = _normalise_text(" ".join(item.values())).lower()
                if terms and not any(term in text for term in terms):
                    continue
                if not any(token in text for token in (
                    "managers' transactions", "managers transactions", "manager transaction",
                    "johdon liiketoimet", "ledende medarbejdere", "ledende person", "insyn",
                    "transaktioner i aktier", "person discharging managerial responsibilities", "pdmr",
                )):
                    continue
                date_text = _parse_date(item.get("pubDate", ""))
                try:
                    if date_text and datetime.fromisoformat(date_text).date() < cutoff:
                        continue
                except ValueError:
                    pass
                matched += 1; links.append(item.get("link", ""))
                tx = _nasdaq_transaction(item, source_name)
                if tx:
                    transactions.append(tx)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {str(exc)[:220]}")
    if transactions:
        status = "SUCCESS_WITH_RESULTS"
    elif matched:
        status = "DISCOVERY_ONLY"
    elif attempts:
        status = "SUCCESS_NO_RESULTS"
    else:
        status = "SOURCE_ERROR"
    return {
        "source": source_name, "source_type": "OFFICIAL_EXCHANGE_FEED", "attempted": True,
        "status": status, "results": len(transactions), "announcements_found": matched,
        "checked_at": _now(), "url": links[0] if links else NASDAQ_MAIN_RSS,
        "direct_primary_source_checked": True, "transactions": transactions,
        "error": "; ".join(errors),
    }


def fetch_euronext_oslo(ticker: str, company: str, *, lookback_days: int = 90,
                         session: requests.Session | None = None) -> dict[str, Any]:
    client = session or requests.Session(); terms = [term.lower() for term in _terms(ticker, company)]
    base = {
        "source": "Euronext Oslo Børs – selskapsmeldinger", "source_type": "OFFICIAL_PRIMARY",
        "attempted": True, "checked_at": _now(), "url": EURONEXT_OSLO_NEWS,
        "direct_primary_source_checked": True, "transactions": [],
    }
    try:
        response = client.get(EURONEXT_OSLO_NEWS, params={"combine": str(company or _ticker_root(ticker))},
                              timeout=DEFAULT_TIMEOUT_SECONDS, headers={"User-Agent": "AI-Aksje-Analyzer-Pro/19.14.1"})
        response.raise_for_status(); text = _normalise_text(response.text).lower()
        matched = bool(any(term in text for term in terms) and any(token in text for token in (
            "mandatory notification of trade", "primary insider", "meldepliktig handel", "pdmr",
        )))
        base.update({
            "status": "DISCOVERY_ONLY" if matched else "SUCCESS_NO_RESULTS",
            "results": 0, "announcements_found": int(matched), "url": response.url, "error": "",
        })
    except Exception as exc:
        base.update({"status": "SOURCE_ERROR", "results": 0, "error": f"{type(exc).__name__}: {str(exc)[:400]}"})
    return base


def fetch_official_insider_sources(ticker: str, company: str, market: str, *, lookback_days: int = 90,
                                    session: requests.Session | None = None) -> dict[str, Any]:
    """Run market-specific direct sources before any secondary discovery."""
    market = str(market or "").strip()
    attempts: list[dict[str, Any]] = []
    if market == "Sverige":
        attempts.append(fetch_sweden_fi(ticker, company, lookback_days=lookback_days, session=session))
        # Nasdaq is a direct official fallback, especially when issuer-name matching
        # in the FI export is incomplete.
        attempts.append(fetch_nasdaq_nordic(ticker, company, market, lookback_days=lookback_days, session=session))
    elif market in {"Finland", "Danmark"}:
        attempts.append(fetch_nasdaq_nordic(ticker, company, market, lookback_days=lookback_days, session=session))
    elif market == "Norge":
        attempts.append(fetch_euronext_oslo(ticker, company, lookback_days=lookback_days, session=session))
    transactions = [dict(tx) for attempt in attempts for tx in attempt.get("transactions") or []]
    if transactions:
        status = "SUCCESS_WITH_RESULTS"
    elif attempts and all(attempt.get("status") == "SUCCESS_NO_RESULTS" for attempt in attempts):
        status = "SUCCESS_NO_RESULTS"
    elif any(attempt.get("status") == "DISCOVERY_ONLY" for attempt in attempts):
        status = "DISCOVERY_ONLY"
    elif attempts:
        status = "SOURCE_ERROR"
    else:
        status = "NOT_SUPPORTED"
    return {"version": VERSION, "market": market, "status": status, "attempts": attempts,
            "transactions": transactions, "direct_primary_source_checked": bool(attempts)}


__all__ = [
    "VERSION", "fetch_official_insider_sources", "fetch_sweden_fi",
    "fetch_nasdaq_nordic", "fetch_euronext_oslo",
]
