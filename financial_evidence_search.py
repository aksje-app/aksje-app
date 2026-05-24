from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import quote_plus

from actor_registry import actor_roles, load_actor_registry, match_actor_text, record_actor_hits
from nordic_market_sources import local_news_queries, market_family, ticker_root
from open_web_news_search import search_open_web_articles


FINANCIAL_DOMAINS = {
    "Norge": ["dn.no", "finansavisen.no", "e24.no", "newsweb.oslobors.no"],
    "Sverige": ["di.se", "placera.se", "borsvarlden.com", "nasdaqomxnordic.com"],
    "Danmark": ["borsen.dk", "euroinvestor.dk", "marketwire.dk", "nasdaqomxnordic.com"],
    "Finland": ["inderes.fi", "kauppalehti.fi", "globenewswire.com", "nasdaqomxnordic.com"],
    "Brasil": ["valor.globo.com", "infomoney.com.br", "rad.cvm.gov.br"],
    "USA": ["sec.gov", "marketwatch.com", "reuters.com", "bloomberg.com", "cnbc.com"],
}

INSIDER_KEYWORDS = (
    "primarinnsider",
    "primærinnsider",
    "primary insider",
    "insider transaction",
    "insynshandel",
    "ledende medarbejdere",
    "managers transactions",
)

OWNER_KEYWORDS = (
    "flagging",
    "flaggning",
    "major shareholder",
    "storaksjonar",
    "storaksjonær",
    "eierandel",
    "ownership",
    "acionista",
)

