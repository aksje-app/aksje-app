from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from runtime_env import data_source_env_status
from runtime_env import redact_secrets
from source_budget import NEWSAPI_DAILY_FREE_LIMIT


MARKET_DIAGNOSTIC_TICKERS = {
    "USA": "AAPL",
    "Norge": "EQNR.OL",
    "Sverige": "VOLV-B.ST",
    "Danmark": "NOVO-B.CO",
    "Finland": "NOKIA.HE",
}


def horizon_to_months(horizon: str | None) -> int:
    text = str(horizon or "3m").strip().lower()
    mapping = {"1m": 1, "3m": 3, "6m": 6, "12m": 12}
    return mapping.get(text, 3)


def horizon_to_days(horizon: str | None) -> int:
    return max(31, horizon_to_months(horizon) * 31)


def build_data_source_status(horizon: str | None = None) -> list[dict[str, Any]]:
    env = data_source_env_status()
    months = horizon_to_months(horizon)
    news_cache_entries = 0
    news_auto = False
    try:
        from news import newsapi_status

        news_status = newsapi_status()
        news_cache_entries = int(news_status.get("cache_entries") or 0)
        news_auto = bool(news_status.get("auto_calls_allowed"))
    except Exception:
        pass
    sources = env.get("env_sources") or []
    any_key = bool(env.get("finnhub_key") or env.get("newsapi_key"))
    if sources:
        source_note = "env-fil lest"
        detail = f"{len(sources)} env-fil(er) funnet"
    elif any_key:
        source_note = "nokler i miljo"
        detail = "aktive API-nokler finnes, env-fil ikke identifisert"
    else:
        source_note = "ikke funnet"
        detail = "0 env-fil(er) og ingen API-nokler funnet"
    return [
        {
            "Kilde": "Miljo/API-nokler",
            "Status": source_note,
            "Detalj": detail,
            "Vindu": "-",
        },
        {
            "Kilde": "Finnhub insider",
            "Status": "nokkel funnet" if env.get("finnhub_key") else "nokkel mangler",
            "Detalj": "insider-transactions",
            "Vindu": f"{months} mnd",
        },
        {
            "Kilde": "Finnhub earnings",
            "Status": "nokkel funnet" if env.get("finnhub_key") else "nokkel mangler",
            "Detalj": "earnings calendar",
            "Vindu": f"{months} mnd frem",
        },
        {
            "Kilde": "NewsAPI",
            "Status": "nokkel funnet" if env.get("newsapi_key") else "nokkel mangler",
            "Detalj": f"global nyhetskilde, cache {news_cache_entries}, auto {'paa' if news_auto else 'av'}",
            "Vindu": f"{horizon_to_days(horizon)} dager",
        },
        {
            "Kilde": "NewsAPI budsjett",
            "Status": "planlegges per Kjor",
            "Detalj": f"gratisnivaa er normalt {NEWSAPI_DAILY_FREE_LIMIT} requests/dag; en request er ett query-kall, ikke antall tickere i teksten",
            "Vindu": "cache for gjenbruk",
        },
        {
            "Kilde": "Nordiske/offisielle sok",
            "Status": "gratis sokelenker",
            "Detalj": "NewsWeb, Finansinspektionen, Nasdaq Nordic, OAM, FIN-FSA og CVM vises som diagnostikk/lenker til manuell bekreftelse",
            "Vindu": f"{horizon_to_days(horizon)} dager",
        },
        {
            "Kilde": "Open web",
            "Status": "gratis web-sok ved Kjor",
            "Detalj": "GDELT og Google News RSS uten lokal API-nokkel; brukes bare under eksplisitt radarkjoring",
            "Vindu": f"{min(horizon_to_days(horizon), 90)} dager",
        },
        {
            "Kilde": "Aktorregister",
            "Status": "lokal matching",
            "Detalj": "aktivt register brukes til alias/person/fond/holdingselskap for insider- og bjellesau-spor",
            "Vindu": "-",
        },
    ]


def _safe_error(value: Any) -> str:
    text = redact_secrets(value).strip()
    if not text:
        return ""
    return text[:160]


