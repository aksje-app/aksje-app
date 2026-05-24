"""
universe_engine.py

v18.5.10: Smart AI-utvalg koblet til felles datamodell og service-lag.

Motoren er bevisst adskilt fra Streamlit/UI. Den kan:
- bygge ticker-univers fra valgte marked/kilder
- hente score via eksisterende analyse.score_stock eller en injisert test-provider
- beregne normalisert AI-score, risiko, momentum/strength og sektor
- filtrere på risiko, sektor, score og strength
- rangere kandidatene og returnere et stabilt resultatobjekt

Den skriver ikke runtime-data til disk. UI bestemmer selv om resultatet skal lagres i
session_state, Top Picks eller watchlist.
"""

from __future__ import annotations
from utils import _safe_float, _clamp as _raw_clamp  # v18.6.3 centralized helpers

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app_version import get_app_version
from market_universe import BASE_MARKET_SCOPES, MARKET_SCOPE_OPTIONS, SOURCE_SCOPE_OPTIONS, normalize_market_scopes
from security_metadata import resolve_security_metadata


ScoreProvider = Callable[[str, bool], Optional[Mapping[str, Any]]]


def _clamp(value: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    return _raw_clamp(value, lo, hi)

RISK_ORDER = {"Lav": 1, "Middels": 2, "Høy": 3, "Ukjent": 4}


@dataclass(frozen=True)
class SmartUniverseCandidate:
    rank: int
    ticker: str
    name: str
    market: str
    source: str
    sector: str
    ai_score: float
    smart_score: float
    strength: float
    risk: str
    risk_score: float
    sentiment: float
    ret_1m_pct: Optional[float]
    ret_3m_pct: Optional[float]
    ret_6m_pct: Optional[float]
    insider_score: Optional[float]
    insider_adjustment: Optional[float]
    insider_label: str
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)






def normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def parse_ticker_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts: List[str] = []
        for part in value.replace(";", ",").replace("|", ",").replace("/", ",").replace("\n", ",").split(","):
            parts.extend(part.split())
        return _dedupe_keep_order(parts)
    if isinstance(value, Mapping):
        out: List[str] = []
        ticker = normalize_ticker(value.get("ticker") or value.get("symbol"))
        if ticker:
            out.append(ticker)
        for item in value.values():
            out.extend(parse_ticker_list(item))
        return _dedupe_keep_order(out)
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            out.extend(parse_ticker_list(item))
        return _dedupe_keep_order(out)
    return _dedupe_keep_order([value])


