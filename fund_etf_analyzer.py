"""
fund_etf_analyzer.py

v18.5.38 Fund / ETF Analyzer v1 + Progress.

Pure helper layer for analysing funds and ETFs with a fund-specific decision
quality model. The module has no Streamlit dependency and does not fetch data by
itself; the UI passes data providers only when the user presses run.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app_version import get_app_version


FundDataProvider = Callable[[str], Optional[Mapping[str, Any]]]
BenchmarkProvider = Callable[[str], Optional[Mapping[str, Any]]]
ProgressCallback = Callable[[Mapping[str, Any]], None]
StopCallback = Callable[[], bool]


FUND_TEST_MODE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "Rask": {
        "tests": ["Fondstype", "Kostnad", "Avkastning", "Risiko", "Datakvalitet"],
        "description": "Rask screening av kostnad, avkastning og risiko.",
        "api_multiplier": 1.0,
    },
    "Normal": {
        "tests": ["Fondstype", "Kostnad", "Avkastning", "Risiko", "Maks drawdown", "Benchmark", "Fondskvalitet", "Datakvalitet"],
        "description": "Anbefalt modus med benchmark og fondskvalitet.",
        "api_multiplier": 1.25,
    },
    "Grundig": {
        "tests": ["Fondstype", "Kostnad", "Avkastning", "Risiko", "Maks drawdown", "Benchmark", "Aktiv merverdi", "Fondskvalitet", "Forklaring", "Datakvalitet"],
        "description": "Grundigere vurdering med aktiv-vs-indeks og forklaring.",
        "api_multiplier": 1.55,
    },
}

OBJECTIVE_WEIGHTS = {
    "Balansert": {"cost": 0.22, "return": 0.20, "risk": 0.20, "benchmark": 0.18, "data": 0.12, "fit": 0.08},
    "Lav kostnad": {"cost": 0.38, "return": 0.14, "risk": 0.18, "benchmark": 0.14, "data": 0.10, "fit": 0.06},
    "Lav risiko": {"cost": 0.20, "return": 0.14, "risk": 0.34, "benchmark": 0.14, "data": 0.10, "fit": 0.08},
    "Best historikk": {"cost": 0.16, "return": 0.34, "risk": 0.18, "benchmark": 0.16, "data": 0.10, "fit": 0.06},
    "Grunnmur": {"cost": 0.30, "return": 0.16, "risk": 0.22, "benchmark": 0.12, "data": 0.10, "fit": 0.10},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def normalize_fund_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def parse_fund_list(value: Any) -> List[str]:
    raw = str(value or "")
    for sep in [";", "\n", "\t"]:
        raw = raw.replace(sep, ",")
    out: List[str] = []
    seen = set()
    for part in raw.split(","):
        for token in str(part).split():
            symbol = normalize_fund_symbol(token)
            if symbol and symbol not in seen:
                out.append(symbol)
                seen.add(symbol)
    return out


def get_fund_test_mode_config(test_mode: str = "Normal") -> Dict[str, Any]:
    mode = str(test_mode or "Normal").strip()
    if mode not in FUND_TEST_MODE_CONFIGS:
        mode = "Normal"
    cfg = dict(FUND_TEST_MODE_CONFIGS[mode])
    cfg["mode"] = mode
    cfg["tests"] = list(cfg.get("tests") or FUND_TEST_MODE_CONFIGS["Normal"]["tests"])
    return cfg


def estimate_fund_etf_run(
    symbols: Sequence[str],
    *,
    test_mode: str = "Normal",
    include_benchmark: bool = True,
    fetch_costs: bool = True,
) -> Dict[str, Any]:
    clean: List[str] = []
    seen = set()
    for raw in symbols or []:
        symbol = normalize_fund_symbol(raw)
        if symbol and symbol not in seen:
            clean.append(symbol)
            seen.add(symbol)
    cfg = get_fund_test_mode_config(test_mode)
    tests = [t for t in cfg["tests"] if include_benchmark or t not in {"Benchmark", "Aktiv merverdi"}]
    total_tests = len(clean) * len(tests)
    price_calls = len(clean)
    benchmark_calls = 1 if include_benchmark and clean else 0
    metadata_calls = len(clean) if fetch_costs else 0
    load_score = int(math.ceil((price_calls + benchmark_calls + metadata_calls) * float(cfg.get("api_multiplier", 1.0))))
    if load_score <= 12:
        load_label = "Lav"
    elif load_score <= 45:
        load_label = "Medium"
    else:
        load_label = "Høy"
    return {
        "mode": cfg["mode"],
        "description": cfg.get("description", ""),
        "funds": len(clean),
        "tests": tests,
        "tests_per_fund": len(tests),
        "total_tests": total_tests,
        "price_calls": price_calls,
        "benchmark_calls": benchmark_calls,
        "metadata_calls": metadata_calls,
        "load_label": load_label,
    }


def _emit_progress(
    callback: Optional[ProgressCallback],
    *,
    symbol: str = "",
    fund_index: int = 0,
    fund_total: int = 0,
    test_name: str = "",
    test_index: int = 0,
    tests_per_fund: int = 0,
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
        "symbol": symbol,
        "fund_index": fund_index,
        "fund_total": fund_total,
        "test_name": test_name,
        "test_index": test_index,
        "tests_per_fund": tests_per_fund,
        "completed_tests": completed_tests,
        "total_tests": total_tests,
        "percent": round(pct, 1),
        "message": message,
        "updated_at": _now_iso(),
    })


def _prices_from_data(data: Optional[Mapping[str, Any]]) -> List[float]:
    if not data:
        return []
    raw = data.get("prices") or data.get("close") or data.get("closes") or []
    try:
        values = list(raw)
    except Exception:
        return []
    out: List[float] = []
    for value in values:
        val = _safe_float(value, None)
        if val is not None and val > 0:
            out.append(float(val))
    return out


def _period_return(prices: Sequence[float]) -> Optional[float]:
    vals = [float(x) for x in prices or [] if _safe_float(x, None) is not None and float(x) > 0]
    if len(vals) < 2:
        return None
    return (vals[-1] / vals[0] - 1.0) * 100.0


def _daily_returns(prices: Sequence[float]) -> List[float]:
    vals = [float(x) for x in prices or [] if _safe_float(x, None) is not None and float(x) > 0]
    out: List[float] = []
    for prev, cur in zip(vals, vals[1:]):
        if prev > 0:
            out.append((cur / prev) - 1.0)
    return out


def _annualized_volatility(prices: Sequence[float]) -> Optional[float]:
    rets = _daily_returns(prices)
    if len(rets) < 20:
        return None
    mean = sum(rets) / len(rets)
    variance = sum((x - mean) ** 2 for x in rets) / max(1, len(rets) - 1)
    return math.sqrt(variance) * math.sqrt(252.0) * 100.0


def _max_drawdown(prices: Sequence[float]) -> Optional[float]:
    vals = [float(x) for x in prices or [] if _safe_float(x, None) is not None and float(x) > 0]
    if len(vals) < 2:
        return None
    peak = vals[0]
    worst = 0.0
    for val in vals:
        peak = max(peak, val)
        if peak > 0:
            dd = (val / peak - 1.0) * 100.0
            worst = min(worst, dd)
    return worst


def _expense_ratio(data: Optional[Mapping[str, Any]]) -> Optional[float]:
    if not data:
        return None
    for key in ["expense_ratio", "expenseRatio", "annualReportExpenseRatio", "netExpenseRatio", "total_expense_ratio"]:
        val = _safe_float(data.get(key), None)
        if val is not None:
            # Some APIs return 0.002 for 0.20%, others 0.20.
            return val * 100.0 if 0 < val < 0.08 else val
    return None


def classify_fund(symbol: str, declared_type: str = "Alle", data: Optional[Mapping[str, Any]] = None) -> str:
    declared = str(declared_type or "Alle")
    if declared in {"Indeksfond", "Aktivt fond", "ETF"}:
        return declared
    if data:
        quote_type = str(data.get("quoteType") or data.get("type") or "").upper()
        category = str(data.get("category") or data.get("fundFamily") or "").upper()
        name = str(data.get("name") or data.get("longName") or "").upper()
        if "ETF" in quote_type or " ETF" in name:
            return "ETF"
        if "INDEX" in category or "INDEKS" in category or "INDEX" in name or "INDEKS" in name:
            return "Indeksfond"
    s = str(symbol or "").upper()
    if any(tag in s for tag in ["ETF", ".L", ".PA", ".DE"]):
        return "ETF"
    return "Fond"


def _score_cost(expense: Optional[float], fund_type: str) -> float:
    if expense is None:
        return 55.0
    # Thresholds are stricter for index funds/ETFs, more tolerant for active funds.
    if fund_type in {"Indeksfond", "ETF"}:
        return _clamp(100.0 - (expense / 0.80) * 75.0, 10.0, 100.0)
    if fund_type == "Aktivt fond":
        return _clamp(100.0 - (expense / 1.80) * 65.0, 8.0, 100.0)
    return _clamp(100.0 - (expense / 1.20) * 70.0, 8.0, 100.0)


def _score_return(total_return: Optional[float]) -> float:
    if total_return is None:
        return 50.0
    # 5y/period return may vary, keep conservative.
    return _clamp(50.0 + total_return * 0.9, 5.0, 100.0)


def _score_risk(volatility: Optional[float], drawdown: Optional[float]) -> float:
    vol_score = 65.0 if volatility is None else _clamp(100.0 - volatility * 2.2, 5.0, 100.0)
    dd_score = 65.0 if drawdown is None else _clamp(100.0 + drawdown * 1.9, 5.0, 100.0)
    return round((vol_score * 0.55) + (dd_score * 0.45), 1)


def _score_benchmark(total_return: Optional[float], benchmark_return: Optional[float], expense: Optional[float], fund_type: str) -> float:
    if total_return is None or benchmark_return is None:
        return 55.0
    excess = total_return - benchmark_return
    fee_drag = expense or 0.0
    if fund_type == "Aktivt fond":
        # Active funds need excess return after fee drag to score high.
        return _clamp(55.0 + excess * 1.7 - fee_drag * 8.0, 5.0, 100.0)
    # Index/ETF should be close to benchmark, not necessarily beat it.
    tracking_gap = abs(excess)
    return _clamp(95.0 - tracking_gap * 1.4 - fee_drag * 3.0, 10.0, 100.0)


def _score_data_quality(prices: Sequence[float], expense: Optional[float], benchmark_return: Optional[float]) -> float:
    n = len(prices or [])
    score = 30.0
    if n >= 60:
        score += 20.0
    if n >= 250:
        score += 20.0
    if n >= 750:
        score += 10.0
    if expense is not None:
        score += 10.0
    if benchmark_return is not None:
        score += 10.0
    return _clamp(score, 5.0, 100.0)


def analyze_fund_record(
    symbol: str,
    data: Optional[Mapping[str, Any]],
    *,
    fund_type: str = "Alle",
    objective: str = "Balansert",
    benchmark_data: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    symbol = normalize_fund_symbol(symbol)
    data = data or {}
    prices = _prices_from_data(data)
    benchmark_prices = _prices_from_data(benchmark_data)
    detected_type = classify_fund(symbol, fund_type, data)
    expense = _expense_ratio(data)
    total_return = _period_return(prices)
    benchmark_return = _period_return(benchmark_prices)
    volatility = _annualized_volatility(prices)
    drawdown = _max_drawdown(prices)

    cost_score = _score_cost(expense, detected_type)
    return_score = _score_return(total_return)
    risk_score = _score_risk(volatility, drawdown)
    benchmark_score = _score_benchmark(total_return, benchmark_return, expense, detected_type)
    data_score = _score_data_quality(prices, expense, benchmark_return)
    fit_score = 86.0 if detected_type in {"Indeksfond", "ETF"} and objective in {"Grunnmur", "Lav kostnad", "Balansert"} else 68.0
    if detected_type == "Aktivt fond" and benchmark_score < 55:
        fit_score -= 14.0
    fit_score = _clamp(fit_score, 5.0, 100.0)

    weights = OBJECTIVE_WEIGHTS.get(objective) or OBJECTIVE_WEIGHTS["Balansert"]
    quality = round(
        cost_score * weights["cost"]
        + return_score * weights["return"]
        + risk_score * weights["risk"]
        + benchmark_score * weights["benchmark"]
        + data_score * weights["data"]
        + fit_score * weights["fit"],
        1,
    )

    if quality >= 75:
        grade = "Høy"
    elif quality >= 58:
        grade = "Middels"
    else:
        grade = "Lav"

    positives: List[str] = []
    cautions: List[str] = []
    if cost_score >= 78:
        positives.append("lav kostnad")
    elif expense is None:
        cautions.append("kostnad mangler")
    else:
        cautions.append("kostnad bør vurderes")
    if return_score >= 65:
        positives.append("god historikk i perioden")
    elif total_return is None:
        cautions.append("mangler nok prisdata")
    if risk_score >= 70:
        positives.append("akseptabel risiko/drawdown")
    elif risk_score < 45:
        cautions.append("høy risiko eller drawdown")
    if detected_type == "Aktivt fond":
        if benchmark_score >= 65:
            positives.append("aktiv merverdi støttes av benchmark-sjekk")
        else:
            cautions.append("aktiv merverdi ikke godt nok bevist")
    elif benchmark_score >= 70:
        positives.append("følger benchmark godt")
    if data_score < 55:
        cautions.append("svak datakvalitet")

    if grade == "Høy":
        decision = "Kan vurderes"
    elif grade == "Middels":
        decision = "Vurder videre"
    else:
        decision = "Vent / forkast"
    if detected_type == "Aktivt fond" and benchmark_score < 55:
        decision = "Krever mer bevis"

    return {
        "symbol": symbol,
        "name": data.get("name") or data.get("longName") or symbol,
        "fund_type": detected_type,
        "objective": objective,
        "decision_quality": quality,
        "grade": grade,
        "decision": decision,
        "expense_ratio_pct": None if expense is None else round(expense, 3),
        "period_return_pct": None if total_return is None else round(total_return, 2),
        "benchmark_return_pct": None if benchmark_return is None else round(benchmark_return, 2),
        "excess_return_pct": None if total_return is None or benchmark_return is None else round(total_return - benchmark_return, 2),
        "volatility_pct": None if volatility is None else round(volatility, 2),
        "max_drawdown_pct": None if drawdown is None else round(drawdown, 2),
        "cost_score": round(cost_score, 1),
        "return_score": round(return_score, 1),
        "risk_score": round(risk_score, 1),
        "benchmark_score": round(benchmark_score, 1),
        "data_quality": round(data_score, 1),
        "fit_score": round(fit_score, 1),
        "reasons_positive": positives[:4],
        "reasons_caution": cautions[:4],
        "data_points": len(prices),
        "version": get_app_version(),
        "created_at": _now_iso(),
    }


def run_fund_etf_lab(
    symbols: Sequence[str],
    *,
    data_provider: FundDataProvider,
    benchmark_provider: Optional[BenchmarkProvider] = None,
    benchmark_symbol: str = "SPY",
    fund_type: str = "Alle",
    objective: str = "Balansert",
    test_mode: str = "Normal",
    progress_callback: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
    max_funds: int = 40,
) -> Dict[str, Any]:
    clean: List[str] = []
    seen = set()
    for raw in symbols or []:
        symbol = normalize_fund_symbol(raw)
        if symbol and symbol not in seen:
            clean.append(symbol)
            seen.add(symbol)
        if len(clean) >= max(1, int(max_funds or 40)):
            break
    budget = estimate_fund_etf_run(clean, test_mode=test_mode, include_benchmark=bool(benchmark_provider), fetch_costs=True)
    tests = list(budget.get("tests") or [])
    total_tests = int(budget.get("total_tests") or 0)
    completed = 0
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    interrupted = False

    benchmark_data: Optional[Mapping[str, Any]] = None
    if benchmark_provider and benchmark_symbol:
        try:
            benchmark_data = benchmark_provider(benchmark_symbol)
        except Exception as exc:
            errors.append({"symbol": benchmark_symbol, "test": "Benchmark", "error": str(exc)[:200]})
            benchmark_data = None

    _emit_progress(progress_callback, completed_tests=0, total_tests=total_tests, status="starting", message="Starter Fond / ETF-analyse")

    for fund_idx, symbol in enumerate(clean, start=1):
        if should_stop and should_stop():
            interrupted = True
            break
        data: Optional[Mapping[str, Any]] = None
        for test_idx, test_name in enumerate(tests, start=1):
            if should_stop and should_stop():
                interrupted = True
                break
            _emit_progress(
                progress_callback,
                symbol=symbol,
                fund_index=fund_idx,
                fund_total=len(clean),
                test_name=test_name,
                test_index=test_idx,
                tests_per_fund=len(tests),
                completed_tests=completed,
                total_tests=total_tests,
                status="running",
            )
            try:
                # Fetch once at first test. Subsequent tests reuse same data.
                if data is None:
                    data = data_provider(symbol)
                # Computation happens after all named checks have been displayed.
            except Exception as exc:
                errors.append({"symbol": symbol, "test": test_name, "error": str(exc)[:200]})
                data = None
            completed += 1
            _emit_progress(
                progress_callback,
                symbol=symbol,
                fund_index=fund_idx,
                fund_total=len(clean),
                test_name=test_name,
                test_index=test_idx,
                tests_per_fund=len(tests),
                completed_tests=completed,
                total_tests=total_tests,
                status="running",
            )
        if interrupted:
            break
        try:
            row = analyze_fund_record(symbol, data, fund_type=fund_type, objective=objective, benchmark_data=benchmark_data)
            if row.get("data_points", 0) < 2:
                row["decision"] = "Mangler data"
                row.setdefault("reasons_caution", []).append("ingen prisserie funnet")
            results.append(row)
        except Exception as exc:
            errors.append({"symbol": symbol, "test": "Analyse", "error": str(exc)[:200]})

    ranked = sorted(results, key=lambda x: (float(x.get("decision_quality") or 0), float(x.get("data_quality") or 0)), reverse=True)
    index_candidates = [r for r in ranked if r.get("fund_type") in {"Indeksfond", "ETF"}]
    active_candidates = [r for r in ranked if r.get("fund_type") == "Aktivt fond"]
    needs_proof = [r for r in ranked if r.get("decision") in {"Krever mer bevis", "Vent / forkast", "Mangler data"}]
    summary = {
        "best_symbol": ranked[0].get("symbol") if ranked else "",
        "best_quality": ranked[0].get("decision_quality") if ranked else None,
        "analyzed": len(results),
        "errors": len(errors),
        "interrupted": interrupted,
    }
    return {
        "version": get_app_version(),
        "created_at": _now_iso(),
        "fund_type": fund_type,
        "objective": objective,
        "test_mode": test_mode,
        "benchmark_symbol": benchmark_symbol,
        "symbols": clean,
        "budget": budget,
        "completed_tests": completed,
        "total_tests": total_tests,
        "interrupted": interrupted,
        "summary": summary,
        "ranked": ranked,
        "index_candidates": index_candidates,
        "active_candidates": active_candidates,
        "needs_proof": needs_proof,
        "errors": errors,
    }
