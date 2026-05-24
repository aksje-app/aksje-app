from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import quote_plus

from actor_registry import load_actor_registry, match_actor_text, normalize_actor_row
from nordic_market_sources import market_family, ticker_root


NORDIC_MARKETS = {"Norge", "Sverige", "Danmark", "Finland", "Norden"}

OFFICIAL_SOURCE_TERMS = {
    "Norge": [
        ("NewsWeb", "site:newsweb.oslobors.no {root} {name} primærinnsider OR flagging"),
        ("NewsWeb", "site:newsweb.oslobors.no {root} {name} meldepliktig handel"),
        ("Finansaviser", "{root} {name} primærinnsider flagging storaksjonær"),
    ],
    "Sverige": [
        ("Finansinspektionen", "{root} {name} insynshandel flaggning"),
        ("Nasdaq Nordic", "site:nasdaqomxnordic.com {root} {name} company announcement"),
        ("Finansaviser", "{root} {name} insynspersoner storägare"),
    ],
    "Danmark": [
        ("Nasdaq Nordic", "site:nasdaqomxnordic.com {root} {name} selskabsmeddelelse"),
        ("OAM Danmark", "{root} {name} ledende medarbejdere insider"),
        ("Finansaviser", "{root} {name} storaktionær ledende medarbejdere"),
    ],
    "Finland": [
        ("Nasdaq Nordic", "site:nasdaqomxnordic.com {root} {name} managers transactions"),
        ("FIN-FSA", "{root} {name} managers transactions flagging"),
        ("Finansaviser", "{root} {name} sisäpiiri omistus"),
    ],
}

SOURCE_DOMAINS = {
    "Norge": ["newsweb.oslobors.no", "dn.no", "finansavisen.no", "e24.no"],
    "Sverige": ["fi.se", "di.se", "placera.se", "nasdaqomxnordic.com"],
    "Danmark": ["nasdaqomxnordic.com", "finanstilsynet.dk", "borsen.dk", "marketwire.dk"],
    "Finland": ["nasdaqomxnordic.com", "finanssivalvonta.fi", "kauppalehti.fi", "inderes.fi"],
}

INSIDER_WORDS = (
    "primærinnsider",
    "primarinnsider",
    "meldepliktig handel",
    "insynshandel",
    "ledende medarbejdere",
    "managers transactions",
    "insider",
)

