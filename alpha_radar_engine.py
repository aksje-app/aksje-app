from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence


ALPHA_RADAR_MODES = [
    "Blandet Alpha Radar",
    "Skjulte small/mid caps",
    "Insider og bjellesauer",
    "Ravare/makro-medvind",
    "Resultat-vendepunkt",
    "Uvanlig volum",
    "Kontraer etter fall",
]

MARKET_CAP_FILTERS = [
    "Alle",
    "Mikro/small",
    "Small/mid",
    "Unnga megacaps",
    "Kun large/mega",
]

PRECISION_LEVELS = [
    "Streng",
    "Balansert",
    "Utforskende",
]

MARKET_CAP_LIMITS = {
    "Mikro/small": 1_500_000_000,
    "Small/mid": 15_000_000_000,
    "Unnga megacaps": 75_000_000_000,
    "Kun large/mega": 40_000_000_000,
}

STRICT_CAP_FILTERS = {"Mikro/small", "Small/mid", "Kun large/mega"}

BASE_HIDDEN_WEIGHTS = {
    "underfollowed": 14.0,
    "inflection": 14.0,
    "catalyst": 12.0,
    "insider_bjellesau": 11.0,
    "volume_accumulation": 10.0,
    "macro_second_order": 9.0,
    "value_gap": 7.0,
    "surprise_gap": 7.0,
    "seasonality": 4.0,
    "technical_turn": 5.0,
    "why_now": 4.0,
    "evidence": 3.0,
}

HORIZON_MULTIPLIERS = {
    "1m": {
        "volume_accumulation": 1.75,
        "catalyst": 1.50,
        "technical_turn": 1.45,
        "why_now": 1.35,
        "value_gap": 0.75,
        "inflection": 0.90,
    },
    "3m": {
        "catalyst": 1.25,
        "insider_bjellesau": 1.18,
        "volume_accumulation": 1.15,
        "surprise_gap": 1.12,
    },
    "6m": {
        "underfollowed": 1.18,
        "inflection": 1.28,
        "macro_second_order": 1.20,
        "value_gap": 1.10,
        "technical_turn": 0.82,
    },
    "12m": {
        "underfollowed": 1.32,
        "inflection": 1.48,
        "macro_second_order": 1.35,
        "value_gap": 1.28,
        "volume_accumulation": 0.70,
        "technical_turn": 0.70,
    },
}

MODE_MULTIPLIERS = {
    "Blandet Alpha Radar": {},
    "Skjulte small/mid caps": {
        "underfollowed": 1.80,
        "value_gap": 1.25,
        "surprise_gap": 1.20,
        "evidence": 0.88,
    },
    "Insider og bjellesauer": {
        "insider_bjellesau": 2.25,
        "why_now": 1.25,
        "catalyst": 1.12,
    },
    "Ravare/makro-medvind": {
        "macro_second_order": 2.10,
        "seasonality": 1.35,
        "underfollowed": 1.12,
    },
    "Resultat-vendepunkt": {
        "inflection": 2.05,
        "surprise_gap": 1.45,
        "value_gap": 1.20,
    },
    "Uvanlig volum": {
        "volume_accumulation": 2.15,
        "technical_turn": 1.35,
        "why_now": 1.30,
    },
    "Kontraer etter fall": {
        "surprise_gap": 1.95,
        "value_gap": 1.45,
        "inflection": 1.25,
        "underfollowed": 1.15,
    },
}

ACTIVE_SIGNAL_FACTORS = {
    "Borsverdi": ("underfollowed", "value_gap"),
    "Insider/bjellesauer": ("insider_bjellesau",),
    "Nyheter/katalysator": ("catalyst", "why_now"),
    "Ravarer/makro": ("macro_second_order",),
    "Arstid/syklus": ("seasonality", "macro_second_order"),
    "Uvanlig volum": ("volume_accumulation", "technical_turn"),
    "Resultater": ("inflection", "surprise_gap"),
}

CATALYST_KEYWORDS = (
    "approval",
    "avtale",
    "backlog",
    "beat",
    "breakout",
    "contract",
    "earnings beat",
    "guidance",
    "insider buy",
    "licence",
    "margin expansion",
    "order",
    "partnership",
    "patent",
    "restructuring",
    "spin-off",
    "takeover",
    "turnaround",
    "upgrade",
)

MACRO_KEYWORDS = (
    "brent",
    "commodity",
    "copper",
    "energy",
    "export",
    "fertilizer",
    "gas",
    "gold",
    "laks",
    "metal",
    "offshore",
    "oil",
    "power",
    "salmon",
    "seafood",
    "shipping",
    "silver",
    "supply",
)

INFLECTION_KEYWORDS = (
    "cost cut",
    "guidance",
    "margin",
    "new ceo",
    "recovery",
    "refinancing",
    "restructuring",
    "turnaround",
)


@dataclass(frozen=True)
class AlphaRadarCandidate:
    rank: int
    ticker: str
    name: str
    market: str
    horizon: str
    mode: str
    alpha_score: float
    hidden_potential_score: float
    potential_score: float
    catalyst_score: float | None
    underfollowed_score: float
    inflection_score: float
    insider_score: float | None
    volume_score: float
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


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _normalize_unit(value: Any, default: float = 0.5) -> float:
    number = _float(value, None)
    if number is None:
        if default is None:
            return None
        return float(default)
    if number > 10:
        number = number / 100.0
    elif number > 1:
        number = number / 10.0
    return _clamp(number)


