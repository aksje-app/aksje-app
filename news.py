import os
import requests
from dotenv import load_dotenv

load_dotenv()
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

POSITIVE_WORDS = [
    "beat", "beats", "growth", "profit", "surge", "upgrade", "strong", "record",
    "bullish", "launch", "partnership", "approval", "raises", "outperform", "buy",
    "contract", "order", "expansion", "dividend", "positive"
]
NEGATIVE_WORDS = [
    "miss", "falls", "drop", "lawsuit", "cut", "downgrade", "weak", "loss",
    "bearish", "investigation", "recall", "warning", "underperform", "sell",
    "decline", "debt", "fine", "negative"
]

def get_news(query, limit=8):
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
        return items, None
    except Exception as e:
        return [], str(e)

def simple_finance_sentiment(articles):
    if not articles:
        return 0.50
    scores = []
    for a in articles:
        text = f"{a.get('title','')} {a.get('description','')}".lower()
        pos = sum(1 for w in POSITIVE_WORDS if w in text)
        neg = sum(1 for w in NEGATIVE_WORDS if w in text)
        scores.append(max(0.0, min(1.0, 0.5 + (pos - neg) * 0.12)))
    return round(sum(scores) / len(scores), 3)
