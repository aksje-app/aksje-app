from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable, Iterable, Mapping, Sequence

from alpha_radar_currency import market_cap_fields
from alpha_radar_ownership import ownership_signal_scores, split_ownership_evidence
from data_source_diagnostics import summarize_source_error

try:
    from evidence_ledger import build_evidence_ledger
except Exception:  # pragma: no cover - optional evidence layer
    build_evidence_ledger = None


HORIZON_WEIGHTS = {
    "1m": {
        "fresh_source_evidence": 0.26,
        "ownership_insider": 0.18,
        "catalyst_altdata_macro": 0.18,
        "expectation_change": 0.12,
        "earnings_surprise": 0.10,
        "market_confirmation": 0.10,
        "fundamental_acceleration": 0.04,
        "risk_filter": 0.02,
    },
    "3m": {
        "fresh_source_evidence": 0.22,
        "ownership_insider": 0.18,
        "catalyst_altdata_macro": 0.16,
        "expectation_change": 0.18,
        "earnings_surprise": 0.12,
        "market_confirmation": 0.08,
        "fundamental_acceleration": 0.04,
        "risk_filter": 0.02,
    },
    "6m": {
        "fresh_source_evidence": 0.16,
        "ownership_insider": 0.14,
        "catalyst_altdata_macro": 0.16,
        "expectation_change": 0.18,
        "earnings_surprise": 0.12,
        "fundamental_acceleration": 0.18,
        "market_confirmation": 0.04,
        "risk_filter": 0.02,
    },
    "12m": {
        "fresh_source_evidence": 0.12,
        "ownership_insider": 0.10,
        "catalyst_altdata_macro": 0.16,
        "expectation_change": 0.16,
        "earnings_surprise": 0.10,
        "fundamental_acceleration": 0.26,
        "market_confirmation": 0.04,
        "risk_filter": 0.06,
    },
}


@dataclass(frozen=True)
class EarlyWarningCandidate:
    rank: int
    ticker: str
    name: str
    market: str
    horizon: str
    mode: str
    alpha_score: float
    hidden_potential_score: float
    early_warning_score: float
    potential_score: float
    catalyst_score: float | None
    underfollowed_score: float | None
    inflection_score: float | None
    insider_score: float | None
    bjellesau_score: float | None
    volume_score: float | None
    macro_score: float | None
    evidence_score: float
    risk_score: float
    crowdedness_penalty: float
    liquidity_penalty: float
    market_cap: float | None
    market_cap_currency: str
    market_cap_nok_estimate: float | None
    market_cap_display: str
    data_quality: str
    base_score: float
    why_now: str
    thesis: str
    signals: list[str]
    reject_reasons: list[str]
    warning_reasons: list[str]
    manual_review: str
    factor_scores: dict[str, float | None]
    factor_quality: dict[str, str]
    source: str
    evidence_items: list[dict[str, Any]]
    insider_evidence: list[dict[str, Any]]
    bjellesau_evidence: list[dict[str, Any]]
    news_evidence: list[dict[str, Any]]
    nbim_evidence: list[dict[str, Any]]
    evidence_ledger: list[dict[str, Any]]
    source_diagnostics: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _unit(value: Any) -> float | None:
    number = _float(value, None)
    if number is None:
        return None
    if number > 10:
        number = number / 100.0
    return _clamp(number)


def _ret(value: Any) -> float:
    number = _float(value, 0.0) or 0.0
    if abs(number) > 2:
        number = number / 100.0
    return number


def _safe_ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _infer_market(ticker: str) -> str:
    ticker = _safe_ticker(ticker)
    if ticker.endswith(".OL"):
        return "Norge"
    if ticker.endswith(".ST"):
        return "Sverige"
    if ticker.endswith(".HE"):
        return "Finland"
    if ticker.endswith(".CO"):
        return "Danmark"
    if ticker.endswith(".SA"):
        return "Brasil"
    return "USA/annet"