def _dedupe_keep_order(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        ticker = normalize_ticker(value)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def _round_robin(lists: Sequence[Sequence[str]], limit: int) -> List[str]:
    limit = max(1, int(limit or 1))
    clean_lists = [list(x or []) for x in lists if x]
    out: List[str] = []
    seen: set[str] = set()
    idx = 0
    while len(out) < limit and any(idx < len(items) for items in clean_lists):
        for items in clean_lists:
            if idx >= len(items):
                continue
            ticker = normalize_ticker(items[idx])
            if ticker and ticker not in seen:
                seen.add(ticker)
                out.append(ticker)
                if len(out) >= limit:
                    break
        idx += 1
    return out


def infer_market_from_ticker(ticker: str) -> str:
    t = normalize_ticker(ticker)
    if t.endswith(".OL"):
        return "Norge"
    if t.endswith(".ST"):
        return "Sverige"
    if t.endswith(".HE"):
        return "Finland"
    if t.endswith(".CO"):
        return "Danmark"
    if t.endswith(".SA"):
        return "Brasil"
    return "USA"


def infer_sector_from_ticker(ticker: str, item: Optional[Mapping[str, Any]] = None) -> str:
    item = item or {}
    for key in ("sector", "Sector", "industry", "Industry"):
        value = str(item.get(key, "") or "").strip()
        if value:
            return value[:48]

    t = normalize_ticker(ticker)
    if any(x in t for x in ("AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ADBE", "CRM", "PLTR", "SNOW")):
        return "Technology"
    if any(x in t for x in ("JPM", "BAC", "GS", "DNB", "STB", "NDA", "SHB", "SEB", "SWED")):
        return "Financials"
    if any(x in t for x in ("XOM", "CVX", "EQNR", "AKRBP", "VAR", "SHEL", "FRO", "HAFNI", "BORR", "MPCC")):
        return "Energy"
    if any(x in t for x in ("ABB", "VOLV", "CAT", "GE", "BA", "KOG", "SAAB", "SAND", "ATCO", "SKF", "ASSA")):
        return "Industrials"
    if any(x in t for x in ("JNJ", "PFE", "MRK", "NOVO", "AZN", "LLY", "GETI")):
        return "Healthcare"
    if any(x in t for x in ("AMZN", "TSLA", "MCD", "NKE", "HD", "ORK", "MOWI", "SALM", "BAKKA", "HM-B")):
        return "Consumer"
    if any(x in t for x in ("YAR", "NHY", "NEM", "LIN", "NUE", "RIO", "BOL", "SSAB")):
        return "Materials"
    if any(x in t for x in ("TEL", "TELIA", "ERIC")):
        return "Communication"
    return "Unknown"


def _normalize_ai_score(value: Any) -> float:
    score = _safe_float(value, 5.0)
    if score is None:
        score = 5.0
    if score > 10 and score <= 100:
        score = score / 10.0
    return round(_clamp(score, 0, 10), 2)


def _pct(value: Any) -> Optional[float]:
    number = _safe_float(value, None)
    if number is None:
        return None
    # Appens analysemodul bruker 0.12 for 12 %, ikke 12.
    if abs(number) <= 2:
        number *= 100
    return round(number, 2)


def compute_strength(item: Mapping[str, Any]) -> float:
    for key in ("momentum_strength", "strength", "forecast_strength"):
        value = _safe_float(item.get(key), None)
        if value is not None:
            if value <= 10:
                value *= 10
            return round(_clamp(value), 1)

    parts = item.get("score_parts") if isinstance(item.get("score_parts"), Mapping) else {}
    if parts:
        momentum = _safe_float(parts.get("momentum"), 0.5) or 0.5
        trend = _safe_float(parts.get("trend"), 0.5) or 0.5
        volume = _safe_float(parts.get("volume"), 0.5) or 0.5
        return round(_clamp((momentum * 0.55 + trend * 0.35 + volume * 0.10) * 100), 1)

    ret_1m = _safe_float(item.get("ret_1m"), 0.0) or 0.0
    ret_3m = _safe_float(item.get("ret_3m"), 0.0) or 0.0
    ret_6m = _safe_float(item.get("ret_6m"), 0.0) or 0.0
    raw = 50 + (ret_1m * 140) + (ret_3m * 85) + (ret_6m * 45)
    return round(_clamp(raw), 1)


def compute_risk_score(item: Mapping[str, Any]) -> float:
    explicit = _safe_float(item.get("risk_score"), None)
    if explicit is not None:
        if explicit <= 1:
            explicit *= 100
        return round(_clamp(explicit), 1)

    volatility = _safe_float(item.get("volatility"), 0.0) or 0.0
    max_drawdown = _safe_float(item.get("max_drawdown"), 0.0) or 0.0
    ai_score = _normalize_ai_score(item.get("score", 5.0))

    # volatility fra analysis.py er daglig std. Konverter grovt til annualisert.
    annual_vol = abs(volatility) * math.sqrt(252) if abs(volatility) < 1 else abs(volatility)
    drawdown_pct = abs(max_drawdown) * 100 if abs(max_drawdown) <= 1 else abs(max_drawdown)

    vol_component = _clamp((annual_vol / 0.65) * 55, 0, 55)
    drawdown_component = _clamp((drawdown_pct / 60) * 35, 0, 35)
    weak_score_penalty = _clamp((5.0 - ai_score) * 4, 0, 10)
    return round(_clamp(vol_component + drawdown_component + weak_score_penalty), 1)


def risk_label_from_score(risk_score: float) -> str:
    if risk_score <= 35:
        return "Lav"
    if risk_score <= 65:
        return "Middels"
    return "Høy"


def _sentiment_0_to_1(item: Mapping[str, Any]) -> float:
    sentiment = _safe_float(item.get("sentiment"), 0.5)
    if sentiment is None:
        return 0.5
    # Noen moduler kan bruke -1..1. Flytt dette til 0..1.
    if -1 <= sentiment <= 1:
        if sentiment < 0:
            return _clamp((sentiment + 1) / 2, 0, 1)
        return _clamp(sentiment, 0, 1)
    if 1 < sentiment <= 100:
        return _clamp(sentiment / 100, 0, 1)
    return 0.5


def _insider_score_0_to_100(item: Mapping[str, Any]) -> Optional[float]:
    candidates = [
        item.get("insider_score"),
        item.get("insider"),
    ]
    parts = item.get("score_parts") if isinstance(item.get("score_parts"), Mapping) else {}
    candidates.append(parts.get("insider"))
    for value in candidates:
        score = _safe_float(value, None)
        if score is None:
            continue
        if score <= 1:
            score *= 100
        elif score <= 10:
            score *= 10
        return round(_clamp(score), 1)
    return None


def _reason(ai_score: float, strength: float, risk: str, sector: str, insider_score: Optional[float] = None) -> str:
    parts: List[str] = []
    if ai_score >= 7.5:
        parts.append("høy AI-score")
    elif ai_score >= 6.5:
        parts.append("solid AI-score")
    else:
        parts.append("akseptabel score")
    if strength >= 70:
        parts.append("sterkt momentum")
    elif strength >= 50:
        parts.append("moderat momentum")
    else:
        parts.append("svakt momentum")
    parts.append(f"{risk.lower()} risiko")
    if insider_score is not None:
        if insider_score >= 65:
            parts.append("positivt insiderbilde")
        elif insider_score <= 35:
            parts.append("svakt insiderbilde")
        else:
            parts.append("nÃ¸ytralt insiderbilde")
    if sector and sector != "Unknown":
        parts.append(f"sektor: {sector}")
    return ", ".join(parts)


def _smart_score(ai_score: float, strength: float, risk_score: float, sentiment: float, insider_score: Optional[float] = None) -> float:
    score_0_100 = ai_score * 10
    value = score_0_100 * 0.55 + strength * 0.30 + (100 - risk_score) * 0.10 + (sentiment * 100) * 0.05
    if insider_score is not None:
        value += (float(insider_score) - 50.0) * 0.08
    return round(_clamp(value), 2)



def _display_name_or_fallback_v18571(ticker, item):
    return str(resolve_security_metadata(ticker, item).get("name") or normalize_ticker(ticker))


def candidate_from_score_item(ticker: str, item: Mapping[str, Any], source: str = "Smart AI") -> SmartUniverseCandidate:
    ticker = normalize_ticker(item.get("ticker") or item.get("symbol") or ticker)
    ai_score = _normalize_ai_score(item.get("score", item.get("ai_score", 5.0)))
    strength = compute_strength(item)
    risk_score = compute_risk_score(item)
    risk = str(item.get("risk") or risk_label_from_score(risk_score))
    if risk not in RISK_ORDER:
        risk = risk_label_from_score(risk_score)
    metadata = resolve_security_metadata(ticker, item)
    sector = str(metadata.get("sector") or infer_sector_from_ticker(ticker, item))
    if not risk or risk == "Ukjent":
        risk = str(metadata.get("risk") or risk_label_from_score(risk_score))
    sentiment = _sentiment_0_to_1(item)
    insider_score = _insider_score_0_to_100(item)
    insider_adjustment = _safe_float(item.get("insider_adjustment"), None)
    insider_label = str(item.get("insider_label") or ("Ingen insiderdata" if insider_score is None else "Insiderdata"))
    return SmartUniverseCandidate(
        rank=0,
        ticker=ticker,
        name=_display_name_or_fallback_v18571(ticker, item),
        market=str(item.get("market") or infer_market_from_ticker(ticker)),
        source=str(source or item.get("source") or "Smart AI"),
        sector=sector,
        ai_score=ai_score,
        smart_score=_smart_score(ai_score, strength, risk_score, sentiment, insider_score),
        strength=strength,
        risk=risk,
        risk_score=risk_score,
        sentiment=round(sentiment, 3),
        ret_1m_pct=_pct(item.get("ret_1m")),
        ret_3m_pct=_pct(item.get("ret_3m")),
        ret_6m_pct=_pct(item.get("ret_6m")),
        insider_score=insider_score,
        insider_adjustment=insider_adjustment,
        insider_label=insider_label,
        reason=_reason(ai_score, strength, risk, sector, insider_score),
    )


def _default_score_provider(ticker: str, use_news: bool) -> Optional[Mapping[str, Any]]:
    from analysis import score_stock

    return score_stock(ticker, use_news=use_news, include_insider=True)


def _tickers_from_existing_scope(scope: str, existing_tickers_by_scope: Optional[Mapping[str, Sequence[str]]]) -> List[str]:
    if not existing_tickers_by_scope:
        return []
    values: List[str] = []
    wanted = str(scope or "")
    for key, tickers in existing_tickers_by_scope.items():
        key_text = str(key or "")
        if key_text == wanted or key_text.startswith(wanted) or wanted in key_text:
            values.extend(list(tickers or []))
    return _dedupe_keep_order(values)


def resolve_universe_tickers(
    scopes: Sequence[str],
    max_count: int = 30,
    manual_ticker: str = "",
    existing_tickers_by_scope: Optional[Mapping[str, Sequence[str]]] = None,
) -> List[str]:
    """Resolve selected scope(s) to a runnable ticker universe.

    Supports regular markets from stocks.py plus existing app scopes such as
    Watchlist and Top Picks when the UI passes them in.
    """
    max_count = max(1, min(int(max_count or 30), 250))
    selected = normalize_market_scopes(scopes)
    if not selected:
        return []

    source_lists: List[List[str]] = []
    manual = normalize_ticker(manual_ticker)
    if manual:
        source_lists.append([manual])

    try:
        from stocks import (
            get_all_tickers,
            get_brazilian_tickers,
            get_danish_tickers,
            get_finnish_tickers,
            get_norwegian_tickers,
            get_sp500_tickers,
            get_swedish_tickers,
        )
    except Exception:
        get_sp500_tickers = get_norwegian_tickers = get_swedish_tickers = get_finnish_tickers = get_danish_tickers = get_brazilian_tickers = get_all_tickers = None  # type: ignore

    for scope in selected:
        if scope == "Alle":
            if all([get_sp500_tickers, get_norwegian_tickers, get_swedish_tickers, get_finnish_tickers, get_danish_tickers, get_brazilian_tickers]):
                per_market = max(5, math.ceil(max_count / max(1, len(BASE_MARKET_SCOPES))))
                source_lists.extend([
                    list(get_sp500_tickers(limit=per_market) or []),
                    list(get_norwegian_tickers(limit=per_market) or []),
                    list(get_swedish_tickers(limit=per_market) or []),
                    list(get_finnish_tickers(limit=per_market) or []),
                    list(get_danish_tickers(limit=per_market) or []),
                    list(get_brazilian_tickers(limit=per_market) or []),
                ])
            elif get_all_tickers:
                source_lists.append(list(get_all_tickers(limit_per_market=max(5, math.ceil(max_count / max(1, len(BASE_MARKET_SCOPES))))) or []))
        elif scope == "USA" and get_sp500_tickers:
            source_lists.append(list(get_sp500_tickers(limit=max_count) or []))
        elif scope == "Norge" and get_norwegian_tickers:
            source_lists.append(list(get_norwegian_tickers(limit=max_count) or []))
        elif scope == "Sverige" and get_swedish_tickers:
            source_lists.append(list(get_swedish_tickers(limit=max_count) or []))
        elif scope == "Finland" and get_finnish_tickers:
            source_lists.append(list(get_finnish_tickers(limit=max_count) or []))
        elif scope == "Danmark" and get_danish_tickers:
            source_lists.append(list(get_danish_tickers(limit=max_count) or []))
        elif scope == "Brasil" and get_brazilian_tickers:
            source_lists.append(list(get_brazilian_tickers(limit=max_count) or []))
        elif scope == "Norden":
            if get_norwegian_tickers:
                source_lists.append(list(get_norwegian_tickers(limit=max_count) or []))
            if get_swedish_tickers:
                source_lists.append(list(get_swedish_tickers(limit=max_count) or []))
            if get_finnish_tickers:
                source_lists.append(list(get_finnish_tickers(limit=max_count) or []))
            if get_danish_tickers:
                source_lists.append(list(get_danish_tickers(limit=max_count) or []))
        elif scope in {"Top Picks", "Watchlist", "Paper trading", "Portefølje", "Smart AI-utvalg"}:
            source_lists.append(_tickers_from_existing_scope(scope, existing_tickers_by_scope))
        else:
            source_lists.append(_tickers_from_existing_scope(scope, existing_tickers_by_scope))

    return _round_robin(source_lists, max_count)




def resolve_strict_universe_tickers(
    config: Mapping[str, Any],
    existing_tickers_by_scope: Optional[Mapping[str, Sequence[str]]] = None,
) -> Tuple[List[str], str]:
    """Resolve tickers with workspace mode as the source of truth.

    v18.5.26: Smart Universe Picker is strict. If the user chooses
    Enkeltaksje, Smart AI must scan only that ticker. If the user chooses
    Watchlist/Top Picks/Paper/Portefølje/Manuell liste, the scan must not
    silently fall back to market candidates or prepend old manual tickers.
    """
    mode = str(config.get("mode") or "Markedvalg").strip()
    max_count = max(1, min(int(config.get("max_count", 30) or 30), 250))
    scopes = [str(x) for x in (config.get("scopes") or []) if str(x or "").strip()]
    manual = normalize_ticker(config.get("manual_ticker"))
    manual_list = parse_ticker_list(config.get("manual_list") or config.get("manual_tickers") or config.get("tickers"))

    def from_scope(name: str) -> List[str]:
        return _tickers_from_existing_scope(name, existing_tickers_by_scope)[:max_count]

    if mode == "Enkeltaksje":
        return (_dedupe_keep_order([manual])[:1], "Enkeltaksje")
    if mode == "Manuell liste" or "Manuell liste" in scopes:
        return (manual_list[:max_count], "Manuell liste")
    if mode == "Top Picks":
        return (from_scope("Top Picks"), "Top Picks")
    if mode == "Watchlist":
        return (from_scope("Watchlist"), "Watchlist")
    if mode == "Paper trading":
        return (from_scope("Paper trading"), "Paper trading")
    if mode == "Portefølje":
        return (from_scope("Portefølje"), "Portefølje")
    if mode == "Smart AI-utvalg":
        return (from_scope("Smart AI-utvalg"), "Smart AI-utvalg")
    if mode != "Markedvalg":
        for source_scope in SOURCE_SCOPE_OPTIONS:
            if source_scope in scopes:
                return (from_scope(source_scope), source_scope)

    market_scopes = [scope for scope in scopes if scope in MARKET_SCOPE_OPTIONS]
    if mode == "Multi-marked":
        return (resolve_universe_tickers(market_scopes, max_count=max_count, manual_ticker="", existing_tickers_by_scope=existing_tickers_by_scope), "Multi-marked")

    # Markedvalg is market-only. Manual ticker is intentionally ignored here;
    # Enkeltaksje is the only mode that should scan a manual single ticker.
    if not market_scopes:
        return ([], "Markedvalg")
    return (resolve_universe_tickers(market_scopes, max_count=max_count, manual_ticker="", existing_tickers_by_scope=existing_tickers_by_scope), "Markedvalg")


def filter_smart_candidates(
    candidates: Sequence[SmartUniverseCandidate],
    sectors: Sequence[str],
    max_risk: str,
    min_score: float,
    min_strength: float,
) -> List[SmartUniverseCandidate]:
    selected_sectors = {str(x) for x in sectors if x and x != "Alle sektorer"}
    max_risk_value = RISK_ORDER.get(str(max_risk or "Middels"), 2)
    min_score = float(min_score or 0)
    min_strength = float(min_strength or 0)

    out: List[SmartUniverseCandidate] = []
    for candidate in candidates:
        if selected_sectors and candidate.sector not in selected_sectors:
            continue
        if RISK_ORDER.get(candidate.risk, 4) > max_risk_value:
            continue
        if candidate.ai_score < min_score:
            continue
        if candidate.strength < min_strength:
            continue
        out.append(candidate)
    return sorted(out, key=lambda c: (-c.smart_score, -c.ai_score, -c.strength, c.risk_score, c.ticker))


def _rank(candidates: Sequence[SmartUniverseCandidate]) -> List[SmartUniverseCandidate]:
    ranked: List[SmartUniverseCandidate] = []
    for idx, candidate in enumerate(candidates, start=1):
        ranked.append(
            SmartUniverseCandidate(
                rank=idx,
                ticker=candidate.ticker,
                name=candidate.name,
                market=candidate.market,
                source=candidate.source,
                sector=candidate.sector,
                ai_score=candidate.ai_score,
                smart_score=candidate.smart_score,
                strength=candidate.strength,
                risk=candidate.risk,
                risk_score=candidate.risk_score,
                sentiment=candidate.sentiment,
                ret_1m_pct=candidate.ret_1m_pct,
                ret_3m_pct=candidate.ret_3m_pct,
                ret_6m_pct=candidate.ret_6m_pct,
                insider_score=candidate.insider_score,
                insider_adjustment=candidate.insider_adjustment,
                insider_label=candidate.insider_label,
                reason=candidate.reason,
            )
        )
    return ranked


def run_smart_ai_universe(
    config: Mapping[str, Any],
    existing_tickers_by_scope: Optional[Mapping[str, Sequence[str]]] = None,
    score_provider: Optional[ScoreProvider] = None,
) -> Dict[str, Any]:
    """Run the operative Smart AI universe selection.

    The function only runs when called explicitly by the UI. It does not write
    files and it does not mutate Streamlit state.
    """
    score_provider = score_provider or _default_score_provider
    max_count = max(1, min(int(config.get("max_count", 30) or 30), 250))
    scopes = normalize_market_scopes(config.get("scopes") or [])
    use_news = bool(config.get("use_news", False))
    max_risk = str(config.get("max_risk") or "Middels")
    sectors = list(config.get("sectors") or ["Alle sektorer"])
    min_score = float(config.get("min_top_pick_score", 0) or 0)
    min_strength = float(config.get("min_strength", 0) or 0)

    tickers, strict_source = resolve_strict_universe_tickers(config, existing_tickers_by_scope=existing_tickers_by_scope)

    raw_candidates: List[SmartUniverseCandidate] = []
    errors: List[Dict[str, str]] = []
    scanned = 0
    for ticker in tickers:
        try:
            item = score_provider(ticker, use_news)
            scanned += 1
            if not item:
                errors.append({"ticker": ticker, "error": "Ingen analysedata returnert"})
                continue
            raw_candidates.append(candidate_from_score_item(ticker, item, source="Smart AI"))
        except Exception as exc:
            scanned += 1
            errors.append({"ticker": ticker, "error": str(exc)[:180]})

    filtered = filter_smart_candidates(raw_candidates, sectors, max_risk, min_score, min_strength)
    ranked = _rank(filtered[:max_count])
    top_pick_limit = max(1, min(10, max_count))
    top_picks = ranked[:top_pick_limit]
    status = "ok" if ranked else ("empty_after_filter" if raw_candidates else "empty")

    return {
        "version": get_app_version(),
        "strict_source": strict_source,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": dict(config),
        "scopes": scopes,
        "universe_size": len(tickers),
        "scanned": scanned,
        "raw_candidates": len(raw_candidates),
        "matched_candidates": len(ranked),
        "top_tickers": [c.ticker for c in top_picks],
        "candidates": [c.as_dict() for c in ranked],
        "top_picks": [c.as_dict() for c in top_picks],
        "errors": errors[:25],
        "summary": {
            "text": f"{len(ranked)} av {len(raw_candidates)} scorede kandidater matcher filtrene.",
            "strict_source": strict_source,
            "filters": {
                "max_risk": max_risk,
                "min_score": min_score,
                "min_strength": min_strength,
                "sectors": sectors,
            },
        },
    }


def candidate_dicts_for_app(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return app-compatible ranking rows for latest_rankings_v148."""
    out: List[Dict[str, Any]] = []
    for row in result.get("candidates", []) or []:
        if not isinstance(row, Mapping):
            continue
        out.append(
            {
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "score": row.get("ai_score"),
                "smart_score": row.get("smart_score"),
                "strength": row.get("strength"),
                "risk": row.get("risk"),
                "risk_score": row.get("risk_score"),
                "insider_score": row.get("insider_score"),
                "insider_adjustment": row.get("insider_adjustment"),
                "insider_label": row.get("insider_label"),
                "sector": row.get("sector"),
                "source": "Smart AI",
                "reason": row.get("reason"),
                "ret_1m": (row.get("ret_1m_pct") / 100) if isinstance(row.get("ret_1m_pct"), (int, float)) else None,
                "ret_3m": (row.get("ret_3m_pct") / 100) if isinstance(row.get("ret_3m_pct"), (int, float)) else None,
                "ret_6m": (row.get("ret_6m_pct") / 100) if isinstance(row.get("ret_6m_pct"), (int, float)) else None,
            }
        )
    return out