def summarize_source_error(label: str, error: Any) -> str:
    text = redact_secrets(error).strip()
    if not text:
        return ""
    low = text.lower()
    label = str(label or "kilde").strip()
    if "too many requests" in low or "rate limit" in low or "quota" in low:
        return f"{label}: API-kvote brukt opp"
    if "403" in low or "forbidden" in low:
        return f"{label}: ikke tilgang/dekning for valgt marked"
    if "mangler" in low and ("key" in low or "nokkel" in low or "nøkkel" in low):
        return f"{label}: API-nokkel mangler"
    if "connectionerror" in low or "max retries" in low or "temporarily unavailable" in low:
        return f"{label}: nettverk/API midlertidig utilgjengelig"
    if "unsupported" in low or "not supported" in low:
        return f"{label}: ticker/marked ikke stottet"
    return f"{label}: {text[:90]}"


def probe_market_data_sources(
    *,
    horizon: str | None = None,
    insider_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    earnings_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    news_provider: Callable[..., Any] | None = None,
    markets: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    months = horizon_to_months(horizon)
    days = horizon_to_days(horizon)
    selected_markets = list(markets or MARKET_DIAGNOSTIC_TICKERS.keys())
    rows: list[dict[str, Any]] = []
    for market in selected_markets:
        ticker = MARKET_DIAGNOSTIC_TICKERS.get(market, str(market))
        row: dict[str, Any] = {
            "Marked": market,
            "Ticker": ticker,
            "Insider": "ikke testet",
            "Earnings": "ikke testet",
            "Nyheter": "ikke testet",
            "Forklaring": "",
        }
        notes: list[str] = []
        if insider_provider is not None:
            try:
                insider = insider_provider(ticker, months=months)
                count = int((insider or {}).get("transactions") or len((insider or {}).get("latest_transactions") or []))
                error = _safe_error((insider or {}).get("error"))
                row["Insider"] = f"{count} treff" if count else "0 treff"
                if error:
                    notes.append(summarize_source_error("insider", error))
            except TypeError:
                try:
                    insider = insider_provider(ticker)
                    count = int((insider or {}).get("transactions") or len((insider or {}).get("latest_transactions") or []))
                    row["Insider"] = f"{count} treff" if count else "0 treff"
                except Exception as exc:
                    row["Insider"] = "API feilet"
                    notes.append(f"insider: {type(exc).__name__}")
            except Exception as exc:
                row["Insider"] = "API feilet"
                notes.append(f"insider: {type(exc).__name__}")
        if earnings_provider is not None:
            try:
                earnings = earnings_provider(ticker, months=months)
                days_until = (earnings or {}).get("days_until")
                error = _safe_error((earnings or {}).get("error"))
                row["Earnings"] = f"{days_until} dager" if days_until is not None else "0 treff"
                if error:
                    notes.append(summarize_source_error("earnings", error))
            except TypeError:
                try:
                    earnings = earnings_provider(ticker)
                    days_until = (earnings or {}).get("days_until")
                    row["Earnings"] = f"{days_until} dager" if days_until is not None else "0 treff"
                except Exception as exc:
                    row["Earnings"] = "API feilet"
                    notes.append(f"earnings: {type(exc).__name__}")
            except Exception as exc:
                row["Earnings"] = "API feilet"
                notes.append(f"earnings: {type(exc).__name__}")
        if news_provider is not None:
            try:
                articles, error = news_provider(ticker, limit=3, source="manual", days_back=days)
                count = len(list(articles or []))
                row["Nyheter"] = f"{count} treff" if count else "0 treff"
                if error:
                    notes.append(summarize_source_error("news", error))
            except TypeError:
                try:
                    articles, error = news_provider(ticker, 3)
                    count = len(list(articles or []))
                    row["Nyheter"] = f"{count} treff" if count else "0 treff"
                    if error:
                        notes.append(summarize_source_error("news", error))
                except Exception as exc:
                    row["Nyheter"] = "API feilet"
                    notes.append(f"news: {type(exc).__name__}")
            except Exception as exc:
                row["Nyheter"] = "API feilet"
                notes.append(f"news: {type(exc).__name__}")
        row["Forklaring"] = " | ".join(notes) if notes else "OK/ingen feilmelding"
        rows.append(row)
    return rows


__all__ = [
    "MARKET_DIAGNOSTIC_TICKERS",
    "build_data_source_status",
    "horizon_to_days",
    "horizon_to_months",
    "probe_market_data_sources",
    "summarize_source_error",
]
