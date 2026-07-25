"""Free financial-media source registry and cached RSS collection for v19.0.19a.

The registry keeps source identity, market role and quality policy separate from
company scoring. Feeds are cached once per URL so a 25-stock scan does not fetch
the same publication 25 times. Paid/licensed full-text extraction is not used.
"""
from __future__ import annotations

from html import unescape
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse
from xml.etree import ElementTree
import json
import os
import re
import time
import unicodedata

from storage_architecture import runtime_data_path

VERSION = "v19.0.19a"
FEED_CACHE_PATH = runtime_data_path("news_intelligence") / "source_feed_cache.json"
FEED_CACHE_TTL_SECONDS = max(300, int(os.getenv("NEWS_SOURCE_FEED_CACHE_MINUTES", "30") or 30) * 60)
FEED_STALE_MAX_SECONDS = max(
    FEED_CACHE_TTL_SECONDS,
    int(os.getenv("NEWS_SOURCE_STALE_MAX_HOURS", "24") or 24) * 3600,
)
HTTP_TIMEOUT_SECONDS = max(5, int(os.getenv("NEWS_SOURCE_HTTP_TIMEOUT_SECONDS", "12") or 12))
MAX_FEED_ITEMS = max(20, int(os.getenv("NEWS_SOURCE_MAX_FEED_ITEMS", "120") or 120))
_CACHE_LOCK = RLock()

# Direct, publication-controlled feeds. Yahoo Finance company news is collected
# through yfinance in news_intelligence.py and therefore is not duplicated here.
SOURCE_REGISTRY: dict[str, list[dict[str, Any]]] = {
    "Norge": [
        {
            "id": "e24",
            "publisher": "E24",
            "label": "E24 RSS",
            "url": "https://e24.no/rss",
            "domain": "e24.no",
            "source_role": "PRIMARY_NEWS",
            "article_type_default": "news",
        },
    ],
    "Sverige": [
        {
            "id": "efn",
            "publisher": "EFN",
            "label": "EFN RSS",
            "url": "https://efn.se/rss/infront",
            "domain": "efn.se",
            "source_role": "PRIMARY_NEWS",
            "article_type_default": "news",
        },
    ],
    "Brasil": [
        {
            "id": "infomoney",
            "publisher": "InfoMoney",
            "label": "InfoMoney Mercados RSS",
            "url": "https://www.infomoney.com.br/mercados/feed/",
            "fallback_urls": ["https://www.infomoney.com.br/feed/"],
            "domain": "infomoney.com.br",
            "source_role": "PRIMARY_NEWS",
            "article_type_default": "news",
        },
        {
            "id": "money_times",
            "publisher": "Money Times",
            "label": "Money Times Mercados RSS",
            "url": "https://www.moneytimes.com.br/mercados/feed/",
            "fallback_urls": ["https://www.moneytimes.com.br/feed/"],
            "domain": "moneytimes.com.br",
            "source_role": "SECONDARY_CONFIRMATION",
            "article_type_default": "news",
        },
        {
            "id": "brazil_journal",
            "publisher": "Brazil Journal",
            "label": "Brazil Journal RSS",
            "url": "https://braziljournal.com/feed/",
            "domain": "braziljournal.com",
            "source_role": "BACKGROUND_DEPTH",
            "article_type_default": "analysis",
        },
    ],
    "USA": [
        {
            "id": "cnbc",
            "publisher": "CNBC",
            "label": "CNBC Finance RSS",
            "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
            "fallback_urls": ["https://www.cnbc.com/id/100003114/device/rss/rss.html"],
            "domain": "cnbc.com",
            "source_role": "MARKET_CONTEXT",
            "article_type_default": "news",
        },
    ],
}

PUBLISHER_QUALITY: dict[str, float] = {
    "reuters": 1.00,
    "associated press": 0.96,
    "ap": 0.96,
    "bloomberg": 0.94,
    "financial times": 0.93,
    "ft": 0.93,
    "wall street journal": 0.93,
    "e24": 0.93,
    "infomoney": 0.92,
    "cnbc": 0.88,
    "efn": 0.86,
    "yahoo finance": 0.86,
    "money times": 0.84,
    "brazil journal": 0.82,
    "marketwatch": 0.80,
    "nasdaq": 0.80,
    "business wire": 0.65,
    "pr newswire": 0.55,
    "stockstory": 0.42,
    "motley fool": 0.35,
}