def _normalize_return(value: Any) -> float:
    number = _float(value, 0.0) or 0.0
    if abs(number) > 2:
        number = number / 100.0
    return number


def _score_from_return(value: Any, multiplier: float) -> float:
    return _clamp(0.5 + _normalize_return(value) * multiplier)


def _safe_ticker(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _stable_ticker_noise(ticker: str) -> float:
    total = sum((idx + 1) * ord(ch) for idx, ch in enumerate(_safe_ticker(ticker)))
    return (total % 17) / 1000.0


def _infer_market(ticker: str) -> str:
    ticker = _safe_ticker(ticker)
    suffix_map = {
        ".OL": "Norge",
        ".ST": "Sverige",
        ".CO": "Danmark",
        ".HE": "Finland",
        ".SA": "Brasil",
    }
    for suffix, label in suffix_map.items():
        if ticker.endswith(suffix):
            return label
    return "USA/annet"


def _row_score_part(row: Mapping[str, Any], key: str, default: float = 0.5) -> float:
    parts = row.get("score_parts")
    if isinstance(parts, Mapping) and key in parts:
        return _normalize_unit(parts.get(key), default)
    return _normalize_unit(row.get(key), default)


def _text_blob(row: Mapping[str, Any]) -> str:
    fields = [
        row.get("reason"),
        row.get("thesis"),
        row.get("note"),
        row.get("notes"),
        row.get("headline"),
        row.get("summary"),
        row.get("sector"),
        row.get("industry"),
        row.get("insider_label"),
    ]
    articles = row.get("articles")
    if isinstance(articles, Iterable) and not isinstance(articles, (str, bytes, Mapping)):
        for article in articles:
            if isinstance(article, Mapping):
                fields.extend([article.get("title"), article.get("summary"), article.get("description")])
            else:
                fields.append(article)
    return " ".join(str(x or "") for x in fields).lower()


def _news_count(row: Mapping[str, Any]) -> int | None:
    for key in ("news_count", "article_count"):
        value = _float(row.get(key), None)
        if value is not None:
            return int(value)
    articles = row.get("articles")
    if isinstance(articles, Iterable) and not isinstance(articles, (str, bytes, Mapping)):
        try:
            return len(list(articles))
        except Exception:
            return None
    return None


def _base_score(row: Mapping[str, Any]) -> float:
    score = _float(row.get("score"), None)
    if score is None:
        return 5.0
    if score > 100:
        return 10.0
    if score > 10:
        return score / 10.0
    return max(0.0, min(10.0, score))


def _known_market_cap(row: Mapping[str, Any]) -> float | None:
    value = _float(row.get("market_cap"), None)
    if value is None or value <= 0:
        return None
    return value


def _market_cap_filter_ok(row: Mapping[str, Any], market_cap_filter: str) -> bool:
    market_cap = _float(row.get("market_cap"), None)
    if market_cap is None or market_cap_filter == "Alle":
        return True
    if market_cap_filter in {"Mikro/small", "Small/mid", "Unnga megacaps"}:
        return market_cap <= MARKET_CAP_LIMITS[market_cap_filter]
    if market_cap_filter == "Kun large/mega":
        return market_cap >= MARKET_CAP_LIMITS[market_cap_filter]
    return True


def _market_cap_block_reason(row: Mapping[str, Any], market_cap_filter: str) -> str | None:
    market_cap = _known_market_cap(row)
    if market_cap_filter == "Alle":
        return None
    if market_cap is None:
        return f"ukjent borsverdi blokkert for {market_cap_filter}"
    if market_cap_filter in {"Mikro/small", "Small/mid", "Unnga megacaps"}:
        limit = MARKET_CAP_LIMITS[market_cap_filter]
        if market_cap > limit:
            return f"for stor borsverdi for {market_cap_filter}"
    if market_cap_filter == "Kun large/mega":
        minimum = MARKET_CAP_LIMITS[market_cap_filter]
        if market_cap < minimum:
            return "for liten borsverdi for Kun large/mega"
    return None


def normalize_alpha_radar_parameters(
    *,
    mode: str,
    market_cap_filter: str,
    precision_level: str,
    active_signals: Sequence[str] | None,
    fill_low_data: bool,
) -> dict[str, Any]:
    mode = mode if mode in ALPHA_RADAR_MODES else "Blandet Alpha Radar"
    precision_level = precision_level if precision_level in PRECISION_LEVELS else "Streng"
    market_cap_filter = market_cap_filter if market_cap_filter in MARKET_CAP_FILTERS else "Alle"
    warnings: list[str] = []

    if mode == "Skjulte small/mid caps":
        if market_cap_filter == "Kun large/mega":
            warnings.append("Skjulte small/mid caps kan ikke kombineres med Kun large/mega; bruker Small/mid.")
            market_cap_filter = "Small/mid"
        elif market_cap_filter in {"Alle", "Unnga megacaps"}:
            warnings.append("Skjulte small/mid caps bruker Small/mid som hard borsverdi-gate.")
            market_cap_filter = "Small/mid"

    max_signals = 3 if precision_level == "Streng" else 4 if precision_level == "Balansert" else 5
    clean_signals: list[str] = []
    for signal in active_signals or []:
        if signal in ACTIVE_SIGNAL_FACTORS and signal not in clean_signals:
            clean_signals.append(signal)
    if len(clean_signals) > max_signals:
        warnings.append(f"Signal-lupe er begrenset til {max_signals} signaler i {precision_level} presisjon.")
        clean_signals = clean_signals[:max_signals]

    if precision_level == "Streng" and fill_low_data:
        warnings.append("Streng presisjon tillater ikke lav-data utfylling.")
        fill_low_data = False
    if market_cap_filter in STRICT_CAP_FILTERS and fill_low_data:
        warnings.append(f"{market_cap_filter} krever kjent borsverdi; lav-data utfylling er slatt av.")
        fill_low_data = False

    return {
        "mode": mode,
        "market_cap_filter": market_cap_filter,
        "precision_level": precision_level,
        "active_signals": clean_signals,
        "fill_low_data": bool(fill_low_data),
        "parameter_warnings": warnings,
    }


def _data_quality_gate(
    row: Mapping[str, Any],
    *,
    market_cap_filter: str,
    precision_level: str,
) -> dict[str, Any]:
    blocking: list[str] = []
    warnings: list[str] = []

    cap_reason = _market_cap_block_reason(row, market_cap_filter)
    if cap_reason:
        blocking.append(cap_reason)

    market_cap = _known_market_cap(row)
    if precision_level == "Streng" and market_cap is None:
        blocking.append("ukjent borsverdi blokkert i Streng presisjon")
    elif precision_level == "Balansert" and market_cap is None:
        warnings.append("ukjent borsverdi")

    if row.get("data_missing"):
        if precision_level in {"Streng", "Balansert"}:
            blocking.append("lav-data kandidat blokkert")
        else:
            warnings.append("lav-data kandidat")

    required_score_fields = ("score", "ret_1m", "ret_3m", "volatility", "max_drawdown")
    missing = [key for key in required_score_fields if row.get(key) is None]
    if precision_level == "Streng" and missing:
        blocking.append("mangler kjernefelter: " + ", ".join(missing[:4]))
    elif missing:
        warnings.append("mangler kjernefelter: " + ", ".join(missing[:4]))

    data_quality = "Blokkert" if blocking else "Svak" if warnings else "OK"
    return {
        "ok": not blocking,
        "data_quality": data_quality,
        "blocking_reasons": blocking,
        "warning_reasons": warnings,
    }


def _underfollowed_score(row: Mapping[str, Any], base_score: float) -> float:
    market_cap = _float(row.get("market_cap"), None)
    if market_cap is None:
        score = 0.56 if not row.get("data_missing") else 0.46
    elif market_cap < 750_000_000:
        score = 0.88
    elif market_cap < 3_000_000_000:
        score = 0.79
    elif market_cap < 12_000_000_000:
        score = 0.67
    elif market_cap < 40_000_000_000:
        score = 0.52
    else:
        score = 0.30

    news = _news_count(row)
    if news is not None:
        if news <= 1:
            score += 0.10
        elif news <= 3:
            score += 0.06
        elif news >= 10:
            score -= 0.10

    analyst_count = _float(row.get("analyst_count"), None)
    if analyst_count is None:
        score += 0.03
    elif analyst_count <= 3:
        score += 0.10
    elif analyst_count >= 15:
        score -= 0.10

    if 5.0 <= base_score <= 7.8:
        score += 0.06
    elif base_score >= 8.8:
        score -= 0.08
    return _clamp(score)


def _has_articles_or_news(row: Mapping[str, Any]) -> bool:
    articles = row.get("articles")
    if isinstance(articles, Sequence) and not isinstance(articles, (str, bytes)):
        return len(articles) > 0
    return bool(_news_count(row))


def _catalyst_score(row: Mapping[str, Any], include_news: bool, include_insider: bool) -> float | None:
    explicit_values = [
        row.get("catalyst_score"),
        row.get("event_score"),
        row.get("local_news_score"),
        row.get("small_news_big_impact_score"),
    ]
    explicit_scores = [_normalize_unit(value, None) for value in explicit_values if value is not None]
    explicit_scores = [value for value in explicit_scores if value is not None]
    if explicit_scores:
        return max(explicit_scores)

    text = _text_blob(row)
    keyword_hits = sum(1 for word in CATALYST_KEYWORDS if word in text)
    if not include_news and not keyword_hits:
        return None
    if include_news and not _has_articles_or_news(row) and not keyword_hits:
        return None
    keyword_score = _clamp(0.40 + keyword_hits * 0.085)
    sentiment_raw = row.get("sentiment", row.get("news_sentiment"))
    sentiment = _normalize_unit(sentiment_raw, 0.5) if sentiment_raw is not None else 0.5
    volume = _row_score_part(row, "volume", 0.5)
    insider = _normalize_unit(row.get("insider_score"), 0.5) if include_insider and row.get("insider_score") is not None else 0.5
    news_boost = 0.0
    if include_news:
        count = _news_count(row)
        if count is not None:
            news_boost = min(max(count, 0), 8) * 0.012
    return _clamp(keyword_score * 0.34 + sentiment * 0.22 + volume * 0.18 + insider * 0.18 + 0.05 + news_boost)


def _inflection_score(row: Mapping[str, Any]) -> float:
    explicit_values = [row.get("inflection_score"), row.get("turnaround_score"), row.get("result_inflection_score")]
    explicit_scores = [_normalize_unit(value, None) for value in explicit_values if value is not None]
    explicit_scores = [value for value in explicit_scores if value is not None]
    if explicit_scores:
        return max(explicit_scores)

    ret_1m = _normalize_return(row.get("ret_1m"))
    ret_3m = _normalize_return(row.get("ret_3m"))
    ret_6m = _normalize_return(row.get("ret_6m"))
    ret_1y = _normalize_return(row.get("ret_1y"))
    quality = _row_score_part(row, "quality", 0.5)
    growth = _row_score_part(row, "fundamental_growth", 0.5)
    debt = _row_score_part(row, "debt", 0.5)
    text_hits = sum(1 for word in INFLECTION_KEYWORDS if word in _text_blob(row))

    price_turn = 0.48
    if ret_6m < -0.10 and ret_1m > 0.03:
        price_turn += 0.18
    if ret_3m < 0.03 and ret_1m > 0.06:
        price_turn += 0.12
    if ret_1y < -0.15 and ret_3m > 0.05:
        price_turn += 0.10

    fundamentals = quality * 0.34 + growth * 0.42 + debt * 0.24
    return _clamp(price_turn * 0.46 + fundamentals * 0.42 + min(text_hits, 3) * 0.04)


def _insider_bjellesau_score(row: Mapping[str, Any], include_insider: bool) -> float | None:
    explicit_values = [
        row.get("bjellesau_score"),
        row.get("smart_money_score"),
        row.get("owner_signal"),
        row.get("insider_quality_score"),
        row.get("historical_insider_quality_score"),
    ]
    explicit_scores = [_normalize_unit(value, None) for value in explicit_values if value is not None]
    explicit_scores = [value for value in explicit_scores if value is not None]
    if explicit_scores:
        return max(explicit_scores)
    has_insider_score = row.get("insider_score") is not None
    buy_count = _float(row.get("insider_buy_count", row.get("buy_count")), 0.0) or 0.0
    sell_count = _float(row.get("insider_sell_count", row.get("sell_count")), 0.0) or 0.0
    label = str(row.get("insider_label") or "").lower()
    if not include_insider and not has_insider_score and not buy_count and not sell_count and not label:
        return None
    if include_insider and not has_insider_score and not buy_count and not sell_count and not label:
        return None
    insider = _normalize_unit(row.get("insider_score"), 0.5) if has_insider_score else 0.5
    score = insider * 0.70 + 0.15
    if buy_count > sell_count:
        score += min((buy_count - sell_count) * 0.035, 0.14)
    if "buy" in label or "kjop" in label:
        score += 0.06
    if "sell" in label or "salg" in label:
        score -= 0.08
    return _clamp(score)


def _volume_accumulation_score(row: Mapping[str, Any]) -> float:
    explicit = row.get("volume_accumulation_score", row.get("abnormal_volume_score"))
    if explicit is not None:
        return _normalize_unit(explicit)
    volume = _row_score_part(row, "volume", row.get("volume_trend_score", 0.5))
    ret_1m = _normalize_return(row.get("ret_1m"))
    ret_3m = _normalize_return(row.get("ret_3m"))
    quiet_break = 0.5
    if abs(ret_3m) < 0.08 and ret_1m > 0.04:
        quiet_break += 0.16
    if ret_3m < 0 and ret_1m > 0.03:
        quiet_break += 0.12
    return _clamp(volume * 0.62 + quiet_break * 0.38)


def _macro_second_order_score(row: Mapping[str, Any]) -> float | None:
    explicit = row.get("macro_tailwind_score", row.get("commodity_tailwind_score"))
    if explicit is not None:
        return _normalize_unit(explicit)
    text = _text_blob(row)
    hits = sum(1 for word in MACRO_KEYWORDS if word in text)
    sector = str(row.get("sector") or row.get("industry") or "").lower()
    sector_hits = sum(1 for word in MACRO_KEYWORDS if word in sector)
    has_beta = any(row.get(key) is not None for key in ("oil_beta", "commodity_beta", "fx_tailwind"))
    if not hits and not sector_hits and not has_beta:
        return None
    beta = max(
        _normalize_unit(row.get("oil_beta"), 0.5),
        _normalize_unit(row.get("commodity_beta"), 0.5),
        _normalize_unit(row.get("fx_tailwind"), 0.5),
    )
    return _clamp(0.42 + min(hits + sector_hits, 5) * 0.055 + (beta - 0.5) * 0.42)


def _value_gap_score(row: Mapping[str, Any]) -> float:
    explicit = row.get("value_gap_score", row.get("value_score"))
    if explicit is not None:
        return _normalize_unit(explicit)
    value_part = _row_score_part(row, "value", 0.5)
    pe = _float(row.get("forward_pe", row.get("trailing_pe")), None)
    pe_score = value_part
    if pe is not None and pe > 0:
        pe_score = _clamp(1.0 - pe / 55.0)
    drawdown = abs(min(_float(row.get("max_drawdown"), -0.12) or -0.12, 0.0))
    quality = _row_score_part(row, "quality", 0.5)
    pain_discount = _clamp(0.45 + drawdown * 0.70)
    return _clamp(pe_score * 0.45 + value_part * 0.25 + pain_discount * 0.18 + quality * 0.12)


def _surprise_gap_score(row: Mapping[str, Any], inflection: float, catalyst: float) -> float:
    ret_1m = _normalize_return(row.get("ret_1m"))
    ret_3m = _normalize_return(row.get("ret_3m"))
    ret_6m = _normalize_return(row.get("ret_6m"))
    ret_1y = _normalize_return(row.get("ret_1y"))
    old_pain = 0.0
    if ret_6m < -0.08:
        old_pain += 0.16
    if ret_1y < -0.15:
        old_pain += 0.14
    early_green = 0.0
    if ret_1m > 0.02:
        early_green += 0.12
    if ret_3m > -0.02:
        early_green += 0.08
    return _clamp(0.38 + old_pain + early_green + inflection * 0.22 + catalyst * 0.16)


def _seasonality_score(row: Mapping[str, Any]) -> float:
    explicit = row.get("seasonality_score", row.get("cycle_score"))
    if explicit is not None:
        return _normalize_unit(explicit)
    text = _text_blob(row)
    seasonal_words = ("season", "winter", "summer", "q4", "harvest", "retail", "travel", "tourism", "shipping", "energy", "salmon")
    hits = sum(1 for word in seasonal_words if word in text)
    return _clamp(0.46 + min(hits, 4) * 0.055)


def _technical_turn_score(row: Mapping[str, Any]) -> float:
    trend = _row_score_part(row, "trend", 0.5)
    momentum = _row_score_part(row, "momentum", None)
    if momentum is None:
        momentum = (
            _score_from_return(row.get("ret_1m"), 2.5) * 0.45
            + _score_from_return(row.get("ret_3m"), 1.4) * 0.32
            + _score_from_return(row.get("ret_6m"), 0.8) * 0.23
        )
    ret_1m = _normalize_return(row.get("ret_1m"))
    ret_3m = _normalize_return(row.get("ret_3m"))
    early_turn = 0.5
    if ret_1m > 0.03 and ret_3m < 0.12:
        early_turn += 0.14
    if ret_1m > 0.08:
        early_turn += 0.07
    return _clamp(momentum * 0.48 + trend * 0.28 + early_turn * 0.24)


def _evidence_score(row: Mapping[str, Any], include_news: bool, include_insider: bool) -> float:
    keys = (
        "score",
        "ret_1m",
        "ret_3m",
        "ret_6m",
        "ret_1y",
        "volatility",
        "max_drawdown",
        "profit_margin",
        "revenue_growth",
        "market_cap",
    )
    count = sum(1 for key in keys if row.get(key) is not None)
    if include_news and _news_count(row):
        count += 1
    if include_insider and row.get("insider_score") is not None:
        count += 1
    if row.get("data_missing"):
        return 0.28
    return _clamp(0.28 + min(count, 11) * 0.062)


def _risk_score(row: Mapping[str, Any]) -> float:
    explicit = row.get("risk_score")
    if explicit is not None:
        value = _float(explicit, None)
        if value is not None:
            if value <= 1:
                return round(_clamp(value) * 100.0, 1)
            return round(_clamp(value / 100.0) * 100.0, 1)
    volatility = _float(row.get("volatility"), 0.026) or 0.026
    if volatility > 1:
        volatility = volatility / 100.0
    drawdown = abs(min(_float(row.get("max_drawdown"), -0.18) or -0.18, 0.0))
    risk = volatility * 880.0 + drawdown * 88.0
    if row.get("data_missing"):
        risk += 12.0
    return round(max(5.0, min(95.0, risk)), 1)


def _crowdedness_penalty(row: Mapping[str, Any], mode: str) -> float:
    market_cap = _float(row.get("market_cap"), None)
    news = _news_count(row)
    score = _base_score(row)
    penalty = 0.0
    if market_cap is not None:
        if market_cap > 250_000_000_000:
            penalty += 24.0
        elif market_cap > 100_000_000_000:
            penalty += 17.0
        elif market_cap > 40_000_000_000:
            penalty += 9.0
    if news is not None and news >= 12:
        penalty += 6.0
    if score >= 8.6:
        penalty += 5.0
    if mode in {"Skjulte small/mid caps", "Kontraer etter fall"}:
        penalty *= 1.22
    return round(min(30.0, penalty), 1)


def _liquidity_penalty(row: Mapping[str, Any]) -> float:
    if row.get("data_missing"):
        return 5.0
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


def _why_now_score(factors: Mapping[str, float]) -> float:
    return _clamp(
        factors["catalyst"] * 0.28
        + factors["volume_accumulation"] * 0.22
        + factors["insider_bjellesau"] * 0.20
        + factors["inflection"] * 0.20
        + factors["macro_second_order"] * 0.10
    )


def _adjusted_weights(horizon: str, mode: str, active_signals: Sequence[str] | None) -> dict[str, float]:
    weights = dict(BASE_HIDDEN_WEIGHTS)
    for key, mult in HORIZON_MULTIPLIERS.get(horizon, {}).items():
        weights[key] = weights.get(key, 0.0) * mult
    for key, mult in MODE_MULTIPLIERS.get(mode, {}).items():
        weights[key] = weights.get(key, 0.0) * mult
    for signal in active_signals or []:
        for key in ACTIVE_SIGNAL_FACTORS.get(signal, ()):
            weights[key] = weights.get(key, 0.0) * 1.18
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def _factor_quality(row: Mapping[str, Any], factor: str, value: float | None) -> str:
    if value is None:
        return "mangler"
    if factor == "catalyst":
        if any(row.get(key) is not None for key in ("catalyst_score", "event_score", "local_news_score", "small_news_big_impact_score")):
            return "ekte"
        if _has_articles_or_news(row):
            return "ekte"
        return "proxy"
    if factor == "insider_bjellesau":
        if any(row.get(key) is not None for key in ("bjellesau_score", "smart_money_score", "owner_signal", "insider_quality_score", "historical_insider_quality_score", "insider_score")):
            return "ekte"
        if row.get("insider_buy_count") is not None or row.get("buy_count") is not None or row.get("insider_label"):
            return "proxy"
        return "mangler"
    if factor == "macro_second_order":
        if row.get("macro_tailwind_score") is not None or row.get("commodity_tailwind_score") is not None:
            return "ekte"
        return "proxy"
    if factor in {"underfollowed", "inflection", "volume_accumulation", "value_gap", "surprise_gap", "seasonality", "technical_turn"}:
        return "proxy" if row.get("data_missing") else "beregnet"
    return "beregnet"


def _factor_scores(row: Mapping[str, Any], include_news: bool, include_insider: bool) -> dict[str, float | None]:
    base_score = _base_score(row)
    catalyst = _catalyst_score(row, include_news=include_news, include_insider=include_insider)
    inflection = _inflection_score(row)
    factors = {
        "underfollowed": _underfollowed_score(row, base_score),
        "inflection": inflection,
        "catalyst": catalyst,
        "insider_bjellesau": _insider_bjellesau_score(row, include_insider=include_insider),
        "volume_accumulation": _volume_accumulation_score(row),
        "macro_second_order": _macro_second_order_score(row),
        "value_gap": _value_gap_score(row),
        "surprise_gap": _surprise_gap_score(row, inflection=inflection, catalyst=catalyst or 0.0),
        "seasonality": _seasonality_score(row),
        "technical_turn": _technical_turn_score(row),
        "evidence": _evidence_score(row, include_news=include_news, include_insider=include_insider),
    }
    scoring = {key: (0.0 if value is None else float(value)) for key, value in factors.items()}
    factors["why_now"] = _why_now_score(scoring)
    return factors


def _signals(row: Mapping[str, Any], factors: Mapping[str, float], risk_level: float) -> list[str]:
    labels = {
        "underfollowed": "underdekket",
        "inflection": "vendepunkt",
        "catalyst": "katalysator",
        "insider_bjellesau": "insider/bjellesau",
        "volume_accumulation": "uvanlig volum",
        "macro_second_order": "makro/ravare",
        "value_gap": "prising-gap",
        "surprise_gap": "surprise gap",
        "seasonality": "arstid/syklus",
        "technical_turn": "teknisk vending",
    }
    signals = [
        f"{labels[key]} {value * 100:.0f}"
        for key, value in sorted(factors.items(), key=lambda item: item[1], reverse=True)
        if key in labels and value >= 0.62
    ][:5]
    ret_1m = _normalize_return(row.get("ret_1m"))
    ret_6m = _normalize_return(row.get("ret_6m"))
    if ret_6m < -0.08 and ret_1m > 0.03:
        signals.insert(0, "pain-to-gain: svak 6m, bedre 1m")
    if risk_level >= 68:
        signals.append("hoy risiko")
    if row.get("data_missing"):
        signals.append("lav datadekning")
    return signals[:6] or ["krever manuell validering"]


def _why_now(row: Mapping[str, Any], factors: Mapping[str, float], signals: Sequence[str]) -> str:
    ticker = _safe_ticker(row.get("ticker"))
    if row.get("data_missing"):
        return f"{ticker} er med som lav-data hypotese fordi universet trenger manuell sjekk, ikke fordi datagrunnlaget er sterkt."
    top = sorted(
        ((key, value) for key, value in factors.items() if key not in {"evidence"}),
        key=lambda item: item[1],
        reverse=True,
    )[:3]
    label_map = {
        "underfollowed": "underdekkethet",
        "inflection": "vendepunkt",
        "catalyst": "katalysator",
        "insider_bjellesau": "insider/bjellesau",
        "volume_accumulation": "uvanlig volum",
        "macro_second_order": "makro/ravare-medvind",
        "value_gap": "prising-gap",
        "surprise_gap": "surprise gap",
        "seasonality": "sesong/syklus",
        "technical_turn": "teknisk vending",
        "why_now": "why-now",
    }
    factors_text = ", ".join(label_map.get(key, key) for key, _value in top)
    signal_text = "; ".join(list(signals)[:2])
    return f"{ticker}: {factors_text} peker mest opp akkurat naa. Sjekk manuelt: {signal_text}."


def _reject_reasons(row: Mapping[str, Any], risk_level: float, crowdedness: float, liquidity: float, evidence: float) -> list[str]:
    reasons: list[str] = []
    if evidence < 0.45:
        reasons.append("tynt datagrunnlag")
    if crowdedness >= 12:
        reasons.append("kan vaere for kjent/overdekket")
    if liquidity >= 10:
        reasons.append("likviditet maa sjekkes")
    if risk_level >= 70:
        reasons.append("hoy volatilitet/drawdown")
    if _news_count(row) == 0:
        reasons.append("mangler nyhetsbekreftelse")
    return reasons[:4]


def _manual_review_note(row: Mapping[str, Any], reject_reasons: Sequence[str]) -> str:
    if row.get("data_missing"):
        return "Manuell sjekk: lav-data hypotese. Bekreft ticker, likviditet, nyheter og tall foer den vurderes videre."
    if reject_reasons:
        return "Manuell sjekk: " + ", ".join(reject_reasons) + "."
    return "Manuell sjekk: bekreft nyhetskilde, likviditet, tall, insiderdata og posisjonsstorrelse."


def _provider_call(provider: Callable[..., Mapping[str, Any] | None], ticker: str, include_news: bool, include_insider: bool) -> Mapping[str, Any] | None:
    try:
        return provider(ticker, use_news=include_news, include_insider=include_insider)
    except TypeError:
        try:
            return provider(ticker, use_news=include_news)
        except TypeError:
            return provider(ticker)


def _fallback_row(ticker: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": ticker,
        "score": 5.0,
        "market": _infer_market(ticker),
        "data_missing": True,
    }


def _score_candidate(
    row: Mapping[str, Any],
    *,
    horizon: str,
    mode: str,
    include_news: bool,
    include_insider: bool,
    market_cap_filter: str,
    active_signals: Sequence[str] | None,
) -> AlphaRadarCandidate | None:
    ticker = _safe_ticker(row.get("ticker"))
    if not ticker:
        return None

    factors = _factor_scores(row, include_news=include_news, include_insider=include_insider)
    scoring_factors = {key: (0.0 if value is None else float(value)) for key, value in factors.items()}
    factor_quality = {key: _factor_quality(row, key, value) for key, value in factors.items() if key != "why_now"}
    weights = _adjusted_weights(horizon, mode, active_signals)
    raw = sum(scoring_factors.get(key, 0.0) * weight for key, weight in weights.items()) * 100.0
    risk_level = _risk_score(row)
    crowdedness = _crowdedness_penalty(row, mode=mode)
    liquidity = _liquidity_penalty(row)
    evidence = scoring_factors["evidence"] * 100.0

    penalty = risk_level * 0.10 + crowdedness + liquidity
    if scoring_factors["why_now"] < 0.50:
        penalty += 5.0
    missing_focus = [
        signal for signal in active_signals or []
        if any(factors.get(factor_key) is None for factor_key in ACTIVE_SIGNAL_FACTORS.get(signal, ()))
    ]
    if missing_focus:
        penalty += min(18.0, 7.0 * len(missing_focus))
    hidden = max(0.0, min(100.0, raw - penalty + _stable_ticker_noise(ticker) * 100.0))
    if row.get("data_missing"):
        hidden = min(hidden, 48.0)

    signals = _signals(row, scoring_factors, risk_level)
    reject_reasons = _reject_reasons(row, risk_level, crowdedness, liquidity, scoring_factors["evidence"])
    warning_reasons = list(row.get("warning_reasons") or [])
    if missing_focus:
        warning_reasons.append("mangler data for valgt signal-lupe: " + ", ".join(missing_focus[:3]))
    why_now = _why_now(row, scoring_factors, signals)
    thesis = (
        f"{ticker} er en {mode.lower()}-hypotese for {horizon}. "
        f"Hidden score drives av {', '.join(signals[:3])}."
    )

    return AlphaRadarCandidate(
        rank=0,
        ticker=ticker,
        name=str(row.get("name") or row.get("company") or ticker),
        market=str(row.get("market") or _infer_market(ticker)),
        horizon=horizon,
        mode=mode,
        alpha_score=round(hidden, 1),
        hidden_potential_score=round(hidden, 1),
        potential_score=round(raw, 1),
        catalyst_score=None if factors["catalyst"] is None else round(float(factors["catalyst"]) * 100.0, 1),
        underfollowed_score=round(scoring_factors["underfollowed"] * 100.0, 1),
        inflection_score=round(scoring_factors["inflection"] * 100.0, 1),
        insider_score=None if factors["insider_bjellesau"] is None else round(float(factors["insider_bjellesau"]) * 100.0, 1),
        volume_score=round(scoring_factors["volume_accumulation"] * 100.0, 1),
        macro_score=None if factors["macro_second_order"] is None else round(float(factors["macro_second_order"]) * 100.0, 1),
        evidence_score=round(evidence, 1),
        risk_score=round(risk_level, 1),
        crowdedness_penalty=round(crowdedness, 1),
        liquidity_penalty=round(liquidity, 1),
        market_cap=_known_market_cap(row),
        data_quality=str(row.get("data_quality") or "OK"),
        base_score=round(_base_score(row), 2),
        why_now=why_now,
        thesis=thesis,
        signals=signals,
        reject_reasons=reject_reasons,
        warning_reasons=warning_reasons,
        manual_review=_manual_review_note(row, list(reject_reasons) + warning_reasons),
        factor_scores={key: (None if value is None else round(float(value) * 100.0, 1)) for key, value in factors.items()},
        factor_quality=factor_quality,
        source="Alpha Radar V2 Contrarian / Hidden Potential",
    )


def run_alpha_radar(
    tickers: Iterable[str],
    *,
    horizon: str = "3m",
    limit: int = 10,
    max_scan: int = 60,
    include_news: bool = False,
    include_insider: bool = False,
    mode: str = "Blandet Alpha Radar",
    market_cap_filter: str = "Alle",
    precision_level: str = "Streng",
    active_signals: Sequence[str] | None = None,
    fill_low_data: bool = True,
    score_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    insider_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    news_provider: Callable[..., Iterable[Mapping[str, Any]]] | None = None,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Build a contrarian hidden-potential shortlist from explicit tickers.

    The engine is side-effect free: it does not trade, persist, or fetch by
    itself. Callers inject providers and decide when to run it.
    """

    horizon = horizon if horizon in HORIZON_MULTIPLIERS else "3m"
    params = normalize_alpha_radar_parameters(
        mode=mode,
        market_cap_filter=market_cap_filter,
        precision_level=precision_level,
        active_signals=active_signals,
        fill_low_data=fill_low_data,
    )
    mode = params["mode"]
    market_cap_filter = params["market_cap_filter"]
    precision_level = params["precision_level"]
    active_signals = params["active_signals"]
    fill_low_data = params["fill_low_data"]
    limit = max(1, min(int(limit or 10), 15))
    max_scan = max(limit, min(int(max_scan or 60), 250))

    seen: set[str] = set()
    clean_tickers: list[str] = []
    for raw in tickers or []:
        ticker = _safe_ticker(raw)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        clean_tickers.append(ticker)
        if len(clean_tickers) >= max_scan:
            break

    candidates: list[AlphaRadarCandidate] = []
    skipped: list[str] = []
    excluded: list[dict[str, Any]] = []
    excluded_reason_counts: dict[str, int] = {}
    low_data_count = 0

    def _progress(completed: int, ticker_value: str = "", status: str = "scanner") -> None:
        if progress_callback is None:
            return
        try:
            progress_callback({
                "completed": int(completed),
                "total": len(clean_tickers),
                "ticker": ticker_value,
                "status": status,
                "scored_count": len(candidates),
                "excluded_count": len(excluded),
                "skipped_count": len(skipped),
                "low_data_count": low_data_count,
            })
        except Exception:
            pass

    def _exclude(ticker_value: str, reasons: Sequence[str], row_value: Mapping[str, Any] | None = None) -> None:
        clean_reasons = [str(reason) for reason in reasons if str(reason).strip()] or ["ukjent aarsak"]
        for reason in clean_reasons:
            excluded_reason_counts[reason] = excluded_reason_counts.get(reason, 0) + 1
        excluded.append({
            "ticker": ticker_value,
            "reasons": clean_reasons,
            "market_cap": _known_market_cap(row_value or {}),
        })
        skipped.append(ticker_value)

    _progress(0, "", "starter")

    for index, ticker in enumerate(clean_tickers, start=1):
        row: Mapping[str, Any] | None = None
        if score_provider is not None:
            try:
                row = _provider_call(score_provider, ticker, include_news=include_news, include_insider=include_insider)
            except Exception:
                row = None
        if not row:
            if not fill_low_data:
                _exclude(ticker, ["mangler analysedata"])
                _progress(index, ticker, "ekskludert")
                continue
            row = _fallback_row(ticker)
            low_data_count += 1
        else:
            row = dict(row)
            row.setdefault("ticker", ticker)

        if include_news and news_provider is not None and not row.get("articles"):
            try:
                row["articles"] = list(news_provider(ticker) or [])
            except Exception:
                row["articles"] = []
        if include_insider and insider_provider is not None and row.get("insider_score") is None:
            try:
                insider = insider_provider(ticker)
                if isinstance(insider, Mapping):
                    row["insider_score"] = insider.get("score")
                    row["insider_label"] = insider.get("label") or insider.get("direction")
                    row["insider_buy_count"] = insider.get("buy_count")
                    row["insider_sell_count"] = insider.get("sell_count")
            except Exception:
                pass

        gate = _data_quality_gate(
            row,
            market_cap_filter=market_cap_filter,
            precision_level=precision_level,
        )
        if not gate["ok"]:
            _exclude(ticker, gate["blocking_reasons"], row)
            _progress(index, ticker, "ekskludert")
            continue
        row = dict(row)
        row["data_quality"] = gate["data_quality"]
        row["warning_reasons"] = list(gate["warning_reasons"])

        candidate = _score_candidate(
            row,
            horizon=horizon,
            mode=mode,
            include_news=include_news,
            include_insider=include_insider,
            market_cap_filter=market_cap_filter,
            active_signals=active_signals,
        )
        if candidate is None:
            skipped.append(ticker)
            _progress(index, ticker, "hoppet over")
        else:
            candidates.append(candidate)
            _progress(index, ticker, "scoret")

    ranked = sorted(candidates, key=lambda item: item.hidden_potential_score, reverse=True)[:limit]
    ranked = [
        AlphaRadarCandidate(**{**candidate.to_dict(), "rank": idx})
        for idx, candidate in enumerate(ranked, start=1)
    ]

    _progress(len(clean_tickers), "", "ferdig")

    return {
        "horizon": horizon,
        "mode": mode,
        "market_cap_filter": market_cap_filter,
        "precision_level": precision_level,
        "active_signals": list(active_signals or []),
        "parameter_warnings": list(params.get("parameter_warnings") or []),
        "effective_parameters": {
            "mode": mode,
            "market_cap_filter": market_cap_filter,
            "precision_level": precision_level,
            "active_signals": list(active_signals or []),
            "fill_low_data": bool(fill_low_data),
        },
        "limit": limit,
        "max_scan": max_scan,
        "scanned_count": len(clean_tickers),
        "scored_count": len(candidates),
        "candidate_count": len(ranked),
        "low_data_count": low_data_count,
        "skipped_count": len(skipped),
        "skipped_tickers": skipped[:20],
        "excluded_count": len(excluded),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "excluded_samples": excluded[:15],
        "candidates": [candidate.to_dict() for candidate in ranked],
        "disclaimer": "Hypoteseliste for manuell analyse. Ikke investeringsraad og ikke automatisk handel.",
    }


__all__ = [
    "ALPHA_RADAR_MODES",
    "MARKET_CAP_FILTERS",
    "PRECISION_LEVELS",
    "AlphaRadarCandidate",
    "normalize_alpha_radar_parameters",
    "run_alpha_radar",
]
