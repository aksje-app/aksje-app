from __future__ import annotations

from typing import Any, Mapping, Sequence


NEWSAPI_DAILY_FREE_LIMIT = 100


def _bool(value: Any) -> bool:
    return bool(value)


def estimate_source_budget(
    *,
    planned_tickers: int,
    source_values: Mapping[str, Any] | None = None,
    max_newsapi_per_ticker: int = 1,
    max_financial_newsapi_per_ticker: int = 2,
) -> dict[str, Any]:
    source_values = dict(source_values or {})
    planned = max(0, int(planned_tickers or 0))
    news_on = _bool(source_values.get("news"))
    insider_on = _bool(source_values.get("insider"))
    results_on = _bool(source_values.get("results"))
    macro_on = _bool(source_values.get("macro"))
    newsapi_calls = planned * max_newsapi_per_ticker if news_on else 0
    financial_calls = planned * max_financial_newsapi_per_ticker if (news_on or insider_on) else 0
    free_official = planned * (5 if insider_on else 2 if news_on else 0)
    open_web_calls = planned * (3 if (news_on or insider_on) else 0)
    actor_registry = planned if (news_on or insider_on) else 0
    finansavisen_overlay = planned if insider_on else 0
    cache_entries = 0
    has_newsapi_key = False
    try:
        from news import newsapi_status

        status = newsapi_status()
        cache_entries = int(status.get("cache_entries") or 0)
        has_newsapi_key = bool(status.get("has_key"))
    except Exception:
        pass
    return {
        "planned_tickers": planned,
        "score_calls": planned,
        "newsapi_calls": newsapi_calls,
        "financial_newsapi_calls": financial_calls,
        "newsapi_total": newsapi_calls + financial_calls,
        "newsapi_daily_free_limit": NEWSAPI_DAILY_FREE_LIMIT,
        "newsapi_has_key": has_newsapi_key,
        "newsapi_cache_entries": cache_entries,
        "free_official_queries": free_official,
        "search_engine_links": free_official,
        "open_web_calls": open_web_calls,
        "open_web_gdelt_calls": open_web_calls,
        "actor_registry_checks": actor_registry,
        "finansavisen_overlay_checks": finansavisen_overlay,
        "finnhub_insider_calls": planned if insider_on else 0,
        "finnhub_earnings_calls": planned if results_on else 0,
        "macro_proxy_calls": 1 if macro_on else 0,
        "cache_policy": "NewsAPI bruker cache per query/limit/sprak/domene; samme cachetreff bruker ikke ny request.",
    }


def source_budget_text(budget: Mapping[str, Any]) -> str:
    return (
        f"score {budget.get('score_calls', 0)}, "
        f"gratis/offisielle sok {budget.get('free_official_queries', 0)}, "
        f"open web maks {budget.get('open_web_calls', budget.get('open_web_gdelt_calls', 0))}, "
        f"aktorregister {budget.get('actor_registry_checks', 0)}, "
        f"Finansavisen lokalt {budget.get('finansavisen_overlay_checks', 0)}, "
        f"NewsAPI planlagt maks {budget.get('newsapi_total', 0)}/{budget.get('newsapi_daily_free_limit', NEWSAPI_DAILY_FREE_LIMIT)} daglig gratisgrense, "
        f"cache {budget.get('newsapi_cache_entries', 0)}, "
        f"Finnhub insider {budget.get('finnhub_insider_calls', 0)}, "
        f"earnings {budget.get('finnhub_earnings_calls', 0)}, "
        f"makro/proxy {budget.get('macro_proxy_calls', 0)}"
    )


def source_budget_rows(budget: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"Kilde": "Gratis/offisielle sok", "Planlagt": budget.get("free_official_queries", 0), "Kost": "0 API-kall", "Bruk": "NewsWeb/OAM/FI/Nasdaq/SEC/Google-lenker"},
        {"Kilde": "Open web", "Planlagt": budget.get("open_web_calls", budget.get("open_web_gdelt_calls", 0)), "Kost": "gratis offentlige kilder", "Bruk": "GDELT/Google News RSS for aktor-/ticker-sok nar NewsAPI ikke finner nok"},
        {"Kilde": "Aktørregister", "Planlagt": budget.get("actor_registry_checks", 0), "Kost": "0 API-kall", "Bruk": "Alias/person/holdingselskap mot ticker/marked"},
        {"Kilde": "Finansavisen Bjellesauer", "Planlagt": budget.get("finansavisen_overlay_checks", 0), "Kost": "0 API-kall", "Bruk": "Lokalt importert XLSX-snapshot med bjellesau-handler"},
        {"Kilde": "NewsAPI", "Planlagt": budget.get("newsapi_total", 0), "Kost": f"teller mot {budget.get('newsapi_daily_free_limit', NEWSAPI_DAILY_FREE_LIMIT)}/dag", "Bruk": f"Kun shortlist/cache der mulig. Cache entries: {budget.get('newsapi_cache_entries', 0)}"},
        {"Kilde": "Finnhub insider", "Planlagt": budget.get("finnhub_insider_calls", 0), "Kost": "Finnhub-kvote", "Bruk": "USA/der API dekker"},
        {"Kilde": "Finnhub earnings", "Planlagt": budget.get("finnhub_earnings_calls", 0), "Kost": "Finnhub-kvote", "Bruk": "Resultatkalender"},
        {"Kilde": "Makro/proxy", "Planlagt": budget.get("macro_proxy_calls", 0), "Kost": "cache/proxy", "Bruk": "Felles snapshot per kjøring"},
    ]


__all__ = [
    "NEWSAPI_DAILY_FREE_LIMIT",
    "estimate_source_budget",
    "source_budget_rows",
    "source_budget_text",
]
