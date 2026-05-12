"""
auto_test_lab.py

v18.5.37 Auto Test Lab Progress + Safe Run Controls.

Pure helper layer for testing many tickers against the app's existing signal
stack without forcing the user to type one ticker for each module.

The module is intentionally side-effect free:
- no Streamlit dependency
- no background/cron work
- no file writes
- no NewsAPI calls unless the UI/provider explicitly passes use_news=True
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from itertools import combinations
import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app_version import get_app_version


ScoreProvider = Callable[[str, bool], Optional[Mapping[str, Any]]]
EventRiskProvider = Callable[[str, Sequence[float]], Optional[Mapping[str, Any]]]
ProgressCallback = Callable[[Mapping[str, Any]], None]
StopCallback = Callable[[], bool]


TARGET_PROFILES = {
    "Balansert": {"score": 0.26, "smart": 0.18, "momentum": 0.16, "risk": 0.16, "event": 0.10, "learning": 0.08, "data": 0.06},
    "Momentum": {"score": 0.20, "smart": 0.16, "momentum": 0.28, "risk": 0.12, "event": 0.08, "learning": 0.08, "data": 0.08},
    "Lav risiko": {"score": 0.18, "smart": 0.14, "momentum": 0.12, "risk": 0.28, "event": 0.16, "learning": 0.06, "data": 0.06},
    "Kortsiktig": {"score": 0.20, "smart": 0.14, "momentum": 0.26, "risk": 0.14, "event": 0.12, "learning": 0.08, "data": 0.06},
    "Langsiktig": {"score": 0.24, "smart": 0.18, "momentum": 0.12, "risk": 0.18, "event": 0.08, "learning": 0.10, "data": 0.10},
}

TEST_MODE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "Rask": {
        "tests": ["AI-score", "Smart-score", "Momentum", "Risiko", "Datakvalitet"],
        "description": "Rask screening uten event-risk/backtest-lignende ekstrasjekker.",
        "api_multiplier": 1.0,
    },
    "Normal": {
        "tests": ["AI-score", "Smart-score", "Momentum", "Risiko", "Learning", "Hendelsesrisiko", "Datakvalitet"],
        "description": "Anbefalt modus med learning og hendelsesrisiko.",
        "api_multiplier": 1.25,
    },
    "Grundig": {
        "tests": ["AI-score", "Smart-score", "Momentum", "Risiko", "Learning", "Hendelsesrisiko", "Kombinasjoner", "Datakvalitet"],
        "description": "Grundigere vurdering med kombinasjoner og ekstra kvalitetskontroll.",
        "api_multiplier": 1.55,
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_test_mode_config(test_mode: str = "Normal") -> Dict[str, Any]:
    """Return a safe test-mode config used by both UI and engine."""
    mode = str(test_mode or "Normal").strip()
    if mode not in TEST_MODE_CONFIGS:
        mode = "Normal"
    cfg = dict(TEST_MODE_CONFIGS[mode])
    cfg["mode"] = mode
    cfg["tests"] = list(cfg.get("tests") or TEST_MODE_CONFIGS["Normal"]["tests"])
    return cfg


def estimate_auto_lab_run(
    tickers: Sequence[str],
    *,
    test_mode: str = "Normal",
    use_news: bool = False,
    include_event: bool = True,
) -> Dict[str, Any]:
    """Estimate scope/API budget before Auto Test Lab starts.

    The estimate is intentionally conservative and explainable; it does not
    perform any network calls.
    """
    clean = []
    seen = set()
    for raw in tickers or []:
        ticker = normalize_ticker(raw)
        if ticker and ticker not in seen:
            clean.append(ticker)
            seen.add(ticker)
    cfg = get_test_mode_config(test_mode)
    tests = [t for t in cfg["tests"] if include_event or t != "Hendelsesrisiko"]
    total_tests = len(clean) * len(tests)
    # One quote/history pull per ticker is expected. Event/news can add work.
    estimated_data_calls = int(math.ceil(len(clean) * float(cfg.get("api_multiplier", 1.0))))
    news_calls = len(clean) if use_news else 0
    event_checks = len(clean) if include_event and "Hendelsesrisiko" in tests else 0
    load_score = estimated_data_calls + news_calls + max(0, event_checks // 3)
    if load_score <= 12:
        load_label = "Lav"
    elif load_score <= 45:
        load_label = "Medium"
    else:
        load_label = "Høy"
    return {
        "mode": cfg["mode"],
        "description": cfg.get("description", ""),
        "tickers": len(clean),
        "tests": tests,
        "tests_per_ticker": len(tests),
        "total_tests": total_tests,
        "estimated_data_calls": estimated_data_calls,
        "news_calls": news_calls,
        "event_checks": event_checks,
        "load_label": load_label,
    }


def _emit_progress(
    callback: Optional[ProgressCallback],
    *,
    ticker: str = "",
    ticker_index: int = 0,
    ticker_total: int = 0,
    test_name: str = "",
    test_index: int = 0,
    tests_per_ticker: int = 0,
    completed_tests: int = 0,
    total_tests: int = 0,
    status: str = "running",
    message: str = "",
) -> None:
    if callback is None:
        return
    pct = 0.0 if total_tests <= 0 else _clamp((completed_tests / total_tests) * 100.0, 0.0, 100.0)
    callback({
        "status": status,
        "ticker": ticker,
        "ticker_index": ticker_index,
        "ticker_total": ticker_total,
        "test_name": test_name,
        "test_index": test_index,
        "tests_per_ticker": tests_per_ticker,
        "completed_tests": completed_tests,
        "total_tests": total_tests,
        "percent": round(pct, 1),
        "message": message,
        "updated_at": _now_iso(),
    })


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def parse_ticker_list(value: Any) -> List[str]:
    raw = str(value or "")
    for sep in [";", "\n", "\t"]:
        raw = raw.replace(sep, ",")
    out: List[str] = []
    seen = set()
    for part in raw.split(","):
        # Also allow whitespace separated values in each comma chunk.
        for token in str(part).split():
            ticker = normalize_ticker(token)
            if ticker and ticker not in seen:
                out.append(ticker)
                seen.add(ticker)
    return out


def _score_0_100(value: Any) -> float:
    val = _safe_float(value, 0.0) or 0.0
    # Existing app score is normally 0-10. Smart-score may already be 0-100.
    if val <= 10.0:
        return _clamp(val * 10.0)
    return _clamp(val)


def _pct(value: Any) -> Optional[float]:
    val = _safe_float(value, None)
    if val is None:
        return None
    # App returns are normally decimals (0.05). Some candidates use percent.
    return val if abs(val) > 1.5 else val * 100.0


def _history_close_values(item: Mapping[str, Any], limit: int = 260) -> List[float]:
    hist = item.get("hist")
    if hist is None:
        return []
    try:
        data = hist
        if hasattr(data, "columns") and "Close" in list(data.columns):
            series = data["Close"]
        elif hasattr(data, "dropna"):
            series = data
        else:
            return []
        if hasattr(series, "dropna"):
            series = series.dropna()
        values = []
        for v in list(series)[-limit:]:
            f = _safe_float(v)
            if f is not None and f > 0:
                values.append(f)
        return values
    except Exception:
        return []


def _volatility_score(item: Mapping[str, Any]) -> float:
    risk = str(item.get("risk") or "").lower()
    if risk.startswith("lav"):
        return 82.0
    if risk.startswith("middels"):
        return 62.0
    if risk.startswith("høy") or risk.startswith("hoy"):
        return 34.0

    risk_score = _safe_float(item.get("risk_score"), None)
    if risk_score is not None:
        # Universe risk_score is 0=low risk, 100=high risk.
        return _clamp(100.0 - risk_score)

    vol = _safe_float(item.get("volatility"), None)
    dd = _safe_float(item.get("max_drawdown"), None)
    if vol is None and dd is None:
        return 55.0
    vol_component = 100.0 - min(70.0, (vol or 0) * 1000.0)
    dd_component = 100.0 - min(60.0, abs(dd or 0) * 120.0)
    return _clamp(vol_component * 0.60 + dd_component * 0.40)


def _momentum_score(item: Mapping[str, Any]) -> float:
    parts = item.get("score_parts") if isinstance(item.get("score_parts"), Mapping) else {}
    if parts:
        momentum = _safe_float(parts.get("momentum"), None)
        trend = _safe_float(parts.get("trend"), None)
        if momentum is not None or trend is not None:
            return _clamp(((momentum or 0.5) * 0.58 + (trend or 0.5) * 0.42) * 100.0)

    returns = [x for x in [_pct(item.get("ret_1m")), _pct(item.get("ret_3m")), _pct(item.get("ret_6m"))] if x is not None]
    if not returns:
        strength = _safe_float(item.get("strength"), None)
        return _clamp(strength if strength is not None else 50.0)
    # Center around 50 and reward broad positive momentum, cap extremes.
    score = 50.0 + sum([returns[0] * 1.4] + [r * 0.65 for r in returns[1:]]) / max(1, len(returns))
    positives = sum(1 for r in returns if r > 0)
    score += positives * 4.0
    return _clamp(score)


def _data_quality_score(item: Mapping[str, Any]) -> float:
    score = 42.0
    if item.get("score") is not None:
        score += 12
    if isinstance(item.get("score_parts"), Mapping) and item.get("score_parts"):
        score += 14
    values = _history_close_values(item)
    if len(values) >= 180:
        score += 18
    elif len(values) >= 80:
        score += 10
    elif len(values) >= 30:
        score += 5
    if item.get("market_cap"):
        score += 4
    if item.get("news_error"):
        score -= 6
    return _clamp(score)


def _learning_score(learning_stats: Optional[Mapping[str, Any]], ticker: str = "") -> float:
    if not isinstance(learning_stats, Mapping) or not learning_stats:
        return 50.0

    candidates: List[Any] = []
    ticker = normalize_ticker(ticker)
    for key in (ticker, "global", "all", "summary", "stats"):
        val = learning_stats.get(key)
        if isinstance(val, Mapping):
            candidates.append(val)
    candidates.append(learning_stats)

    for row in candidates:
        for k in ("hit_rate", "trefferate", "direction_hit_rate", "accuracy", "inside_band_rate"):
            val = _safe_float(row.get(k), None)
            if val is not None:
                return _clamp(val * 100.0 if val <= 1.0 else val)
        wins = _safe_float(row.get("hits") or row.get("wins"), None)
        total = _safe_float(row.get("samples") or row.get("total") or row.get("count"), None)
        if wins is not None and total and total > 0:
            return _clamp((wins / total) * 100.0)
    return 50.0


def _event_score(event_info: Optional[Mapping[str, Any]]) -> Tuple[float, str, int]:
    if not isinstance(event_info, Mapping) or not event_info:
        return 72.0, "Ingen konkret hendelsesrisiko vurdert i Auto Test Lab.", 0
    alerts = list(event_info.get("alerts") or [])
    adjustment = int(_safe_float(event_info.get("confidence_adjustment"), 0) or 0)
    red = sum(1 for a in alerts if str(a.get("level") or "").lower() == "red")
    yellow = sum(1 for a in alerts if str(a.get("level") or "").lower() == "yellow")
    score = 86.0 + adjustment - red * 10 - yellow * 5
    if not alerts:
        msg = "Ingen konkret hendelsesrisiko funnet med tilgjengelige datakilder."
    else:
        first = alerts[0].get("message") or alerts[0].get("category") or "Hendelsesrisiko nær"
        msg = f"{red} røde / {yellow} gule hendelsessignaler. {first}"
    return _clamp(score), msg, adjustment


def decision_grade(score: float, event_score: float, risk_score: float, data_quality: float) -> Tuple[str, str]:
    if data_quality < 42:
        return "Vent", "Mangler datakvalitet"
    if event_score < 45:
        return "Vent", "Høy hendelsesrisiko"
    if risk_score < 35:
        return "Vent", "Risiko for høy"
    if score >= 76:
        return "Høy", "Test videre"
    if score >= 62:
        return "Middels", "Test videre med forsiktighet"
    if score >= 50:
        return "Lav", "Krever mer bekreftelse"
    return "Vent", "Forkast/vent"


@dataclass(frozen=True)
class DecisionQualityResult:
    ticker: str
    name: str
    decision_quality: float
    grade: str
    action: str
    ai_score: float
    smart_score: float
    momentum_score: float
    risk_score: float
    event_score: float
    learning_score: float
    data_quality: float
    event_adjustment: int
    ret_1m_pct: Optional[float]
    ret_3m_pct: Optional[float]
    ret_6m_pct: Optional[float]
    reasons_positive: List[str]
    reasons_caution: List[str]
    no_trade_reasons: List[str]
    event_summary: str
    source: str = "Auto Test Lab"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_decision_quality(
    item: Mapping[str, Any],
    *,
    event_info: Optional[Mapping[str, Any]] = None,
    learning_stats: Optional[Mapping[str, Any]] = None,
    target: str = "Balansert",
) -> DecisionQualityResult:
    ticker = normalize_ticker(item.get("ticker"))
    name = str(item.get("name") or ticker)
    ai_score = _score_0_100(item.get("score"))
    smart_score = _score_0_100(item.get("smart_score", item.get("score")))
    momentum = _momentum_score(item)
    risk = _volatility_score(item)
    event, event_summary, event_adjustment = _event_score(event_info)
    learning = _learning_score(learning_stats, ticker)
    data_quality = _data_quality_score(item)

    weights = TARGET_PROFILES.get(str(target or "Balansert"), TARGET_PROFILES["Balansert"])
    score = (
        ai_score * weights["score"]
        + smart_score * weights["smart"]
        + momentum * weights["momentum"]
        + risk * weights["risk"]
        + event * weights["event"]
        + learning * weights["learning"]
        + data_quality * weights["data"]
    )
    # Hard guardrails: good score cannot fully hide major event/risk/data warnings.
    if event < 45:
        score -= 10
    if risk < 35:
        score -= 8
    if data_quality < 42:
        score -= 9
    score = _clamp(score)

    grade, action = decision_grade(score, event, risk, data_quality)

    positives: List[str] = []
    caution: List[str] = []
    no_trade: List[str] = []

    if ai_score >= 70:
        positives.append("AI-score er sterk")
    elif ai_score < 52:
        caution.append("AI-score er svak")
    if smart_score >= 70:
        positives.append("Smart-score støtter signalet")
    if momentum >= 68:
        positives.append("Momentum/trend er positiv")
    elif momentum < 45:
        caution.append("Momentum/trend er svakt")
    if risk >= 68:
        positives.append("Risiko/volatilitet er akseptabel")
    elif risk < 45:
        caution.append("Risiko/volatilitet trekker ned")
    if learning >= 62:
        positives.append("Learning history støtter signalet")
    elif learning < 45:
        caution.append("Learning history er svak/usikker")
    if event < 60:
        caution.append(event_summary)
    if data_quality < 55:
        caution.append("Datakvalitet er begrenset")

    if grade == "Vent":
        no_trade = [r for r in caution[:3]] or [action]
    if not positives:
        positives.append("Ingen sterk positiv driver dominerer ennå")
    if not caution:
        caution.append("Ingen store røde flagg fra tilgjengelige tester")

    return DecisionQualityResult(
        ticker=ticker,
        name=name,
        decision_quality=round(score, 1),
        grade=grade,
        action=action,
        ai_score=round(ai_score, 1),
        smart_score=round(smart_score, 1),
        momentum_score=round(momentum, 1),
        risk_score=round(risk, 1),
        event_score=round(event, 1),
        learning_score=round(learning, 1),
        data_quality=round(data_quality, 1),
        event_adjustment=int(event_adjustment),
        ret_1m_pct=_pct(item.get("ret_1m")),
        ret_3m_pct=_pct(item.get("ret_3m")),
        ret_6m_pct=_pct(item.get("ret_6m")),
        reasons_positive=positives[:4],
        reasons_caution=caution[:4],
        no_trade_reasons=no_trade[:4],
        event_summary=event_summary,
        source=str(item.get("source") or "Auto Test Lab"),
    )


def _candidate_sector(row: Mapping[str, Any]) -> str:
    sector = str(row.get("sector") or "Ukjent").strip()
    if sector and sector != "Ukjent":
        return sector
    t = normalize_ticker(row.get("ticker"))
    if t.endswith(".OL"):
        return "Norge"
    if t.endswith(".ST"):
        return "Sverige"
    return "USA/Global"


def build_candidate_combinations(
    candidates: Sequence[Mapping[str, Any]],
    *,
    sizes: Sequence[int] = (3, 5),
    max_combinations: int = 80,
) -> List[Dict[str, Any]]:
    """Build a small, explainable combination list from top decision candidates.

    This is deliberately not an exhaustive optimizer. It tests combinations from
    the best candidates only to avoid combinatorial explosions and false precision.
    """
    usable = [dict(c) for c in candidates if str(c.get("grade")) != "Vent"]
    usable.sort(key=lambda x: float(x.get("decision_quality") or 0), reverse=True)
    pool = usable[: min(12, len(usable))]
    if len(pool) < 2:
        return []

    results: List[Dict[str, Any]] = []
    seen = set()
    for size in sizes:
        size = int(size or 0)
        if size < 2 or size > len(pool):
            continue
        checked = 0
        for combo in combinations(pool, size):
            checked += 1
            if checked > max_combinations:
                break
            tickers = tuple(normalize_ticker(x.get("ticker")) for x in combo)
            if tickers in seen:
                continue
            seen.add(tickers)
            qualities = [float(x.get("decision_quality") or 0) for x in combo]
            risks = [float(x.get("risk_score") or 0) for x in combo]
            events = [float(x.get("event_score") or 0) for x in combo]
            sectors = {_candidate_sector(x) for x in combo}
            avg_quality = sum(qualities) / len(qualities)
            avg_risk = sum(risks) / len(risks)
            avg_event = sum(events) / len(events)
            diversification_bonus = min(8.0, max(0, len(sectors) - 1) * 2.5)
            weak_penalty = sum(1 for q in qualities if q < 60) * 3.0
            combo_score = _clamp(avg_quality * 0.68 + avg_risk * 0.14 + avg_event * 0.10 + diversification_bonus - weak_penalty)
            results.append({
                "tickers": list(tickers),
                "size": size,
                "combination_score": round(combo_score, 1),
                "avg_decision_quality": round(avg_quality, 1),
                "avg_risk_score": round(avg_risk, 1),
                "avg_event_score": round(avg_event, 1),
                "sectors": sorted(sectors),
                "reason": f"{size} aksjer · {len(sectors)} grupper · avg kvalitet {avg_quality:.1f}",
            })
    results.sort(key=lambda x: float(x.get("combination_score") or 0), reverse=True)
    return results[:10]


def run_auto_test_lab(
    tickers: Sequence[str],
    *,
    score_provider: ScoreProvider,
    event_risk_provider: Optional[EventRiskProvider] = None,
    learning_stats: Optional[Mapping[str, Any]] = None,
    use_news: bool = False,
    target: str = "Balansert",
    max_candidates: int = 25,
    combination_sizes: Sequence[int] = (3, 5),
    test_mode: str = "Normal",
    progress_callback: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
) -> Dict[str, Any]:
    clean_tickers: List[str] = []
    seen = set()
    for raw in tickers or []:
        ticker = normalize_ticker(raw)
        if ticker and ticker not in seen:
            clean_tickers.append(ticker)
            seen.add(ticker)
        if len(clean_tickers) >= max(1, int(max_candidates or 25)):
            break

    cfg = get_test_mode_config(test_mode)
    tests = list(cfg.get("tests") or TEST_MODE_CONFIGS["Normal"]["tests"])
    if event_risk_provider is None and "Hendelsesrisiko" in tests:
        tests = [t for t in tests if t != "Hendelsesrisiko"]
    total_tests = len(clean_tickers) * max(1, len(tests))
    completed_tests = 0
    interrupted = False

    rows: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    scanned = 0

    _emit_progress(
        progress_callback,
        ticker_total=len(clean_tickers),
        tests_per_ticker=len(tests),
        completed_tests=0,
        total_tests=total_tests,
        status="starting",
        message="Starter Auto Test Lab",
    )

    for ticker_idx, ticker in enumerate(clean_tickers, start=1):
        if should_stop is not None and should_stop():
            interrupted = True
            _emit_progress(
                progress_callback,
                ticker=ticker,
                ticker_index=ticker_idx,
                ticker_total=len(clean_tickers),
                tests_per_ticker=len(tests),
                completed_tests=completed_tests,
                total_tests=total_tests,
                status="interrupted",
                message="Avbrutt før neste ticker.",
            )
            break

        scanned += 1
        item: Optional[Mapping[str, Any]] = None
        event_info = None
        ticker_failed = False

        for test_idx, test_name in enumerate(tests, start=1):
            if should_stop is not None and should_stop():
                interrupted = True
                _emit_progress(
                    progress_callback,
                    ticker=ticker,
                    ticker_index=ticker_idx,
                    ticker_total=len(clean_tickers),
                    test_name=test_name,
                    test_index=test_idx,
                    tests_per_ticker=len(tests),
                    completed_tests=completed_tests,
                    total_tests=total_tests,
                    status="interrupted",
                    message="Avbrutt av bruker.",
                )
                break

            _emit_progress(
                progress_callback,
                ticker=ticker,
                ticker_index=ticker_idx,
                ticker_total=len(clean_tickers),
                test_name=test_name,
                test_index=test_idx,
                tests_per_ticker=len(tests),
                completed_tests=completed_tests,
                total_tests=total_tests,
                status="running",
                message=f"{ticker}: {test_name}",
            )
            try:
                if item is None:
                    # The score provider normally performs the only heavy market-data fetch for the ticker.
                    item = score_provider(ticker, bool(use_news))
                    if not item:
                        rejected.append({"ticker": ticker, "reason": "Ingen analysedata returnert"})
                        ticker_failed = True
                if not ticker_failed and test_name == "Hendelsesrisiko" and event_risk_provider is not None:
                    prices = _history_close_values(item or {})
                    event_info = event_risk_provider(ticker, prices)
            except Exception as exc:
                errors.append({"ticker": ticker, "test": test_name, "error": str(exc)[:180]})
                ticker_failed = True
            finally:
                completed_tests += 1
                _emit_progress(
                    progress_callback,
                    ticker=ticker,
                    ticker_index=ticker_idx,
                    ticker_total=len(clean_tickers),
                    test_name=test_name,
                    test_index=test_idx,
                    tests_per_ticker=len(tests),
                    completed_tests=completed_tests,
                    total_tests=total_tests,
                    status="running",
                    message=f"Ferdig: {ticker} / {test_name}",
                )

            if ticker_failed:
                # Count remaining tests for this ticker as skipped so total progress remains understandable.
                remaining = len(tests) - test_idx
                if remaining > 0:
                    completed_tests += remaining
                    _emit_progress(
                        progress_callback,
                        ticker=ticker,
                        ticker_index=ticker_idx,
                        ticker_total=len(clean_tickers),
                        test_name="Hoppet over",
                        test_index=len(tests),
                        tests_per_ticker=len(tests),
                        completed_tests=completed_tests,
                        total_tests=total_tests,
                        status="skipped",
                        message=f"{ticker}: hopper over resten av testene.",
                    )
                break

        if interrupted:
            break
        if ticker_failed or not item:
            continue
        try:
            decision = compute_decision_quality(item, event_info=event_info, learning_stats=learning_stats, target=target)
            row = decision.as_dict()
            row["raw_score_available"] = bool(item.get("score") is not None)
            row["test_mode"] = cfg["mode"]
            rows.append(row)
        except Exception as exc:
            errors.append({"ticker": ticker, "test": "Decision Quality", "error": str(exc)[:180]})

    rows.sort(key=lambda x: float(x.get("decision_quality") or 0), reverse=True)
    rejected.extend([
        {"ticker": r.get("ticker"), "reason": "; ".join(r.get("no_trade_reasons") or [r.get("action") or "Vent"])}
        for r in rows
        if str(r.get("grade")) == "Vent"
    ])
    combinations_out = [] if interrupted else build_candidate_combinations(rows, sizes=combination_sizes)

    best_single = rows[:10]
    test_further = [r for r in rows if str(r.get("grade")) in {"Høy", "Middels"}]
    status = "interrupted" if interrupted else ("ok" if rows else "empty")
    _emit_progress(
        progress_callback,
        ticker_total=len(clean_tickers),
        tests_per_ticker=len(tests),
        completed_tests=completed_tests,
        total_tests=total_tests,
        status="interrupted" if interrupted else "done",
        message="Auto Test Lab avbrutt." if interrupted else "Auto Test Lab ferdig.",
    )

    return {
        "version": get_app_version(),
        "status": status,
        "target": target,
        "test_mode": cfg["mode"],
        "planned_tests": tests,
        "total_tests": total_tests,
        "completed_tests": min(completed_tests, total_tests),
        "interrupted": interrupted,
        "use_news": bool(use_news),
        "requested_tickers": clean_tickers,
        "scanned": scanned,
        "analyzed": len(rows),
        "best_single": best_single,
        "test_further": test_further[:15],
        "combinations": combinations_out,
        "rejected": rejected[:20],
        "errors": errors[:20],
        "summary": {
            "text": f"Auto Test Lab analyserte {len(rows)} av {len(clean_tickers)} tickere." + (" Kjøringen ble avbrutt." if interrupted else ""),
            "best_ticker": best_single[0]["ticker"] if best_single else None,
            "best_quality": best_single[0]["decision_quality"] if best_single else None,
            "combinations": len(combinations_out),
            "completed_tests": min(completed_tests, total_tests),
            "total_tests": total_tests,
        },
    }