DOMAIN_QUALITY: dict[str, float] = {
    "reuters.com": 1.00,
    "apnews.com": 0.96,
    "bloomberg.com": 0.94,
    "ft.com": 0.93,
    "wsj.com": 0.93,
    "e24.no": 0.93,
    "infomoney.com.br": 0.92,
    "cnbc.com": 0.88,
    "efn.se": 0.86,
    "moneytimes.com.br": 0.84,
    "braziljournal.com": 0.82,
    "marketwatch.com": 0.80,
    "nasdaq.com": 0.80,
    "finance.yahoo.com": 0.76,
    "globenewswire.com": 0.72,
    "businesswire.com": 0.65,
    "prnewswire.com": 0.55,
    "sec.gov": 1.00,
    "newsweb.no": 0.95,
}

SPONSORED_MARKERS = (
    "conteúdo de marca", "conteudo de marca", "conteúdo empiricus", "conteudo empiricus",
    "publieditorial", "patrocinado", "sponsored", "paid content", "partner content",
    "a word from our partners", "um conteúdo ", "um conteudo ", "advertorial",
)
RECOMMENDATION_MARKERS = (
    "comprar ou vender", "carteira recomendada", "day trade", "análise técnica",
    "analise tecnica", "buy or sell", "price target", "kursmål", "kursmal",
    "upgrade", "downgrade", "outperform", "underperform", "top pick",
)
OPINION_MARKERS = ("opinião", "opiniao", "opinion", "commentary", "coluna", "column")
LIVE_MARKERS = ("ao vivo", "tempo real", "live blog", "live:", "market live")
PRESS_RELEASE_MARKERS = ("press release", "pressemelding", "comunicado ao mercado", "business wire", "pr newswire")

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "at", "from",
    "og", "eller", "av", "til", "for", "med", "på", "pa", "fra", "som", "etter",
    "e", "ou", "de", "da", "do", "das", "dos", "para", "com", "em", "no", "na", "nos", "nas",
}
LEGAL_WORDS = {
    "asa", "as", "ab", "oyj", "oy", "a/s", "sa", "s/a", "inc", "corp", "corporation", "company",
    "limited", "ltd", "plc", "holding", "holdings", "group", "grupo", "companhia", "brasileira",
}


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _domain(url: str) -> str:
    try:
        return urlparse(str(url or "")).netloc.casefold().removeprefix("www.")
    except Exception:
        return ""


def source_enabled(source_id: str) -> bool:
    key = "NEWS_SOURCE_" + re.sub(r"[^A-Z0-9]+", "_", str(source_id or "").upper()) + "_ENABLED"
    return str(os.getenv(key, "true")).strip().casefold() not in {"0", "false", "no", "off"}


def source_specs(market: str, ir_feed_url: str = "") -> list[dict[str, Any]]:
    specs = [dict(row) for row in SOURCE_REGISTRY.get(str(market or ""), []) if source_enabled(str(row.get("id") or ""))]
    if str(ir_feed_url or "").strip():
        specs.append({
            "id": "company_ir",
            "publisher": "Selskapets IR-feed",
            "label": "Selskapets IR-feed",
            "url": str(ir_feed_url).strip(),
            "domain": _domain(str(ir_feed_url)),
            "source_role": "PRIMARY_COMPANY",
            "article_type_default": "press_release",
            "quality_override": 1.00,
        })
    return specs


def query_tokens(ticker: str, company_name: str = "") -> list[str]:
    base = str(ticker or "").upper().split(".")[0].strip()
    tokens: list[str] = []
    if len(base) >= 2:
        tokens.append(_normalize_text(base))
    words = re.findall(r"[A-Za-zÀ-ÿ0-9&-]+", str(company_name or ""))
    meaningful = []
    for word in words:
        normalized = _normalize_text(word).strip("-&")
        if len(normalized) < 4 or normalized in LEGAL_WORDS or normalized in STOPWORDS:
            continue
        meaningful.append(normalized)
    # Longer brand-like words are safer than generic short terms.
    for word in sorted(dict.fromkeys(meaningful), key=lambda value: (-len(value), value))[:6]:
        if word not in tokens:
            tokens.append(word)
    return tokens


def canonical_title(title: str) -> str:
    text = re.sub(r"\s*[-–—|]\s*(Reuters|AP|Bloomberg|CNBC|Yahoo Finance|E24|EFN|InfoMoney|Money Times)\s*$", "", str(title or ""), flags=re.I)
    words = re.findall(r"[a-z0-9æøåà-ÿ]+", _normalize_text(text))
    return " ".join(word for word in words if word not in STOPWORDS)[:220]


