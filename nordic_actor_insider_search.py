from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import quote_plus

from actor_registry import actor_roles, load_actor_registry, match_actor_text, normalize_actor_row, record_actor_hits
from nordic_market_sources import market_family, ticker_root
from open_web_news_search import search_open_web_articles


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


def _actor_aliases(actor: Mapping[str, Any], *, max_aliases: int = 3) -> list[str]:
    raw = f"{actor.get('name') or ''}; {actor.get('aliases') or ''}"
    aliases: list[str] = []
    for part in raw.replace(",", ";").split(";"):
        alias = _clean(part)
        if len(alias) < 3:
            continue
        if alias.lower() not in {item.lower() for item in aliases}:
            aliases.append(alias)
        if len(aliases) >= max_aliases:
            break
    return aliases


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
    actor_alias_pool: list[str] = []
    for raw in rows:
        actor = normalize_actor_row(raw)
        if not actor.get("active"):
            continue
        actor_text = f"{actor.get('name') or ''} {actor.get('aliases') or ''}"
        if not match_actor_text(actor_text, market=market, ticker=ticker, rows=[actor]):
            continue
        for alias in _actor_aliases(actor, max_aliases=2):
            if alias.lower() not in {item.lower() for item in actor_alias_pool}:
                actor_alias_pool.append(alias)
            queries.append(("Aktørregister", f'"{alias}" "{name or root}" (flagging OR insider OR eierandel OR aksjer)'))
            queries.append(("Aktørregister", f'"{alias}" {root} (kjøp OR kjøper OR flagging OR primærinnsider OR insynshandel)'))
            if len(queries) >= max_actor_queries:
                break
        if len(queries) >= max_actor_queries:
            break
    if actor_alias_pool:
        alias_group = " OR ".join(f'"{alias}"' for alias in actor_alias_pool[:12])
        queries.insert(0, ("Aktørregister", f"({alias_group}) \"{name or root}\" (flagging OR insider OR eierandel OR aksjer)"))
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
    use_open_web: bool = True,
    max_open_web_queries: int = 2,
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
    try:
        actor_rows_for_match = load_actor_registry()
    except Exception:
        actor_rows_for_match = []
    open_web_used = 0
    executed_queries = max(max_newsapi_queries if news_provider is not None else 0, max_open_web_queries if use_open_web else 0)
    if executed_queries > 0:
        for index, item in enumerate(plan[:executed_queries]):
            found: list[Mapping[str, Any]] = []
            error = None
            if news_provider is not None and index < max_newsapi_queries:
                found, error = _call_news_provider(news_provider, item["query"], days_back=days_back, domains=domains)
            for diag in diagnostics:
                if diag.get("title") == item["query"]:
                    if news_provider is not None and index < max_newsapi_queries:
                        diag["status"] = f"NewsAPI søkt, {len(found)} treff"
                        diag["detail"] = f"{diag.get('detail')} | NewsAPI request brukt for shortlist/cache."
                    break
            if error:
                errors.append(str(error)[:180])
            if use_open_web and open_web_used < max_open_web_queries and len(found or []) < 2:
                web_found, web_error = search_open_web_articles(
                    item["query"],
                    days_back=days_back,
                    limit=4,
                    domains=domains,
                )
                open_web_used += 1
                if web_found:
                    found = list(found or []) + web_found
                if web_error:
                    errors.append(web_error[:180])
                for diag in diagnostics:
                    if diag.get("title") == item["query"]:
                        old = str(diag.get("detail") or "")
                        if news_provider is not None and index < max_newsapi_queries:
                            diag["status"] = f"NewsAPI+open web søkt, {len(found)} treff"
                        else:
                            diag["status"] = f"Open web søkt, {len(found)} treff"
                        diag["detail"] = f"{old} | Open web gratis søk: {len(web_found)} treff"
                        break
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
                actor_matches = match_actor_text(text, market=market, ticker=ticker, rows=actor_rows_for_match)
                if not actor_matches:
                    actor_matches = match_actor_text(item["query"], market=market, ticker=ticker, rows=actor_rows_for_match)
                for actor in actor_matches:
                    actor_name = actor.get("name") or actor.get("matched_alias") or "Ukjent aktor"
                    roles = actor_roles(actor)
                    title_prefix = "Fant bjellesau/insider-watch" if {"Bjellesau", "Insider watch"} <= set(roles) else "Fant bjellesau" if "Bjellesau" in roles else "Fant insider-watch" if "Insider watch" in roles else "Fant aktor"
                    actor_evidence.append({
                        "type": " + ".join(roles),
                        "title": f"{title_prefix}: {actor_name}",
                        "source": normalized["source"],
                        "published": normalized["published"],
                        "url": normalized["url"],
                        "detail": f"Matchet aktørregister-alias '{actor.get('matched_alias')}' i nordisk søk: {normalized['title']}",
                        "actor": actor_name,
                        "actor_type": actor.get("actor_type"),
                        "actor_roles": roles,
                        "matched_alias": actor.get("matched_alias"),
                        "strength": actor.get("strength"),
                        "trust_level": actor.get("trust_level"),
                        "found_by": "Nordic Actor/Insider Search",
                    })
                record_actor_hits(actor_matches, ticker=ticker, market=market, source="Nordic Actor/Insider Search")
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
        "open_web_requests_used": open_web_used,
        "free_official_queries": len([item for item in plan if int(item.get("api_cost") or 0) == 0]),
    }


__all__ = [
    "build_nordic_actor_search_plan",
    "search_nordic_actor_insider",
]