OWNER_WORDS = (
    "flagging",
    "flaggning",
    "storaksjonær",
    "storaksjonar",
    "storägare",
    "storaktionær",
    "ownership",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def _market(row: Mapping[str, Any]) -> str:
    ticker = _clean(row.get("ticker")).upper()
    market = _clean(row.get("market"))
    family = market_family(ticker, market)
    if family in {"Norge", "Sverige", "Danmark", "Finland"}:
        return family
    if family == "Norden":
        return "Norden"
    return family


def _actor_queries(row: Mapping[str, Any], *, max_actor_queries: int = 5) -> list[tuple[str, str]]:
    ticker = _clean(row.get("ticker")).upper()
    market = _market(row)
    name = _clean(row.get("name") or row.get("company"))
    root = ticker_root(ticker)
    queries: list[tuple[str, str]] = []
    try:
        rows = load_actor_registry()
    except Exception:
        rows = []
    for raw in rows:
        actor = normalize_actor_row(raw)
        if not actor.get("active"):
            continue
        actor_text = f"{actor.get('name') or ''} {actor.get('aliases') or ''}"
        if not match_actor_text(actor_text, market=market, ticker=ticker, rows=[actor]):
            continue
        alias = _clean((actor.get("aliases") or actor.get("name") or "").split(";")[0])
        if alias:
            queries.append(("Aktørregister", f'"{alias}" {root} {name} flagging insider eierandel'))
        if len(queries) >= max_actor_queries:
            break
    return queries


def build_nordic_actor_search_plan(
    row: Mapping[str, Any],
    *,
    include_insider: bool = True,
    include_news: bool = True,
    max_actor_queries: int = 5,
) -> list[dict[str, Any]]:
    ticker = _clean(row.get("ticker")).upper()
    if not ticker:
        return []
    market = _market(row)
    if market == "Norden":
        market = market_family(ticker, row.get("market"))
    if market not in NORDIC_MARKETS:
        return []
    name = _clean(row.get("name") or row.get("company"))
    root = ticker_root(ticker)
    templates = OFFICIAL_SOURCE_TERMS.get(market, [])
    plan: list[dict[str, Any]] = []
    for source, template in templates:
        query = template.format(root=root, name=name or root)
        plan.append({
            "type": "offisiell/gratis",
            "source": source,
            "market": market,
            "query": query,
            "url": _search_url(query),
            "api_cost": 0,
            "status": "søkelink/diagnostikk, ikke hentet automatisk",
        })
    if include_insider or include_news:
        for source, query in _actor_queries(row, max_actor_queries=max_actor_queries):
            plan.append({
                "type": "aktørregister",
                "source": source,
                "market": market,
                "query": query,
                "url": _search_url(query),
                "api_cost": 0,
                "status": "aktørstyrt søkelink",
            })
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in plan:
        marker = _clean(item.get("query")).lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out[:10]


def _call_news_provider(news_provider: Callable[..., tuple[Iterable[Mapping[str, Any]], Any]], query: str, *, days_back: int, domains: Sequence[str]) -> tuple[list[Mapping[str, Any]], Any]:
    try:
        articles, error = news_provider(query, limit=4, source="manual", days_back=days_back, language=None, domains=",".join(domains[:8]))
    except TypeError:
        try:
            articles, error = news_provider(query, limit=4, source="manual", days_back=days_back)
        except TypeError:
            articles, error = news_provider(query, 4)
    return list(articles or []), error


def _article_text(article: Mapping[str, Any]) -> str:
    return " ".join(str(article.get(key) or "") for key in ("title", "description", "content", "source")).lower()


def search_nordic_actor_insider(
    row: Mapping[str, Any],
    *,
    news_provider: Callable[..., tuple[Iterable[Mapping[str, Any]], Any]] | None = None,
    days_back: int = 93,
    include_insider: bool = True,
    include_news: bool = True,
    max_newsapi_queries: int = 1,
) -> dict[str, Any]:
    plan = build_nordic_actor_search_plan(row, include_insider=include_insider, include_news=include_news)
    diagnostics = [
        {
            "type": "nordisk-aktør/insider",
            "title": item["query"],
            "source": item["source"],
            "status": item["status"],
            "window": f"{days_back} dager",
            "detail": "Gratis/offisiell eller manuell søkelenke. Skiller diagnostikk fra faktisk hentet evidence.",
            "url": item["url"],
        }
        for item in plan
    ]
    articles: list[dict[str, Any]] = []
    actor_evidence: list[dict[str, Any]] = []
    insider_evidence: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    errors: list[str] = []
    market = _market(row)
    ticker = _clean(row.get("ticker")).upper()
    domains = SOURCE_DOMAINS.get(market, [])
    if news_provider is not None and max_newsapi_queries > 0:
        for item in plan[:max_newsapi_queries]:
            found, error = _call_news_provider(news_provider, item["query"], days_back=days_back, domains=domains)
            for diag in diagnostics:
                if diag.get("title") == item["query"]:
                    diag["status"] = f"NewsAPI søkt, {len(found)} treff"
                    diag["detail"] = f"{diag.get('detail')} | NewsAPI request brukt for shortlist/cache."
                    break
            if error:
                errors.append(str(error)[:180])
            for article in found:
                if not isinstance(article, Mapping):
                    continue
                normalized = {
                    "title": _clean(article.get("title") or article.get("headline") or "Uten tittel"),
                    "description": _clean(article.get("description") or article.get("summary")),
                    "source": _clean(article.get("source") or article.get("publisher") or "Nordisk søk"),
                    "url": _clean(article.get("url") or article.get("link")),
                    "published": _clean(article.get("published") or article.get("publishedAt") or article.get("date")),
                }
                articles.append(normalized)
                text = _article_text(normalized)
                actor_matches = match_actor_text(text, market=market, ticker=ticker)
                for actor in actor_matches:
                    actor_name = actor.get("name") or actor.get("matched_alias") or "Ukjent aktor"
                    actor_evidence.append({
                        "type": actor.get("actor_type") or "Bjellesau",
                        "title": f"Fant bjellesau: {actor_name}",
                        "source": normalized["source"],
                        "published": normalized["published"],
                        "url": normalized["url"],
                        "detail": f"Matchet aktørregister-alias '{actor.get('matched_alias')}' i nordisk søk: {normalized['title']}",
                        "actor": actor_name,
                        "actor_type": actor.get("actor_type"),
                        "matched_alias": actor.get("matched_alias"),
                        "strength": actor.get("strength"),
                        "found_by": "Nordic Actor/Insider Search",
                    })
                if not actor_matches and any(word in text for word in OWNER_WORDS + INSIDER_WORDS):
                    unmatched.append({
                        "name": normalized["title"][:120],
                        "source": normalized["source"],
                        "url": normalized["url"],
                        "reason": "Kildeord funnet, men ingen aktiv aktor/alias matchet",
                        "ticker_hint": ticker,
                    })
                if any(word in text for word in INSIDER_WORDS):
                    insider_evidence.append({
                        "type": "Insider",
                        "title": normalized["title"],
                        "source": normalized["source"],
                        "published": normalized["published"],
                        "url": normalized["url"],
                        "detail": "Nordisk søk fant insider-/primærinnsiderord. Bekreft originalkilden manuelt.",
                        "actor": "Insider",
                        "found_by": "Nordic Actor/Insider Search",
                    })
                if any(word in text for word in OWNER_WORDS):
                    insider_evidence.append({
                        "type": "Flagging/eier",
                        "title": normalized["title"],
                        "source": normalized["source"],
                        "published": normalized["published"],
                        "url": normalized["url"],
                        "detail": "Nordisk søk fant flagging-/eierord. Bekreft originalkilden manuelt.",
                        "actor": "Eier",
                        "found_by": "Nordic Actor/Insider Search",
                    })
    return {
        "plan": plan,
        "diagnostics": diagnostics,
        "articles": articles[:12],
        "actor_evidence": actor_evidence[:10],
        "insider_evidence": insider_evidence[:10],
        "unmatched": unmatched[:12],
        "errors": errors[:4],
        "newsapi_requests_used": min(max_newsapi_queries, len(plan)) if news_provider is not None else 0,
        "free_official_queries": len([item for item in plan if int(item.get("api_cost") or 0) == 0]),
    }


__all__ = [
    "build_nordic_actor_search_plan",
    "search_nordic_actor_insider",
]