def classify_article(title: str, summary: str = "", categories: Sequence[str] | None = None,
                     default: str = "news") -> str:
    text = _normalize_text(" ".join([str(title or ""), str(summary or ""), " ".join(categories or [])]))
    if any(marker in text for marker in SPONSORED_MARKERS):
        return "sponsored"
    if any(marker in text for marker in PRESS_RELEASE_MARKERS):
        return "press_release"
    if any(marker in text for marker in RECOMMENDATION_MARKERS):
        return "recommendation"
    if any(marker in text for marker in OPINION_MARKERS):
        return "opinion"
    if any(marker in text for marker in LIVE_MARKERS):
        return "live_blog"
    return str(default or "news")


def source_quality(url: str, publisher: str = "", article_type: str = "news",
                   override: Any = None) -> float:
    try:
        if override is not None:
            base = float(override)
        else:
            base = 0.62
            publisher_text = _normalize_text(publisher)
            # Original publisher wins over an aggregator URL, e.g. Reuters on Yahoo Finance.
            for known, quality in sorted(PUBLISHER_QUALITY.items(), key=lambda item: -len(item[0])):
                if publisher_text == known or known in publisher_text:
                    base = quality
                    break
            else:
                domain = _domain(url)
                for known, quality in DOMAIN_QUALITY.items():
                    if domain == known or domain.endswith("." + known):
                        base = quality
                        break
    except (TypeError, ValueError):
        base = 0.62
    kind = str(article_type or "news").casefold()
    if kind == "sponsored":
        base = min(base, 0.20)
    elif kind == "recommendation":
        base *= 0.72
    elif kind == "opinion":
        base *= 0.88
    elif kind == "press_release":
        base = min(base, 0.72)
    elif kind == "analysis":
        base *= 0.94
    return max(0.0, min(1.0, round(base, 4)))


def _read_cache() -> dict[str, Any]:
    try:
        return json.loads(FEED_CACHE_PATH.read_text(encoding="utf-8")) if FEED_CACHE_PATH.exists() else {}
    except Exception:
        return {}


def _write_cache(cache: Mapping[str, Any]) -> None:
    FEED_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(str(FEED_CACHE_PATH) + ".tmp")
    temp.write_text(json.dumps(dict(cache), ensure_ascii=False), encoding="utf-8")
    temp.replace(FEED_CACHE_PATH)


def _fetch_feed_text(url: str) -> tuple[str, str, float]:
    now = time.time()
    with _CACHE_LOCK:
        cache = _read_cache()
        cached = dict(cache.get(url) or {})
        age = max(0.0, now - float(cached.get("cached_at") or 0.0))
        if cached.get("text") and age <= FEED_CACHE_TTL_SECONDS:
            return str(cached.get("text") or ""), "HIT", age

    import requests

    try:
        response = requests.get(
            url,
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={
                "User-Agent": "AI-Aksje-Analyzer/19.0.19 (+financial-news-feed; metadata-only)",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
            },
        )
        response.raise_for_status()
        content = response.content
        text = content.decode(getattr(response, "encoding", None) or "utf-8", errors="replace")
        # Reject HTML challenge/paywall pages masquerading as HTTP 200.
        if "<rss" not in text[:1000].casefold() and "<feed" not in text[:1000].casefold() and "<rdf:rdf" not in text[:1000].casefold():
            raise ValueError("Svaret var ikke RSS/Atom XML")
        with _CACHE_LOCK:
            cache = _read_cache()
            cache[url] = {"cached_at": now, "text": text, "last_error": ""}
            _write_cache(cache)
        return text, "MISS", 0.0
    except Exception as exc:
        if cached.get("text") and age <= FEED_STALE_MAX_SECONDS:
            with _CACHE_LOCK:
                cache = _read_cache()
                cache[url] = {**cached, "last_error": str(exc)[:300], "last_error_at": now}
                _write_cache(cache)
            return str(cached.get("text") or ""), "STALE_FALLBACK", age
        raise


