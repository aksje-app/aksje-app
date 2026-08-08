"""Shared, persistent NewsAPI budget and request client.

Every NewsAPI consumer uses this module.  The local daily budget protects the
Developer plan, the cache prevents Streamlit reruns from spending requests, and
the health snapshot is safe to expose in reports without leaking API keys or
raw request URLs.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from storage_architecture import runtime_data_path


STATE_PATH = runtime_data_path("newsapi", "budget.json")
CACHE_PATH = runtime_data_path("newsapi", "shared_cache.json")
_LOCK = threading.RLock()
_LAST_REQUEST = 0.0
_REPORT_BUDGET = threading.local()


class NewsApiError(RuntimeError):
    status = "SOURCE_ERROR"


class NewsApiRateLimited(NewsApiError):
    status = "RATE_LIMITED"

    def __init__(self, retry_after: float = 0.0):
        super().__init__("HTTP 429 – NewsAPI-kapasitetsgrense")
        self.retry_after = max(0.0, float(retry_after or 0.0))


class NewsApiDailyQuotaExceeded(NewsApiError):
    status = "DAILY_QUOTA_EXCEEDED"

    def __init__(self, remaining: int = 0):
        super().__init__("NewsAPI-døgnbudsjettet er brukt; øvrige kilder benyttes")
        self.remaining = max(0, int(remaining or 0))


class NewsApiReportQuotaExceeded(NewsApiDailyQuotaExceeded):
    status = "REPORT_QUOTA_EXCEEDED"

    def __init__(self, remaining: int = 0):
        NewsApiError.__init__(self, "NewsAPI-budsjettet for denne rapporten er brukt; øvrige kilder benyttes")
        self.remaining = max(0, int(remaining or 0))


def begin_report_budget(max_requests: int, *, label: str = "REPORT") -> None:
    """Start a thread-local hard request budget for one report execution."""
    _REPORT_BUDGET.active = True
    _REPORT_BUDGET.limit = max(0, int(max_requests or 0))
    _REPORT_BUDGET.used = 0
    _REPORT_BUDGET.cache_hits = 0
    _REPORT_BUDGET.label = str(label or "REPORT")


def report_budget_snapshot() -> dict[str, Any]:
    active = bool(getattr(_REPORT_BUDGET, "active", False))
    limit = int(getattr(_REPORT_BUDGET, "limit", 0) or 0)
    used = int(getattr(_REPORT_BUDGET, "used", 0) or 0)
    return {
        "active": active,
        "label": str(getattr(_REPORT_BUDGET, "label", "") or ""),
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "cache_hits": int(getattr(_REPORT_BUDGET, "cache_hits", 0) or 0),
    }


def end_report_budget() -> dict[str, Any]:
    snapshot = report_budget_snapshot()
    _REPORT_BUDGET.active = False
    return snapshot


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def configured_budget() -> int:
    """Return the operational budget; ten Developer requests remain reserved."""
    raw = os.getenv("NEWSAPI_DAILY_BUDGET", "50")
    try:
        value = int(raw or 50)
    except (TypeError, ValueError):
        value = 50
    return max(0, min(50, value))


def _state() -> dict[str, Any]:
    today = _now().date().isoformat()
    state = _read_json(STATE_PATH, {})
    if not isinstance(state, Mapping) or str(state.get("utc_date") or "") != today:
        state = {
            "utc_date": today,
            "requests": 0,
            "by_purpose": {},
            "cache_hits": 0,
            "cache_misses": 0,
            "last_status": "NOT_USED",
            "last_checked_at": "",
            "last_success_at": "",
        }
    return dict(state)


def _save_state(state: Mapping[str, Any]) -> None:
    _write_json(STATE_PATH, dict(state))


def _cache_key(query: str, params: Mapping[str, Any], purpose: str) -> str:
    payload = json.dumps(
        {"query": query, "params": dict(params), "purpose": purpose},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cached(key: str, ttl_seconds: int) -> list[dict[str, Any]] | None:
    cache = _read_json(CACHE_PATH, {})
    item = cache.get(key) if isinstance(cache, Mapping) else None
    if not isinstance(item, Mapping):
        return None
    if time.time() - float(item.get("cached_at") or 0.0) >= max(60, int(ttl_seconds)):
        return None
    rows = item.get("articles")
    return [dict(row) for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else None


def _store_cache(key: str, rows: list[dict[str, Any]]) -> None:
    cache = _read_json(CACHE_PATH, {})
    cache = dict(cache) if isinstance(cache, Mapping) else {}
    cache[key] = {"cached_at": time.time(), "articles": rows}
    if len(cache) > 500:
        ordered = sorted(cache.items(), key=lambda item: float((item[1] or {}).get("cached_at") or 0.0), reverse=True)
        cache = dict(ordered[:400])
    _write_json(CACHE_PATH, cache)


def _record(state: dict[str, Any], purpose: str, status: str, *, spent: bool = False) -> None:
    if spent:
        state["requests"] = int(state.get("requests") or 0) + 1
        by_purpose = dict(state.get("by_purpose") or {})
        by_purpose[purpose] = int(by_purpose.get(purpose) or 0) + 1
        state["by_purpose"] = by_purpose
    state["last_status"] = status
    state["last_checked_at"] = _now().isoformat(timespec="seconds")
    if status == "SUCCESS":
        state["last_success_at"] = state["last_checked_at"]
    _save_state(state)


def fetch_articles(
    query: str,
    *,
    purpose: str,
    limit: int = 30,
    from_date: str = "",
    domains: list[str] | None = None,
    cache_ttl_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch NewsAPI articles through one cache, rate gate and daily budget."""
    key = os.getenv("NEWSAPI_KEY", "").strip()
    if not key:
        raise NewsApiError("NEWSAPI_KEY er ikke konfigurert")
    ttl = int(cache_ttl_seconds or int(os.getenv("NEWSAPI_SHARED_CACHE_TTL_HOURS", "12") or 12) * 3600)
    request_params: dict[str, Any] = {
        "sortBy": "publishedAt",
        "pageSize": min(100, max(1, int(limit))),
    }
    if from_date:
        request_params["from"] = str(from_date)
    if domains:
        request_params["domains"] = ",".join(sorted({str(domain) for domain in domains if domain}))
    cache_id = _cache_key(query, request_params, purpose)
    with _LOCK:
        state = _state()
        cached = _cached(cache_id, ttl)
        if cached is not None:
            if bool(getattr(_REPORT_BUDGET, "active", False)):
                _REPORT_BUDGET.cache_hits = int(getattr(_REPORT_BUDGET, "cache_hits", 0) or 0) + 1
            state["cache_hits"] = int(state.get("cache_hits") or 0) + 1
            _record(state, purpose, "CACHE_HIT")
            return cached
        state["cache_misses"] = int(state.get("cache_misses") or 0) + 1
        budget = configured_budget()
        used = int(state.get("requests") or 0)
        if bool(getattr(_REPORT_BUDGET, "active", False)):
            report_limit = int(getattr(_REPORT_BUDGET, "limit", 0) or 0)
            report_used = int(getattr(_REPORT_BUDGET, "used", 0) or 0)
            if report_limit <= 0 or report_used >= report_limit:
                _record(state, purpose, "REPORT_QUOTA_EXCEEDED")
                raise NewsApiReportQuotaExceeded(max(0, report_limit - report_used))
        if budget <= 0 or used >= budget:
            _record(state, purpose, "DAILY_QUOTA_EXCEEDED")
            raise NewsApiDailyQuotaExceeded(max(0, budget - used))

        import requests

        global _LAST_REQUEST
        minimum_interval = max(0.1, float(os.getenv("NEWSAPI_MIN_INTERVAL_SECONDS", "1.0") or 1.0))
        wait = max(0.0, minimum_interval - (time.monotonic() - _LAST_REQUEST))
        if wait:
            time.sleep(wait)
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, **request_params},
            headers={"X-Api-Key": key},
            timeout=12,
        )
        _LAST_REQUEST = time.monotonic()
        status_code = int(getattr(response, "status_code", 200) or 200)
        response_headers = getattr(response, "headers", {}) or {}
        _record(state, purpose, "HTTP_" + str(status_code), spent=True)
        if bool(getattr(_REPORT_BUDGET, "active", False)):
            _REPORT_BUDGET.used = int(getattr(_REPORT_BUDGET, "used", 0) or 0) + 1
        if status_code == 429:
            retry_after = float(response_headers.get("Retry-After") or 0.0)
            state = _state()
            _record(state, purpose, "RATE_LIMITED")
            raise NewsApiRateLimited(retry_after)
        response.raise_for_status()
        payload = response.json()
        raw_rows = payload.get("articles") if isinstance(payload, Mapping) else []
        rows: list[dict[str, Any]] = []
        for raw in raw_rows or []:
            if not isinstance(raw, Mapping):
                continue
            rows.append({
                "title": str(raw.get("title") or ""),
                "summary": str(raw.get("description") or ""),
                "url": str(raw.get("url") or ""),
                "publisher": str((raw.get("source") or {}).get("name") or ""),
                "published_at": str(raw.get("publishedAt") or ""),
            })
        _store_cache(cache_id, rows)
        state = _state()
        _record(state, purpose, "SUCCESS")
        return rows


