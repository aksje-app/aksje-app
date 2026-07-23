"""Insider Intelligence Engine v18.7.1.

Uses public insider transaction data when available. Missing coverage is represented
as neutral/unknown and never fabricated. Results are cached to reduce provider load.
"""
from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence
import json, math, time, threading

from storage_architecture import runtime_data_path
from durable_runtime import read_json as durable_read_json, write_json as durable_write_json
from international_insider_sources import discover_with_newsapi, source_for_market

VERSION = "v18.7.12"
CACHE_PATH = runtime_data_path("insider_intelligence") / "cache.json"
CACHE_TTL_SECONDS = 24 * 3600
MAX_WORKERS = 4
_CACHE_LOCK = threading.RLock()

ROLE_WEIGHTS = {
    "chief executive": 1.00, "ceo": 1.00, "president": 0.85,
    "chief financial": 0.95, "cfo": 0.95, "chair": 0.90,
    "director": 0.70, "officer": 0.65, "vp": 0.55,
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _load_cache() -> dict[str, Any]:
    value = durable_read_json("insider_intelligence/cache.json", CACHE_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _save_cache(data: Mapping[str, Any]) -> None:
    durable_write_json("insider_intelligence/cache.json", CACHE_PATH, dict(data))


def _store_cached_result(ticker: str, result: Mapping[str, Any]) -> None:
    with _CACHE_LOCK:
        cache = _load_cache()
        cache[ticker] = {"cached_at": time.time(), "result": dict(result)}
        _save_cache(cache)


def _role_weight(role: str) -> float:
    text = str(role or "").lower()
    return max((weight for token, weight in ROLE_WEIGHTS.items() if token in text), default=0.45)


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "reset_index") and hasattr(value, "to_dict"):
        try:
            return [dict(x) for x in value.reset_index().to_dict("records")]
        except Exception:
            pass
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [dict(x) for x in value if isinstance(x, Mapping)]
    return []


def _pick(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(k).lower().replace("_", " "): v for k, v in row.items()}
    for name in names:
        key = name.lower().replace("_", " ")
        if key in lowered:
            return lowered[key]
    return None


def _parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        try: return value.to_pydatetime().replace(tzinfo=timezone.utc)
        except Exception: pass
    text = str(value).strip()
    for candidate in (text[:10], text):
        try:
            dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            return dt.replace(tzinfo=dt.tzinfo or timezone.utc)
        except Exception:
            continue
    return None


def _transaction_type(row: Mapping[str, Any]) -> str:
    text = " ".join(str(_pick(row, x) or "") for x in ("transaction", "text", "type", "transaction type")).lower()
    shares = _f(_pick(row, "shares", "shares traded", "position change"), 0.0)
    if any(x in text for x in ("sale", "sell", "disposed", "disposition")) or shares < 0:
        return "SELL"
    if any(x in text for x in ("purchase", "buy", "acquired", "acquisition")) or shares > 0:
        return "BUY"
    return "OTHER"


def score_transactions(ticker: str, rows: Sequence[Mapping[str, Any]], lookback_days: int = 90) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    evidence, weighted_buy, weighted_sell = [], 0.0, 0.0
    buyers, sellers, total_buy, total_sell = set(), set(), 0.0, 0.0
    for raw in rows:
        row = dict(raw)
        dt = _parse_date(_pick(row, "start date", "date", "transaction date", "filing date"))
        age = (now - dt).days if dt else lookback_days
        if age < 0 or age > lookback_days:
            continue
        kind = _transaction_type(row)
        if kind == "OTHER":
            continue
        insider = str(_pick(row, "insider", "insider name", "owner", "name") or "Ukjent insider")
        role = str(_pick(row, "position", "title", "relationship") or "")
        shares = abs(_f(_pick(row, "shares", "shares traded", "position change"), 0.0))
        value = abs(_f(_pick(row, "value", "transaction value", "total value"), 0.0))
        if not value:
            price = abs(_f(_pick(row, "value", "price", "transaction price"), 0.0))
            value = shares * price if shares and price else shares
        recency = max(0.15, 1.0 - age / max(1, lookback_days))
        importance = _role_weight(role)
        magnitude = min(1.0, math.log10(max(value, 1.0)) / 7.0)
        weighted = (0.45 * recency + 0.30 * importance + 0.25 * magnitude)
        if kind == "BUY":
            weighted_buy += weighted; total_buy += value; buyers.add(insider)
        else:
            weighted_sell += weighted; total_sell += value; sellers.add(insider)
        evidence.append({
            "date": dt.date().isoformat() if dt else "Ukjent", "type": kind,
            "insider": insider, "role": role or "Ukjent rolle", "shares": round(shares, 2),
            "price": round(abs(_f(_pick(row, "price", "transaction price"), 0.0)), 4),
            "value": round(value, 2), "age_days": age,
            "currency": str(_pick(row, "currency") or ""),
            "source": str(_pick(row, "source") or "Offentlig innsiderrapportering"),
            "source_url": str(_pick(row, "source url", "source_url", "url") or ""),
            "document_id": str(_pick(row, "document id", "document_id", "accession") or ""),
            "verification": str(_pick(row, "verification") or "STRUCTURED_PROVIDER"),
            "published_at": str(_pick(row, "published at", "published_at", "filing date") or ""),
            "retrieved_at": str(_pick(row, "retrieved at", "retrieved_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")),
        })
    evidence.sort(key=lambda x: (x["date"], x["value"]), reverse=True)
    if not evidence:
        return {"ticker": ticker, "score": 50.0, "signal": "INGEN VERIFISERTE TRANSAKSJONER", "coverage": "MISSING", "buy_count": 0, "sell_count": 0, "net_value": 0.0, "evidence": [], "reason": "Kilden ble kontrollert, men ingen verifiserte insidertransaksjoner var tilgjengelige."}
    cluster_bonus = min(12.0, max(0, len(buyers) - 1) * 4.0)
    direction = (weighted_buy - weighted_sell) / max(0.8, weighted_buy + weighted_sell)
    value_direction = (total_buy - total_sell) / max(1.0, total_buy + total_sell)
    combined_direction = .55 * direction + .45 * value_direction
    score = max(0.0, min(100.0, 50.0 + combined_direction * 34.0 + (cluster_bonus if total_buy >= total_sell else 0.0)))
    # Counts and cluster bonus may not turn a net-sale period into a positive signal.
    if total_sell > total_buy:
        score = min(score, 61.0)
    signal = "STERKT POSITIV" if score >= 78 else "POSITIV" if score >= 62 else "NØYTRAL" if score >= 42 else "NEGATIV" if score >= 25 else "STERKT NEGATIV"
    return {
        "ticker": ticker, "score": round(score, 2), "signal": signal, "coverage": "AVAILABLE",
        "buy_count": sum(1 for x in evidence if x["type"] == "BUY"),
        "sell_count": sum(1 for x in evidence if x["type"] == "SELL"),
        "unique_buyers": len(buyers), "unique_sellers": len(sellers),
        "buy_value": round(total_buy, 2), "sell_value": round(total_sell, 2),
        "net_value": round(total_buy - total_sell, 2), "evidence": evidence[:10],
        "reason": (
            f"{len(buyers)} kjøper(e), {len(sellers)} selger(e) siste {lookback_days} dager; "
            f"nettoverdi {round(total_buy - total_sell, 2)}."
        ),
    }


def fetch_insider_intelligence(ticker: str, force_refresh: bool = False, lookback_days: int = 90,
                               market: str = "", company: str = "") -> dict[str, Any]:
    ticker = str(ticker or "").upper().strip()
    cache = _load_cache(); cached = cache.get(ticker)
    if cached and not force_refresh and time.time() - _f(cached.get("cached_at"), 0) < CACHE_TTL_SECONDS and (cached.get("result") or {}).get("search_log"):
        result = dict(cached.get("result") or {})
        source = source_for_market(market)
        result.setdefault("currency", source.get("currency", ""))
        result.setdefault("official_source", source.get("name", ""))
        result.setdefault("official_search_url", source.get("search_url", ""))
        if result.get("coverage") != "AVAILABLE" and market and "source_discovery" not in result:
            discovery = discover_with_newsapi(ticker, company, market)
            result["source_discovery"] = discovery
            if discovery.get("articles"):
                result.update({"score": 50.0, "signal": "KILDER FUNNET", "coverage": "DISCOVERY_ONLY",
                               "reason": f"{len(discovery['articles'])} mulig(e) kildemelding(er) funnet; avventer strukturert verifikasjon."})
            elif discovery.get("status") == "NEWSAPI_NOT_CONFIGURED":
                result.update({"signal": "KILDE IKKE KONFIGURERT", "coverage": "NOT_CONFIGURED",
                               "reason": "NEWSAPI_KEY mangler; primærkilden ga ingen strukturerte transaksjoner."})
            elif discovery.get("status") == "DISCOVERY_ERROR":
                result.update({"signal": "KILDEFEIL", "coverage": "ERROR",
                               "reason": str(discovery.get("error") or "Kildeoppslag feilet")})
            _store_cached_result(ticker, result)
        return result
    search_log: list[dict[str, Any]] = []
    try:
        import yfinance as yf
        obj = yf.Ticker(ticker)
        value = None
        provider_error = ""
        for attr in ("insider_transactions", "get_insider_transactions"):
            try:
                candidate = getattr(obj, attr)
                value = candidate() if callable(candidate) else candidate
                if value is not None: break
            except Exception as exc:
                provider_error = str(exc)
                continue
        provider_rows = _records(value)
        search_log.append({
            "source": "yfinance / public filings", "source_type": "SECONDARY_STRUCTURED",
            "attempted": True, "status": "SUCCESS_WITH_RESULTS" if provider_rows else ("ERROR" if provider_error and value is None else "SUCCESS_NO_RESULTS"),
            "results": len(provider_rows), "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": provider_error[:500] if value is None else "",
        })
        verified_rows = list(provider_rows)
        if str(market or "") == "USA":
            from sec_form4_source import fetch_sec_form4
            sec = fetch_sec_form4(ticker, lookback_days=lookback_days)
            search_log.append({key: sec.get(key) for key in (
                "source", "source_type", "attempted", "status", "results", "filings_found", "checked_at", "error"
            )})
            verified_rows.extend(sec.get("transactions") or [])
        result = score_transactions(ticker, verified_rows, lookback_days=lookback_days)
        result["source"] = ", ".join(
            row["source"] for row in search_log if row.get("status") == "SUCCESS_WITH_RESULTS"
        ) or "Kontrollerte offentlige kilder"
        result["fetched_at"] = datetime.now(timezone.utc).isoformat()
        source = source_for_market(market)
        result["currency"] = source.get("currency", "")
        result["official_source"] = source.get("name", "")
        result["official_search_url"] = source.get("search_url", "")
        if result.get("coverage") != "AVAILABLE" and market:
            discovery = discover_with_newsapi(ticker, company, market)
            search_log.append({
                "source": discovery.get("official_source") or "Offisiell markeds-/tilsynskilde via NewsAPI",
                "source_type": "PRIMARY_SOURCE_DISCOVERY",
                "attempted": discovery.get("status") != "NEWSAPI_NOT_CONFIGURED",
                "status": {
                    "DISCOVERY_FOUND": "DISCOVERY_ONLY", "NO_DISCOVERY": "SUCCESS_NO_RESULTS",
                    "NEWSAPI_NOT_CONFIGURED": "NOT_CONFIGURED", "DISCOVERY_ERROR": "ERROR",
                }.get(str(discovery.get("status") or ""), "NOT_SEARCHED"),
                "results": len(discovery.get("articles") or []),
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "url": discovery.get("official_search_url") or "",
                "error": discovery.get("error") or "",
            })
            result["source_discovery"] = discovery
            if discovery.get("articles"):
                result.update({
                    "score": 50.0, "signal": "KILDER FUNNET", "coverage": "DISCOVERY_ONLY",
                    "reason": f"{len(discovery['articles'])} mulig(e) kildemelding(er) funnet; transaksjonen må struktureres og verifiseres før scoring.",
                })
            elif discovery.get("status") == "NEWSAPI_NOT_CONFIGURED":
                result.update({"signal": "KILDE IKKE KONFIGURERT", "coverage": "NOT_CONFIGURED",
                               "reason": "NEWSAPI_KEY mangler; ingen sekundær kildeoppdagelse ble utført."})
            elif discovery.get("status") == "DISCOVERY_ERROR":
                result.update({"signal": "KILDEFEIL", "coverage": "ERROR",
                               "reason": str(discovery.get("error") or "Kildeoppslag feilet")})
    except Exception as exc:
        source = source_for_market(market)
        discovery = discover_with_newsapi(ticker, company, market) if market else {}
        found = list(discovery.get("articles") or [])
        result = {
            "ticker": ticker, "score": 50.0,
            "signal": "KILDER FUNNET" if found else "KILDEFEIL",
            "coverage": "DISCOVERY_ONLY" if found else "ERROR",
            "buy_count": 0, "sell_count": 0, "net_value": 0.0, "evidence": [],
            "reason": (f"{len(found)} mulig(e) kildemelding(er) funnet; avventer strukturert verifikasjon."
                       if found else str(exc)),
            "source": "NewsAPI discovery" if found else "unavailable",
            "source_discovery": discovery, "currency": source.get("currency", ""),
            "official_source": source.get("name", ""),
            "official_search_url": source.get("search_url", ""),
        }
        search_log.append({
            "source": "yfinance / public filings", "source_type": "SECONDARY_STRUCTURED",
            "attempted": True, "status": "ERROR", "results": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": str(exc)[:500],
        })
    result["search_log"] = search_log
    result["sources_checked"] = sum(1 for row in search_log if row.get("attempted"))
    result["verified_fact_count"] = len(result.get("evidence") or [])
    _store_cached_result(ticker, result)
    return result


def enrich_rows(rows: Sequence[Mapping[str, Any]], force_refresh: bool = False, progress_callback: Any | None = None) -> list[dict[str, Any]]:
    source_rows = [dict(row) for row in rows]
    total = len(source_rows)

    def enrich_one(index: int, row: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        clean = dict(row)
        insider = fetch_insider_intelligence(
            str(clean.get("ticker") or ""), force_refresh=force_refresh,
            market=str(clean.get("market") or ""),
            company=str(clean.get("name") or clean.get("longName") or clean.get("shortName") or ""),
        )
        clean["insider_intelligence"] = insider
        clean["insider_score"] = insider.get("score", 50.0)
        clean["insider_signal"] = insider.get("signal", "INGEN DATA")
        return index, clean

    completed = 0
    ordered: list[dict[str, Any] | None] = [None] * total
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, total or 1))) as pool:
        futures = {pool.submit(enrich_one, index, row): index for index, row in enumerate(source_rows)}
        for future in as_completed(futures):
            index, clean = future.result()
            ordered[index] = clean
            completed += 1
            if progress_callback:
                progress_callback(completed, total, str(clean.get("ticker") or ""))
    return [row for row in ordered if row is not None]
