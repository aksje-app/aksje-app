"""News & Sentiment Intelligence Engine v18.7.2.

Collects recent public company news, deduplicates repeated stories and calculates a
transparent 0-100 score. Missing coverage is neutral and never treated as positive
or negative evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Sequence
import hashlib
import json
import math
import os
import re
import time

from news_source_registry import (
    DEFAULT_RSS_FEEDS,
    canonical_title as source_canonical_title,
    classify_article,
    fetch_rss_source,
    query_tokens as build_query_tokens,
    source_quality as registry_source_quality,
    source_specs,
)

from app_version import APP_VERSION
from storage_architecture import runtime_data_path
from operational_telemetry import record_source_attempt
from newsapi_budget import (
    NewsApiDailyQuotaExceeded,
    NewsApiError,
    NewsApiRateLimited,
    fetch_articles as fetch_newsapi_articles,
)

COMPONENT_VERSION = APP_VERSION
VERSION = APP_VERSION
CACHE_PATH = runtime_data_path("news_intelligence") / "cache.json"
_CACHE_LOCK = RLock()
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
    temp = Path(str(CACHE_PATH) + ".tmp")
    temp.write_text(json.dumps(dict(cache), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CACHE_PATH)


def _cache_get(key: str) -> dict[str, Any]:
    with _CACHE_LOCK:
        return dict((_load_cache().get(key) or {}))


def _cache_put(key: str, result: Mapping[str, Any]) -> None:
    with _CACHE_LOCK:
        cache = _load_cache()
        cache[key] = {"cached_at": time.time(), "result": dict(result)}
        _save_cache(cache)



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
        try:
            dt = parsedate_to_datetime(text)
            return dt.replace(tzinfo=dt.tzinfo or timezone.utc)
        except Exception:
            return None


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return urlparse(str(url or "")).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _source_quality(url: str, publisher: str = "", article_type: str = "news", override: Any = None) -> float:
    return registry_source_quality(url, publisher, article_type, override)


def _canonical_title(title: str) -> str:
    return source_canonical_title(title)


_COMPANY_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "company", "co", "ltd",
    "limited", "plc", "asa", "as", "ab", "oyj", "sa", "group", "holding",
    "holdings", "class", "ordinary", "common", "stock",
}


def _company_aliases(ticker: str, company_name: str = "") -> list[str]:
    raw_ticker = str(ticker or "").upper().strip()
    base_ticker = re.split(r"[.:-]", raw_ticker)[0]
    resolved_name = str(company_name or "").strip()
    if not resolved_name or resolved_name.upper() in {raw_ticker, base_ticker}:
        try:
            from security_metadata import resolve_security_metadata
            resolved_name = str(resolve_security_metadata(raw_ticker).get("name") or resolved_name).strip()
        except Exception:
            pass
    aliases: list[str] = []
    for value in (raw_ticker, base_ticker):
        if len(value) >= 3 and value not in aliases:
            aliases.append(value.casefold())
    cleaned = re.sub(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ ]+", " ", resolved_name).strip()
    words = [word for word in cleaned.split() if len(word) >= 3 and word.casefold() not in _COMPANY_SUFFIXES]
    if words:
        full = " ".join(words).casefold()
        if len(full) >= 3 and full not in aliases:
            aliases.append(full)
        # Distinctive company tokens are accepted, but common corporate suffixes
        # and one/two-letter noise are never relevance evidence.
        for word in words:
            token = word.casefold()
            if token not in aliases:
                aliases.append(token)
    return aliases


def article_company_relevance(
    row: Mapping[str, Any], ticker: str, company_name: str = "",
) -> dict[str, Any]:
    role = str(row.get("source_role") or "").upper()
    url = str(row.get("url") or row.get("link") or "")
    if role == "PRIMARY_COMPANY" or "investor" in _domain(url):
        return {
            "company_relevant": True, "relevance_score": 1.0,
            "relevance_basis": "PRIMARY_COMPANY_SOURCE", "matched_aliases": [],
        }
    # Secondary aggregators are noisy: a company mentioned only in the body of
    # an article about another issuer is not sufficient evidence. Require an
    # explicit company/ticker match in the headline. Primary company sources
    # were accepted above without this restriction.
    haystack = str(row.get("title") or "").casefold()
    aliases = _company_aliases(ticker, company_name)
    matched = []
    for alias in aliases:
        pattern = r"(?<![0-9a-z])" + re.escape(alias) + r"(?![0-9a-z])"
        if re.search(pattern, haystack, flags=re.IGNORECASE):
            matched.append(alias)
    score = 1.0 if matched else 0.0
    return {
        "company_relevant": bool(matched),
        "relevance_score": score,
        "relevance_basis": "EXPLICIT_COMPANY_OR_TICKER_MATCH" if matched else "NO_COMPANY_OR_TICKER_MATCH",
        "matched_aliases": matched,
    }


def _item_from_yfinance(raw: Mapping[str, Any]) -> dict[str, Any]:
    content = raw.get("content") if isinstance(raw.get("content"), Mapping) else raw
    provider = content.get("provider") if isinstance(content.get("provider"), Mapping) else {}
    click = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), Mapping) else {}
    canonical = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), Mapping) else {}
    publisher = provider.get("displayName") or raw.get("publisher") or ""
    title = content.get("title") or raw.get("title") or ""
    summary = content.get("summary") or content.get("description") or raw.get("summary") or ""
    return {
        "title": title,
        "summary": summary,
        "url": click.get("url") or canonical.get("url") or content.get("link") or raw.get("link") or "",
        "publisher": publisher,
        "original_publisher": publisher,
        "collector_source": "Yahoo Finance / yfinance",
        "source_role": "TICKER_DISCOVERY",
        "article_type": classify_article(title, summary),
        "published_at": content.get("pubDate") or raw.get("providerPublishTime") or raw.get("published_at"),
    }


def _fetch_yfinance(ticker: str) -> list[dict[str, Any]]:
    import yfinance as yf
    raw = getattr(yf.Ticker(ticker), "news", None) or []
    return [_item_from_yfinance(x) for x in raw if isinstance(x, Mapping)]


def _fetch_newsapi(query: str, limit: int = 30) -> list[dict[str, Any]]:
    if not os.getenv("NEWSAPI_KEY", "").strip():
        return []
    return fetch_newsapi_articles(
        query,
        purpose="NEWS_COMPANY",
        limit=limit,
        cache_ttl_seconds=CACHE_TTL_SECONDS,
    )


def normalize_articles(rows: Sequence[Mapping[str, Any]], lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    unique: dict[str, dict[str, Any]] = {}
    include_sponsored = str(os.getenv("NEWS_INCLUDE_SPONSORED", "false")).strip().casefold() in {"1", "true", "yes", "on"}
    for raw in rows:
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        summary = str(raw.get("summary") or raw.get("description") or "").strip()
        article_type = str(raw.get("article_type") or classify_article(title, summary, raw.get("categories") or [])).casefold()
        if article_type == "sponsored" and not include_sponsored:
            continue
        dt = _parse_date(raw.get("published_at") or raw.get("publishedAt") or raw.get("providerPublishTime"))
        age_hours = max(0.0, (now - dt).total_seconds() / 3600.0) if dt else lookback_days * 24.0
        if age_hours > lookback_days * 24.0:
            continue
        url = str(raw.get("url") or raw.get("link") or "")
        publisher = str(raw.get("original_publisher") or raw.get("publisher") or raw.get("source") or "").strip()
        canonical = _canonical_title(title)
        if not canonical:
            continue
        key = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]
        item = {
            "title": title,
            "summary": summary,
            "url": url,
            "publisher": publisher,
            "original_publisher": publisher,
            "collector_source": str(raw.get("collector_source") or raw.get("collector") or publisher).strip(),
            "source_id": str(raw.get("source_id") or "").strip(),
            "source_role": str(raw.get("source_role") or "PUBLISHED_NEWS").strip(),
            "article_type": article_type,
            "categories": list(raw.get("categories") or []),
            "published_at": dt.isoformat() if dt else "",
            "age_hours": round(age_hours, 1),
            "source_quality": round(_source_quality(
                url,
                publisher,
                article_type,
                raw.get("source_quality_override"),
            ), 2),
            "verification": str(raw.get("verification") or "PUBLISHED_SOURCE"),
            "company_relevant": raw.get("company_relevant") is True,
            "relevance_score": round(_f(raw.get("relevance_score")), 3),
            "relevance_basis": str(raw.get("relevance_basis") or ""),
            "matched_aliases": list(raw.get("matched_aliases") or []),
        }
        previous = unique.get(key)
        if not previous or item["source_quality"] > previous["source_quality"]:
            unique[key] = item
    return sorted(unique.values(), key=lambda x: (x["age_hours"], -x["source_quality"]))



def score_articles(
    ticker: str, rows: Sequence[Mapping[str, Any]], lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    company_name: str = "",
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    relevant_rows: list[dict[str, Any]] = []
    rejected_irrelevant: list[dict[str, Any]] = []
    for source_row in rows:
        if not isinstance(source_row, Mapping):
            continue
        annotated = dict(source_row)
        relevance = (
            article_company_relevance(annotated, ticker, company_name)
            if str(company_name or "").strip()
            else {
                "company_relevant": True, "relevance_score": 1.0,
                "relevance_basis": "UNSCOPED_SCORING_INPUT", "matched_aliases": [],
            }
        )
        annotated.update(relevance)
        if relevance["company_relevant"]:
            relevant_rows.append(annotated)
        else:
            rejected_irrelevant.append({
                "title": str(annotated.get("title") or ""),
                "publisher": str(annotated.get("publisher") or annotated.get("source") or ""),
                "url": str(annotated.get("url") or annotated.get("link") or ""),
                "reason": relevance["relevance_basis"],
            })
    filtered_sponsored_count = sum(
        1 for row in rows
        if str(row.get("article_type") or classify_article(
            str(row.get("title") or ""), str(row.get("summary") or row.get("description") or ""), row.get("categories") or []
        )).casefold() == "sponsored"
    )
    recommendation_count = sum(
        1 for row in rows
        if str(row.get("article_type") or classify_article(
            str(row.get("title") or ""), str(row.get("summary") or row.get("description") or ""), row.get("categories") or []
        )).casefold() == "recommendation"
    )
    articles = normalize_articles(relevant_rows, lookback_days)
    if not articles:
        return {
            "ticker": ticker, "score": 50.0, "sentiment": "INGEN DATA", "coverage": "MISSING",
            "article_count": 0, "positive_count": 0, "negative_count": 0, "high_impact_count": 0,
            "filtered_sponsored_count": filtered_sponsored_count, "recommendation_count": recommendation_count,
            "fetched_article_count": len(rows), "relevant_article_count": 0,
            "rejected_irrelevant_count": len(rejected_irrelevant),
            "rejected_irrelevant_articles": rejected_irrelevant[:20],
            "events": [], "summary": "Ingen selskapsrelevante nyheter funnet i tilgjengelige kilder.",
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
        copy["source_url"] = copy.get("url") or ""
        role = str(copy.get("source_role") or "PUBLISHED_NEWS")
        copy["source_type"] = "PRIMARY_COMPANY" if role == "PRIMARY_COMPANY" or "investor" in _domain(copy.get("url") or "") else "PUBLISHED_NEWS"
        copy["verification"] = str(copy.get("verification") or "PUBLISHED_SOURCE")
        copy["retrieved_at"] = now.isoformat(timespec="seconds")
        copy["fact_id"] = "NEWS-" + hashlib.sha1(
            f"{copy.get('title','')}|{copy.get('url','')}|{copy.get('published_at','')}".encode("utf-8")
        ).hexdigest()[:12].upper()
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
        "high_impact_count": high_impact_count, "filtered_sponsored_count": filtered_sponsored_count,
        "recommendation_count": recommendation_count, "topics": top_topics, "events": enriched[:10], "summary": summary,
        "fetched_article_count": len(rows), "relevant_article_count": len(articles),
        "rejected_irrelevant_count": len(rejected_irrelevant),
        "rejected_irrelevant_articles": rejected_irrelevant[:20],
        "relevance_policy": "EXPLICIT_COMPANY_OR_TICKER_MATCH_OR_PRIMARY_COMPANY_SOURCE",
    }


def fetch_news_intelligence(ticker: str, company_name: str = "", force_refresh: bool = False,
                            lookback_days: int = DEFAULT_LOOKBACK_DAYS, market: str = "",
                            ir_feed_url: str = "") -> dict[str, Any]:
    ticker = str(ticker or "").upper().strip()
    key = f"{VERSION}|{ticker}|{company_name.strip().lower()}|{market}|{ir_feed_url}|{lookback_days}"
    cached = _cache_get(key)
    if cached and not force_refresh and time.time() - _f(cached.get("cached_at")) < CACHE_TTL_SECONDS and (cached.get("result") or {}).get("search_log"):
        return dict(cached.get("result") or {})
    sources: list[str] = []
    search_log: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        _yf_started = time.perf_counter()
        yf_rows = _fetch_yfinance(ticker)
        record_source_attempt(
            source_id="yahoo_finance", market=str(market or "Globalt"), publisher="Yahoo Finance",
            url="https://finance.yahoo.com", success=True,
            response_ms=(time.perf_counter() - _yf_started) * 1000.0, article_count=len(yf_rows),
            relevant_count=sum(
                article_company_relevance(row, ticker, company_name).get("company_relevant") is True
                for row in yf_rows
            ), cache_status="DIRECT", parser_status="OK", volume_check=False,
        )
        rows.extend(yf_rows)
        if yf_rows: sources.append("Yahoo Finance / yfinance")
        search_log.append({
            "source": "yfinance company news", "source_type": "SECONDARY_AGGREGATOR",
            "attempted": True, "status": "SUCCESS_WITH_RESULTS" if yf_rows else "SUCCESS_NO_RESULTS",
            "results": len(yf_rows), "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": "",
        })
    except Exception as exc:
        record_source_attempt(
            source_id="yahoo_finance", market=str(market or "Globalt"), publisher="Yahoo Finance",
            url="https://finance.yahoo.com", success=False,
            response_ms=(time.perf_counter() - locals().get("_yf_started", time.perf_counter())) * 1000.0,
            parser_status="UNKNOWN", error=exc, volume_check=False,
        )
        errors.append(f"yfinance: {exc}")
        search_log.append({
            "source": "yfinance company news", "source_type": "SECONDARY_AGGREGATOR",
            "attempted": True, "status": "ERROR", "results": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": str(exc)[:500],
        })
    try:
        fallback_only = str(os.getenv("NEWSAPI_FALLBACK_ONLY", "true")).strip().casefold() not in {"0", "false", "no"}
        minimum_existing = max(1, int(os.getenv("NEWSAPI_FALLBACK_MIN_EXISTING_ARTICLES", "3") or 3))
        if fallback_only and len(yf_rows if "yf_rows" in locals() else []) >= minimum_existing:
            search_log.append({
                "source": "NewsAPI broad company search", "source_type": "LICENSED_AGGREGATOR",
                "attempted": False, "status": "SKIPPED_BUDGET_POLICY", "results": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "error": f"Ikke brukt: yfinance ga minst {minimum_existing} saker; døgnbudsjett bevart",
            })
            api_rows = []
        else:
            query = f'"{company_name.strip()}" OR "{ticker}"' if company_name.strip() else ticker
            api_rows = _fetch_newsapi(query)
        for row in api_rows:
            row.setdefault("collector_source", "NewsAPI")
            row.setdefault("source_role", "LICENSED_AGGREGATOR")
            row.setdefault("article_type", classify_article(str(row.get("title") or ""), str(row.get("description") or row.get("summary") or "")))
        rows.extend(api_rows)
        if api_rows: sources.append("NewsAPI")
        if not (fallback_only and len(yf_rows if "yf_rows" in locals() else []) >= minimum_existing):
            search_log.append({
                "source": "NewsAPI broad company search", "source_type": "LICENSED_AGGREGATOR",
                "attempted": bool(os.getenv("NEWSAPI_KEY", "").strip()),
                "status": ("SUCCESS_WITH_RESULTS" if api_rows else "SUCCESS_NO_RESULTS") if os.getenv("NEWSAPI_KEY", "").strip() else "NOT_CONFIGURED",
                "results": len(api_rows), "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": "",
            })
    except NewsApiDailyQuotaExceeded:
        errors.append("NewsAPI: døgnbudsjettet er brukt")
        search_log.append({
            "source": "NewsAPI broad company search", "source_type": "LICENSED_AGGREGATOR",
            "attempted": False, "status": "DAILY_QUOTA_EXCEEDED", "results": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": "Lokalt døgnbudsjett er brukt; øvrige kilder benyttes",
        })
    except NewsApiRateLimited as exc:
        errors.append("NewsAPI: HTTP 429 – kapasitetsgrense")
        search_log.append({
            "source": "NewsAPI broad company search", "source_type": "LICENSED_AGGREGATOR",
            "attempted": True, "status": "RATE_LIMITED", "results": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "retry_after_seconds": exc.retry_after,
            "error": "HTTP 429 – kapasitetsgrense; øvrige kilder brukes",
        })
    except NewsApiError:
        search_log.append({
            "source": "NewsAPI broad company search", "source_type": "LICENSED_AGGREGATOR",
            "attempted": False, "status": "NOT_CONFIGURED", "results": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": "NewsAPI er ikke konfigurert; øvrige kilder benyttes",
        })
    except Exception as exc:
        errors.append(f"NewsAPI: {exc}")
        search_log.append({
            "source": "NewsAPI broad company search", "source_type": "LICENSED_AGGREGATOR",
            "attempted": True, "status": "ERROR", "results": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": str(exc)[:500],
        })
    feed_specs = source_specs(str(market or ""), ir_feed_url)
    tokens = build_query_tokens(ticker, company_name)
    for spec in feed_specs:
        publisher = str(spec.get("label") or spec.get("publisher") or "RSS")
        feed_url = str(spec.get("url") or "")
        try:
            rss_rows, feed_meta = fetch_rss_source(spec, tokens)
            rows.extend(rss_rows)
            if rss_rows:
                sources.append(str(spec.get("publisher") or publisher))
            search_log.append({
                "source": publisher,
                "source_id": str(spec.get("id") or "rss"),
                "source_type": "PRIMARY_OR_DIRECT_RSS",
                "source_role": str(spec.get("source_role") or "PUBLISHED_NEWS"),
                "attempted": True,
                "status": "SUCCESS_WITH_RESULTS" if rss_rows else "SUCCESS_NO_RESULTS",
                "results": len(rss_rows),
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "url": feed_meta.get("feed_url") or feed_url,
                "configured_url": feed_url,
                "fallback_used": bool(feed_meta.get("fallback_used")),
                "fallback_failures": list(feed_meta.get("fallback_failures") or []),
                "cache_status": feed_meta.get("cache_status"),
                "cache_age_seconds": feed_meta.get("cache_age_seconds"),
                "feed_items_scanned": feed_meta.get("feed_items_scanned"),
                "relevant_items": feed_meta.get("relevant_items"),
                "duplicate_items": feed_meta.get("duplicate_items"),
                "filtered_commercial_items": feed_meta.get("filtered_commercial_items"),
                "response_ms": feed_meta.get("response_ms"),
                "source_health_score": feed_meta.get("source_health_score"),
                "source_health_alert": feed_meta.get("source_health_alert"),
                "error": "",
            })
        except Exception as exc:
            errors.append(f"{publisher}: {exc}")
            search_log.append({
                "source": publisher,
                "source_id": str(spec.get("id") or "rss"),
                "source_type": "PRIMARY_OR_DIRECT_RSS",
                "source_role": str(spec.get("source_role") or "PUBLISHED_NEWS"),
                "attempted": True,
                "status": "ERROR",
                "results": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "url": feed_url,
                "error": str(exc)[:500],
            })
    result = score_articles(ticker, rows, lookback_days, company_name=company_name)
    unique_sources = list(dict.fromkeys(source for source in sources if source))
    result["source"] = ", ".join(unique_sources) if unique_sources else "unavailable"
    result["configured_market_sources"] = [str(spec.get("label") or spec.get("publisher") or "") for spec in feed_specs]
    result["source_breakdown"] = {
        publisher: sum(1 for event in result.get("events") or [] if str(event.get("publisher") or "") == publisher)
        for publisher in sorted({str(event.get("publisher") or "") for event in result.get("events") or [] if event.get("publisher")})
    }
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    result["errors"] = errors
    result["search_log"] = search_log
    result["sources_checked"] = sum(1 for row in search_log if row.get("attempted"))
    result["verified_fact_count"] = len(result.get("events") or [])
    from evidence_contract import canonical_status, source_budget
    result["canonical_evidence_status"] = canonical_status(result, result.get("events") or [])
    result["source_budget"] = source_budget(result)
    successful_checks = [row for row in search_log if row.get("status") in {"SUCCESS_WITH_RESULTS", "SUCCESS_NO_RESULTS"}]
    if not sources and errors and not successful_checks:
        result["coverage"] = "ERROR"
        result["sentiment"] = "KILDEFEIL"
        result["summary"] = "Nyhetskildene kunne ikke hentes. Nøytral score brukes."
    _cache_put(key, result)
    return result


def enrich_rows(rows: Sequence[Mapping[str, Any]], force_refresh: bool = False, progress_callback: Any | None = None) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    total = len(rows)
    for index, raw in enumerate(rows, start=1):
        row = dict(raw)
        result = fetch_news_intelligence(
            str(row.get("ticker") or row.get("symbol") or ""),
            str(row.get("longName") or row.get("shortName") or row.get("name") or ""),
            force_refresh=force_refresh,
            market=str(row.get("market") or ""),
            ir_feed_url=str(row.get("ir_feed_url") or row.get("investor_relations_feed") or ""),
        )
        row["news_intelligence"] = result
        row["news_score"] = result.get("score", 50.0)
        row["news_sentiment"] = result.get("sentiment", "INGEN DATA")
        row["news_summary"] = result.get("summary", "")
        enriched.append(row)
        if progress_callback:
            progress_callback(index, total, str(row.get("ticker") or ""))
    return enriched
