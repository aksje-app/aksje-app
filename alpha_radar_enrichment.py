from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

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
        return list(_BJELLESAU_CACHE[1])
    names: list[str] = []
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
    return list(names)


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
    if name and name.upper() != ticker:
        query_parts.append(name)
    query = " OR ".join([x for x in query_parts if x])
    try:
        try:
            articles, error = provider(query, limit=8, source="manual")
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
    if error:
        row["alpha_news_error"] = str(error)[:180]
    return row


def enrich_with_insider_quality(
    row: dict[str, Any],
    *,
    include_insider: bool,
    insider_provider: Callable[..., Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    if not include_insider:
        return row
    ticker = _safe_ticker(row.get("ticker"))
    insider = None
    if insider_provider is not None:
        try:
            insider = insider_provider(ticker)
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
    relation_boost = 0.0
    matched_names: list[str] = []
    for tx in latest_transactions[:8]:
        text = f"{tx.get('name', '')} {tx.get('relation', '')}".lower()
        if any(role in text for role in ("ceo", "cfo", "chair", "founder", "director", "board")):
            relation_boost += 0.035
        for name in watchlist:
            if name and name in text:
                matched_names.append(name)
                relation_boost += 0.08
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
    row["bjellesau_score"] = _clamp(row["insider_quality_score"] + (0.10 if matched_names else 0.0))
    row["smart_money_score"] = row["bjellesau_score"]
    if matched_names:
        row["bjellesau_match"] = sorted(set(matched_names))[:5]
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
    if earnings_provider is not None:
        try:
            earnings = earnings_provider(ticker)
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
    else:
        row.pop("result_inflection_score", None)
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
) -> dict[str, Any]:
    """Attach real-world signal proxies to an Alpha Radar row.

    All external work is opt-in and should be called from an explicit run
    action. Missing APIs return neutral fields plus error notes.
    """

    enriched = dict(row or {})
    enriched.setdefault("ticker", ticker)
    signals = set(active_signals or [])
    mode_text = str(mode or "")
    news_on = include_news or "Nyheter/katalysator" in signals
    insider_on = include_insider or "Insider/bjellesauer" in signals or "Insider" in mode_text
    macro_on = include_macro or "Ravarer/makro" in signals or "Ravare" in mode_text
    results_on = include_results or "Resultater" in signals or "Resultat" in mode_text

    enriched = enrich_with_news(enriched, include_news=news_on, news_provider=news_provider)
    enriched = enrich_with_insider_quality(enriched, include_insider=insider_on, insider_provider=insider_provider)
    enriched = enrich_with_macro_tailwind(enriched, include_macro=macro_on, commodity_snapshot=commodity_snapshot)
    enriched = enrich_with_results(enriched, include_results=results_on, earnings_provider=earnings_provider)
    return enriched


__all__ = [
    "COMMODITY_PROXIES",
    "enrich_alpha_radar_row",
    "fetch_market_proxy_snapshot",
    "infer_macro_themes",
    "load_bjellesau_watchlist",
]
