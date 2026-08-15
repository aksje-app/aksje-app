"""Verified SEC Form 4 retrieval with fact-level provenance.

Only successfully parsed Form 4 transactions are marked verified. Filing
metadata without parsable transactions remains discovery evidence and never
enters insider scoring as a confirmed buy or sale.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from xml.etree import ElementTree

SEC_BASE = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"
_TICKER_CACHE_LOCK = threading.RLock()
_TICKER_CACHE: dict[str, tuple[str, str]] = {}
_TICKER_CACHE_FETCHED_AT = 0.0
_TICKER_CACHE_TTL_SECONDS = 24 * 3600


def _headers() -> dict[str, str]:
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not user_agent:
        return {}
    return {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}


def _value(node: Any, path: str) -> str:
    found = node.find(path)
    if found is None:
        wanted = path.rsplit("/", 1)[-1]
        for candidate in node.iter():
            if str(candidate.tag).rsplit("}", 1)[-1] == wanted:
                found = candidate
                break
    return str(found.text or "").strip() if found is not None else ""


def _number(value: Any) -> float:
    try:
        return float(str(value or "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _ticker_registry(session: Any) -> dict[str, tuple[str, str]]:
    """Fetch the static SEC ticker registry once per process/day."""
    global _TICKER_CACHE, _TICKER_CACHE_FETCHED_AT
    with _TICKER_CACHE_LOCK:
        if _TICKER_CACHE and time.time() - _TICKER_CACHE_FETCHED_AT < _TICKER_CACHE_TTL_SECONDS:
            return _TICKER_CACHE
        response = session.get(f"{SEC_BASE}/files/company_tickers.json", headers=_headers(), timeout=15)
        response.raise_for_status()
        registry: dict[str, tuple[str, str]] = {}
        for row in (response.json() or {}).values():
            key = str(row.get("ticker") or "").upper().replace(".", "-")
            if key:
                registry[key] = (str(row.get("cik_str") or "").zfill(10), str(row.get("title") or ""))
        if registry:
            _TICKER_CACHE = registry
            _TICKER_CACHE_FETCHED_AT = time.time()
        return registry


def _ticker_cik(ticker: str, session: Any) -> tuple[str, str]:
    wanted = str(ticker or "").upper().replace(".", "-")
    return _ticker_registry(session).get(wanted, ("", ""))


def _parse_form4(xml_bytes: bytes, *, filing: Mapping[str, Any], filing_url: str) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(xml_bytes)
    owner = _value(root, ".//reportingOwner/reportingOwnerId/rptOwnerName") or "Ukjent rapporteringspliktig"
    role_parts = [
        _value(root, ".//reportingOwner/reportingOwnerRelationship/officerTitle"),
        "Director" if _value(root, ".//reportingOwner/reportingOwnerRelationship/isDirector") == "1" else "",
        "Officer" if _value(root, ".//reportingOwner/reportingOwnerRelationship/isOfficer") == "1" else "",
    ]
    role = ", ".join(part for part in role_parts if part) or "Ukjent rolle"
    rows: list[dict[str, Any]] = []
    transactions = [
        node for node in root.iter()
        if str(node.tag).rsplit("}", 1)[-1] == "nonDerivativeTransaction"
    ]
    for transaction in transactions:
        code = _value(transaction, ".//transactionCoding/transactionCode").upper()
        if code not in {"P", "S"}:
            continue
        shares = abs(_number(_value(transaction, ".//transactionAmounts/transactionShares/value")))
        price = abs(_number(_value(transaction, ".//transactionAmounts/transactionPricePerShare/value")))
        transaction_date = _value(transaction, ".//transactionDate/value") or str(filing.get("filing_date") or "")
        rows.append({
            "date": transaction_date,
            "type": "BUY" if code == "P" else "SELL",
            "insider": owner,
            "role": role,
            "shares": round(shares, 4),
            "price": round(price, 4),
            "value": round(shares * price, 2) if shares and price else 0.0,
            "currency": "USD",
            "source": "SEC Form 4",
            "source_url": filing_url,
            "document_id": str(filing.get("accession") or ""),
            "verification": "VERIFIED_PRIMARY",
            "published_at": str(filing.get("filing_date") or ""),
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    return rows


def fetch_sec_form4(ticker: str, lookback_days: int = 90, session: Any = None) -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result: dict[str, Any] = {
        "source": "SEC EDGAR Form 4",
        "source_type": "PRIMARY_REGULATORY",
        "attempted": False,
        "status": "NOT_CONFIGURED",
        "checked_at": checked_at,
        "results": 0,
        "filings_found": 0,
        "transactions": [],
        "error": "",
    }
    if not _headers():
        result["error"] = "SEC_USER_AGENT mangler"
        return result
    if session is None:
        import requests
        session = requests.Session()
    result["attempted"] = True
    try:
        cik, company = _ticker_cik(ticker, session)
        if not cik:
            result.update({"status": "SUCCESS_NO_RESULTS", "company": "", "error": "Ticker ikke funnet i SEC-registeret"})
            return result
        response = session.get(f"{SEC_DATA}/submissions/CIK{cik}.json", headers=_headers(), timeout=15)
        response.raise_for_status()
        recent = (response.json().get("filings") or {}).get("recent") or {}
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=max(1, int(lookback_days)))
        filings: list[dict[str, str]] = []
        for index, form in enumerate(recent.get("form") or []):
            if str(form).upper() != "4":
                continue
            filing_date = str((recent.get("filingDate") or [""])[index])
            try:
                if datetime.fromisoformat(filing_date).date() < cutoff:
                    continue
            except ValueError:
                continue
            filings.append({
                "accession": str((recent.get("accessionNumber") or [""])[index]),
                "primary_document": str((recent.get("primaryDocument") or [""])[index]),
                "filing_date": filing_date,
            })
        result["filings_found"] = len(filings)
        transactions: list[dict[str, Any]] = []
        for filing in filings[:20]:
            accession_path = filing["accession"].replace("-", "")
            filing_url = f"{SEC_BASE}/Archives/edgar/data/{int(cik)}/{accession_path}/{filing['primary_document']}"
            try:
                filing_response = session.get(filing_url, headers=_headers(), timeout=15)
                filing_response.raise_for_status()
                transactions.extend(_parse_form4(filing_response.content, filing=filing, filing_url=filing_url))
            except Exception:
                continue
        result["transactions"] = transactions
        result["results"] = len(transactions)
        result["company"] = company
        result["status"] = "SUCCESS_WITH_RESULTS" if transactions else "SUCCESS_NO_RESULTS"
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = str(exc)[:500]
    return result
