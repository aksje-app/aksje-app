"""News & Sentiment Intelligence Engine v18.7.2.

Collects recent public company news, deduplicates repeated stories and calculates a
transparent 0-100 score. Missing coverage is neutral and never treated as positive
or negative evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse
import hashlib
import json
import math
import os
import re
import time

from storage_architecture import runtime_data_path

VERSION = "v18.7.2"
CACHE_PATH = runtime_data_path("news_intelligence") / "cache.json"
CACHE_TTL_SECONDS = int(os.getenv("NEWS_INTELLIGENCE_CACHE_TTL_HOURS", "6") or 6) * 3600
DEFAULT_LOOKBACK_DAYS = int(os.getenv("NEWS_INTELLIGENCE_LOOKBACK_DAYS", "14") or 14)

POSITIVE_TERMS = {
    "beat": 1.4, "beats": 1.4, "record": 1.1, "growth": 0.8, "profit": 0.8,
    "upgrade": 1.2, "outperform": 1.0, "approval": 1.2, "contract": 0.9,
    "partnership": 0.7, "raises guidance": 1.5, "strong demand": 1.0,
    "buyback": 0.8, "dividend increase": 0.9, "acquisition": 0.5,
    "resultatvekst": 1.0, "oppjusterer": 1.3, "kontrakt": 0.9, "godkjenning": 1.2,
}
NEGATIVE_TERMS = {
    "miss": 1.4, "misses": 1.4, "warning": 1.4, "downgrade": 1.2,
    "investigation": 1.2, "lawsuit": 1.0, "recall": 1.1, "fine": 0.9,
    "cuts guidance": 1.5, "weak demand": 1.0, "default": 1.5, "bankruptcy": 2.0,
    "data breach": 1.2, "fraud": 1.7, "layoffs": 0.7, "loss": 0.7,
    "resultatvarsel": 1.5, "nedjusterer": 1.3, "etterforskning": 1.2, "søksmål": 1.0,
}
HIGH_IMPACT_TERMS = (
    "earnings", "guidance", "acquisition", "merger", "takeover", "approval",
    "investigation", "lawsuit", "bankruptcy", "resultat", "oppkjøp", "fusjon",
    "resultatvarsel", "godkjenning", "etterforskning",
)
SOURCE_QUALITY = {
    "reuters.com": 1.00, "apnews.com": 0.95, "bloomberg.com": 0.95,
    "ft.com": 0.93, "wsj.com": 0.93, "cnbc.com": 0.85, "marketwatch.com": 0.80,
    "finance.yahoo.com": 0.76, "globenewswire.com": 0.72, "businesswire.com": 0.72,
    "nasdaq.com": 0.80, "sec.gov": 1.00, "newsweb.no": 0.95,
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _load_cache() -> dict[str, Any]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    except Exception:
        return {}


def _save_cache(cache: Mapping[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(dict(cache), ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc)
    except Exception:
        return None


def _domain(url: str) -> str:
    try:
        host = urlparse(str(url or "")).netloc.lower().removeprefix("www.")
        return host
    except Exception:
        return ""


def _source_quality(url: str, publisher: str = "") -> float:
    domain = _domain(url)
    for known, quality in SOURCE_QUALITY.items():
        if domain == known or domain.endswith("." + known):
            return quality
    text = str(publisher or "").lower()
    if any(x in text for x in ("reuters", "associated press", "bloomberg", "financial times")):
        return 0.93
    return 0.62


def _canonical_title(title: str) -> str:
    words = re.findall(r"[a-z0-9æøå]+", str(title or "").lower())
    stop = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "at", "from"}
    return " ".join(x for x in words if x not in stop)[:180]


def _item_from_yfinance(raw: Mapping[str, Any]) -> dict[str, Any]:
    content = raw.get("content") if isinstance(raw.get("content"), Mapping) else raw
    provider = content.get("provider") if isinstance(content.get("provider"), Mapping) else {}
    click = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), Mapping) else {}
    canonical = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), Mapping) else {}
    return {
        "title": content.get("title") or raw.get("title") or "",
        "summary": content.get("summary") or content.get("description") or raw.get("summary") or "",
        "url": click.get("url") or canonical.get("url") or content.get("link") or raw.get("link") or "",
        "publisher": provider.get("displayName") or raw.get("publisher") or "",
        "published_at": content.get("pubDate") or raw.get("providerPublishTime") or raw.get("published_at"),
    }


def _fetch_yfinance(ticker: str) -> list[dict[str, Any]]:
    import yfinance as yf
    raw = getattr(yf.Ticker(ticker), "news", None) or []
    return [_item_from_yfinance(x) for x in raw if isinstance(x, Mapping)]


def _fetch_newsapi(query: str, limit: int = 30) -> list[dict[str, Any]]:
    key = os.getenv("NEWSAPI_KEY", "").strip()
    if not key:
        return []
    import requests
    response = requests.get(
        "https://newsapi.org/v2/everything",
        params={"q": query, "sortBy": "publishedAt", "pageSize": min(100, limit), "language": "en", "apiKey": key},
        timeout=12,
    )
    response.raise_for_status()
    rows = response.json().get("articles") or []
    return [{
        "title": x.get("title") or "", "summary": x.get("description") or "",
        "url": x.get("url") or "", "publisher": (x.get("source") or {}).get("name") or "",
        "published_at": x.get("publishedAt"),
    } for x in rows if isinstance(x, Mapping)]


def normalize_articles(rows: Sequence[Mapping[str, Any]], lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    unique: dict[str, dict[str, Any]] = {}
    for raw in rows:
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        dt = _parse_date(raw.get("published_at") or raw.get("publishedAt") or raw.get("providerPublishTime"))
        age_hours = max(0.0, (now - dt).total_seconds() / 3600.0) if dt else lookback_days * 24.0
        if age_hours > lookback_days * 24.0:
            continue
        url = str(raw.get("url") or raw.get("link") or "")
        key = hashlib.sha1(_canonical_title(title).encode("utf-8")).hexdigest()[:16]
        item = {
            "title": title,
            "summary": str(raw.get("summary") or raw.get("description") or "").strip(),
            "url": url,
            "publisher": str(raw.get("publisher") or raw.get("source") or "").strip(),
            "published_at": dt.isoformat() if dt else "",
            "age_hours": round(age_hours, 1),
            "source_quality": round(_source_quality(url, str(raw.get("publisher") or "")), 2),
        }
        previous = unique.get(key)
        if not previous or item["source_quality"] > previous["source_quality"]:
            unique[key] = item
    return sorted(unique.values(), key=lambda x: (x["age_hours"], -x["source_quality"]))


def score_articles(ticker: str, rows: Sequence[Mapping[str, Any]], lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
    articles = normalize_articles(rows, lookback_days)
    if not articles:
        return {
            "ticker": ticker, "score": 50.0, "sentiment": "INGEN DATA", "coverage": "MISSING",
            "article_count": 0, "positive_count": 0, "negative_count": 0, "high_impact_count": 0,
            "events": [], "summary": "Ingen relevante nyheter funnet i tilgjengelige kilder.",
        }
    weighted_total = 0.0
    total_weight = 0.0
    positive_count = negative_count = high_impact_count = 0
    topics: dict[str, int] = {}
    enriched: list[dict[str, Any]] = []
    for item in articles:
        text = f"{item['title']} {item['summary']}".lower()
        pos = sum(weight for term, weight in POSITIVE_TERMS.items() if term in text)
        neg = sum(weight for term, weight in NEGATIVE_TERMS.items() if term in text)
        raw_sentiment = max(-1.0, min(1.0, (pos - neg) / max(1.0, pos + neg)))
        if raw_sentiment > 0.15: positive_count += 1
        elif raw_sentiment < -0.15: negative_count += 1
        impact = 1.35 if any(term in text for term in HIGH_IMPACT_TERMS) else 1.0
        if impact > 1.0: high_impact_count += 1
        recency = max(0.18, 1.0 - _f(item["age_hours"]) / max(24.0, lookback_days * 24.0))
        weight = recency * _f(item["source_quality"], 0.62) * impact
        weighted_total += raw_sentiment * weight
        total_weight += weight
        for topic in HIGH_IMPACT_TERMS:
            if topic in text:
                topics[topic] = topics.get(topic, 0) + 1
        copy = dict(item)
        copy["sentiment_score"] = round(raw_sentiment, 3)
        copy["impact"] = "HIGH" if impact > 1.0 else "NORMAL"
        enriched.append(copy)
    direction = weighted_total / max(0.01, total_weight)
    breadth = min(8.0, math.log1p(len(articles)) * 2.5)
    score = max(0.0, min(100.0, 50.0 + direction * 38.0 + (breadth if direction > 0.12 else -breadth if direction < -0.12 else 0.0)))
    sentiment = "STERKT POSITIV" if score >= 78 else "POSITIV" if score >= 62 else "NØYTRAL" if score >= 42 else "NEGATIV" if score >= 25 else "STERKT NEGATIV"
    top_topics = [x[0] for x in sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
    balance = "overveiende positivt" if score >= 62 else "overveiende negativt" if score < 42 else "blandet eller nøytralt"
    summary = f"Nyhetsbildet er {balance}. {len(articles)} unike saker, hvorav {high_impact_count} vurderes som høy påvirkning."
    if top_topics:
        summary += " Viktigste tema: " + ", ".join(top_topics) + "."
    return {
        "ticker": ticker, "score": round(score, 2), "sentiment": sentiment, "coverage": "AVAILABLE",
        "article_count": len(articles), "positive_count": positive_count, "negative_count": negative_count,
        "high_impact_count": high_impact_count, "topics": top_topics, "events": enriched[:10], "summary": summary,
    }


def fetch_news_intelligence(ticker: str, company_name: str = "", force_refresh: bool = False, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
    ticker = str(ticker or "").upper().strip()
    key = f"{ticker}|{company_name.strip().lower()}|{lookback_days}"
    cache = _load_cache()
    cached = cache.get(key)
    if cached and not force_refresh and time.time() - _f(cached.get("cached_at")) < CACHE_TTL_SECONDS:
        return dict(cached.get("result") or {})
    sources: list[str] = []
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        yf_rows = _fetch_yfinance(ticker)
        if yf_rows:
            rows.extend(yf_rows); sources.append("yfinance")
    except Exception as exc:
        errors.append(f"yfinance: {exc}")
    try:
        query = company_name.strip() or ticker
        api_rows = _fetch_newsapi(query)
        if api_rows:
            rows.extend(api_rows); sources.append("NewsAPI")
    except Exception as exc:
        errors.append(f"NewsAPI: {exc}")
    result = score_articles(ticker, rows, lookback_days)
    result["source"] = ", ".join(sources) if sources else "unavailable"
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    result["errors"] = errors
    if not sources and errors:
        result["coverage"] = "ERROR"
        result["sentiment"] = "KILDEFEIL"
        result["summary"] = "Nyhetskildene kunne ikke hentes. Nøytral score brukes."
    cache[key] = {"cached_at": time.time(), "result": result}
    _save_cache(cache)
    return result


def enrich_rows(rows: Sequence[Mapping[str, Any]], force_refresh: bool = False) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        result = fetch_news_intelligence(
            str(row.get("ticker") or row.get("symbol") or ""),
            str(row.get("name") or row.get("longName") or row.get("shortName") or ""),
            force_refresh=force_refresh,
        )
        row["news_intelligence"] = result
        row["news_score"] = result.get("score", 50.0)
        row["news_sentiment"] = result.get("sentiment", "INGEN DATA")
        row["news_summary"] = result.get("summary", "")
        enriched.append(row)
    return enriched