def _clean_markup(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _local_name(tag: str) -> str:
    return str(tag or "").split("}")[-1].split(":")[-1].casefold()


def _value(item: ElementTree.Element, *names: str) -> str:
    wanted = {name.casefold() for name in names}
    for node in list(item):
        if _local_name(node.tag) not in wanted:
            continue
        if _local_name(node.tag) == "link" and node.attrib.get("href"):
            return str(node.attrib.get("href") or "").strip()
        return _clean_markup("".join(node.itertext()))
    return ""


def _categories(item: ElementTree.Element) -> list[str]:
    rows: list[str] = []
    for node in list(item):
        if _local_name(node.tag) != "category":
            continue
        value = node.attrib.get("term") or "".join(node.itertext())
        cleaned = _clean_markup(value)
        if cleaned:
            rows.append(cleaned)
    return rows


def _matches_tokens(title: str, summary: str, tokens: Sequence[str]) -> bool:
    cleaned = _normalize_text(f"{title} {summary}")
    valid = [_normalize_text(token) for token in tokens if len(_normalize_text(token)) >= 2]
    return not valid or any(token in cleaned for token in valid)


def fetch_rss_source(spec: Mapping[str, Any], tokens: Sequence[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    primary_url = str(spec.get("url") or "").strip()
    urls = [primary_url] + [str(value or "").strip() for value in spec.get("fallback_urls") or []]
    urls = list(dict.fromkeys(value for value in urls if value))
    if not urls:
        raise ValueError("RSS-adresse mangler")
    publisher = str(spec.get("publisher") or spec.get("label") or "RSS")
    failures: list[str] = []
    for url_index, url in enumerate(urls):
        try:
            text, cache_status, cache_age_seconds = _fetch_feed_text(url)
            root = ElementTree.fromstring(text.encode("utf-8", errors="replace"))
            rows: list[dict[str, Any]] = []
            items = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
            for item in items[:MAX_FEED_ITEMS]:
                title = _value(item, "title")
                summary = _value(item, "description", "summary", "content", "encoded")
                if not title or not _matches_tokens(title, summary, tokens):
                    continue
                categories = _categories(item)
                article_type = classify_article(
                    title,
                    summary,
                    categories,
                    default=str(spec.get("article_type_default") or "news"),
                )
                source_node = _value(item, "source")
                original_publisher = source_node or publisher
                row_url = _value(item, "link", "guid", "id")
                rows.append({
                    "title": title,
                    "summary": summary,
                    "url": row_url,
                    "publisher": original_publisher,
                    "original_publisher": original_publisher,
                    "collector_source": str(spec.get("label") or publisher),
                    "source_id": str(spec.get("id") or "rss"),
                    "source_role": str(spec.get("source_role") or "PUBLISHED_NEWS"),
                    "published_at": _value(item, "pubdate", "published", "updated", "date"),
                    "verification": "PUBLISHED_SOURCE",
                    "article_type": article_type,
                    "categories": categories,
                    "source_quality_override": spec.get("quality_override"),
                })
            return rows, {
                "cache_status": cache_status,
                "cache_age_seconds": round(cache_age_seconds, 1),
                "feed_items_scanned": min(len(items), MAX_FEED_ITEMS),
                "feed_url": url,
                "fallback_used": url_index > 0,
                "fallback_failures": failures,
            }
        except Exception as exc:
            failures.append(f"{url}: {type(exc).__name__}: {exc}"[:500])
    raise RuntimeError("Alle RSS-adresser feilet: " + " | ".join(failures))



def source_health_snapshot() -> list[dict[str, Any]]:
    now = time.time()
    with _CACHE_LOCK:
        cache = _read_cache()
    rows: list[dict[str, Any]] = []
    for market, specs in SOURCE_REGISTRY.items():
        for spec in specs:
            entry = dict(cache.get(str(spec.get("url") or "")) or {})
            age = max(0.0, now - float(entry.get("cached_at") or 0.0)) if entry else None
            rows.append({
                "id": spec.get("id"),
                "market": market,
                "publisher": spec.get("publisher"),
                "label": spec.get("label"),
                "url": spec.get("url"),
                "enabled": source_enabled(str(spec.get("id") or "")),
                "source_role": spec.get("source_role"),
                "cached": bool(entry.get("text")),
                "cache_age_seconds": round(age, 1) if age is not None else None,
                "last_error": str(entry.get("last_error") or ""),
            })
    return rows


# Backwards-compatible tuple view used by older diagnostics/tests.
DEFAULT_RSS_FEEDS = {
    market: [(str(spec.get("label") or spec.get("publisher")), str(spec.get("url") or "")) for spec in specs]
    for market, specs in SOURCE_REGISTRY.items()
}


__all__ = [
    "VERSION", "SOURCE_REGISTRY", "DEFAULT_RSS_FEEDS", "source_specs", "source_enabled",
    "source_quality", "query_tokens", "canonical_title", "classify_article",
    "fetch_rss_source", "source_health_snapshot", "FEED_CACHE_PATH",
]
