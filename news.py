import os
import requests
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

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

def get_news(query, limit=6):
    """
    Henter nyheter bare når app.py ber om det.
    Bruker NEWSAPI_KEY fra .env lokalt eller Environment Variables på Render.
    """
    if not NEWSAPI_KEY or NEWSAPI_KEY.startswith("din_"):
        return [], "Mangler NEWSAPI_KEY. Legg den i .env lokalt eller Render Environment Variables."

    try:
        response = requests.get(
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

        data = response.json()

        if response.status_code != 200:
            return [], data.get("message", f"NewsAPI-feil: {response.status_code}")

        articles = []
        for article in data.get("articles", [])[:limit]:
            articles.append({
                "title": article.get("title") or "",
                "description": article.get("description") or "",
                "source": (article.get("source") or {}).get("name", ""),
                "url": article.get("url", ""),
                "published": (article.get("publishedAt") or "")[:10],
            })

        return articles, None

    except Exception as e:
        return [], str(e)

def simple_finance_sentiment(articles):
    if not articles:
        return 0.50

    scores = []

    for article in articles:
        text = f"{article.get('title','')} {article.get('description','')}".lower()

        positives = sum(1 for word in POSITIVE_WORDS if word in text)
        negatives = sum(1 for word in NEGATIVE_WORDS if word in text)

        score = max(0.0, min(1.0, 0.5 + (positives - negatives) * 0.10))
        scores.append(score)

    return round(sum(scores) / len(scores), 3)
