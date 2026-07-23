"""Official-market source catalogue and NewsAPI discovery for insider events.

Discovery is intentionally separate from transaction scoring.  An article or
announcement hit can point to a primary source, but it is not treated as a
structured transaction until amount, direction and date have been verified.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import urlparse
from newsapi_budget import (
    NewsApiDailyQuotaExceeded,
    NewsApiError,
    NewsApiRateLimited,
    fetch_articles as fetch_newsapi_articles,
)


SOURCE_CATALOGUE: dict[str, dict[str, Any]] = {
    "Norge": {
        "currency": "NOK", "name": "Oslo Børs NewsWeb / Finanstilsynet",
        "domains": ["newsweb.oslobors.no", "finanstilsynet.no"],
        "search_url": "https://newsweb.oslobors.no/",
        "terms": ["primary insider", "primærinnsider", "mandatory notification of trade"],
    },
    "Sverige": {
        "currency": "SEK", "name": "Finansinspektionen PDMR-register",
        "domains": ["fi.se", "marknadssok.fi.se"],
        "search_url": "https://marknadssok.fi.se/publiceringsklient/en-GB/Search/Start/Insyn",
        "terms": ["PDMR transaction", "insynshandel", "ledningsperson transaktion"],
    },
    "Finland": {
        "currency": "EUR", "name": "FIN-FSA / Nasdaq Helsinki",
        "domains": ["finanssivalvonta.fi", "nasdaq.com", "news.eu.nasdaq.com"],
        "search_url": "https://www.finanssivalvonta.fi/en/financial-market-participants/capital-markets/issuers-and-investors/listing/",
        "terms": ["managers transaction", "PDMR transaction", "johtohenkilö liiketoimi"],
    },
    "Danmark": {
        "currency": "DKK", "name": "Finanstilsynet OAM / Nasdaq Copenhagen",
        "domains": ["finanstilsynet.dk", "nasdaq.com", "news.eu.nasdaq.com"],
        "search_url": "https://www.finanstilsynet.dk/finansielle-temaer/kapitalmarked/selskabsmeddelelser",
        "terms": ["ledende medarbejder transaktion", "PDMR transaction", "manager transaction"],
    },
    "Brasil": {
        "currency": "BRL", "name": "CVM Dados Abertos",
        "domains": ["gov.br", "cvm.gov.br", "dados.cvm.gov.br"],
        "search_url": "https://www.gov.br/cvm/pt-br/acesso-a-informacao-cvm/dados-abertos",
        "terms": ["negociação administradores", "insider trading companhia", "valores mobiliários administradores"],
    },
    "USA": {
        "currency": "USD", "name": "SEC / public filings",
        "domains": ["sec.gov"], "search_url": "https://www.sec.gov/edgar/search/",
        "terms": ["insider purchase", "insider sale", "Form 4"],
    },
}

_NEWS_CACHE: dict[str, dict[str, Any]] = {}
_NEWS_CACHE_SECONDS = 12 * 60 * 60


def source_for_market(market: str) -> dict[str, Any]:
    return dict(SOURCE_CATALOGUE.get(str(market or ""), {}))


def _official_domain(url: str, domains: list[str]) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def discover_with_newsapi(ticker: str, company: str, market: str, limit: int = 10) -> dict[str, Any]:
    source = source_for_market(market)
    base = {
        "market": market, "currency": source.get("currency", ""),
        "official_source": source.get("name", "Ikke konfigurert"),
        "official_search_url": source.get("search_url", ""),
        "articles": [], "status": "NO_DISCOVERY", "provider": "NewsAPI",
        "source_label": f"NewsAPI-kildeoppdagelse for {source.get('name', 'offisiell kilde')}",
        "direct_primary_source_checked": False,
    }
    key = os.getenv("NEWSAPI_KEY", "").strip()
    if not key:
        base["status"] = "NEWSAPI_NOT_CONFIGURED"
        return base
    terms = list(source.get("terms") or ["insider transaction"])
    query = " OR ".join(f'"{term}"' for term in terms)
    try:
        cached = _NEWS_CACHE.get(market) or {}
        if time.time() - float(cached.get("cached_at") or 0) < _NEWS_CACHE_SECONDS:
            market_articles = list(cached.get("articles") or [])
        else:
            domains = list(source.get("domains") or [])
            fetched = fetch_newsapi_articles(
                query,
                purpose=f"INSIDER_DISCOVERY_{str(market or 'UNKNOWN').upper()}",
                limit=100,
                from_date=(datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat(),
                domains=domains,
                cache_ttl_seconds=_NEWS_CACHE_SECONDS,
            )
            market_articles = []
            for raw in fetched:
                url = str(raw.get("url") or "")
                market_articles.append({
                    "title": str(raw.get("title") or ""),
                    "summary": str(raw.get("summary") or ""), "url": url,
                    "published_at": str(raw.get("published_at") or ""),
                    "publisher": str(raw.get("publisher") or ""),
                    "official_domain": _official_domain(url, domains),
                    "verification": "DISCOVERY_ONLY",
                })
            _NEWS_CACHE[market] = {"cached_at": time.time(), "articles": market_articles}
        ticker_token = str(ticker or "").upper().split(".")[0].replace("-", "")
        company_token = " ".join(str(company or "").lower().split()[:2])
        articles = []
        for article in market_articles:
            haystack = f"{article.get('title','')} {article.get('summary','')}".lower()
            ticker_match = len(ticker_token) >= 3 and ticker_token.lower() in haystack.replace("-", "")
            company_match = len(company_token) >= 4 and company_token in haystack
            if ticker_match or company_match:
                clean = dict(article); clean.pop("summary", None)
                articles.append(clean)
            if len(articles) >= max(1, int(limit)):
                break
        base["articles"] = articles
        base["status"] = "DISCOVERY_FOUND" if articles else "NO_DISCOVERY"
    except NewsApiDailyQuotaExceeded as exc:
        base["status"] = "DAILY_QUOTA_EXCEEDED"
        base["error"] = str(exc)
    except NewsApiRateLimited as exc:
        base["status"] = "RATE_LIMITED"
        base["retry_after_seconds"] = exc.retry_after
        base["error"] = str(exc)
    except NewsApiError as exc:
        base["status"] = "NEWSAPI_NOT_CONFIGURED"
        base["error"] = str(exc)
    except Exception:
        base["status"] = "DISCOVERY_ERROR"
        base["error"] = "NewsAPI-kildeoppdagelsen feilet; den navngitte primærkilden ble ikke kontrollert direkte"
    return base
