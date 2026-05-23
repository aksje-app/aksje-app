from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable, Iterable, Mapping, Sequence


HORIZON_WEIGHTS = {
    "1m": {
        "expectation_change": 0.16,
        "earnings_surprise": 0.16,
        "fundamental_acceleration": 0.14,
        "market_confirmation": 0.28,
        "ownership_insider": 0.08,
        "catalyst_altdata_macro": 0.14,
        "risk_filter": 0.04,
    },
    "3m": {
        "expectation_change": 0.25,
        "earnings_surprise": 0.20,
        "fundamental_acceleration": 0.16,
        "market_confirmation": 0.18,
        "ownership_insider": 0.10,
        "catalyst_altdata_macro": 0.08,
        "risk_filter": 0.03,
    },
    "6m": {
        "expectation_change": 0.22,
        "earnings_surprise": 0.16,
        "fundamental_acceleration": 0.26,
        "market_confirmation": 0.12,
        "ownership_insider": 0.08,
        "catalyst_altdata_macro": 0.12,
        "risk_filter": 0.04,
    },
    "12m": {
        "expectation_change": 0.18,
        "earnings_surprise": 0.12,
        "fundamental_acceleration": 0.28,
        "market_confirmation": 0.10,
        "ownership_insider": 0.06,
        "catalyst_altdata_macro": 0.16,
        "risk_filter": 0.10,
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
    volume_score: float | None
    macro_score: float | None
    evidence_score: float
    risk_score: float
    crowdedness_penalty: float
    liquidity_penalty: float
    market_cap: float | None
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
        row.get("result_inflection_score"),
        row.get("guidance_score"),
        row.get("surprise_score"),
    ]
    scores = [_unit(value) for value in values if value is not None]
    scores = [value for value in scores if value is not None]
    if scores:
        return max(scores), "ekte"
    if row.get("earnings_days_until") is not None:
        return 0.54, "proxy"
    return None, "mangler"


def _fundamental_acceleration(row: Mapping[str, Any]) -> tuple[float, str]:
    growth = _unit(row.get("revenue_growth"))
    margin = _unit(row.get("profit_margin"))
    quality = _score_part(row, "quality")
    fundamental_growth = _score_part(row, "fundamental_growth")
    values = [value for value in (growth, margin, quality, fundamental_growth) if value is not None]
    if not values:
        base = _float(row.get("score"), None)
        return (_clamp((base or 5.0) / 10.0), "proxy")
    return (_clamp(sum(values) / len(values)), "ekte" if growth is not None or margin is not None else "proxy")


def _market_confirmation(row: Mapping[str, Any]) -> tuple[float, str]:
    momentum = _score_part(row, "momentum")
    trend = _score_part(row, "trend")
    volume = _score_part(row, "volume")
    ret_1m = _ret(row.get("ret_1m"))
    ret_3m = _ret(row.get("ret_3m"))
    ret_score = _clamp(0.48 + ret_1m * 2.1 + ret_3m * 0.9)
    values = [value for value in (momentum, trend, volume, ret_score) if value is not None]
    return (_clamp(sum(values) / len(values)), "beregnet")


def _ownership_insider(row: Mapping[str, Any], include_insider: bool) -> tuple[float | None, str]:
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
    values = [
        row.get("catalyst_score"),
        row.get("small_news_big_impact_score"),
        row.get("local_news_score"),
        row.get("macro_tailwind_score"),
        row.get("commodity_tailwind_score"),
    ]
    scores = [_unit(value) for value in values if value is not None]
    scores = [value for value in scores if value is not None]
    if scores:
        return max(scores), "ekte"
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
    rejects = []
    if liquidity >= 10:
        rejects.append("likviditet maa sjekkes")
    if risk_level >= 70:
        rejects.append("hoy volatilitet/drawdown")
    data_quality = "Svak" if missing_focus else "OK"
    why = f"{ticker}: {', '.join(signals[:3])} peker mest opp i Early Warning. Bekreft manuelt foer vurdering."
    cap = _market_cap(row)
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
        insider_score=factor_scores.get("ownership_insider"),
        volume_score=factor_scores.get("market_confirmation"),
        macro_score=factor_scores.get("fundamental_acceleration"),
        evidence_score=round(100.0 - data_penalty, 1),
        risk_score=risk_level,
        crowdedness_penalty=0.0,
        liquidity_penalty=round(liquidity, 1),
        market_cap=cap,
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
) -> dict[str, Any]:
    horizon = horizon if horizon in HORIZON_WEIGHTS else "3m"
    limit = max(1, min(int(limit or 10), 15))
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
                "excluded_count": 0,
                "skipped_count": len(skipped),
                "low_data_count": 0,
            })
        except Exception:
            pass

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

    ranked = sorted(candidates, key=lambda item: item.early_warning_score, reverse=True)[:limit]
    ranked = [EarlyWarningCandidate(**{**candidate.to_dict(), "rank": idx}) for idx, candidate in enumerate(ranked, start=1)]
    progress(len(clean), "", "ferdig")
    return {
        "horizon": horizon,
        "mode": "Early Warning V1",
        "market_cap_filter": "Etter valgt univers",
        "precision_level": "Datakvalitet styrt per faktor",
        "active_signals": ["Forventningsendring", "Earnings", "Fundamental akselerasjon", "Pris/volum"],
        "limit": limit,
        "max_scan": max_scan,
        "scanned_count": len(clean),
        "scored_count": len(candidates),
        "candidate_count": len(ranked),
        "low_data_count": 0,
        "skipped_count": len(skipped),
        "skipped_tickers": skipped[:20],
        "excluded_count": 0,
        "excluded_reason_counts": {},
        "excluded_samples": [],
        "scope_limits": {
            "listed_equities": True,
            "ipo_preipo_included": bool(include_ipo),
            "ipo_note": "IPO/pre-IPO er merket separat og blandes ikke direkte med ordinare aksjer i denne V1-rangeringen.",
        },
        "candidates": [candidate.to_dict() for candidate in ranked],
        "disclaimer": "Tidligvarslingsliste for manuell analyse. Ikke investeringsraad og ikke automatisk handel.",
    }


__all__ = ["EarlyWarningCandidate", "HORIZON_WEIGHTS", "run_early_warning"]
