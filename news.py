import logging
import json
import os
import time
import datetime as dt
from pathlib import Path

import requests
from runtime_env import data_source_env_status, env_value, load_app_env, redact_secrets

load_app_env()
NEWSAPI_KEY = env_value("NEWSAPI_KEY")
NEWS_CACHE_TTL_HOURS = int(os.getenv("NEWSAPI_CACHE_TTL_HOURS", "24") or 24)
NEWS_ALLOW_AUTO_CALLS = str(os.getenv("NEWSAPI_ALLOW_AUTO_CALLS", "false")).lower() in {"1", "true", "yes", "on"}
NEWS_CACHE_PATH = Path(os.getenv("NEWSAPI_CACHE_PATH", "data/services/newsapi_cache.json"))

POSITIVE_WORDS = [
    "beat", "beats", "growth", "profit", "surge", "upgrade", "strong", "record",
    "bullish", "launch", "partnership", "approval", "raises", "outperform", "buy",
    "contract", "order", "expansion", "dividend", "positive", "guidance", "demand"
]
NEGATIVE_WORDS = [
    "miss", "falls", "drop", "lawsuit", "cut", "downgrade", "weak", "loss",
    "bearish", "investigation", "recall", "warning", "underperform", "sell",
    "decline", "debt", "fine", "negative", "layoffs", "slump"
]


def _cache_key(query, limit, language=None, domains=None):
    safe = str(query or "").strip().lower()
    return f"{safe}|{int(limit or 0)}|lang={language or '*'}|domains={domains or '*'}"


def _load_cache():
    try:
        if NEWS_CACHE_PATH.exists():
            return json.loads(NEWS_CACHE_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return {}


def _save_cache(cache):
    try:
        NEWS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        NEWS_CACHE_PATH.write_text(json.dumps(cache or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


def _fresh(entry, ttl_hours):
    try:
        ts = float((entry or {}).get("ts") or 0)
        return (time.time() - ts) <= max(60, float(ttl_hours) * 3600)
    except Exception:
        return False


def newsapi_status():
    cache = _load_cache()
    env_status = data_source_env_status()
    return {
        "has_key": bool(env_status.get("newsapi_key")),
        "auto_calls_allowed": bool(env_status.get("newsapi_auto_calls")),
        "env_loaded": bool(env_status.get("env_loaded")),
        "env_sources": list(env_status.get("env_sources") or []),
        "cache_ttl_hours": NEWS_CACHE_TTL_HOURS,
        "cache_entries": len(cache),
        "cache_path": str(NEWS_CACHE_PATH),
    }


def get_news(query, limit=8, *, source="manual", force=False, ttl_hours=None, days_back=None, language="en", domains=None):
    """Fetch news with a cache and an automatic-call guard.

    v18.5.31: NewsAPI should not be consumed silently by ordinary Streamlit
    reruns. Manual button clicks may fetch live data. Automatic scoring/event
    risk calls use cache by default and only hit NewsAPI when
    NEWSAPI_ALLOW_AUTO_CALLS=true.
    """
    ttl = NEWS_CACHE_TTL_HOURS if ttl_hours is None else ttl_hours
    query = str(query or "").strip()
    key = _cache_key(query, limit, language=language, domains=domains)
    cache = _load_cache()
    cached = cache.get(key) or {}
    if cached and _fresh(cached, ttl) and not force:
        return list(cached.get("articles") or []), None

    source = str(source or "manual").lower()
    manual = source in {"manual", "button", "user"}
    if not manual and not NEWS_ALLOW_AUTO_CALLS:
        if cached.get("articles"):
            return list(cached.get("articles") or []), "Bruker cache: automatisk NewsAPI-kall er slått av."
        return [], "NewsAPI automatisk bruk er slått av. Trykk nyhetsknappen eller sett NEWSAPI_ALLOW_AUTO_CALLS=true."

    api_key = env_value("NEWSAPI_KEY")
    if not api_key or api_key.startswith("din_"):
        return [], "Mangler NewsAPI-nøkkel. Legg NEWSAPI_KEY i .env"

    try:
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": limit,
            "apiKey": api_key,
        }
        if language:
            params["language"] = language
        if domains:
            params["domains"] = str(domains)
        if days_back:
            try:
                from_date = dt.date.today() - dt.timedelta(days=max(1, int(days_back)))
                params["from"] = from_date.isoformat()
            except Exception:
                pass
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params=params,
            timeout=12,
        )
        data = r.json()
        if r.status_code != 200:
            return [], data.get("message", f"NewsAPI-feil: {r.status_code}")

        items = []
        for a in data.get("articles", [])[:limit]:
            items.append({
                "title": a.get("title") or "",
                "description": a.get("description") or "",
                "source": (a.get("source") or {}).get("name", ""),
                "url": a.get("url", ""),
                "published": (a.get("publishedAt") or "")[:10],
            })
        cache[key] = {"ts": time.time(), "articles": items, "source": source}
        _save_cache(cache)
        return items, None
    except Exception as e:
        if cached.get("articles"):
            return list(cached.get("articles") or []), redact_secrets(f"Bruker cache etter NewsAPI-feil: {e}")
        return [], redact_secrets(str(e))


def simple_finance_sentiment(articles):
    if not articles:
        return 0.50
    scores = []
    for a in articles:
        text = f"{a.get('title','')} {a.get('description','')}".lower()
        pos = sum(1 for word in POSITIVE_WORDS if word in text)
        neg = sum(1 for word in NEGATIVE_WORDS if word in text)
        scores.append(max(0.0, min(1.0, 0.5 + (pos - neg) * 0.10)))
    return round(sum(scores) / len(scores), 3)