def health_snapshot() -> dict[str, Any]:
    """Return non-secret source health and the current UTC budget window."""
    with _LOCK:
        state = _state()
    budget = configured_budget()
    used = int(state.get("requests") or 0)
    tomorrow = _now().date() + timedelta(days=1)
    return {
        "source": "NewsAPI",
        "configured": bool(os.getenv("NEWSAPI_KEY", "").strip()),
        "plan": str(os.getenv("NEWSAPI_PLAN", "Developer") or "Developer"),
        "daily_budget": budget,
        "used_today": used,
        "remaining_today": max(0, budget - used),
        "cache_hits": int(state.get("cache_hits") or 0),
        "cache_misses": int(state.get("cache_misses") or 0),
        "last_status": str(state.get("last_status") or "NOT_USED"),
        "last_checked_at": str(state.get("last_checked_at") or ""),
        "last_success_at": str(state.get("last_success_at") or ""),
        "budget_window": "UTC",
        "next_local_budget_window": f"{tomorrow.isoformat()}T00:00:00Z",
        "developer_delay_hours": 24 if str(os.getenv("NEWSAPI_PLAN", "Developer")).casefold() == "developer" else 0,
        "reserved_requests": 10,
        "report_budget": report_budget_snapshot(),
    }


__all__ = [
    "NewsApiDailyQuotaExceeded",
    "NewsApiReportQuotaExceeded",
    "NewsApiError",
    "NewsApiRateLimited",
    "configured_budget",
    "begin_report_budget",
    "end_report_budget",
    "fetch_articles",
    "health_snapshot",
    "report_budget_snapshot",
]
