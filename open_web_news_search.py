from __future__ import annotations

import json
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_RSS_ENDPOINT = "https://news.google.com/rss/search"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _timespan(days_back: int | None) -> str:
    days = max(1, min(int(days_back or 31), 90))
    return f"{days}d"


def _domain_allowed(article: Mapping[str, Any], domains: Sequence[str] | None) -> bool:
    # Domains are used as search diagnostics elsewhere. GDELT stays broad so
    # local financial sources outside our hand-picked list are still allowed.
    return True


def search_gdelt_articles(
    query: str,
    *,
    days_back: int = 31,
    limit: int = 5,
    domains: Sequence[str] | None = None,
    timeout: float = 4.0,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch public web-news matches from GDELT DOC 2.0.

    This is used only during explicit radar runs. It is not Google scraping and
    needs no local API key; diagnostics keep it separate from NewsAPI evidence.
    """

    clean_query = _clean(query)
    if len(clean_query) < 3:
        return [], "query for kort"
    params = {
        "query": clean_query,
        "mode": "ArtList",
        "format": "json",
        "sort": "HybridRel",
        "maxrecords": max(1, min(int(limit or 5), 25)),
        "timespan": _timespan(days_back),
    }
    url = GDELT_DOC_ENDPOINT + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "AlphaRadar/18.6"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
        raw = json.loads(payload)
    except Exception as exc:
        return [], f"GDELT feilet: {type(exc).__name__}"

    raw_articles = raw.get("articles") if isinstance(raw, Mapping) else []
    if not isinstance(raw_articles, list):
        return [], "GDELT returnerte ikke artikkelliste"

    articles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_article in raw_articles:
        if not isinstance(raw_article, Mapping):
            continue
        if not _domain_allowed(raw_article, domains):
            continue
        url_value = _clean(raw_article.get("url") or raw_article.get("url_mobile"))
        title = _clean(raw_article.get("title"))
        marker = url_value or title.lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        articles.append({
            "title": title or "Uten tittel",
            "description": _clean(raw_article.get("description")),
            "source": _clean(raw_article.get("domain") or raw_article.get("sourcecountry") or "GDELT"),
            "url": url_value,
            "published": _clean(raw_article.get("seendate") or raw_article.get("published") or raw_article.get("date")),
            "provider": "GDELT",
            "language": _clean(raw_article.get("language")),
            "source_country": _clean(raw_article.get("sourcecountry") or raw_article.get("sourceCountry")),
        })
        if len(articles) >= max(1, int(limit or 5)):
            break
    return articles, None


def search_google_news_rss(
    query: str,
    *,
    days_back: int = 31,
    limit: int = 5,
    domains: Sequence[str] | None = None,
    timeout: float = 6.0,
) -> tuple[list[dict[str, Any]], str | None]:
    clean_query = _clean(query)
    if len(clean_query) < 3:
        return [], "query for kort"
    days = max(1, min(int(days_back or 31), 365))
    params = {
        "q": f"{clean_query} when:{days}d",
        "hl": "no",
        "gl": "NO",
        "ceid": "NO:no",
    }
    url = GOOGLE_NEWS_RSS_ENDPOINT + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "AlphaRadar/18.6"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
        root = ElementTree.fromstring(payload)
    except Exception as exc:
        return [], f"Google News RSS feilet: {type(exc).__name__}"

    articles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        title = _clean(item.findtext("title"))
        link = _clean(item.findtext("link"))
        published = _clean(item.findtext("pubDate"))
        source_node = item.find("source")
        source = _clean(source_node.text if source_node is not None else "") or "Google News"
        marker = link or title.lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        articles.append({
            "title": title or "Uten tittel",
            "description": _clean(item.findtext("description")),
            "source": source,
            "url": link,
            "published": published,
            "provider": "Google News RSS",
            "language": "",
            "source_country": "",
        })
        if len(articles) >= max(1, int(limit or 5)):
            break
    return articles, None


def search_open_web_articles(
    query: str,
    *,
    days_back: int = 31,
    limit: int = 5,
    domains: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    gdelt_articles, gdelt_error = search_gdelt_articles(
        query,
        days_back=days_back,
        limit=limit,
        domains=domains,
    )
    if gdelt_articles:
        return gdelt_articles, gdelt_error
    google_articles, google_error = search_google_news_rss(
        query,
        days_back=days_back,
        limit=limit,
        domains=domains,
    )
    if google_articles:
        return google_articles, None
    errors = " | ".join(error for error in (gdelt_error, google_error) if error)
    return google_articles, errors or None


__all__ = [
    "GDELT_DOC_ENDPOINT",
    "GOOGLE_NEWS_RSS_ENDPOINT",
    "search_gdelt_articles",
    "search_google_news_rss",
    "search_open_web_articles",
]
