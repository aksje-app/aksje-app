"""Insider Intelligence Engine v18.7.1.

Uses public insider transaction data when available. Missing coverage is represented
as neutral/unknown and never fabricated. Results are cached to reduce provider load.
"""
from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence
import hashlib, json, math, time, threading

from storage_architecture import runtime_data_path
from durable_runtime import read_json as durable_read_json, write_json as durable_write_json
from international_insider_sources import discover_with_newsapi, source_for_market
from official_insider_sources import fetch_official_insider_sources
from app_version import APP_VERSION

VERSION = APP_VERSION
CACHE_PATH = runtime_data_path("insider_intelligence") / "cache.json"
CACHE_TTL_SECONDS = 24 * 3600
INSIDER_CACHE_SCHEMA_VERSION = 2
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
        cache[ticker] = {
            "cached_at": time.time(), "schema_version": INSIDER_CACHE_SCHEMA_VERSION,
            "app_version": APP_VERSION, "result": dict(result),
        }
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
    from insider_transaction_semantics import transaction_type
    return transaction_type(row)


def _deduplicate_transactions(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Prefer a primary filing when providers repeat the same transaction."""
    selected: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        dt = _parse_date(_pick(row, "start date", "date", "transaction date", "filing date"))
        key = (
            str(_pick(row, "insider", "insider name", "owner", "name") or "").casefold().strip(),
            dt.date().isoformat() if dt else "",
            _transaction_type(row),
            round(abs(_f(_pick(row, "shares", "shares traded", "position change"), 0.0)), 4),
            round(abs(_f(_pick(row, "price", "transaction price"), 0.0)), 4),
        )
        existing = selected.get(key)
        primary = str(_pick(row, "source_type", "source type") or "").upper() == "OFFICIAL_PRIMARY"
        existing_primary = bool(existing and str(_pick(existing, "source_type", "source type") or "").upper() == "OFFICIAL_PRIMARY")
        if existing is None or (primary and not existing_primary):
            selected[key] = row
    return list(selected.values())


def score_transactions(
    ticker: str, rows: Sequence[Mapping[str, Any]], lookback_days: int = 180,
    sell_lookback_days: int = 90,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    evidence, weighted_buy, weighted_sell = [], 0.0, 0.0
    buyers, sellers, total_buy, total_sell = set(), set(), 0.0, 0.0
    for raw in _deduplicate_transactions(rows):
        row = dict(raw)
        dt = _parse_date(_pick(row, "start date", "date", "transaction date", "filing date"))
        age = (now - dt).days if dt else lookback_days
        kind = _transaction_type(row)
        if kind == "OTHER":
            continue
        active_lookback = sell_lookback_days if kind == "SELL" else lookback_days
        if age < 0 or age > active_lookback:
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
        planned_10b5_1 = bool(row.get("planned_10b5_1"))
        if kind == "BUY":
            weighted_buy += weighted; total_buy += value; buyers.add(insider)
        else:
            # Pre-arranged 10b5-1 sales are real transactions but normally carry
            # less discretionary information than an unplanned open-market sale.
            weighted_sell += weighted * (0.25 if planned_10b5_1 else 1.0)
            total_sell += value; sellers.add(insider)
        source_type = str(_pick(row, "source_type", "source type") or "SECONDARY_STRUCTURED").upper()
        source_url = str(_pick(row, "source url", "source_url", "url") or "")
        document_id = str(_pick(row, "document id", "document_id", "accession") or "")
        form_type = str(_pick(row, "form type", "form_type", "form") or "")
        verification = str(_pick(row, "verification") or (
            "PRIMARY_DOCUMENT" if source_type == "OFFICIAL_PRIMARY" else "STRUCTURED_PROVIDER"
        ))
        primary_source_verified = bool(
            source_type == "OFFICIAL_PRIMARY"
            and source_url
            and (document_id or form_type or str(_pick(row, "direct_primary_source_checked") or "").casefold() in {"1", "true", "yes"})
        )
        provenance_quality = "PRIMARY_DOCUMENT" if primary_source_verified else "SECONDARY_STRUCTURED"
        fact_seed = "|".join((ticker, insider, dt.date().isoformat() if dt else "", kind, str(shares), str(value), source_url, document_id))
        evidence.append({
            "fact_id": "INSIDER-" + hashlib.sha1(fact_seed.encode("utf-8")).hexdigest()[:12].upper(),
            "date": dt.date().isoformat() if dt else "Ukjent", "type": kind,
            "insider": insider, "role": role or "Ukjent rolle", "shares": round(shares, 2),
            "price": round(abs(_f(_pick(row, "price", "transaction price"), 0.0)), 4),
            "value": round(value, 2), "age_days": age,
            "currency": str(_pick(row, "currency") or ""),
            "source": str(_pick(row, "source") or ("Offisiell primærkilde" if primary_source_verified else "Strukturert dataleverandør")),
            "source_type": source_type,
            "source_url": source_url,
            "document_id": document_id,
            "form_type": form_type,
            "verification": verification,
            "primary_source_verified": primary_source_verified,
            "provenance_quality": provenance_quality,
            "provenance_complete": bool(primary_source_verified),
            "published_at": str(_pick(row, "published at", "published_at", "filing date") or ""),
            "retrieved_at": str(_pick(row, "retrieved at", "retrieved_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")),
            "planned_10b5_1": planned_10b5_1,
        })
    evidence.sort(key=lambda x: (x["date"], x["value"]), reverse=True)
    if not evidence:
        return {"ticker": ticker, "score": 50.0, "signal": "INGEN VERIFISERTE TRANSAKSJONER", "coverage": "MISSING", "buy_count": 0, "sell_count": 0, "net_value": 0.0, "evidence": [], "reason": "Kilden ble kontrollert, men ingen verifiserte insidertransaksjoner var tilgjengelige."}
    cluster_bonus = min(12.0, max(0, len(buyers) - 1) * 4.0)
    direction = (weighted_buy - weighted_sell) / max(0.8, weighted_buy + weighted_sell)
    value_direction = (total_buy - total_sell) / max(1.0, total_buy + total_sell)
    combined_direction = .55 * direction + .45 * value_direction
    # One small or pre-arranged sale must not receive the same extreme score as
    # a broad, recent cluster.  Evidence intensity controls distance from 50.
    evidence_intensity = min(1.0, (weighted_buy + weighted_sell) / 3.0)
    score = max(0.0, min(100.0, 50.0 + combined_direction * 34.0 * evidence_intensity + (cluster_bonus if total_buy >= total_sell else 0.0)))
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
        "primary_verified_fact_count": sum(row.get("primary_source_verified") is True for row in evidence),
        "secondary_fact_count": sum(row.get("primary_source_verified") is not True for row in evidence),
        "provenance_status": (
            "PRIMARY_VERIFIED" if any(row.get("primary_source_verified") is True for row in evidence)
            else "SECONDARY_ONLY"
        ),
        "reason": (
            f"{len(buyers)} kjøper(e) siste {lookback_days} dager, {len(sellers)} selger(e) siste {sell_lookback_days} dager; "
            f"nettoverdi {round(total_buy - total_sell, 2)}."
        ),
    }


def fetch_insider_intelligence(ticker: str, force_refresh: bool = False, lookback_days: int = 180,
                               market: str = "", company: str = "", *,
                               primary_only: bool = False) -> dict[str, Any]:
    ticker = str(ticker or "").upper().strip()
    cache = _load_cache(); cached = cache.get(ticker)
    cached_logs = (cached.get("result") or {}).get("search_log") if cached else []
    brazil_primary_cached = any("CVM" in str(row.get("source") or "") for row in cached_logs or [])
    direct_primary_cached = any(bool(row.get("direct_primary_source_checked")) for row in cached_logs or [])
    requires_direct_primary = str(market or "") in {"Norge", "Sverige", "Finland", "Danmark", "USA"}
    cache_has_required_primary = (market != "Brasil" or brazil_primary_cached) and (not requires_direct_primary or direct_primary_cached)
    cache_schema_current = bool(cached and int(_f(cached.get("schema_version"), 0)) == INSIDER_CACHE_SCHEMA_VERSION)
    if cached and cache_schema_current and not force_refresh and time.time() - _f(cached.get("cached_at"), 0) < CACHE_TTL_SECONDS and cached_logs and cache_has_required_primary:
        result = dict(cached.get("result") or {})
        source = source_for_market(market)
        result.setdefault("currency", source.get("currency", ""))
        result.setdefault("official_source", source.get("name", ""))
        result.setdefault("official_search_url", source.get("search_url", ""))
        if not primary_only and result.get("coverage") not in {"AVAILABLE", "CHECKED_NO_EVENTS"} and market and "source_discovery" not in result:
            discovery = discover_with_newsapi(ticker, company, market)
            result["source_discovery"] = discovery
            if discovery.get("articles"):
                result.update({"score": 50.0, "signal": "KILDER FUNNET", "coverage": "DISCOVERY_ONLY",
                               "reason": f"{len(discovery['articles'])} mulig(e) kildemelding(er) funnet; avventer strukturert verifikasjon."})
            elif discovery.get("status") == "NEWSAPI_NOT_CONFIGURED":
                result.update({"signal": "KILDE IKKE KONFIGURERT", "coverage": "NOT_CONFIGURED",
                               "reason": "NEWSAPI_KEY mangler; primærkilden ga ingen strukturerte transaksjoner."})
            elif discovery.get("status") in {"RATE_LIMITED", "DAILY_QUOTA_EXCEEDED"}:
                result.update({
                    "signal": "KILDEKONTROLL DELVIS",
                    "coverage": "PARTIAL_SOURCE_FAILURE",
                    "reason": (
                        "Sekundær NewsAPI-kildeoppdagelse var begrenset. "
                        "Dette betyr ikke at den navngitte primærkilden feilet eller ble kontrollert direkte."
                    ),
                })
            elif discovery.get("status") == "DISCOVERY_ERROR":
                result.update({"signal": "KILDEKONTROLL DELVIS", "coverage": "PARTIAL_SOURCE_FAILURE",
                               "reason": "Sekundær kildeoppdagelse feilet etter direkte primærkildeforsøk."})
            result.setdefault("search_log", []).append({
                "source": discovery.get("source_label") or "NewsAPI-kildeoppdagelse",
                "source_type": "SECONDARY_SOURCE_DISCOVERY",
                "attempted": discovery.get("status") not in {"NEWSAPI_NOT_CONFIGURED", "DAILY_QUOTA_EXCEEDED"},
                "status": {
                    "DISCOVERY_FOUND": "DISCOVERY_ONLY", "NO_DISCOVERY": "SUCCESS_NO_RESULTS",
                    "NEWSAPI_NOT_CONFIGURED": "NOT_CONFIGURED", "DISCOVERY_ERROR": "SOURCE_ERROR",
                    "RATE_LIMITED": "RATE_LIMITED", "DAILY_QUOTA_EXCEEDED": "DAILY_QUOTA_EXCEEDED",
                }.get(str(discovery.get("status") or ""), "NOT_SEARCHED"),
                "results": len(discovery.get("articles") or []),
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "url": "",
                "requested_primary_source": discovery.get("official_source") or "",
                "direct_primary_source_checked": False,
                "error": str(discovery.get("error") or "")[:240],
            })
            _store_cached_result(ticker, result)
        from evidence_contract import normalize_search_payload
        return normalize_search_payload(result, area="insider")
    search_log: list[dict[str, Any]] = []
    verified_rows: list[dict[str, Any]] = []
    official_result: dict[str, Any] = {"status": "NOT_SUPPORTED", "attempts": [], "transactions": []}

    # Direct official sources are always attempted before secondary aggregators. A
    # provider failure must never prevent a direct primary-source check.
    try:
        official_result = dict(fetch_official_insider_sources(
            ticker, company, str(market or ""), lookback_days=lookback_days
        ) or {})
    except Exception as exc:
        official_result = {
            "status": "SOURCE_ERROR", "attempts": [{
                "source": source_for_market(market).get("name", "Offisiell primærkilde"),
                "source_type": "OFFICIAL_PRIMARY", "attempted": True,
                "status": "SOURCE_ERROR", "results": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "url": source_for_market(market).get("search_url", ""),
                "direct_primary_source_checked": True, "error": str(exc)[:500],
            }], "transactions": [],
        }
    for attempt in official_result.get("attempts") or []:
        if not isinstance(attempt, Mapping):
            continue
        search_log.append({key: attempt.get(key) for key in (
            "source", "source_type", "attempted", "status", "results", "announcements_found",
            "checked_at", "url", "direct_primary_source_checked", "error"
        )})
    verified_rows.extend(
        dict(row) for row in (official_result.get("transactions") or []) if isinstance(row, Mapping)
    )

    # Secondary structured provider. The lightweight all-candidate pass skips
    # this provider; the expensive evidence shortlist retains the full search.
    # Errors are recorded, not raised, so direct
    # official results remain authoritative and usable.
    provider_rows: list[dict[str, Any]] = []
    provider_error = ""
    value: Any = None
    if not primary_only:
        try:
            import yfinance as yf
            obj = yf.Ticker(ticker)
            for attr in ("insider_transactions", "get_insider_transactions"):
                try:
                    candidate = getattr(obj, attr)
                    value = candidate() if callable(candidate) else candidate
                    if value is not None:
                        break
                except Exception as exc:
                    provider_error = str(exc)
            provider_rows = _records(value)
            for provider_row in provider_rows:
                provider_row.setdefault("source", "yfinance / public filings")
                provider_row.setdefault("source_type", "SECONDARY_STRUCTURED")
                provider_row.setdefault("verification", "STRUCTURED_PROVIDER")
        except Exception as exc:
            provider_error = str(exc)
    if not primary_only:
        search_log.append({
            "source": "yfinance / public filings", "source_type": "SECONDARY_STRUCTURED",
            "attempted": True,
            "status": "SUCCESS_WITH_RESULTS" if provider_rows else ("SOURCE_ERROR" if provider_error else "SUCCESS_NO_RESULTS"),
            "results": len(provider_rows),
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": provider_error[:500],
        })
    verified_rows.extend(provider_rows)

    sec: dict[str, Any] = {}
    if str(market or "") == "USA":
        try:
            from sec_form4_source import fetch_sec_form4
            sec = dict(fetch_sec_form4(ticker, lookback_days=lookback_days) or {})
        except Exception as exc:
            sec = {
                "source": "SEC Form 4", "source_type": "OFFICIAL_PRIMARY", "attempted": True,
                "status": "SOURCE_ERROR", "results": 0, "filings_found": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "error": str(exc)[:500], "transactions": [],
            }
        sec_attempt = {key: sec.get(key) for key in (
            "source", "source_type", "attempted", "status", "results", "filings_found", "checked_at", "error"
        )}
        sec_attempt["direct_primary_source_checked"] = bool(sec.get("attempted"))
        search_log.append(sec_attempt)
        verified_rows.extend(
            dict(row) for row in (sec.get("transactions") or []) if isinstance(row, Mapping)
        )

    if str(market or "") == "Brasil":
        try:
            from cvm_insider_source import fetch_cvm_transactions
            cvm = dict(fetch_cvm_transactions(ticker, company, lookback_days=lookback_days) or {})
        except Exception as exc:
            cvm = {
                "source": "CVM – Valores Mobiliários Negociados e Detidos",
                "source_type": "OFFICIAL_PRIMARY", "attempted": True,
                "status": "SOURCE_ERROR", "results": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "url": "https://dados.cvm.gov.br/dataset/cia_aberta-doc-vlmo",
                "error": str(exc)[:500], "transactions": [],
            }
        search_log.append({key: cvm.get(key) for key in (
            "source", "source_type", "attempted", "status", "results", "checked_at", "url", "error"
        )})
        verified_rows.extend(
            dict(row) for row in (cvm.get("transactions") or []) if isinstance(row, Mapping)
        )

    result = score_transactions(ticker, verified_rows, lookback_days=lookback_days)
    official_statuses = {str(official_result.get("status") or "NOT_SUPPORTED").upper()}
    if sec:
        official_statuses.add(str(sec.get("status") or "NOT_SUPPORTED").upper())
    official_completed_no_events = bool(
        official_statuses & {"SUCCESS_NO_RESULTS", "CHECKED_NO_EVENTS"}
        and not official_statuses & {"SOURCE_ERROR", "ERROR", "RATE_LIMITED"}
    )
    if not result.get("evidence") and official_completed_no_events:
        result.update({
            "score": 50.0, "signal": "KONTROLLERT – INGEN HENDELSER",
            "coverage": "CHECKED_NO_EVENTS", "buy_count": 0, "sell_count": 0,
            "net_value": 0.0, "evidence": [],
            "reason": "Offisiell primærkilde ble kontrollert direkte uten relevante innsidetransaksjoner i perioden.",
        })
    elif not result.get("evidence") and "DISCOVERY_ONLY" in official_statuses:
        result.update({
            "score": 50.0, "signal": "OFFISIELL MELDING FUNNET",
            "coverage": "DISCOVERY_ONLY",
            "reason": "Offisiell børsmelding ble funnet, men transaksjonsfeltene kunne ikke struktureres sikkert.",
        })

    result["source"] = ", ".join(
        str(row.get("source") or "") for row in search_log
        if row.get("status") == "SUCCESS_WITH_RESULTS" and row.get("source")
    ) or (", ".join(
        str(row.get("source") or "") for row in search_log
        if row.get("direct_primary_source_checked") and row.get("source")
    ) or "Kontrollerte offentlige kilder")
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    source = source_for_market(market)
    result["currency"] = source.get("currency", "")
    direct_attempts = [row for row in search_log if row.get("direct_primary_source_checked")]
    result["official_source"] = str((direct_attempts[0] if direct_attempts else {}).get("source") or source.get("name", ""))
    result["official_search_url"] = str((direct_attempts[0] if direct_attempts else {}).get("url") or source.get("search_url", ""))
    result["direct_primary_source_checked"] = bool(direct_attempts)
    if str(market or "") == "Brasil":
        result["official_source"] = "CVM – Valores Mobiliários Negociados e Detidos"
        result["official_search_url"] = "https://dados.cvm.gov.br/dataset/cia_aberta-doc-vlmo"

    # NewsAPI is only source discovery after a direct or structured attempt. It is
    # never presented as an official insider register.
    if not primary_only and result.get("coverage") not in {"AVAILABLE", "CHECKED_NO_EVENTS"} and market:
        discovery = discover_with_newsapi(ticker, company, market)
        discovery_status = str(discovery.get("status") or "")
        search_log.append({
            "source": discovery.get("source_label") or "NewsAPI-kildeoppdagelse",
            "source_type": "SECONDARY_SOURCE_DISCOVERY",
            "attempted": discovery_status not in {"NEWSAPI_NOT_CONFIGURED", "DAILY_QUOTA_EXCEEDED"},
            "status": {
                "DISCOVERY_FOUND": "DISCOVERY_ONLY", "NO_DISCOVERY": "SUCCESS_NO_RESULTS",
                "NEWSAPI_NOT_CONFIGURED": "NOT_CONFIGURED", "DISCOVERY_ERROR": "SOURCE_ERROR",
                "RATE_LIMITED": "RATE_LIMITED", "DAILY_QUOTA_EXCEEDED": "DAILY_QUOTA_EXCEEDED",
            }.get(discovery_status, "NOT_SEARCHED"),
            "results": len(discovery.get("articles") or []),
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "url": "", "requested_primary_source": discovery.get("official_source") or "",
            "direct_primary_source_checked": False,
            "error": str(discovery.get("error") or "")[:240],
        })
        result["source_discovery"] = discovery
        if discovery.get("articles"):
            result.update({
                "score": 50.0, "signal": "KILDER FUNNET", "coverage": "DISCOVERY_ONLY",
                "reason": f"{len(discovery['articles'])} mulig(e) kildemelding(er) funnet; transaksjonen må struktureres og verifiseres før scoring.",
            })
        elif discovery_status == "NEWSAPI_NOT_CONFIGURED":
            result.update({
                "signal": "KILDE IKKE KONFIGURERT", "coverage": "NOT_CONFIGURED",
                "reason": "NEWSAPI_KEY mangler; sekundær kildeoppdagelse ble ikke utført etter primærkildeforsøket.",
            })
        elif discovery_status in {"RATE_LIMITED", "DAILY_QUOTA_EXCEEDED"}:
            result.update({
                "signal": "KILDEKONTROLL DELVIS", "coverage": "PARTIAL_SOURCE_FAILURE",
                "reason": "Sekundær NewsAPI-kildeoppdagelse var begrenset etter direkte primærkildeforsøk.",
            })
        elif discovery_status == "DISCOVERY_ERROR":
            result.update({
                "signal": "KILDEKONTROLL DELVIS", "coverage": "PARTIAL_SOURCE_FAILURE",
                "reason": "Sekundær kildeoppdagelse feilet etter direkte primærkildeforsøk.",
            })
    result["search_log"] = search_log
    result["sources_checked"] = sum(1 for row in search_log if row.get("attempted"))
    result["verified_fact_count"] = sum(
        row.get("primary_source_verified") is True for row in (result.get("evidence") or []) if isinstance(row, Mapping)
    )
    result["structured_fact_count"] = len(result.get("evidence") or [])
    result["secondary_fact_count"] = sum(
        row.get("primary_source_verified") is not True for row in (result.get("evidence") or []) if isinstance(row, Mapping)
    )
    from evidence_contract import canonical_status, normalize_search_payload
    result["canonical_evidence_status"] = canonical_status(result, result.get("evidence") or [])
    result = normalize_search_payload(result, area="insider")
    _store_cached_result(ticker, result)
    return result


def enrich_rows(rows: Sequence[Mapping[str, Any]], force_refresh: bool = False, progress_callback: Any | None = None,
                *, primary_only: bool = False) -> list[dict[str, Any]]:
    source_rows = [dict(row) for row in rows]
    total = len(source_rows)

    def enrich_one(index: int, row: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        clean = dict(row)
        insider = fetch_insider_intelligence(
            str(clean.get("ticker") or ""), force_refresh=force_refresh,
            market=str(clean.get("market") or ""),
            company=str(clean.get("longName") or clean.get("shortName") or clean.get("name") or ""),
            primary_only=primary_only,
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
