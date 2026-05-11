import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
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


def _cache_key(query, limit):
    safe = str(query or "").strip().lower()
    return f"{safe}|{int(limit or 0)}"


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
    except Exception:
        pass


def _fresh(entry, ttl_hours):
    try:
        ts = float((entry or {}).get("ts") or 0)
        return (time.time() - ts) <= max(60, float(ttl_hours) * 3600)
    except Exception:
        return False


def newsapi_status():
    cache = _load_cache()
    return {
        "has_key": bool(NEWSAPI_KEY and not NEWSAPI_KEY.startswith("din_")),
        "auto_calls_allowed": bool(NEWS_ALLOW_AUTO_CALLS),
        "cache_ttl_hours": NEWS_CACHE_TTL_HOURS,
        "cache_entries": len(cache),
        "cache_path": str(NEWS_CACHE_PATH),
    }


def get_news(query, limit=8, *, source="manual", force=False, ttl_hours=None):
    """Fetch news with a cache and an automatic-call guard.

    v18.5.31: NewsAPI should not be consumed silently by ordinary Streamlit
    reruns. Manual button clicks may fetch live data. Automatic scoring/event
    risk calls use cache by default and only hit NewsAPI when
    NEWSAPI_ALLOW_AUTO_CALLS=true.
    """
    ttl = NEWS_CACHE_TTL_HOURS if ttl_hours is None else ttl_hours
    query = str(query or "").strip()
    key = _cache_key(query, limit)
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

    if not NEWSAPI_KEY or NEWSAPI_KEY.startswith("din_"):
        return [], "Mangler NewsAPI-nøkkel. Legg NEWSAPI_KEY i .env"

    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": limit,
                "apiKey": NEWSAPI_KEY,
            },
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
            return list(cached.get("articles") or []), f"Bruker cache etter NewsAPI-feil: {e}"
        return [], str(e)


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