def _market_counts_from_tickers(tickers: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ticker in tickers or []:
        market = _infer_market(str(ticker or ""))
        counts[market] = counts.get(market, 0) + 1
    return counts


def _market_counts_from_candidates(candidates: Sequence["EarlyWarningCandidate"]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates or []:
        market = str(candidate.market or _infer_market(candidate.ticker))
        counts[market] = counts.get(market, 0) + 1
    return counts


def _balanced_candidates(
    candidates: Sequence["EarlyWarningCandidate"],
    *,
    limit: int,
    balance_markets: bool,
) -> list["EarlyWarningCandidate"]:
    ranked = sorted(candidates or [], key=lambda item: item.early_warning_score, reverse=True)
    if not balance_markets or limit <= 1:
        return ranked[:limit]
    by_market: dict[str, list[EarlyWarningCandidate]] = {}
    for candidate in ranked:
        by_market.setdefault(str(candidate.market or _infer_market(candidate.ticker)), []).append(candidate)
    if len(by_market) <= 1:
        return ranked[:limit]

    selected: list[EarlyWarningCandidate] = []
    selected_ids: set[str] = set()
    markets_by_best = sorted(
        by_market,
        key=lambda market: by_market[market][0].early_warning_score if by_market.get(market) else -1,
        reverse=True,
    )
    for market in markets_by_best:
        if len(selected) >= limit:
            break
        top = by_market[market][0]
        selected.append(top)
        selected_ids.add(top.ticker)
    for candidate in ranked:
        if len(selected) >= limit:
            break
        if candidate.ticker in selected_ids:
            continue
        selected.append(candidate)
        selected_ids.add(candidate.ticker)
    return sorted(selected, key=lambda item: item.early_warning_score, reverse=True)[:limit]


def _market_cap(row: Mapping[str, Any]) -> float | None:
    value = _float(row.get("market_cap"), None)
    return value if value and value > 0 else None


def _score_part(row: Mapping[str, Any], key: str) -> float | None:
    parts = row.get("score_parts")
    if isinstance(parts, Mapping):
        value = _unit(parts.get(key))
        if value is not None:
            return value
    return _unit(row.get(f"{key}_score"))


def _quality(value: float | None, *, proxy: bool = False) -> str:
    if value is None:
        return "mangler"
    return "proxy" if proxy else "ekte"


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _news_items(row: Mapping[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    articles = row.get("articles") if isinstance(row.get("articles"), list) else []
    items: list[dict[str, Any]] = []
    for article in articles[:limit]:
        if not isinstance(article, Mapping):
            continue
        title = _clean_text(article.get("title") or article.get("headline"), "Uten tittel")
        source = _clean_text(article.get("source") or article.get("publisher") or article.get("site"), "Ukjent kilde")
        url = _clean_text(article.get("url") or article.get("link"))
        published = _clean_text(article.get("published") or article.get("publishedAt") or article.get("date"))
        items.append({
            "type": "nyhet",
            "title": title,
            "source": source,
            "published": published,
            "url": url,
            "detail": "Nyhets-/katalysatorspor som maa leses manuelt.",
        })
    return items


def _news_count(row: Mapping[str, Any]) -> int:
    articles = row.get("articles") if isinstance(row.get("articles"), list) else []
    if articles:
        return len(articles)
    value = _float(row.get("news_count", row.get("article_count")), 0.0) or 0.0
    return max(0, int(value))


def _insider_items(row: Mapping[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    _combined, insider, _bjellesau = split_ownership_evidence(row, limit=limit)
    return insider


def _ownership_items(row: Mapping[str, Any], limit: int = 8) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    return split_ownership_evidence(row, limit=limit)


def _fresh_source_evidence(row: Mapping[str, Any], *, include_news: bool, include_insider: bool) -> tuple[float | None, str]:
    news_items = _news_items(row) if include_news else []
    ownership_items, insider_items, bjellesau_items = _ownership_items(row) if include_insider else ([], [], [])
    news_count = len(news_items)
    insider_count = len(insider_items)
    bjellesau_count = len(bjellesau_items)
    if not news_count and not insider_count and not bjellesau_count:
        return None, "mangler"
    score = 0.42 + min(news_count, 5) * 0.055 + min(insider_count, 5) * 0.075 + min(bjellesau_count, 4) * 0.08
    if any(item.get("url") for item in news_items + ownership_items):
        score += 0.05
    if insider_count and bjellesau_count:
        quality = "direkte kilde: insider og bjellesau"
    elif bjellesau_count:
        quality = "direkte kilde: bjellesau"
    elif insider_count:
        quality = "direkte kilde: insider"
    else:
        quality = "direkte kilde: nyhet"
    return _clamp(score), quality


def _evidence_items(row: Mapping[str, Any], *, include_news: bool, include_insider: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    news = _news_items(row) if include_news else []
    ownership, insider, bjellesau = _ownership_items(row) if include_insider else ([], [], [])
    financial_insider = [dict(item) for item in row.get("financial_insider_evidence") or [] if isinstance(item, Mapping)] if include_insider else []
    nordic_insider = [dict(item) for item in row.get("nordic_insider_evidence") or [] if isinstance(item, Mapping)] if include_insider else []
    nordic_actor = [dict(item) for item in row.get("nordic_actor_evidence") or [] if isinstance(item, Mapping)] if include_insider else []
    finansavisen_bjellesau = [dict(item) for item in row.get("finansavisen_bjellesau_evidence") or [] if isinstance(item, Mapping)] if include_insider else []
    nbim = [dict(item) for item in row.get("nbim_evidence") or [] if isinstance(item, Mapping)]
    ledger = [dict(item) for item in row.get("evidence_ledger") or [] if isinstance(item, Mapping)]
    if not ledger and build_evidence_ledger is not None:
        try:
            ledger = build_evidence_ledger(row, found_by="Early Warning")
        except Exception:
            ledger = []
    insider = (insider + financial_insider + nordic_insider)[:10]
    if include_insider and (nbim or finansavisen_bjellesau):
        bjellesau = (bjellesau + nordic_actor + finansavisen_bjellesau + nbim)[:10]
    elif include_insider:
        bjellesau = (bjellesau + nordic_actor)[:10]
    combined = ledger if ledger else (ownership + nbim + finansavisen_bjellesau + financial_insider + nordic_insider + nordic_actor + news)
    return combined[:10], insider, bjellesau, news


def _source_diagnostics(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    if isinstance(row.get("source_diagnostics"), list):
        diagnostics.extend(dict(item) for item in row["source_diagnostics"] if isinstance(item, Mapping))
    for key, label in (
        ("alpha_insider_error", "insiderkilde"),
        ("alpha_news_error", "nyhetskilde"),
        ("alpha_financial_search_error", "finanssøk"),
        ("alpha_nordic_search_error", "nordisk aktor-/insidersok"),
        ("alpha_earnings_error", "earningskilde"),
        ("alpha_result_diagnostic", "resultat/vendepunkt"),
    ):
        if row.get(key):
            diagnostics.append({
                "type": "datadiagnostikk",
                "title": label,
                "source": "Radar",
                "status": "mangler/begrenset",
                "detail": summarize_source_error(label, row.get(key)) or str(row.get(key)),
                "url": "",
            })
    if row.get("source_budget_note"):
        diagnostics.append({
            "type": "kildebudsjett",
            "title": "Kildebudsjett / kildeko",
            "source": "Radar",
            "status": "planlagt/brukt",
            "detail": str(row.get("source_budget_note")),
            "url": "",
        })
    clean: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in diagnostics:
        marker = (
            str(item.get("type") or "").lower(),
            str(item.get("title") or "").lower(),
            str(item.get("url") or "").lower(),
        )
        if marker in seen:
            continue
        seen.add(marker)
        clean.append(item)
    return clean[:14]


def _expectation_change(row: Mapping[str, Any]) -> tuple[float | None, str]:
    values = [
        row.get("estimate_revision_score"),
        row.get("revisions_score"),
        row.get("eps_revision_score"),
        row.get("analyst_revision_score"),
    ]
    scores = [_unit(value) for value in values if value is not None]
    scores = [value for value in scores if value is not None]
    if scores:
        return max(scores), "ekte"
    analyst_trend = str(row.get("analyst_trend") or row.get("analyst_label") or "").lower()
    if any(word in analyst_trend for word in ("opp", "up", "raise", "positive", "hevet")):
        return 0.64, "proxy"
    return None, "mangler"


def _earnings_surprise(row: Mapping[str, Any]) -> tuple[float | None, str]:
    values = [
        row.get("earnings_surprise_score"),
        row.get("guidance_score"),
        row.get("surprise_score"),
    ]
    scores = [_unit(value) for value in values if value is not None]
    scores = [value for value in scores if value is not None]
    if scores:
        return max(scores), "ekte"
    proxy_scores = [_unit(row.get(key)) for key in ("result_inflection_score", "inflection_score", "turnaround_score")]
    proxy_scores = [value for value in proxy_scores if value is not None]
    if proxy_scores:
        quality = str(row.get("result_inflection_quality") or "beregnet")
        return max(proxy_scores), quality if quality in {"ekte", "proxy", "beregnet"} else "beregnet"
    if row.get("earnings_days_until") is not None:
        return 0.54, "proxy"
    return None, "mangler"


def _fundamental_acceleration(row: Mapping[str, Any]) -> tuple[float | None, str]:
    growth = _unit(row.get("revenue_growth"))
    margin = _unit(row.get("profit_margin"))
    quality = _score_part(row, "quality")
    fundamental_growth = _score_part(row, "fundamental_growth")
    values = [value for value in (growth, margin, quality, fundamental_growth) if value is not None]
    if not values:
        return None, "mangler"
    return (_clamp(sum(values) / len(values)), "ekte" if growth is not None or margin is not None else "proxy")


def _market_confirmation(row: Mapping[str, Any]) -> tuple[float | None, str]:
    momentum = _score_part(row, "momentum")
    trend = _score_part(row, "trend")
    volume = _score_part(row, "volume")
    ret_score = None
    if row.get("ret_1m") is not None or row.get("ret_3m") is not None:
        ret_1m = _ret(row.get("ret_1m"))
        ret_3m = _ret(row.get("ret_3m"))
        ret_score = _clamp(0.48 + ret_1m * 2.1 + ret_3m * 0.9)
    values = [value for value in (momentum, trend, volume, ret_score) if value is not None]
    if not values:
        return None, "mangler"
    return (_clamp(sum(values) / len(values)), "beregnet")


def _ownership_insider(row: Mapping[str, Any], include_insider: bool) -> tuple[float | None, str]:
    if not include_insider:
        return None, "mangler"
    split = ownership_signal_scores(row)
    if split["combined_score"] is not None:
        return float(split["combined_score"]), str(split["quality"])
    values = [
        row.get("insider_quality_score"),
        row.get("bjellesau_score"),
        row.get("owner_signal"),
        row.get("insider_score"),
    ]
    scores = [_unit(value) for value in values if value is not None]
    scores = [value for value in scores if value is not None]
    if scores:
        return max(scores), "ekte"
    if include_insider and (row.get("insider_buy_count") is not None or row.get("buy_count") is not None):
        buy = _float(row.get("insider_buy_count", row.get("buy_count")), 0.0) or 0.0
        sell = _float(row.get("insider_sell_count", row.get("sell_count")), 0.0) or 0.0
        return _clamp(0.50 + (buy - sell) * 0.04), "proxy"
    return None, "mangler"


def _catalyst_altdata_macro(row: Mapping[str, Any], include_news: bool, include_macro: bool) -> tuple[float | None, str]:
    news_values = [row.get("catalyst_score")]
    has_news = _news_items(row, limit=1) or _news_count(row)
    if has_news or str(row.get("alpha_news_quality") or "").lower() == "ekte":
        news_values.extend([row.get("small_news_big_impact_score"), row.get("local_news_score")])
    news_scores = [_unit(value) for value in news_values if value is not None]
    news_scores = [value for value in news_scores if value is not None]
    if news_scores:
        return max(news_scores), "ekte"
    macro_values = [row.get("macro_tailwind_score"), row.get("commodity_tailwind_score")]
    macro_scores = [_unit(value) for value in macro_values if value is not None]
    macro_scores = [value for value in macro_scores if value is not None]
    if include_macro and macro_scores and row.get("macro_tailwind_notes"):
        return max(macro_scores), "proxy"
    text = " ".join(str(row.get(key) or "") for key in ("sector", "industry", "name", "description")).lower()
    hits = sum(1 for word in ("contract", "order", "patent", "guidance", "oil", "copper", "shipping", "ai", "semiconductor") if word in text)
    if hits and (include_news or include_macro):
        return _clamp(0.48 + hits * 0.04), "proxy"
    return None, "mangler"


def _risk_filter(row: Mapping[str, Any]) -> tuple[float, str]:
    volatility = _float(row.get("volatility"), 0.026) or 0.026
    if volatility > 1:
        volatility = volatility / 100.0
    drawdown = abs(min(_float(row.get("max_drawdown"), -0.18) or -0.18, 0.0))
    risk = _clamp(1.0 - (volatility * 7.5 + drawdown * 1.2))
    return risk, "beregnet"


def _liquidity_penalty(row: Mapping[str, Any]) -> float:
    avg_value = _float(row.get("avg_dollar_volume", row.get("avg_turnover_value")), None)
    if avg_value is None:
        return 0.0
    if avg_value < 50_000:
        return 25.0
    if avg_value < 200_000:
        return 14.0
    if avg_value < 1_000_000:
        return 6.0
    return 0.0


def _risk_score(row: Mapping[str, Any]) -> float:
    risk_filter, _quality_label = _risk_filter(row)
    return round((1.0 - risk_filter) * 100.0, 1)


def _provider_call(provider: Callable[..., Mapping[str, Any] | None], ticker: str, include_news: bool, include_insider: bool) -> Mapping[str, Any] | None:
    try:
        return provider(ticker, use_news=include_news, include_insider=include_insider)
    except TypeError:
        try:
            return provider(ticker, use_news=include_news)
        except TypeError:
            return provider(ticker)


def _factor_bundle(row: Mapping[str, Any], *, include_news: bool, include_insider: bool, include_macro: bool) -> tuple[dict[str, float | None], dict[str, str]]:
    pairs = {
        "fresh_source_evidence": _fresh_source_evidence(row, include_news=include_news, include_insider=include_insider),
        "expectation_change": _expectation_change(row),
        "earnings_surprise": _earnings_surprise(row),
        "fundamental_acceleration": _fundamental_acceleration(row),
        "market_confirmation": _market_confirmation(row),
        "ownership_insider": _ownership_insider(row, include_insider=include_insider),
        "catalyst_altdata_macro": _catalyst_altdata_macro(row, include_news=include_news, include_macro=include_macro),
        "risk_filter": _risk_filter(row),
    }
    return ({key: value for key, (value, _quality_label) in pairs.items()}, {key: quality for key, (_value, quality) in pairs.items()})


def _signals(factors: Mapping[str, float | None]) -> list[str]:
    labels = {
        "expectation_change": "forventninger/revisions",
        "fresh_source_evidence": "ferske kilder",
        "earnings_surprise": "earnings/guiding",
        "fundamental_acceleration": "fundamental akselerasjon",
        "market_confirmation": "pris/volum bekreftelse",
        "ownership_insider": "insider/eierskap",
        "catalyst_altdata_macro": "katalysator/makro",
        "risk_filter": "lavere risikofilter",
    }
    ranked = [
        f"{labels.get(key, key)} {value * 100:.0f}"
        for key, value in sorted(((k, v) for k, v in factors.items() if v is not None), key=lambda item: item[1], reverse=True)
        if value >= 0.62 and key != "risk_filter"
    ]
    return ranked[:6] or ["krever mer datagrunnlag"]


def _has_evidence(items: Sequence[Mapping[str, Any]] | None) -> bool:
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        if any(str(item.get(key) or "").strip() for key in ("title", "url", "source", "actor")):
            return True
    return False


def _hard_evidence_reject_reasons(
    *,
    include_news: bool,
    include_insider: bool,
    insider_evidence: Sequence[Mapping[str, Any]],
    bjellesau_evidence: Sequence[Mapping[str, Any]],
    news_evidence: Sequence[Mapping[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if include_insider and not (_has_evidence(insider_evidence) or _has_evidence(bjellesau_evidence)):
        reasons.append("mangler konkret insider-/bjellesau-evidence")
    if include_news and not _has_evidence(news_evidence):
        reasons.append("mangler konkret nyhets-/katalysator-evidence")
    return reasons


def _score_row(
    row: Mapping[str, Any],
    *,
    horizon: str,
    include_news: bool,
    include_insider: bool,
    include_macro: bool,
) -> EarlyWarningCandidate | None:
    ticker = _safe_ticker(row.get("ticker"))
    if not ticker:
        return None
    factors, quality = _factor_bundle(row, include_news=include_news, include_insider=include_insider, include_macro=include_macro)
    weights = HORIZON_WEIGHTS.get(horizon, HORIZON_WEIGHTS["3m"])
    score = 0.0
    missing_focus = []
    for key, weight in weights.items():
        value = factors.get(key)
        if value is None:
            missing_focus.append(key)
            continue
        score += float(value) * weight * 100.0
    data_penalty = min(22.0, len(missing_focus) * 4.0)
    risk_level = _risk_score(row)
    liquidity = _liquidity_penalty(row)
    score = max(0.0, min(100.0, score - data_penalty - liquidity - risk_level * 0.04))
    signals = _signals(factors)
    warnings = []
    if missing_focus:
        warnings.append("mangler tidligvarslingsdata: " + ", ".join(missing_focus[:4]))
    for key, label in (
        ("alpha_insider_error", "insiderkilde"),
        ("alpha_news_error", "nyhetskilde"),
        ("alpha_financial_search_error", "finanssøk"),
        ("alpha_nordic_search_error", "nordisk aktor-/insidersok"),
        ("alpha_earnings_error", "earningskilde"),
    ):
        if row.get(key):
            warning = summarize_source_error(label, row.get(key))
            if warning and warning not in warnings:
                warnings.append(warning)
    evidence_items, insider_evidence, bjellesau_evidence, news_evidence = _evidence_items(row, include_news=include_news, include_insider=include_insider)
    nbim_evidence = [dict(item) for item in row.get("nbim_evidence") or [] if isinstance(item, Mapping)]
    evidence_ledger = [dict(item) for item in row.get("evidence_ledger") or [] if isinstance(item, Mapping)]
    if not evidence_ledger and build_evidence_ledger is not None:
        try:
            evidence_ledger = build_evidence_ledger(row, found_by="Early Warning")
        except Exception:
            evidence_ledger = []
    source_diagnostics = _source_diagnostics(row)
    if include_insider and not insider_evidence and not bjellesau_evidence and factors.get("ownership_insider") is None:
        warnings.append("ingen konkrete insider-/bjellesaudetaljer funnet")
    if include_news and not news_evidence and factors.get("catalyst_altdata_macro") is None:
        warnings.append("ingen konkrete nyhetslenker funnet")
    rejects = []
    if liquidity >= 10:
        rejects.append("likviditet maa sjekkes")
    if risk_level >= 70:
        rejects.append("hoy volatilitet/drawdown")
    data_quality = "Svak" if missing_focus else "OK"
    ownership_scores = ownership_signal_scores(row) if include_insider else {"insider_score": None, "bjellesau_score": None}
    evidence_note = (
        f"{len(insider_evidence)} insider-spor, {len(bjellesau_evidence)} bjellesau-spor og {len(news_evidence)} nyhetsspor"
        if evidence_items else "ingen direkte kildespor"
    )
    why = f"{ticker}: {', '.join(signals[:3])} peker mest opp i Early Warning; funnet {evidence_note}. Bekreft kildene manuelt foer vurdering."
    cap = _market_cap(row)
    cap_fields = market_cap_fields(ticker, {**dict(row), "market_cap": cap})
    factor_scores = {key: (None if value is None else round(float(value) * 100.0, 1)) for key, value in factors.items()}
    return EarlyWarningCandidate(
        rank=0,
        ticker=ticker,
        name=str(row.get("name") or row.get("company") or ticker),
        market=str(row.get("market") or _infer_market(ticker)),
        horizon=horizon,
        mode="Early Warning V1",
        alpha_score=round(score, 1),
        hidden_potential_score=round(score, 1),
        early_warning_score=round(score, 1),
        potential_score=round(score + data_penalty, 1),
        catalyst_score=factor_scores.get("catalyst_altdata_macro"),
        underfollowed_score=factor_scores.get("expectation_change"),
        inflection_score=factor_scores.get("earnings_surprise"),
        insider_score=None if ownership_scores["insider_score"] is None else round(float(ownership_scores["insider_score"]) * 100.0, 1),
        bjellesau_score=None if ownership_scores["bjellesau_score"] is None else round(float(ownership_scores["bjellesau_score"]) * 100.0, 1),
        volume_score=factor_scores.get("market_confirmation"),
        macro_score=factor_scores.get("fundamental_acceleration"),
        evidence_score=round(100.0 - data_penalty, 1),
        risk_score=risk_level,
        crowdedness_penalty=0.0,
        liquidity_penalty=round(liquidity, 1),
        market_cap=cap,
        market_cap_currency=str(cap_fields["market_cap_currency"]),
        market_cap_nok_estimate=cap_fields["market_cap_nok_estimate"],
        market_cap_display=str(cap_fields["market_cap_display"]),
        data_quality=data_quality,
        base_score=round(_float(row.get("score"), 0.0) or 0.0, 2),
        why_now=why,
        thesis=f"{ticker} er en Early Warning-hypotese for {horizon}, ikke en handelsordre.",
        signals=signals,
        reject_reasons=rejects,
        warning_reasons=warnings,
        manual_review=("Manuell sjekk: " + ", ".join(rejects + warnings) + ".") if rejects or warnings else "Manuell sjekk: bekreft revisions, earnings, kurs/volum og datakilder.",
        factor_scores=factor_scores,
        factor_quality=quality,
        source="Early Warning V1",
        evidence_items=evidence_items,
        insider_evidence=insider_evidence,
        bjellesau_evidence=bjellesau_evidence,
        news_evidence=news_evidence,
        nbim_evidence=nbim_evidence,
        evidence_ledger=evidence_ledger,
        source_diagnostics=source_diagnostics,
    )


def run_early_warning(
    tickers: Iterable[str],
    *,
    horizon: str = "3m",
    limit: int = 10,
    max_scan: int = 60,
    include_news: bool = True,
    include_insider: bool = True,
    include_macro: bool = True,
    include_results: bool = True,
    include_ipo: bool = False,
    score_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    balance_markets: bool = False,
    data_window_months: int | None = None,
) -> dict[str, Any]:
    horizon = horizon if horizon in HORIZON_WEIGHTS else "3m"
    limit = max(1, min(int(limit or 10), 60))
    max_scan = max(limit, min(int(max_scan or 60), 250))
    clean: list[str] = []
    seen: set[str] = set()
    for raw in tickers or []:
        ticker = _safe_ticker(raw)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        clean.append(ticker)
        if len(clean) >= max_scan:
            break

    candidates: list[EarlyWarningCandidate] = []
    skipped: list[str] = []
    excluded: list[dict[str, Any]] = []
    excluded_reason_counts: dict[str, int] = {}
    market_excluded_counts: dict[str, int] = {}

    def progress(completed: int, ticker: str = "", status: str = "scanner") -> None:
        if progress_callback is None:
            return
        try:
            progress_callback({
                "completed": completed,
                "total": len(clean),
                "ticker": ticker,
                "status": status,
                "scored_count": len(candidates),
                "excluded_count": len(excluded),
                "skipped_count": len(skipped),
                "low_data_count": 0,
            })
        except Exception:
            pass

    def exclude(ticker_value: str, reasons: Sequence[str], row_value: Mapping[str, Any] | None = None) -> None:
        clean_reasons = [str(reason) for reason in reasons if str(reason).strip()] or ["ukjent aarsak"]
        for reason in clean_reasons:
            excluded_reason_counts[reason] = excluded_reason_counts.get(reason, 0) + 1
        market = str((row_value or {}).get("market") or _infer_market(ticker_value))
        market_excluded_counts[market] = market_excluded_counts.get(market, 0) + 1
        excluded.append({
            "ticker": ticker_value,
            "reasons": clean_reasons,
            "market": market,
        })
        skipped.append(ticker_value)

    progress(0, "", "starter")
    for index, ticker in enumerate(clean, start=1):
        row = None
        if score_provider is not None:
            try:
                row = _provider_call(score_provider, ticker, include_news=include_news, include_insider=include_insider)
            except Exception:
                row = None
        if not row:
            skipped.append(ticker)
            progress(index, ticker, "hoppet over")
            continue
        row = dict(row)
        row.setdefault("ticker", ticker)
        _combined_evidence, insider_evidence, bjellesau_evidence, news_evidence = _evidence_items(
            row,
            include_news=include_news,
            include_insider=include_insider,
        )
        hard_rejects = _hard_evidence_reject_reasons(
            include_news=include_news,
            include_insider=include_insider,
            insider_evidence=insider_evidence,
            bjellesau_evidence=bjellesau_evidence,
            news_evidence=news_evidence,
        )
        if hard_rejects:
            exclude(ticker, hard_rejects, row)
            progress(index, ticker, "ekskludert")
            continue
        candidate = _score_row(
            row,
            horizon=horizon,
            include_news=include_news,
            include_insider=include_insider,
            include_macro=include_macro,
        )
        if candidate is None:
            skipped.append(ticker)
            progress(index, ticker, "hoppet over")
            continue
        candidates.append(candidate)
        progress(index, ticker, "scoret")

    ranked = _balanced_candidates(candidates, limit=limit, balance_markets=bool(balance_markets))
    ranked = [EarlyWarningCandidate(**{**candidate.to_dict(), "rank": idx}) for idx, candidate in enumerate(ranked, start=1)]
    progress(len(clean), "", "ferdig")
    return {
        "horizon": horizon,
        "mode": "Early Warning V1",
        "market_cap_filter": "Etter valgt univers",
        "precision_level": "Datakvalitet styrt per faktor",
        "active_signals": ["Ferske kilder", "Insider/bjellesauer", "Nyheter/katalysator", "Forventningsendring", "Tidlig markedsbekreftelse"],
        "limit": limit,
        "max_scan": max_scan,
        "scanned_count": len(clean),
        "scored_count": len(candidates),
        "candidate_count": len(ranked),
        "all_candidate_count": len(candidates),
        "low_data_count": 0,
        "skipped_count": len(skipped),
        "skipped_tickers": skipped[:20],
        "excluded_count": len(excluded),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "excluded_samples": excluded[:15],
        "market_scan_counts": _market_counts_from_tickers(clean),
        "market_scored_counts": _market_counts_from_candidates(candidates),
        "market_candidate_counts": _market_counts_from_candidates(ranked),
        "market_excluded_counts": dict(sorted(market_excluded_counts.items())),
        "market_balance_enabled": bool(balance_markets),
        "data_window_months": data_window_months,
        "scope_limits": {
            "listed_equities": True,
            "ipo_preipo_included": bool(include_ipo),
            "ipo_note": "IPO/pre-IPO er merket separat og blandes ikke direkte med ordinare aksjer i denne V1-rangeringen.",
            "euronext_note": "Norge (.OL), Sverige (.ST), Finland (.HE) og Danmark (.CO) tas med naar valgt univers inneholder disse markedene.",
        },
        "candidates": [candidate.to_dict() for candidate in ranked],
        "disclaimer": "Tidligvarslingsliste for manuell analyse. Ikke investeringsraad og ikke automatisk handel.",
    }


__all__ = ["EarlyWarningCandidate", "HORIZON_WEIGHTS", "run_early_warning"]
