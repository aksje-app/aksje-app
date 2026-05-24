from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from alpha_radar_ownership import classify_ownership_item, split_ownership_evidence
from data_source_diagnostics import horizon_to_days, horizon_to_months

try:
    from actor_registry import actor_aliases_for_matching, match_actor_text
except Exception:  # pragma: no cover - optional UI registry
    actor_aliases_for_matching = None
    match_actor_text = None

try:
    from nordic_market_sources import local_market_source_diagnostics, local_news_queries, merge_source_diagnostics
except Exception:  # pragma: no cover - optional source diagnostics
    local_market_source_diagnostics = None
    local_news_queries = None
    merge_source_diagnostics = None

try:
    from financial_evidence_search import search_financial_evidence
except Exception:  # pragma: no cover - optional financial search
    search_financial_evidence = None

try:
    from nordic_actor_insider_search import search_nordic_actor_insider
except Exception:  # pragma: no cover - optional nordic search
    search_nordic_actor_insider = None

try:
    from evidence_ledger import build_evidence_ledger
except Exception:  # pragma: no cover - optional evidence ledger
    build_evidence_ledger = None

try:
    from nbim_radar import apply_nbim_overlay
except Exception:  # pragma: no cover - optional NBIM overlay
    apply_nbim_overlay = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover - depends on runtime
    yf = None

try:
    from news import get_news, simple_finance_sentiment
except Exception:  # pragma: no cover - import guard for static tests
    get_news = None

    def simple_finance_sentiment(_articles):
        return 0.5


COMMODITY_PROXIES = {
    "brent_oil": "BZ=F",
    "wti_oil": "CL=F",
    "natural_gas": "NG=F",
    "copper": "HG=F",
    "gold": "GC=F",
    "silver": "SI=F",
    "usd_nok": "USDNOK=X",
    "usd_sek": "USDSEK=X",
    "usd_brl": "USDBRL=X",
    "rates_10y": "^TNX",
    "shipping_drybulk": "BDRY",
}

THEME_PROXY_MAP = {
    "oil_service": ("brent_oil", "wti_oil"),
    "energy": ("brent_oil", "wti_oil", "natural_gas"),
    "gas": ("natural_gas",),
    "metals": ("copper", "silver"),
    "gold": ("gold",),
    "shipping": ("shipping_drybulk", "brent_oil"),
    "seafood": ("usd_nok", "usd_sek"),
    "export_nordic": ("usd_nok", "usd_sek"),
    "brazil_export": ("usd_brl", "brent_oil"),
    "rate_sensitive": ("rates_10y",),
}

BJELLESAU_CONFIG = Path("data/alpha_radar_bjellesauer.json")
_PROXY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_BJELLESAU_CACHE: tuple[float, list[str]] | None = None


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        value = float(value)
        if math.isnan(value):
            return default
        return value
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _normalize_unit(value: Any, default: float = 0.5) -> float:
    number = _float(value, None)
    if number is None:
        return default
    if number > 10:
        number = number / 100.0
    elif number > 1:
        number = number / 10.0
    return _clamp(number)


def _pct(values: Sequence[float], lookback: int) -> float:
    clean = [float(x) for x in values or [] if _float(x, None) is not None and float(x) > 0]
    if len(clean) <= lookback:
        return 0.0
    return (clean[-1] / clean[-lookback - 1] - 1.0) * 100.0