CATALYST_KEYWORDS = (
    "børsmelding",
    "borsmelding",
    "company announcement",
    "selskabsmeddelelse",
    "kontrakt",
    "contract",
    "order",
    "guidance",
    "guiding",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def _article_text(article: Mapping[str, Any]) -> str:
    return " ".join(str(article.get(key) or "") for key in ("title", "description", "content", "source")).lower()


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


def source_domains_for_market(ticker: str, market: str | None = None) -> list[str]:
    family = market_family(ticker, market)
    return list(FINANCIAL_DOMAINS.get(family, FINANCIAL_DOMAINS.get("USA", [])))


def build_financial_search_plan(row: Mapping[str, Any], *, max_actor_queries: int = 3) -> list[dict[str, str]]:
    ticker = _clean(row.get("ticker")).upper()
    if not ticker:
        return []
    name = _clean(row.get("name") or row.get("company"))
    market = _clean(row.get("market"))
    family = market_family(ticker, market)
    root = ticker_root(ticker)
    actor_queries: list[str] = []
    generic_queries = list(local_news_queries(ticker, name, market))[:4]

    actor_rows = []
    try:
        actor_rows = load_actor_registry()
    except Exception:
        actor_rows = []
    added_actor_queries = 0
    actor_alias_pool: list[str] = []
    for actor in actor_rows:
        if not actor.get("active"):
            continue
        actor_text = f"{actor.get('name') or ''} {actor.get('aliases') or ''}".strip()
        if not actor_text:
            continue
        matches_market = match_actor_text(actor_text, market=market, ticker=ticker, rows=[actor])
        if not matches_market:
            continue
        for alias in _actor_aliases(actor, max_aliases=2):
            if alias.lower() not in {item.lower() for item in actor_alias_pool}:
                actor_alias_pool.append(alias)
            target = name or root
            actor_queries.append(f'"{alias}" "{target}" (flagging OR insider OR ownership OR aksjer)')
            actor_queries.append(f'"{alias}" {root} (kjop OR kjoper OR flagging OR insider OR eierandel)')
            added_actor_queries += 1
            if added_actor_queries >= max_actor_queries:
                break
        if added_actor_queries >= max_actor_queries:
            break
    if actor_alias_pool:
        alias_group = " OR ".join(f'"{alias}"' for alias in actor_alias_pool[:12])
        actor_queries.insert(0, f"({alias_group}) \"{name or root}\" (flagging OR insider OR ownership OR eierandel OR aksjer)")

    plan: list[dict[str, str]] = []
    seen: set[str] = set()
    domains = ", ".join(source_domains_for_market(ticker, market)[:4])
    for query in actor_queries + generic_queries:
        clean = _clean(query)
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        plan.append({
            "query": clean,
            "market": family,
            "domains": domains,
            "url": _search_url(clean),
        })
    return plan[:6]


def _call_news_provider(
    news_provider: Callable[..., tuple[Iterable[Mapping[str, Any]], Any]],
    query: str,
    *,
    days_back: int,
    domains: Sequence[str],
) -> tuple[list[Mapping[str, Any]], Any]:
    try:
        articles, error = news_provider(query, limit=4, source="manual", days_back=days_back, language=None, domains=",".join(domains[:8]))
    except TypeError:
        try:
            articles, error = news_provider(query, limit=4, source="manual", days_back=days_back)
        except TypeError:
            articles, error = news_provider(query, 4)
    return list(articles or []), error


def search_financial_evidence(
    row: Mapping[str, Any],
    *,
    news_provider: Callable[..., tuple[Iterable[Mapping[str, Any]], Any]] | None,
    days_back: int,
    max_queries: int = 4,
    use_open_web: bool = True,
    max_open_web_queries: int = 1,
) -> dict[str, Any]:
    plan = build_financial_search_plan(row)
    diagnostics: list[dict[str, Any]] = [
        {
            "type": "finanssok",
            "title": item["query"],
            "source": "Finans-/offisiell søkeplan",
            "status": "ikke kjørt",
            "window": f"{days_back} dager",
            "detail": f"Prioriterte domener: {item.get('domains') or '-'}",
            "url": item["url"],
        }
        for item in plan
    ]
    ticker = _clean(row.get("ticker")).upper()
    market = _clean(row.get("market"))
    domains = source_domains_for_market(ticker, market)
    articles: list[dict[str, Any]] = []
    actor_evidence: list[dict[str, Any]] = []
    insider_evidence: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_urls: set[str] = set()
    open_web_used = 0
    try:
        actor_rows_for_match = load_actor_registry()
    except Exception:
        actor_rows_for_match = []
    for item in plan[:max_queries]:
        found: list[Mapping[str, Any]] = []
        error = None
        if news_provider is not None:
            found, error = _call_news_provider(news_provider, item["query"], days_back=days_back, domains=domains)
        elif use_open_web:
            error = "NewsAPI mangler; bruker gratis web-søk"
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
                    diag["detail"] = f"{diag.get('detail') or ''} | Open web gratis søk: {len(web_found)} treff"
                    break
        for diag in diagnostics:
            if diag.get("title") == item["query"]:
                diag["status"] = f"søkt, {len(found or [])} treff"
                if error:
                    diag["detail"] = f"{diag.get('detail') or ''} | Feil/varsel: {str(error)[:120]}"
                break
        if error:
            errors.append(str(error)[:180])
        for article in found:
            if not isinstance(article, Mapping):
                continue
            url = _clean(article.get("url") or article.get("link"))
            marker = url or _clean(article.get("title")).lower()
            if marker and marker in seen_urls:
                continue
            seen_urls.add(marker)
            normalized = {
                "title": _clean(article.get("title") or article.get("headline") or "Uten tittel"),
                "description": _clean(article.get("description") or article.get("summary")),
                "source": _clean(article.get("source") or article.get("publisher") or article.get("site") or "Finanssøk"),
                "url": url,
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
                    "detail": f"Finanssøk matchet aktørregister-alias '{actor.get('matched_alias')}' i sak: {normalized['title']}",
                    "actor": actor_name,
                    "actor_type": actor.get("actor_type"),
                    "actor_roles": roles,
                    "matched_alias": actor.get("matched_alias"),
                    "strength": actor.get("strength"),
                    "trust_level": actor.get("trust_level"),
                    "found_by": "Financial Evidence Search",
                })
            record_actor_hits(actor_matches, ticker=ticker, market=market, source="Financial Evidence Search")
            if any(keyword in text for keyword in INSIDER_KEYWORDS):
                insider_evidence.append({
                    "type": "Insider",
                    "title": normalized["title"],
                    "source": normalized["source"],
                    "published": normalized["published"],
                    "url": normalized["url"],
                    "detail": "Finanssøk fant insider-/primærinnsiderord i tittel/beskrivelse. Bekreft originalkilden manuelt.",
                    "actor": "Insider",
                    "found_by": "Financial Evidence Search",
                })
    return {
        "articles": articles[:12],
        "actor_evidence": actor_evidence[:8],
        "insider_evidence": insider_evidence[:8],
        "diagnostics": diagnostics,
        "errors": errors[:4],
        "open_web_requests_used": open_web_used,
    }


__all__ = [
    "build_financial_search_plan",
    "search_financial_evidence",
    "source_domains_for_market",
]
