import os
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

DB_PATH = Path("news_cache.db")
CACHE_HOURS = 12

POSITIVE_WORDS = [
    "beat", "beats", "growth", "profit", "surge", "upgrade", "strong", "record",
    "bullish", "launch", "partnership", "approval", "raises", "outperform", "buy",
    "contract", "order", "expansion", "dividend", "positive", "guidance", "demand",
    "revenue growth", "earnings beat", "new deal", "wins", "higher"
]

NEGATIVE_WORDS = [
    "miss", "falls", "drop", "lawsuit", "cut", "downgrade", "weak", "loss",
    "bearish", "investigation", "recall", "warning", "underperform", "sell",
    "decline", "debt", "fine", "negative", "layoffs", "slump", "probe",
    "earnings miss", "lower guidance", "fraud", "concern"
]


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_cache (
            query TEXT PRIMARY KEY,
            source TEXT,
            fetched_at TEXT,
            articles_json TEXT
        )
        """
    )
    return conn


def _load_cache(query):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT source, fetched_at, articles_json FROM news_cache WHERE query = ?", (query,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None, None

    source, fetched_at, articles_json = row
    fetched = datetime.fromisoformat(fetched_at)
    if datetime.utcnow() - fetched > timedelta(hours=CACHE_HOURS):
        return None, None

    try:
        return json.loads(articles_json), source
    except Exception:
        return None, None


def _save_cache(query, articles, source):
    conn = _connect()
    conn.execute(
        """
        INSERT OR REPLACE INTO news_cache (query, source, fetched_at, articles_json)
        VALUES (?, ?, ?, ?)
        """,
        (query, source, datetime.utcnow().isoformat(), json.dumps(articles)),
    )
    conn.commit()
    conn.close()


def _classify_article(title, description=""):
    text = f"{title} {description}".lower()

    pos = sum(1 for w in POSITIVE_WORDS if w in text)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text)

    if pos > neg:
        return "bullish", f"Fant flere positive signalord ({pos}) enn negative ({neg})."
    if neg > pos:
        return "bearish", f"Fant flere negative signalord ({neg}) enn positive ({pos})."
    return "neutral", "Ingen tydelig bullish/bearish ordvekt."


def _add_ai_filter(articles):
    out = []
    for a in articles:
        label, reason = _classify_article(a.get("title", ""), a.get("description", ""))
        item = dict(a)
        item["sentiment_label"] = label
        item["sentiment_reason"] = reason
        out.append(item)
    return out


def _newsapi(query, limit=8):
    if not NEWSAPI_KEY or NEWSAPI_KEY.startswith("din_"):
        return [], "Mangler NewsAPI-nøkkel."

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

    if r.status_code != 200 or data.get("status") != "ok":
        return [], data.get("message", f"NewsAPI-feil: {r.status_code}")

    articles = []
    for a in data.get("articles", [])[:limit]:
        articles.append({
            "title": a.get("title") or "",
            "description": a.get("description") or "",
            "source": (a.get("source") or {}).get("name", "NewsAPI"),
            "url": a.get("url", ""),
            "published": (a.get("publishedAt") or "")[:10],
        })
    return articles, None


def _finnhub_news(query, limit=8):
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("din_"):
        return [], "Mangler Finnhub API-nøkkel."

    # Finnhub bruker symbol for company-news. Fungerer best på amerikanske tickere.
    symbol = query.upper().replace(".OL", "")
    to_date = datetime.utcnow().date()
    from_date = to_date - timedelta(days=21)

    r = requests.get(
        "https://finnhub.io/api/v1/company-news",
        params={
            "symbol": symbol,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "token": FINNHUB_API_KEY,
        },
        timeout=12,
    )

    if r.status_code != 200:
        return [], f"Finnhub-feil: {r.status_code}"

    data = r.json()
    if not isinstance(data, list):
        return [], "Uventet Finnhub-respons."

    articles = []
    for a in data[:limit]:
        dt = ""
        if a.get("datetime"):
            try:
                dt = datetime.utcfromtimestamp(a["datetime"]).date().isoformat()
            except Exception:
                dt = ""
        articles.append({
            "title": a.get("headline") or "",
            "description": a.get("summary") or "",
            "source": a.get("source") or "Finnhub",
            "url": a.get("url") or "",
            "published": dt,
        })
    return articles, None


def get_smart_news(query, limit=8, force_refresh=False):
    """
    Returnerer (articles, error, source)
    1. Sjekker lokal SQLite-cache
    2. Prøver NewsAPI
    3. Prøver Finnhub som backup
    4. AI-ish bullish/bearish-filter på artiklene
    """
    clean_query = query.strip().upper()

    if not force_refresh:
        cached, source = _load_cache(clean_query)
        if cached:
            return cached, None, f"{source} cache"

    errors = []

    try:
        articles, error = _newsapi(clean_query, limit=limit)
        if articles:
            articles = _add_ai_filter(articles)
            _save_cache(clean_query, articles, "NewsAPI")
            return articles, None, "NewsAPI"
        if error:
            errors.append(error)
    except Exception as e:
        errors.append(f"NewsAPI exception: {e}")

    try:
        articles, error = _finnhub_news(clean_query, limit=limit)
        if articles:
            articles = _add_ai_filter(articles)
            _save_cache(clean_query, articles, "Finnhub")
            return articles, None, "Finnhub"
        if error:
            errors.append(error)
    except Exception as e:
        errors.append(f"Finnhub exception: {e}")

    return [], " | ".join(errors) if errors else "Fant ingen nyheter.", "none"


def analyze_news_sentiment(articles):
    bullish = sum(1 for a in articles if a.get("sentiment_label") == "bullish")
    bearish = sum(1 for a in articles if a.get("sentiment_label") == "bearish")
    neutral = sum(1 for a in articles if a.get("sentiment_label") == "neutral")
    total = max(len(articles), 1)

    score = round((bullish + neutral * 0.5) / total, 3)

    return {
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "score": score,
    }