def _safe_ticker(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _ticker_query(ticker: str) -> str:
    return _safe_ticker(ticker).replace(".OL", "").replace(".ST", "").replace(".CO", "").replace(".HE", "").replace(".SA", "")


def _text_blob(row: Mapping[str, Any]) -> str:
    fields = [
        row.get("ticker"),
        row.get("name"),
        row.get("company"),
        row.get("sector"),
        row.get("industry"),
        row.get("reason"),
        row.get("thesis"),
        row.get("note"),
        row.get("insider_label"),
    ]
    return " ".join(str(x or "") for x in fields).lower()


def load_bjellesau_watchlist(path: Path = BJELLESAU_CONFIG) -> list[str]:
    """Optional local smart-money watchlist.

    The app works without this file. If present, it may be either a JSON list
    of names or a dict with a "names" list.
    """

    global _BJELLESAU_CACHE
    now = time.time()
    if _BJELLESAU_CACHE and now - _BJELLESAU_CACHE[0] < 300:
        names = list(_BJELLESAU_CACHE[1])
    else:
        names = []
        try:
            if path.exists():
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    names = [str(x).strip().lower() for x in raw if str(x).strip()]
                elif isinstance(raw, Mapping):
                    names = [str(x).strip().lower() for x in raw.get("names", []) if str(x).strip()]
        except Exception:
            names = []
        _BJELLESAU_CACHE = (now, names)
    try:
        if actor_aliases_for_matching is not None:
            names.extend(actor_aliases_for_matching(actor_types=("Bjellesau", "Institusjon")))
    except Exception:
        pass
    out: list[str] = []
    for name in names:
        clean = str(name or "").strip().lower()
        if clean and clean not in out:
            out.append(clean)
    return out


def reset_bjellesau_watchlist_cache() -> None:
    global _BJELLESAU_CACHE
    _BJELLESAU_CACHE = None


def fetch_market_proxy_snapshot(
    proxies: Mapping[str, str] | None = None,
    *,
    ttl_seconds: int = 60 * 60 * 6,
) -> dict[str, dict[str, Any]]:
    """Fetch broad macro/commodity proxy returns via yfinance.

    This is called only from explicit Alpha Radar runs. Missing yfinance or
    network data returns a neutral snapshot rather than failing the panel.
    """

    proxies = dict(proxies or COMMODITY_PROXIES)
    snapshot: dict[str, dict[str, Any]] = {}
    if yf is None:
        return {key: {"symbol": symbol, "ret_1m": 0.0, "ret_3m": 0.0, "error": "yfinance mangler"} for key, symbol in proxies.items()}
    now = time.time()
    for key, symbol in proxies.items():
        cache_key = f"{key}:{symbol}"
        cached = _PROXY_CACHE.get(cache_key)
        if cached and now - cached[0] <= ttl_seconds:
            snapshot[key] = dict(cached[1])
            continue
        row = {"symbol": symbol, "ret_1m": 0.0, "ret_3m": 0.0, "error": None}
        try:
            hist = yf.Ticker(symbol).history(period="6mo", interval="1d", auto_adjust=True)
            close = hist["Close"].dropna().tolist() if hist is not None and not hist.empty and "Close" in hist else []
            row["ret_1m"] = round(_pct(close, 21), 3)
            row["ret_3m"] = round(_pct(close, 63), 3)
        except Exception as exc:
            row["error"] = str(exc)[:120]
        _PROXY_CACHE[cache_key] = (now, dict(row))
        snapshot[key] = row
    return snapshot


def infer_macro_themes(row: Mapping[str, Any]) -> list[str]:
    ticker = _safe_ticker(row.get("ticker"))
    text = _text_blob(row)
    themes: list[str] = []
    if any(word in text for word in ("oil", "offshore", "rig", "seismic", "supply", "petro", "energy")):
        themes.append("oil_service")
    if any(word in text for word in ("gas", "lng", "natural gas")):
        themes.append("gas")
    if any(word in text for word in ("copper", "metal", "mining", "aluminium", "steel")):
        themes.append("metals")
    if "gold" in text or "silver" in text:
        themes.append("gold")
    if any(word in text for word in ("shipping", "dry bulk", "tanker", "container")):
        themes.append("shipping")
    if any(word in text for word in ("salmon", "seafood", "laks", "fish")):
        themes.append("seafood")
    if ticker.endswith((".OL", ".ST", ".CO", ".HE")) and any(word in text for word in ("export", "industrial", "industry", "seafood", "shipping", "offshore")):
        themes.append("export_nordic")
    if ticker.endswith(".SA"):
        themes.append("brazil_export")
    if any(word in text for word in ("real estate", "property", "bank", "growth", "duration", "debt")):
        themes.append("rate_sensitive")
    if not themes:
        themes.append("energy" if ticker.endswith(".SA") else "export_nordic" if ticker.endswith((".OL", ".ST", ".CO", ".HE")) else "rate_sensitive")
    out: list[str] = []
    for theme in themes:
        if theme not in out:
            out.append(theme)
    return out[:4]


def _theme_tailwind_score(themes: Sequence[str], snapshot: Mapping[str, Mapping[str, Any]]) -> tuple[float, list[str]]:
    scores: list[float] = []
    notes: list[str] = []
    for theme in themes:
        proxy_keys = THEME_PROXY_MAP.get(theme, ())
        if not proxy_keys:
            continue
        proxy_scores: list[float] = []
        for proxy_key in proxy_keys:
            row = snapshot.get(proxy_key) or {}
            ret_1m = _float(row.get("ret_1m"), 0.0) or 0.0
            ret_3m = _float(row.get("ret_3m"), 0.0) or 0.0
            if proxy_key == "rates_10y":
                score = _clamp(0.50 - ret_1m / 28.0 - ret_3m / 55.0)
            elif proxy_key.startswith("usd_"):
                score = _clamp(0.50 + ret_1m / 35.0 + ret_3m / 70.0)
            else:
                score = _clamp(0.50 + ret_1m / 38.0 + ret_3m / 75.0)
            proxy_scores.append(score)
            notes.append(f"{theme}:{proxy_key} 1m {ret_1m:+.1f}% 3m {ret_3m:+.1f}%")
        if proxy_scores:
            scores.append(sum(proxy_scores) / len(proxy_scores))
    if not scores:
        return 0.5, []
    return _clamp(sum(scores) / len(scores)), notes[:6]


def enrich_with_news(
    row: dict[str, Any],
    *,
    include_news: bool,
    news_provider: Callable[..., tuple[Iterable[Mapping[str, Any]], Any]] | None = None,
    horizon: str = "3m",
) -> dict[str, Any]:
    if not include_news:
        return row
    provider = news_provider or get_news
    if provider is None:
        row["alpha_news_error"] = "News provider mangler"
        return row
    ticker = _safe_ticker(row.get("ticker"))
    query_parts = [_ticker_query(ticker)]
    name = str(row.get("name") or row.get("company") or "").strip()
    if local_news_queries is not None:
        try:
            row["local_news_queries"] = local_news_queries(ticker, name, row.get("market"))
        except Exception:
            pass
    if name and name.upper() != ticker:
        query_parts.append(name)
    query = " OR ".join([x for x in query_parts if x])
    try:
        try:
            articles, error = provider(query, limit=8, source="manual", days_back=horizon_to_days(horizon))
        except TypeError:
            articles, error = provider(query, 8)
        articles = list(articles or [])
    except Exception as exc:
        articles, error = [], str(exc)
    row["articles"] = articles
    row["news_count"] = len(articles)
    row["news_sentiment"] = simple_finance_sentiment(articles)
    if articles:
        row["local_news_score"] = _clamp(0.38 + len(articles[:8]) * 0.045 + (row["news_sentiment"] - 0.5) * 0.9)
        market_cap = _float(row.get("market_cap"), None)
        small_cap_boost = 0.18 if market_cap is not None and market_cap < 5_000_000_000 else 0.06
        row["small_news_big_impact_score"] = _clamp(row["local_news_score"] + small_cap_boost)
        row["catalyst_score"] = max(_normalize_unit(row.get("catalyst_score"), 0.5), row["small_news_big_impact_score"])
        row["alpha_news_quality"] = "ekte"
    else:
        row.pop("local_news_score", None)
        row.pop("small_news_big_impact_score", None)
        if not error:
            row["alpha_news_error"] = "Ingen treff i global nyhetskilde for valgt datavindu"
    if error:
        row["alpha_news_error"] = str(error)[:180]
    return row


def enrich_with_financial_evidence_search(
    row: dict[str, Any],
    *,
    enabled: bool,
    news_provider: Callable[..., tuple[Iterable[Mapping[str, Any]], Any]] | None = None,
    horizon: str = "3m",
) -> dict[str, Any]:
    if not enabled or search_financial_evidence is None:
        return row
    try:
        result = search_financial_evidence(
            row,
            news_provider=news_provider,
            days_back=horizon_to_days(horizon),
            max_queries=2,
        )
    except Exception as exc:
        row["alpha_financial_search_error"] = str(exc)[:180]
        return row

    articles = list(result.get("articles") or [])
    if articles:
        existing = row.get("articles") if isinstance(row.get("articles"), list) else []
        row["articles"] = (existing + articles)[:16]
        row["news_count"] = len(row["articles"])
        row["news_sentiment"] = simple_finance_sentiment(row["articles"])
        row["local_news_score"] = _clamp(0.40 + min(len(row["articles"]), 10) * 0.04 + (row["news_sentiment"] - 0.5) * 0.8)
        row["small_news_big_impact_score"] = max(_normalize_unit(row.get("small_news_big_impact_score"), 0.0), row["local_news_score"])
        row["catalyst_score"] = max(_normalize_unit(row.get("catalyst_score"), 0.5), row["small_news_big_impact_score"])
        row["alpha_news_quality"] = "ekte"

    actor_evidence = [dict(item) for item in result.get("actor_evidence") or [] if isinstance(item, Mapping)]
    if actor_evidence:
        existing_bj = row.get("bjellesau_evidence") if isinstance(row.get("bjellesau_evidence"), list) else []
        row["bjellesau_evidence"] = (existing_bj + actor_evidence)[:10]
        row["bjellesau_signal_score"] = max(_normalize_unit(row.get("bjellesau_signal_score"), 0.0), 0.68 + min(len(actor_evidence), 4) * 0.05)
        row["bjellesau_score"] = max(_normalize_unit(row.get("bjellesau_score"), 0.0), row["bjellesau_signal_score"])
        row["smart_money_score"] = row["bjellesau_score"]

    insider_evidence = [dict(item) for item in result.get("insider_evidence") or [] if isinstance(item, Mapping)]
    if insider_evidence:
        existing_ins = row.get("financial_insider_evidence") if isinstance(row.get("financial_insider_evidence"), list) else []
        row["financial_insider_evidence"] = (existing_ins + insider_evidence)[:10]
        row["insider_signal_score"] = max(_normalize_unit(row.get("insider_signal_score"), 0.0), 0.62 + min(len(insider_evidence), 4) * 0.04)
        row["insider_quality_score"] = max(_normalize_unit(row.get("insider_quality_score"), 0.0), row["insider_signal_score"])

    diagnostics = [dict(item) for item in result.get("diagnostics") or [] if isinstance(item, Mapping)]
    if diagnostics:
        if merge_source_diagnostics is not None:
            row["source_diagnostics"] = merge_source_diagnostics(row.get("source_diagnostics"), diagnostics)
        else:
            row["source_diagnostics"] = diagnostics
    if result.get("errors"):
        row["alpha_financial_search_error"] = " | ".join(str(x) for x in result.get("errors") or [])[:180]
    return row


def enrich_with_nordic_actor_search(
    row: dict[str, Any],
    *,
    enabled: bool,
    news_provider: Callable[..., tuple[Iterable[Mapping[str, Any]], Any]] | None = None,
    horizon: str = "3m",
    include_insider: bool = True,
    include_news: bool = True,
) -> dict[str, Any]:
    if not enabled or search_nordic_actor_insider is None:
        return row
    try:
        result = search_nordic_actor_insider(
            row,
            news_provider=news_provider,
            days_back=horizon_to_days(horizon),
            include_insider=include_insider,
            include_news=include_news,
            max_newsapi_queries=1 if news_provider is not None else 0,
        )
    except Exception as exc:
        row["alpha_nordic_search_error"] = str(exc)[:180]
        return row

    diagnostics = [dict(item) for item in result.get("diagnostics") or [] if isinstance(item, Mapping)]
    if diagnostics:
        if merge_source_diagnostics is not None:
            row["source_diagnostics"] = merge_source_diagnostics(row.get("source_diagnostics"), diagnostics)
        else:
            row["source_diagnostics"] = diagnostics

    articles = [dict(item) for item in result.get("articles") or [] if isinstance(item, Mapping)]
    if articles:
        existing = row.get("articles") if isinstance(row.get("articles"), list) else []
        row["articles"] = (existing + articles)[:18]
        row["news_count"] = len(row["articles"])
        row["news_sentiment"] = simple_finance_sentiment(row["articles"])
        row["local_news_score"] = max(_normalize_unit(row.get("local_news_score"), 0.0), _clamp(0.42 + min(len(row["articles"]), 8) * 0.04))
        row["small_news_big_impact_score"] = max(_normalize_unit(row.get("small_news_big_impact_score"), 0.0), row["local_news_score"])
        row["catalyst_score"] = max(_normalize_unit(row.get("catalyst_score"), 0.5), row["small_news_big_impact_score"])
        row["alpha_news_quality"] = "ekte"

    actor_evidence = [dict(item) for item in result.get("actor_evidence") or [] if isinstance(item, Mapping)]
    if actor_evidence:
        existing_actor = row.get("nordic_actor_evidence") if isinstance(row.get("nordic_actor_evidence"), list) else []
        row["nordic_actor_evidence"] = (existing_actor + actor_evidence)[:12]
        existing_bj = row.get("bjellesau_evidence") if isinstance(row.get("bjellesau_evidence"), list) else []
        row["bjellesau_evidence"] = (existing_bj + actor_evidence)[:12]
        row["bjellesau_signal_score"] = max(_normalize_unit(row.get("bjellesau_signal_score"), 0.0), 0.70 + min(len(actor_evidence), 4) * 0.05)
        row["bjellesau_score"] = max(_normalize_unit(row.get("bjellesau_score"), 0.0), row["bjellesau_signal_score"])
        row["smart_money_score"] = row["bjellesau_score"]

    insider_evidence = [dict(item) for item in result.get("insider_evidence") or [] if isinstance(item, Mapping)]
    if insider_evidence:
        existing_nordic = row.get("nordic_insider_evidence") if isinstance(row.get("nordic_insider_evidence"), list) else []
        row["nordic_insider_evidence"] = (existing_nordic + insider_evidence)[:12]
        existing_ins = row.get("financial_insider_evidence") if isinstance(row.get("financial_insider_evidence"), list) else []
        row["financial_insider_evidence"] = (existing_ins + insider_evidence)[:12]
        row["insider_signal_score"] = max(_normalize_unit(row.get("insider_signal_score"), 0.0), 0.64 + min(len(insider_evidence), 4) * 0.04)
        row["insider_quality_score"] = max(_normalize_unit(row.get("insider_quality_score"), 0.0), row["insider_signal_score"])

    unmatched = [dict(item) for item in result.get("unmatched") or [] if isinstance(item, Mapping)]
    if unmatched:
        existing_unmatched = row.get("unmatched_workbench") if isinstance(row.get("unmatched_workbench"), list) else []
        row["unmatched_workbench"] = (existing_unmatched + unmatched)[:20]
    if result.get("errors"):
        row["alpha_nordic_search_error"] = " | ".join(str(x) for x in result.get("errors") or [])[:180]
    row["source_budget_note"] = (
        f"Nordic Actor/Insider Search: {result.get('free_official_queries', 0)} gratis/offisielle sokelenker, "
        f"{result.get('newsapi_requests_used', 0)} NewsAPI-request brukt."
    )
    return row


def enrich_with_insider_quality(
    row: dict[str, Any],
    *,
    include_insider: bool,
    insider_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    horizon: str = "3m",
) -> dict[str, Any]:
    if not include_insider:
        return row
    ticker = _safe_ticker(row.get("ticker"))
    insider = None
    if insider_provider is not None:
        try:
            insider = insider_provider(ticker, months=horizon_to_months(horizon))
        except TypeError:
            try:
                insider = insider_provider(ticker)
            except Exception as exc:
                row["alpha_insider_error"] = str(exc)[:180]
        except Exception as exc:
            row["alpha_insider_error"] = str(exc)[:180]
    if isinstance(insider, Mapping):
        row["insider_score"] = insider.get("score", row.get("insider_score"))
        row["insider_label"] = insider.get("label") or insider.get("direction") or row.get("insider_label")
        row["insider_buy_count"] = insider.get("buy_count", row.get("insider_buy_count"))
        row["insider_sell_count"] = insider.get("sell_count", row.get("insider_sell_count"))
        row["insider_latest_type"] = insider.get("latest_type", row.get("insider_latest_type"))
        row["insider_latest_date"] = insider.get("latest_date", row.get("insider_latest_date"))
        row["insider_transactions"] = insider.get("transactions", row.get("insider_transactions"))
        row["latest_transactions"] = insider.get("latest_transactions", row.get("latest_transactions"))
        if insider.get("error"):
            row["alpha_insider_error"] = str(insider.get("error"))[:180]

    base = _normalize_unit(row.get("insider_score"), 0.5)
    buy_count = _float(row.get("insider_buy_count"), 0.0) or 0.0
    sell_count = _float(row.get("insider_sell_count"), 0.0) or 0.0
    latest_type = str(row.get("insider_latest_type") or "").upper()
    latest_transactions = row.get("latest_transactions") if isinstance(row.get("latest_transactions"), list) else []
    watchlist = load_bjellesau_watchlist()
    market = str(row.get("market") or "")
    relation_boost = 0.0
    matched_names: list[str] = []
    normalized_transactions: list[dict[str, Any]] = []
    for raw_tx in latest_transactions[:8]:
        tx = dict(raw_tx or {}) if isinstance(raw_tx, Mapping) else {}
        if not tx:
            continue
        text = f"{tx.get('name', '')} {tx.get('relation', '')}".lower()
        if any(role in text for role in ("ceo", "cfo", "chair", "founder", "director", "board")):
            relation_boost += 0.035
        for name in watchlist:
            if name and name in text:
                matched_names.append(name)
                relation_boost += 0.08
        if match_actor_text is not None:
            try:
                for actor in match_actor_text(text, market=market, ticker=ticker, actor_types=("Bjellesau", "Institusjon")):
                    actor_name = str(actor.get("name") or actor.get("matched_alias") or "").strip()
                    if actor_name:
                        matched_names.append(actor_name)
                        tx["actor_registry_match"] = actor_name
                        tx["ownership_type"] = "Bjellesau"
                        relation_boost += 0.10 if actor.get("strength") == "Sterk" else 0.07
            except Exception:
                pass
        tx["ownership_type"] = classify_ownership_item(tx, watchlist_names=watchlist)
        normalized_transactions.append(tx)
    if normalized_transactions:
        row["latest_transactions"] = normalized_transactions
    quality = base
    if buy_count > sell_count:
        quality += min((buy_count - sell_count) * 0.04, 0.18)
    if latest_type == "BUY":
        quality += 0.08
    elif latest_type == "SELL":
        quality -= 0.08
    quality += min(relation_boost, 0.18)
    row["insider_quality_score"] = _clamp(quality)
    row["historical_insider_quality_score"] = row["insider_quality_score"]
    row["insider_signal_score"] = row["insider_quality_score"]
    if matched_names:
        row["bjellesau_signal_score"] = _clamp(0.62 + min(len(set(matched_names)), 4) * 0.06)
        row["bjellesau_score"] = row["bjellesau_signal_score"]
    else:
        row["bjellesau_score"] = _normalize_unit(row.get("bjellesau_score"), None)
    row["smart_money_score"] = row["bjellesau_score"]
    if matched_names:
        row["bjellesau_match"] = sorted(set(matched_names))[:5]
    combined, insider_items, bjellesau_items = split_ownership_evidence(row, limit=8)
    row["ownership_evidence"] = combined
    row["insider_evidence"] = insider_items
    row["bjellesau_evidence"] = bjellesau_items
    return row


def enrich_with_macro_tailwind(
    row: dict[str, Any],
    *,
    include_macro: bool,
    commodity_snapshot: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not include_macro:
        return row
    snapshot = commodity_snapshot if commodity_snapshot is not None else fetch_market_proxy_snapshot()
    themes = infer_macro_themes(row)
    score, notes = _theme_tailwind_score(themes, snapshot)
    row["macro_themes"] = themes
    if notes:
        row["macro_tailwind_score"] = score
        row["commodity_tailwind_score"] = score
        row["macro_tailwind_quality"] = "proxy"
    else:
        row.pop("macro_tailwind_score", None)
        row.pop("commodity_tailwind_score", None)
    row["macro_tailwind_notes"] = notes
    return row


def enrich_with_results(
    row: dict[str, Any],
    *,
    include_results: bool,
    earnings_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    horizon: str = "3m",
) -> dict[str, Any]:
    if not include_results:
        return row
    quality_present = row.get("quality") is not None or (isinstance(row.get("score_parts"), Mapping) and (row.get("score_parts") or {}).get("quality") is not None)
    growth_present = row.get("revenue_growth") is not None or (isinstance(row.get("score_parts"), Mapping) and (row.get("score_parts") or {}).get("fundamental_growth") is not None)
    margin_present = row.get("profit_margin") is not None
    quality = _normalize_unit(row.get("quality", None), _normalize_unit((row.get("score_parts") or {}).get("quality"), 0.5) if isinstance(row.get("score_parts"), Mapping) else 0.5)
    if row.get("revenue_growth") is not None:
        growth = _clamp(0.50 + (_float(row.get("revenue_growth"), 0.0) or 0.0) * 1.35)
    else:
        growth = _normalize_unit((row.get("score_parts") or {}).get("fundamental_growth"), 0.5) if isinstance(row.get("score_parts"), Mapping) else 0.5
    margin = _float(row.get("profit_margin"), None)
    margin_score = _clamp(0.50 + (margin or 0.0) * 1.8) if margin is not None else 0.50
    earnings_score = 0.50
    earnings_has_date = False
    ticker = _safe_ticker(row.get("ticker"))
    earnings = None
    if earnings_provider is None:
        row["alpha_earnings_error"] = "Earnings provider mangler"
    else:
        try:
            earnings = earnings_provider(ticker, months=horizon_to_months(horizon))
        except TypeError:
            try:
                earnings = earnings_provider(ticker)
            except Exception as exc:
                earnings = None
                row["alpha_earnings_error"] = str(exc)[:180]
        except Exception as exc:
            earnings = None
            row["alpha_earnings_error"] = str(exc)[:180]
        try:
            if isinstance(earnings, Mapping):
                row["earnings_days_until"] = earnings.get("days_until")
                row["earnings_date"] = earnings.get("date")
                days = _float(earnings.get("days_until"), None)
                if days is not None and 0 <= days <= 45:
                    earnings_score = 0.62
                    earnings_has_date = True
                if earnings.get("error"):
                    row["alpha_earnings_error"] = str(earnings.get("error"))[:180]
        except Exception as exc:
            row["alpha_earnings_error"] = str(exc)[:180]
    if quality_present or growth_present or margin_present or earnings_has_date:
        row["result_inflection_score"] = _clamp(quality * 0.28 + growth * 0.34 + margin_score * 0.20 + earnings_score * 0.18)
        row["inflection_score"] = max(_normalize_unit(row.get("inflection_score"), 0.5), row["result_inflection_score"])
        row["result_inflection_quality"] = "ekte" if row.get("revenue_growth") is not None or margin_present or earnings_has_date else "beregnet"
        row.pop("alpha_result_diagnostic", None)
    else:
        row.pop("result_inflection_score", None)
        row["alpha_result_diagnostic"] = "Ingen earnings/revisions, guiding, vekst eller margindata funnet i valgt datavindu"
    return row


def enrich_alpha_radar_row(
    row: Mapping[str, Any] | None,
    *,
    ticker: str,
    include_news: bool = False,
    include_insider: bool = False,
    include_macro: bool = False,
    include_results: bool = False,
    mode: str = "",
    active_signals: Sequence[str] | None = None,
    news_provider: Callable[..., tuple[Iterable[Mapping[str, Any]], Any]] | None = None,
    insider_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    earnings_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    commodity_snapshot: Mapping[str, Mapping[str, Any]] | None = None,
    horizon: str = "3m",
) -> dict[str, Any]:
    """Attach real-world signal proxies to an Alpha Radar row.

    All external work is opt-in and should be called from an explicit run
    action. Missing APIs return neutral fields plus error notes.
    """

    enriched = dict(row or {})
    enriched.setdefault("ticker", ticker)
    if apply_nbim_overlay is not None:
        try:
            enriched = apply_nbim_overlay(enriched)
        except Exception:
            pass
    nbim_score = _normalize_unit(enriched.get("nbim_signal_score"), None)
    if nbim_score is not None:
        enriched["owner_signal"] = max(_normalize_unit(enriched.get("owner_signal"), 0.0), nbim_score)
        if nbim_score >= 0.55:
            enriched["bjellesau_score"] = max(_normalize_unit(enriched.get("bjellesau_score"), 0.0), nbim_score)
            enriched["smart_money_score"] = max(_normalize_unit(enriched.get("smart_money_score"), 0.0), nbim_score)
    signals = set(active_signals or [])
    mode_text = str(mode or "")
    news_on = include_news or "Nyheter/katalysator" in signals
    insider_on = include_insider or "Insider/bjellesauer" in signals or "Insider" in mode_text
    macro_on = include_macro or "Ravarer/makro" in signals or "Ravare" in mode_text
    results_on = include_results or "Resultater" in signals or "Resultat" in mode_text

    enriched = enrich_with_news(enriched, include_news=news_on, news_provider=news_provider, horizon=horizon)
    enriched = enrich_with_nordic_actor_search(
        enriched,
        enabled=(news_on or insider_on),
        news_provider=news_provider,
        horizon=horizon,
        include_insider=insider_on,
        include_news=news_on,
    )
    enriched = enrich_with_financial_evidence_search(enriched, enabled=(news_on or insider_on), news_provider=news_provider, horizon=horizon)
    enriched = enrich_with_insider_quality(enriched, include_insider=insider_on, insider_provider=insider_provider, horizon=horizon)
    enriched = enrich_with_macro_tailwind(enriched, include_macro=macro_on, commodity_snapshot=commodity_snapshot)
    enriched = enrich_with_results(enriched, include_results=results_on, earnings_provider=earnings_provider, horizon=horizon)
    if local_market_source_diagnostics is not None:
        try:
            diagnostics = local_market_source_diagnostics(enriched, horizon=horizon)
            if diagnostics:
                if merge_source_diagnostics is not None:
                    enriched["source_diagnostics"] = merge_source_diagnostics(enriched.get("source_diagnostics"), diagnostics)
                else:
                    enriched["source_diagnostics"] = list(diagnostics)
        except Exception:
            pass
    if build_evidence_ledger is not None:
        try:
            enriched["evidence_ledger"] = build_evidence_ledger(enriched, found_by="Alpha Radar/Early Warning")
        except Exception:
            pass
    return enriched


__all__ = [
    "COMMODITY_PROXIES",
    "enrich_alpha_radar_row",
    "enrich_with_nordic_actor_search",
    "fetch_market_proxy_snapshot",
    "infer_macro_themes",
    "load_bjellesau_watchlist",
    "reset_bjellesau_watchlist_cache",
]
