"""
fund_etf_analyzer.py

v18.5.43 Fund / ETF Analyzer with hardened Fund Decision Quality.

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


# v18.5.39: Small curated starter universes. These are intentionally transparent
# and can be replaced by richer broker/fund feeds later. They use Yahoo symbols
# where possible and never fetch data until the user presses Run.
FUND_SELECTION_SOURCES = [
    "Manuell liste",
    "Auto indeksfond",
    "Auto ETF",
    "Auto aktive fond",
    "Alle / balansert miks",
]

FUND_UNIVERSES: Dict[str, List[Dict[str, str]]] = {
    "Indeksfond": [
        {"symbol": "VOO", "type": "ETF", "bucket": "USA bred indeks", "reason": "billig bred S&P 500-eksponering"},
        {"symbol": "VTI", "type": "ETF", "bucket": "USA totalmarked", "reason": "bred totalmarkedseksponering"},
        {"symbol": "ACWI", "type": "ETF", "bucket": "Global indeks", "reason": "global aksjeeksponering"},
        {"symbol": "VT", "type": "ETF", "bucket": "Global totalmarked", "reason": "globalt bredt aksjefond"},
        {"symbol": "VEA", "type": "ETF", "bucket": "Utviklede markeder", "reason": "eksponering utenfor USA"},
        {"symbol": "EEM", "type": "ETF", "bucket": "Emerging markets", "reason": "fremvoksende markeder"},
        {"symbol": "IEFA", "type": "ETF", "bucket": "Internasjonal indeks", "reason": "bred ikke-USA indeks"},
        {"symbol": "IUSQ.DE", "type": "ETF", "bucket": "Global UCITS", "reason": "global UCITS-lignende kandidat"},
        {"symbol": "SXR8.DE", "type": "ETF", "bucket": "S&P 500 UCITS", "reason": "europeisk S&P 500-kandidat"},
        {"symbol": "EUNL.DE", "type": "ETF", "bucket": "MSCI World UCITS", "reason": "bred world-kandidat"},
    ],
    "ETF": [
        {"symbol": "SPY", "type": "ETF", "bucket": "S&P 500", "reason": "stor og likvid benchmark-ETF"},
        {"symbol": "VOO", "type": "ETF", "bucket": "S&P 500", "reason": "lavkost S&P 500"},
        {"symbol": "VTI", "type": "ETF", "bucket": "USA totalmarked", "reason": "bred USA-eksponering"},
        {"symbol": "QQQ", "type": "ETF", "bucket": "Teknologi/vekst", "reason": "Nasdaq 100 / vekstprofil"},
        {"symbol": "ACWI", "type": "ETF", "bucket": "Global", "reason": "global aksjeeksponering"},
        {"symbol": "IWM", "type": "ETF", "bucket": "Small cap", "reason": "small-cap diversifisering"},
        {"symbol": "DIA", "type": "ETF", "bucket": "Dow", "reason": "stor verdi/blue-chip eksponering"},
        {"symbol": "EFA", "type": "ETF", "bucket": "Utviklede markeder", "reason": "ikke-USA utviklede markeder"},
        {"symbol": "EEM", "type": "ETF", "bucket": "Emerging markets", "reason": "fremvoksende markeder"},
        {"symbol": "XLK", "type": "ETF", "bucket": "Sektor teknologi", "reason": "sektor-satellitt teknologi"},
        {"symbol": "XLF", "type": "ETF", "bucket": "Sektor finans", "reason": "sektor-satellitt finans"},
        {"symbol": "XLV", "type": "ETF", "bucket": "Sektor helse", "reason": "defensiv/sektor helse"},
    ],
    "Aktivt fond": [
        {"symbol": "ARKK", "type": "Aktivt fond", "bucket": "Aktiv vekst", "reason": "aktiv/disruptiv vekstprofil, må bevise merverdi"},
        {"symbol": "ARKW", "type": "Aktivt fond", "bucket": "Aktiv teknologi", "reason": "aktiv teknologi/vekst, må testes mot benchmark"},
        {"symbol": "ARKF", "type": "Aktivt fond", "bucket": "Aktiv fintech", "reason": "aktiv tematisk kandidat"},
        {"symbol": "JEPI", "type": "Aktivt fond", "bucket": "Aktiv income", "reason": "aktiv income/covered-call ETF"},
        {"symbol": "JEPQ", "type": "Aktivt fond", "bucket": "Aktiv Nasdaq income", "reason": "aktiv Nasdaq/income-kandidat"},
        {"symbol": "TCAF", "type": "Aktivt fond", "bucket": "Aktiv kapitalallokering", "reason": "aktivt forvaltet ETF-kandidat"},
        {"symbol": "DYNF", "type": "Aktivt fond", "bucket": "Aktiv faktor", "reason": "aktiv faktor/rotasjon"},
        {"symbol": "AVGV", "type": "Aktivt fond", "bucket": "Aktiv verdi", "reason": "aktiv verdifaktor-kandidat"},
    ],
}


def fund_selection_sources() -> List[str]:
    """Return UI-safe source options for fund selection."""
    return list(FUND_SELECTION_SOURCES)


def _dedupe_symbols(items: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in items or []:
        symbol = normalize_fund_symbol(item.get("symbol"))
        if not symbol or symbol in seen:
            continue
        row = dict(item)
        row["symbol"] = symbol
        out.append(row)
        seen.add(symbol)
    return out


def _balanced_mix(max_funds: int) -> List[Dict[str, Any]]:
    """Create a simple balanced mix across broad index, ETF and active candidates."""
    max_funds = max(1, int(max_funds or 8))
    buckets = [
        FUND_UNIVERSES["Indeksfond"],
        FUND_UNIVERSES["ETF"],
        FUND_UNIVERSES["Aktivt fond"],
    ]
    selected: List[Dict[str, Any]] = []
    seen = set()
    i = 0
    while len(selected) < max_funds and any(i < len(bucket) for bucket in buckets):
        for bucket in buckets:
            if len(selected) >= max_funds:
                break
            if i < len(bucket):
                row = dict(bucket[i])
                symbol = normalize_fund_symbol(row.get("symbol"))
                if symbol and symbol not in seen:
                    row["symbol"] = symbol
                    selected.append(row)
                    seen.add(symbol)
        i += 1
    return selected[:max_funds]


def select_fund_candidates(
    *,
    source: str = "Manuell liste",
    fund_type: str = "Alle",
    manual_symbols: Sequence[str] | None = None,
    max_funds: int = 8,
) -> Dict[str, Any]:
    """Resolve fund/ETF candidates from a source.

    v18.5.39 makes `Maks fond` meaningful for automatic sources. Manual mode
    still respects the user's entered order, while auto modes choose from a
    transparent starter universe and return reasons for every selected symbol.
    """
    source = str(source or "Manuell liste").strip()
    if source not in FUND_SELECTION_SOURCES:
        source = "Manuell liste"
    max_funds = max(1, int(max_funds or 8))
    manual = [normalize_fund_symbol(x) for x in (manual_symbols or []) if normalize_fund_symbol(x)]

    if source == "Manuell liste":
        rows = [
            {"symbol": sym, "type": fund_type if fund_type != "Alle" else "Manuell", "bucket": "Manuell", "reason": "valgt manuelt av bruker"}
            for sym in manual
        ]
    elif source == "Auto indeksfond":
        rows = FUND_UNIVERSES["Indeksfond"]
    elif source == "Auto ETF":
        rows = FUND_UNIVERSES["ETF"]
    elif source == "Auto aktive fond":
        rows = FUND_UNIVERSES["Aktivt fond"]
    else:
        rows = _balanced_mix(max_funds)

    if source not in {"Manuell liste", "Alle / balansert miks"}:
        # If user also selected a stricter type, keep the automatic source as the
        # primary intent. For example Auto ETF should remain ETF even if the type
        # select is still Alle.
        selected = _dedupe_symbols(rows)[:max_funds]
    else:
        selected = _dedupe_symbols(rows)[:max_funds]

    symbols = [r["symbol"] for r in selected]
    return {
        "source": source,
        "fund_type": fund_type,
        "max_funds": max_funds,
        "symbols": symbols,
        "selected": selected,
        "selection_summary": f"{len(symbols)} fond/ETF valgt fra {source}",
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




def _active_evidence_test(
    *,
    fund_type: str,
    total_return: Optional[float],
    benchmark_return: Optional[float],
    expense: Optional[float],
    volatility: Optional[float],
    benchmark_volatility: Optional[float] = None,
) -> Dict[str, Any]:
    """Assess whether an active fund has proven enough value after costs.

    This is intentionally conservative: active funds should not score highly just
    because absolute return is positive. They need acceptable excess return vs a
    relevant benchmark, after considering fee drag and extra risk.
    """
    if fund_type != "Aktivt fond":
        return {
            "status": "Ikke relevant",
            "score": None,
            "excess_return_pct": None if total_return is None or benchmark_return is None else round(total_return - benchmark_return, 2),
            "risk_penalty_pct": 0.0,
            "fee_drag_pct": None if expense is None else round(expense, 3),
            "message": "Ikke aktivt fond/aktiv ETF.",
        }
    if total_return is None or benchmark_return is None:
        return {
            "status": "Mangler data",
            "score": 35.0,
            "excess_return_pct": None,
            "risk_penalty_pct": None,
            "fee_drag_pct": None if expense is None else round(expense, 3),
            "message": "Mangler historikk eller benchmark for å bevise aktiv merverdi.",
        }
    excess = float(total_return) - float(benchmark_return)
    fee_drag = float(expense or 0.0)
    risk_penalty = 0.0
    if volatility is not None and benchmark_volatility is not None:
        risk_penalty = max(0.0, float(volatility) - float(benchmark_volatility)) * 0.20
    # Conservative evidence score. Need positive excess above fees and not too much extra risk.
    evidence_score = _clamp(50.0 + (excess * 2.0) - (fee_drag * 10.0) - risk_penalty, 0.0, 100.0)
    net_edge = excess - fee_drag - risk_penalty
    if evidence_score >= 68.0 and net_edge > 0.5:
        status = "Godkjent"
        msg = "Har foreløpig bevist aktiv merverdi mot benchmark etter kostnad/riskojustering."
    elif evidence_score >= 52.0 and net_edge > -1.0:
        status = "Usikker"
        msg = "Noe aktiv merverdi, men ikke sterkt nok til høy tillit."
    else:
        status = "Ikke bevist"
        msg = "Har ikke bevist nok merverdi til å forsvare aktiv kostnad/risiko."
    return {
        "status": status,
        "score": round(evidence_score, 1),
        "excess_return_pct": round(excess, 2),
        "risk_penalty_pct": round(risk_penalty, 2),
        "fee_drag_pct": round(fee_drag, 3),
        "message": msg,
    }


def build_fund_comparator(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build a compact fund-vs-fund comparison summary."""
    valid = [dict(r) for r in (rows or []) if r]
    if not valid:
        return {"count": 0, "leaders": {}, "rows": [], "active_evidence": []}

    def _min_by(key: str):
        candidates = [r for r in valid if _safe_float(r.get(key), None) is not None]
        return min(candidates, key=lambda r: float(r.get(key))) if candidates else None

    def _max_by(key: str):
        candidates = [r for r in valid if _safe_float(r.get(key), None) is not None]
        return max(candidates, key=lambda r: float(r.get(key))) if candidates else None

    def _risk_adjusted(row: Mapping[str, Any]) -> float:
        ret = _safe_float(row.get("period_return_pct"), 0.0) or 0.0
        vol = _safe_float(row.get("volatility_pct"), None)
        dd = abs(_safe_float(row.get("max_drawdown_pct"), 0.0) or 0.0)
        risk = (vol if vol is not None else 18.0) + (dd * 0.35)
        return ret / max(1.0, risk)

    def _after_cost(row: Mapping[str, Any]) -> float:
        ret = _safe_float(row.get("period_return_pct"), 0.0) or 0.0
        fee = _safe_float(row.get("expense_ratio_pct"), 0.0) or 0.0
        return ret - fee

    cheapest = _min_by("expense_ratio_pct")
    best_quality = _max_by("decision_quality")
    best_after_cost = max(valid, key=_after_cost)
    best_risk_adjusted = max(valid, key=_risk_adjusted)
    foundation_candidates = [r for r in valid if r.get("fund_type") in {"Indeksfond", "ETF"}]
    best_foundation = max(foundation_candidates or valid, key=lambda r: (float(r.get("fit_score") or 0), float(r.get("decision_quality") or 0)))

    rows_out: List[Dict[str, Any]] = []
    for r in valid:
        rows_out.append({
            "symbol": r.get("symbol"),
            "name": r.get("name"),
            "fund_type": r.get("fund_type"),
            "decision_quality": r.get("decision_quality"),
            "expense_ratio_pct": r.get("expense_ratio_pct"),
            "period_return_pct": r.get("period_return_pct"),
            "volatility_pct": r.get("volatility_pct"),
            "max_drawdown_pct": r.get("max_drawdown_pct"),
            "excess_return_pct": r.get("excess_return_pct"),
            "active_evidence_status": r.get("active_evidence_status"),
            "active_evidence_score": r.get("active_evidence_score"),
            "decision": r.get("decision"),
        })

    active = [r for r in valid if r.get("fund_type") == "Aktivt fond"]
    active_evidence = sorted(active, key=lambda r: float(r.get("active_evidence_score") or 0), reverse=True)
    return {
        "count": len(valid),
        "leaders": {
            "billigst": cheapest.get("symbol") if cheapest else "-",
            "best_kvalitet": best_quality.get("symbol") if best_quality else "-",
            "best_etter_kostnad": best_after_cost.get("symbol") if best_after_cost else "-",
            "best_risikojustert": best_risk_adjusted.get("symbol") if best_risk_adjusted else "-",
            "best_grunnmur": best_foundation.get("symbol") if best_foundation else "-",
        },
        "rows": rows_out,
        "active_evidence": active_evidence,
    }



BROAD_CORE_HINTS = [
    "GLOBAL", "WORLD", "TOTALMARKED", "TOTAL MARKET", "S&P 500", "SP 500",
    "MSCI", "BRED", "BROAD", "UTVIKLEDE", "INDEKS", "INDEX",
]
SATELLITE_HINTS = [
    "TEKNOLOGI", "TECH", "SEKTOR", "SECTOR", "SMALL", "EMERGING", "VEKST",
    "GROWTH", "FINTECH", "INCOME", "NASDAQ", "FAKTOR", "FACTOR", "VERDI", "VALUE",
]
BROAD_CORE_SYMBOLS = {"SPY", "VOO", "VTI", "VT", "ACWI", "EUNL.DE", "IUSQ.DE", "SXR8.DE", "VEA", "IEFA"}
SATELLITE_SYMBOLS = {"QQQ", "XLK", "XLF", "XLV", "IWM", "EEM", "ARKK", "ARKW", "ARKF", "JEPI", "JEPQ", "TCAF", "DYNF", "AVGV"}

CORE_SATELLITE_PROFILES: Dict[str, Dict[str, Any]] = {
    "Lav kostnad": {"core_pct": 90, "satellite_pct": 10, "max_core": 3, "max_satellite": 2, "description": "Lav kostnad: mest mulig bred grunnmur, få satellitter."},
    "Lav risiko": {"core_pct": 85, "satellite_pct": 15, "max_core": 3, "max_satellite": 2, "description": "Lav risiko: bred grunnmur og begrenset satellittandel."},
    "Grunnmur": {"core_pct": 90, "satellite_pct": 10, "max_core": 3, "max_satellite": 2, "description": "Grunnmur: prioriterer brede indeks-/ETF-kandidater."},
    "Best historikk": {"core_pct": 65, "satellite_pct": 35, "max_core": 3, "max_satellite": 4, "description": "Best historikk: mer rom for satellitter med god kvalitet."},
    "Balansert": {"core_pct": 75, "satellite_pct": 25, "max_core": 3, "max_satellite": 3, "description": "Balansert: bred grunnmur med kontrollerte satellitter."},
}


def _text_has_any(value: Any, hints: Sequence[str]) -> bool:
    text = str(value or "").upper()
    return any(h in text for h in hints)


def _is_broad_core_candidate(row: Mapping[str, Any]) -> bool:
    symbol = str(row.get("symbol") or "").upper()
    ftype = str(row.get("fund_type") or "")
    bucket = row.get("bucket") or row.get("category") or row.get("name") or ""
    if ftype not in {"Indeksfond", "ETF"}:
        return False
    if symbol in BROAD_CORE_SYMBOLS:
        return True
    if _text_has_any(bucket, BROAD_CORE_HINTS) and not _text_has_any(bucket, SATELLITE_HINTS):
        return True
    return False


def _is_satellite_candidate(row: Mapping[str, Any]) -> bool:
    symbol = str(row.get("symbol") or "").upper()
    ftype = str(row.get("fund_type") or "")
    bucket = row.get("bucket") or row.get("category") or row.get("name") or ""
    if symbol in SATELLITE_SYMBOLS:
        return True
    if ftype == "Aktivt fond":
        return True
    if _text_has_any(bucket, SATELLITE_HINTS):
        return True
    return False


def _role_reason(row: Mapping[str, Any], role: str) -> str:
    ftype = str(row.get("fund_type") or "")
    cost = row.get("expense_ratio_pct")
    quality = row.get("decision_quality")
    evidence = row.get("active_evidence_status")
    if role == "Grunnmur":
        return "Bred/lavkost indeks- eller ETF-kandidat med egnet kvalitet som porteføljegrunnmur."
    if role == "Satellitt":
        if ftype == "Aktivt fond":
            return f"Aktiv kandidat med {evidence or 'ukjent'} merverdibevis; bør brukes som mindre satellitt, ikke grunnmur."
        return "Mer spisset/sektor-/temaeksponering; kan brukes som kontrollert satellitt rundt grunnmuren."
    if role == "Krever mer bevis":
        return "Mangler sterk nok dokumentasjon, datakvalitet eller aktiv merverdi til å få plass i forslag nå."
    return "Lav kvalitet, mangelfulle data eller for svak kostnad/risiko-profil for valgt mål."


def classify_core_satellite_role(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Assign a portfolio role to one analysed fund row."""
    r = dict(row or {})
    quality = _safe_float(r.get("decision_quality"), 0.0) or 0.0
    data_q = _safe_float(r.get("data_quality"), 0.0) or 0.0
    cost_score = _safe_float(r.get("cost_score"), 55.0) or 55.0
    decision = str(r.get("decision") or "")
    ftype = str(r.get("fund_type") or "")
    evidence = str(r.get("active_evidence_status") or "")

    if decision in {"Mangler data", "Vent / forkast"} or quality < 50 or data_q < 35:
        role = "Unngå"
    elif ftype == "Aktivt fond" and evidence != "Godkjent":
        role = "Krever mer bevis"
    elif decision == "Krever mer bevis":
        role = "Krever mer bevis"
    elif _is_broad_core_candidate(r) and quality >= 60 and cost_score >= 55 and data_q >= 45:
        role = "Grunnmur"
    elif quality >= 58 and (_is_satellite_candidate(r) or ftype in {"ETF", "Aktivt fond"}):
        role = "Satellitt"
    elif quality >= 62 and ftype in {"Indeksfond", "ETF"}:
        role = "Grunnmur"
    else:
        role = "Krever mer bevis"

    return {
        "symbol": r.get("symbol"),
        "name": r.get("name"),
        "fund_type": ftype,
        "role": role,
        "decision_quality": r.get("decision_quality"),
        "expense_ratio_pct": r.get("expense_ratio_pct"),
        "period_return_pct": r.get("period_return_pct"),
        "volatility_pct": r.get("volatility_pct"),
        "max_drawdown_pct": r.get("max_drawdown_pct"),
        "active_evidence_status": r.get("active_evidence_status"),
        "reason": _role_reason(r, role),
        "cautions": list(r.get("reasons_caution") or [])[:3],
    }


def _allocate_weights(candidates: Sequence[Mapping[str, Any]], total_weight: float) -> List[float]:
    n = len(candidates or [])
    if n <= 0 or total_weight <= 0:
        return []
    scores = [max(20.0, _safe_float(c.get("decision_quality"), 50.0) or 50.0) for c in candidates]
    total_score = sum(scores) or float(n)
    raw = [(s / total_score) * float(total_weight) for s in scores]
    rounded = [round(x, 1) for x in raw]
    drift = round(float(total_weight) - sum(rounded), 1)
    if rounded:
        rounded[0] = round(rounded[0] + drift, 1)
    return rounded


def build_core_satellite_portfolio(
    rows: Sequence[Mapping[str, Any]],
    *,
    profile: str = "Balansert",
    max_positions: int = 8,
) -> Dict[str, Any]:
    """Create a simple core/satellite fund proposal from analysed fund rows.

    The function is deliberately conservative: broad, low-cost index/ETF rows are
    preferred as core. Active funds are only eligible as satellites when their
    active evidence test is approved. Everything else is labelled as needing more
    proof or avoid.
    """
    profile_key = str(profile or "Balansert")
    cfg = CORE_SATELLITE_PROFILES.get(profile_key) or CORE_SATELLITE_PROFILES["Balansert"]
    max_positions = max(1, int(max_positions or 8))
    valid = [dict(r) for r in (rows or []) if r]
    if not valid:
        return {
            "profile": profile_key,
            "status": "Ingen data",
            "allocation": [],
            "core": [],
            "satellites": [],
            "needs_proof": [],
            "avoid": [],
            "warnings": ["Kjør Fond / ETF-analyse først."],
            "summary": "Ingen fond/ETF-data å bygge forslag fra.",
        }

    roles = [classify_core_satellite_role(r) for r in valid]
    by_symbol = {str(r.get("symbol")): dict(r) for r in valid}
    core = [r for r in roles if r.get("role") == "Grunnmur"]
    satellites = [r for r in roles if r.get("role") == "Satellitt"]
    needs = [r for r in roles if r.get("role") == "Krever mer bevis"]
    avoid = [r for r in roles if r.get("role") == "Unngå"]

    def _sort_key(role_row: Mapping[str, Any]) -> Tuple[float, float]:
        full = by_symbol.get(str(role_row.get("symbol")), {})
        return (_safe_float(full.get("decision_quality"), 0.0) or 0.0, _safe_float(full.get("data_quality"), 0.0) or 0.0)

    core = sorted(core, key=_sort_key, reverse=True)[: int(cfg.get("max_core") or 3)]
    remaining_slots = max(0, max_positions - len(core))
    satellites = sorted(satellites, key=_sort_key, reverse=True)[: min(remaining_slots, int(cfg.get("max_satellite") or 3))]

    warnings: List[str] = []
    if not core:
        warnings.append("Fant ingen tydelig grunnmur. Vurder bredt/lavkost indeksfond før satellitter.")
        # Emergency fallback: allow best broad-ish ETF/index candidate if available.
        fallback = sorted([r for r in roles if r.get("fund_type") in {"Indeksfond", "ETF"} and r.get("role") != "Unngå"], key=_sort_key, reverse=True)[:1]
        if fallback:
            fallback[0]["role"] = "Grunnmur"
            fallback[0]["reason"] = "Beste tilgjengelige indeks/ETF-kandidat, men bør valideres som grunnmur."
            core = fallback
            satellites = [s for s in satellites if s.get("symbol") != core[0].get("symbol")]
    if not satellites:
        warnings.append("Ingen klare satellitter valgt; grunnmur kan stå alene.")

    core_pct = float(cfg.get("core_pct") or 75)
    sat_pct = float(cfg.get("satellite_pct") or 25)
    if not satellites:
        core_pct, sat_pct = 100.0, 0.0
    if not core:
        core_pct, sat_pct = 0.0, 100.0 if satellites else 0.0

    allocation: List[Dict[str, Any]] = []
    for role_row, weight in zip(core, _allocate_weights(core, core_pct)):
        row = dict(role_row)
        row["weight_pct"] = weight
        allocation.append(row)
    for role_row, weight in zip(satellites, _allocate_weights(satellites, sat_pct)):
        row = dict(role_row)
        row["weight_pct"] = weight
        allocation.append(row)

    if allocation:
        total = round(sum(float(a.get("weight_pct") or 0.0) for a in allocation), 1)
        drift = round(100.0 - total, 1)
        allocation[0]["weight_pct"] = round(float(allocation[0].get("weight_pct") or 0.0) + drift, 1)

    avg_quality = None
    if allocation:
        avg_quality = round(sum((_safe_float(a.get("decision_quality"), 0.0) or 0.0) * (float(a.get("weight_pct") or 0.0) / 100.0) for a in allocation), 1)

    summary = "Forslag laget med bred grunnmur og kontrollerte satellitter." if allocation else "Ingen allokering foreslått."
    return {
        "profile": profile_key,
        "status": "OK" if allocation else "Mangler kandidater",
        "description": cfg.get("description"),
        "target_core_pct": core_pct,
        "target_satellite_pct": sat_pct,
        "average_quality": avg_quality,
        "allocation": allocation,
        "core": core,
        "satellites": satellites,
        "needs_proof": needs,
        "avoid": avoid,
        "warnings": warnings,
        "summary": summary,
        "role_counts": {
            "grunnmur": len(core),
            "satellitt": len(satellites),
            "krever_mer_bevis": len(needs),
            "unngå": len(avoid),
        },
    }


# v18.5.42: Cost impact over time -------------------------------------------------
DEFAULT_COST_IMPACT_FEES = [0.18, 0.50, 1.00, 1.50]


def future_value_after_costs(
    *,
    start_amount: float = 100_000.0,
    monthly_saving: float = 2_000.0,
    annual_return_pct: float = 7.0,
    annual_fee_pct: float = 0.18,
    years: int = 20,
) -> float:
    """Estimate ending value after annual fund costs using monthly compounding.

    The model is intentionally simple and transparent. It is not a promise of
    future return; it shows how different expense ratios can compound into a
    large value difference over time.
    """
    start = max(0.0, float(start_amount or 0.0))
    saving = max(0.0, float(monthly_saving or 0.0))
    years_i = max(1, int(years or 1))
    gross = float(annual_return_pct or 0.0) / 100.0
    fee = max(0.0, float(annual_fee_pct or 0.0)) / 100.0
    # Conservative: subtract fee from gross annual return before monthly compounding.
    net_annual = max(-0.95, gross - fee)
    monthly_rate = (1.0 + net_annual) ** (1.0 / 12.0) - 1.0
    value = start
    for _ in range(years_i * 12):
        value = value * (1.0 + monthly_rate) + saving
    return round(value, 2)


def _format_cost_label(symbol: str, fee: float) -> str:
    sym = str(symbol or "").strip()
    return f"{sym} · {fee:.2f}%" if sym else f"Kostnad {fee:.2f}%"


def build_cost_impact_table(
    fee_rows: Sequence[Mapping[str, Any]],
    *,
    start_amount: float = 100_000.0,
    monthly_saving: float = 2_000.0,
    annual_return_pct: float = 7.0,
    years: int = 20,
    baseline_fee_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Build cost-impact rows for actual fund fees or generic fee levels.

    `fee_rows` accepts mappings with `label`, `symbol` and `expense_ratio_pct`.
    The output is UI-ready and deterministic so tests can verify the math.
    """
    clean: List[Dict[str, Any]] = []
    for raw in fee_rows or []:
        fee = _safe_float(raw.get("expense_ratio_pct"), None)
        if fee is None or fee < 0:
            continue
        symbol = str(raw.get("symbol") or "").strip()
        label = str(raw.get("label") or raw.get("name") or _format_cost_label(symbol, fee)).strip()
        clean.append({
            "symbol": symbol,
            "label": label,
            "expense_ratio_pct": round(float(fee), 3),
        })

    if not clean:
        clean = [
            {"symbol": "", "label": f"Standard {fee:.2f}%", "expense_ratio_pct": float(fee)}
            for fee in DEFAULT_COST_IMPACT_FEES
        ]

    # Keep unique symbol+fee/label rows while preserving order.
    unique: List[Dict[str, Any]] = []
    seen = set()
    for row in clean:
        key = (row.get("symbol"), row.get("label"), row.get("expense_ratio_pct"))
        if key not in seen:
            unique.append(row)
            seen.add(key)

    fees = [float(r["expense_ratio_pct"]) for r in unique]
    baseline_fee = _safe_float(baseline_fee_pct, None)
    if baseline_fee is None:
        baseline_fee = min(fees) if fees else min(DEFAULT_COST_IMPACT_FEES)
    baseline_fee = max(0.0, float(baseline_fee))
    no_fee_value = future_value_after_costs(
        start_amount=start_amount,
        monthly_saving=monthly_saving,
        annual_return_pct=annual_return_pct,
        annual_fee_pct=0.0,
        years=years,
    )
    baseline_value = future_value_after_costs(
        start_amount=start_amount,
        monthly_saving=monthly_saving,
        annual_return_pct=annual_return_pct,
        annual_fee_pct=baseline_fee,
        years=years,
    )

    out_rows: List[Dict[str, Any]] = []
    for row in unique:
        fee = float(row["expense_ratio_pct"])
        ending = future_value_after_costs(
            start_amount=start_amount,
            monthly_saving=monthly_saving,
            annual_return_pct=annual_return_pct,
            annual_fee_pct=fee,
            years=years,
        )
        out_rows.append({
            "symbol": row.get("symbol") or "",
            "label": row.get("label") or _format_cost_label(row.get("symbol", ""), fee),
            "expense_ratio_pct": round(fee, 3),
            "ending_value": round(ending, 2),
            "vs_baseline": round(ending - baseline_value, 2),
            "cost_drag_vs_no_fee": round(no_fee_value - ending, 2),
            "baseline_fee_pct": round(baseline_fee, 3),
        })

    out_rows = sorted(out_rows, key=lambda r: (float(r.get("expense_ratio_pct") or 0.0), str(r.get("label") or "")))
    best = out_rows[0] if out_rows else {}
    worst = out_rows[-1] if out_rows else {}
    difference_best_worst = None
    if best and worst:
        difference_best_worst = round(float(best.get("ending_value") or 0.0) - float(worst.get("ending_value") or 0.0), 2)
    return {
        "version": get_app_version(),
        "created_at": _now_iso(),
        "start_amount": round(max(0.0, float(start_amount or 0.0)), 2),
        "monthly_saving": round(max(0.0, float(monthly_saving or 0.0)), 2),
        "annual_return_pct": round(float(annual_return_pct or 0.0), 3),
        "years": max(1, int(years or 1)),
        "baseline_fee_pct": round(baseline_fee, 3),
        "no_fee_value": no_fee_value,
        "baseline_value": baseline_value,
        "rows": out_rows,
        "summary": {
            "cheapest_label": best.get("label") if best else "",
            "highest_cost_label": worst.get("label") if worst else "",
            "difference_best_worst": difference_best_worst,
            "count": len(out_rows),
        },
    }


def build_fund_cost_impact(
    analysed_rows: Sequence[Mapping[str, Any]],
    *,
    start_amount: float = 100_000.0,
    monthly_saving: float = 2_000.0,
    annual_return_pct: float = 7.0,
    years: int = 20,
    include_standard_levels: bool = True,
) -> Dict[str, Any]:
    """Create a cost-impact scenario from analysed fund/ETF rows.

    Actual fund rows are used when expense ratios exist. Standard levels are
    added as reference points so users can see the long-term effect even when a
    data provider lacks expense data.
    """
    fee_rows: List[Dict[str, Any]] = []
    for row in analysed_rows or []:
        fee = _safe_float(row.get("expense_ratio_pct"), None)
        if fee is None:
            continue
        symbol = str(row.get("symbol") or "").strip()
        label = symbol or str(row.get("name") or "Fond")
        fee_rows.append({"symbol": symbol, "label": label, "expense_ratio_pct": fee})

    if include_standard_levels:
        for fee in DEFAULT_COST_IMPACT_FEES:
            fee_rows.append({"symbol": "", "label": f"Referanse {fee:.2f}%", "expense_ratio_pct": fee})

    return build_cost_impact_table(
        fee_rows,
        start_amount=start_amount,
        monthly_saving=monthly_saving,
        annual_return_pct=annual_return_pct,
        years=years,
    )



# v18.5.42: Hardened Fund Decision Quality --------------------------------------
FUND_DECISION_COMPONENT_LABELS = {
    "cost": "Kostnad",
    "return": "Avkastning",
    "risk": "Risiko",
    "benchmark": "Benchmark",
    "data": "Datakvalitet",
    "fit": "Rolle/egnethet",
    "cost_impact": "Kostnadseffekt over tid",
    "active_evidence": "Aktiv merverdi",
}


def _score_cost_impact(expense: Optional[float], fund_type: str) -> float:
    """Score long-term cost drag on a 0-100 scale.

    This is deliberately stricter than the simple cost score because a small fee
    difference compounds over decades. Active funds are allowed a higher fee only
    when the active evidence test later supports it.
    """
    if expense is None:
        return 52.0
    fee = max(0.0, float(expense))
    if fund_type in {"Indeksfond", "ETF"}:
        # 0.10-0.25% should score very highly; 1.50% should be a serious warning.
        return _clamp(100.0 - fee * 42.0, 5.0, 100.0)
    if fund_type == "Aktivt fond":
        return _clamp(92.0 - fee * 33.0, 5.0, 100.0)
    return _clamp(95.0 - fee * 38.0, 5.0, 100.0)


def _score_foundation_fit(*, fund_type: str, cost_score: float, benchmark_score: float, data_score: float, risk_score: float, fit_score: float) -> float:
    if fund_type not in {"Indeksfond", "ETF"}:
        return _clamp((fit_score * 0.30) + (data_score * 0.25) + (risk_score * 0.20) + (cost_score * 0.15) + (benchmark_score * 0.10) - 18.0)
    return _clamp((cost_score * 0.30) + (benchmark_score * 0.22) + (data_score * 0.20) + (risk_score * 0.18) + (fit_score * 0.10))


def _score_satellite_fit(*, fund_type: str, return_score: float, risk_score: float, benchmark_score: float, active_evidence: Mapping[str, Any]) -> float:
    evidence = _safe_float(active_evidence.get("score"), 58.0) or 58.0
    if fund_type == "Aktivt fond":
        return _clamp((evidence * 0.45) + (return_score * 0.25) + (risk_score * 0.20) + (benchmark_score * 0.10))
    return _clamp((return_score * 0.35) + (risk_score * 0.25) + (benchmark_score * 0.20) + 12.0)


def build_fund_decision_quality_profile(
    *,
    fund_type: str,
    objective: str,
    expense: Optional[float],
    total_return: Optional[float],
    benchmark_return: Optional[float],
    volatility: Optional[float],
    drawdown: Optional[float],
    cost_score: float,
    return_score: float,
    risk_score: float,
    benchmark_score: float,
    data_score: float,
    fit_score: float,
    active_evidence: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return a stricter, explainable Fund Decision Quality profile.

    v18.5.42 changes Fund Decision Quality from a single weighted number into a
    conservative decision profile. The profile keeps a numeric score, but also
    exposes component scores, role scores, reason codes and guardrails. This
    makes it easier for the UI to explain why a low-cost index fund can be a
    strong core holding and why an active fund must prove value after costs.
    """
    weights = OBJECTIVE_WEIGHTS.get(objective) or OBJECTIVE_WEIGHTS["Balansert"]
    base_quality = (
        cost_score * weights["cost"]
        + return_score * weights["return"]
        + risk_score * weights["risk"]
        + benchmark_score * weights["benchmark"]
        + data_score * weights["data"]
        + fit_score * weights["fit"]
    )
    cost_impact_score = _score_cost_impact(expense, fund_type)
    active_score = active_evidence.get("score") if fund_type == "Aktivt fond" else None
    active_score_num = _safe_float(active_score, 60.0) or 60.0
    risk_adjusted_quality = _clamp((return_score * 0.42) + (risk_score * 0.43) + (benchmark_score * 0.15))
    foundation_score = _score_foundation_fit(
        fund_type=fund_type,
        cost_score=cost_score,
        benchmark_score=benchmark_score,
        data_score=data_score,
        risk_score=risk_score,
        fit_score=fit_score,
    )
    satellite_score = _score_satellite_fit(
        fund_type=fund_type,
        return_score=return_score,
        risk_score=risk_score,
        benchmark_score=benchmark_score,
        active_evidence=active_evidence,
    )

    # Blend in the long-term fee effect and role quality without letting them
    # overpower the underlying risk/return/data scores.
    hardened = (base_quality * 0.72) + (cost_impact_score * 0.12) + (risk_adjusted_quality * 0.08) + (max(foundation_score, satellite_score) * 0.08)

    drivers: List[str] = []
    cautions: List[str] = []
    why_not_100: List[str] = []

    if cost_score >= 78 and cost_impact_score >= 78:
        drivers.append("lav kostnad og god kostnadseffekt over tid")
    elif expense is None:
        cautions.append("kostnad mangler")
        why_not_100.append("mangler kostnadsdata")
    else:
        cautions.append("kostnad trekker ned kvaliteten")
        why_not_100.append("kostnadseffekt over tid er ikke optimal")

    if return_score >= 68:
        drivers.append("god historisk avkastning i dataperioden")
    elif total_return is None:
        cautions.append("historisk avkastning mangler")
        why_not_100.append("mangler nok prisdata")
    else:
        why_not_100.append("avkastningen er ikke tydelig sterk")

    if risk_score >= 72:
        drivers.append("akseptabel risiko og drawdown")
    elif risk_score < 48:
        cautions.append("høy risiko eller drawdown")
        why_not_100.append("risiko/drawdown trekker ned")

    if benchmark_score >= 72:
        drivers.append("sterk benchmark-vurdering")
    elif benchmark_return is None:
        cautions.append("benchmark mangler")
        why_not_100.append("benchmark-data mangler")
    else:
        why_not_100.append("benchmark-gap eller tracking avviker")

    if data_score >= 70:
        drivers.append("god datakvalitet")
    elif data_score < 55:
        cautions.append("svak datakvalitet")
        why_not_100.append("datakvalitet er for svak")

    evidence_status = str(active_evidence.get("status") or "")
    if fund_type == "Aktivt fond":
        if evidence_status == "Godkjent" and active_score_num >= 68:
            drivers.append("aktiv merverdi er bevist mot benchmark")
        elif evidence_status == "Usikker":
            cautions.append("aktiv merverdi er usikker")
            why_not_100.append("aktiv merverdi er ikke stabil nok")
            hardened = min(hardened, 68.0)
        else:
            cautions.append("aktiv merverdi er ikke bevist")
            why_not_100.append("aktivt fond må bevise merverdi etter kostnader")
            hardened = min(hardened, 56.0)
        if expense is not None and expense > 1.20 and active_score_num < 75:
            cautions.append("høy aktiv kostnad uten sterk nok merverdi")
            hardened = min(hardened, 54.0)
    else:
        if foundation_score >= 70:
            drivers.append("egnet som mulig grunnmur")

    if data_score < 40:
        hardened = min(hardened, 52.0)
    if expense is not None and expense > 1.50 and fund_type != "Aktivt fond":
        hardened = min(hardened, 55.0)
        cautions.append("svært høy kostnad for indeks/ETF-kandidat")

    quality = round(_clamp(hardened), 1)
    if quality >= 78:
        grade = "Høy"
    elif quality >= 60:
        grade = "Middels"
    else:
        grade = "Lav"

    if fund_type == "Aktivt fond" and (evidence_status != "Godkjent" or active_score_num < 68):
        decision = "Krever mer bevis"
        recommended_role = "Krever mer bevis"
    elif quality >= 76 and foundation_score >= satellite_score and fund_type in {"Indeksfond", "ETF"}:
        decision = "God kandidat"
        recommended_role = "Grunnmur"
    elif quality >= 66:
        decision = "Kan vurderes"
        recommended_role = "Grunnmur" if foundation_score >= satellite_score and fund_type in {"Indeksfond", "ETF"} else "Satellitt"
    elif quality >= 54:
        decision = "Vurder videre"
        recommended_role = "Krever mer bevis"
    else:
        decision = "Vent / forkast"
        recommended_role = "Unngå"

    if not drivers:
        drivers.append("ingen tydelig hoveddriver funnet")
    if not why_not_100:
        why_not_100.append("ingen fond er risikofritt; score holdes konservativ")

    components = {
        "cost": round(cost_score, 1),
        "return": round(return_score, 1),
        "risk": round(risk_score, 1),
        "benchmark": round(benchmark_score, 1),
        "data": round(data_score, 1),
        "fit": round(fit_score, 1),
        "cost_impact": round(cost_impact_score, 1),
        "active_evidence": None if active_score is None else round(active_score_num, 1),
    }
    role_scores = {
        "grunnmur_score": round(foundation_score, 1),
        "satellitt_score": round(satellite_score, 1),
        "cost_efficiency_score": round(cost_impact_score, 1),
        "risk_adjusted_quality": round(risk_adjusted_quality, 1),
        "active_evidence_score": None if active_score is None else round(active_score_num, 1),
    }
    return {
        "decision_quality": quality,
        "grade": grade,
        "decision": decision,
        "recommended_role": recommended_role,
        "component_scores": components,
        "role_scores": role_scores,
        "drivers": drivers[:5],
        "cautions": cautions[:5],
        "why_not_100": why_not_100[:5],
        "summary": f"{grade} fondskvalitet · {decision} · rolle: {recommended_role}",
    }

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
    benchmark_volatility = _annualized_volatility(benchmark_prices)
    drawdown = _max_drawdown(prices)

    active_evidence = _active_evidence_test(
        fund_type=detected_type,
        total_return=total_return,
        benchmark_return=benchmark_return,
        expense=expense,
        volatility=volatility,
        benchmark_volatility=benchmark_volatility,
    )

    cost_score = _score_cost(expense, detected_type)
    return_score = _score_return(total_return)
    risk_score = _score_risk(volatility, drawdown)
    benchmark_score = _score_benchmark(total_return, benchmark_return, expense, detected_type)
    data_score = _score_data_quality(prices, expense, benchmark_return)
    fit_score = 86.0 if detected_type in {"Indeksfond", "ETF"} and objective in {"Grunnmur", "Lav kostnad", "Balansert"} else 68.0
    if detected_type == "Aktivt fond":
        evidence_score = _safe_float(active_evidence.get("score"), 35.0) or 35.0
        if benchmark_score < 55 or evidence_score < 52:
            fit_score -= 18.0
        elif evidence_score >= 68:
            fit_score += 6.0
    fit_score = _clamp(fit_score, 5.0, 100.0)

    quality_profile = build_fund_decision_quality_profile(
        fund_type=detected_type,
        objective=objective,
        expense=expense,
        total_return=total_return,
        benchmark_return=benchmark_return,
        volatility=volatility,
        drawdown=drawdown,
        cost_score=cost_score,
        return_score=return_score,
        risk_score=risk_score,
        benchmark_score=benchmark_score,
        data_score=data_score,
        fit_score=fit_score,
        active_evidence=active_evidence,
    )
    quality = float(quality_profile.get("decision_quality") or 0.0)
    grade = str(quality_profile.get("grade") or "Lav")

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
        if active_evidence.get("status") == "Godkjent":
            positives.append("aktiv merverdi bevist mot benchmark")
        elif active_evidence.get("status") == "Usikker":
            cautions.append("aktiv merverdi er usikker")
        else:
            cautions.append("aktiv merverdi ikke godt nok bevist")
    elif benchmark_score >= 70:
        positives.append("følger benchmark godt")
    if data_score < 55:
        cautions.append("svak datakvalitet")

    decision = str(quality_profile.get("decision") or "Vurder videre")
    # Keep older reason lists, but enrich them with the hardened profile so the
    # UI can explain Decision Quality without guessing.
    for reason in quality_profile.get("drivers") or []:
        if reason not in positives:
            positives.append(reason)
    for reason in quality_profile.get("cautions") or []:
        if reason not in cautions:
            cautions.append(reason)

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
        "benchmark_volatility_pct": None if benchmark_volatility is None else round(benchmark_volatility, 2),
        "max_drawdown_pct": None if drawdown is None else round(drawdown, 2),
        "cost_score": round(cost_score, 1),
        "return_score": round(return_score, 1),
        "risk_score": round(risk_score, 1),
        "benchmark_score": round(benchmark_score, 1),
        "data_quality": round(data_score, 1),
        "fit_score": round(fit_score, 1),
        "fund_decision_quality": quality_profile,
        "quality_breakdown": quality_profile.get("component_scores"),
        "role_scores": quality_profile.get("role_scores"),
        "recommended_role": quality_profile.get("recommended_role"),
        "quality_verdict": quality_profile.get("summary"),
        "why_not_100": quality_profile.get("why_not_100"),
        "active_evidence_status": active_evidence.get("status"),
        "active_evidence_score": active_evidence.get("score"),
        "active_evidence_message": active_evidence.get("message"),
        "active_evidence": active_evidence,
        "reasons_positive": positives[:4],
        "reasons_caution": cautions[:4],
        "data_points": len(prices),
        "version": get_app_version(),
        "created_at": _now_iso(),
    }




def build_fund_decision_quality_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build a UI-ready summary for hardened Fund Decision Quality."""
    valid = [dict(r) for r in (rows or []) if r]
    if not valid:
        return {
            "count": 0,
            "average_quality": None,
            "grade_counts": {},
            "role_counts": {},
            "decision_counts": {},
            "best_symbol": "",
            "rows": [],
            "warnings": ["Ingen fondskvalitet beregnet ennå."],
        }
    avg = round(sum(_safe_float(r.get("decision_quality"), 0.0) or 0.0 for r in valid) / max(1, len(valid)), 1)
    grade_counts: Dict[str, int] = {}
    role_counts: Dict[str, int] = {}
    decision_counts: Dict[str, int] = {}
    out_rows: List[Dict[str, Any]] = []
    for row in valid:
        grade = str(row.get("grade") or "Ukjent")
        role = str(row.get("recommended_role") or "Ukjent")
        decision = str(row.get("decision") or "Ukjent")
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
        role_counts[role] = role_counts.get(role, 0) + 1
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        profile = dict(row.get("fund_decision_quality") or {})
        out_rows.append({
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "fund_type": row.get("fund_type"),
            "decision_quality": row.get("decision_quality"),
            "grade": grade,
            "decision": decision,
            "recommended_role": role,
            "component_scores": row.get("quality_breakdown") or profile.get("component_scores") or {},
            "role_scores": row.get("role_scores") or profile.get("role_scores") or {},
            "drivers": profile.get("drivers") or row.get("reasons_positive") or [],
            "cautions": profile.get("cautions") or row.get("reasons_caution") or [],
            "why_not_100": row.get("why_not_100") or profile.get("why_not_100") or [],
        })
    out_rows = sorted(out_rows, key=lambda r: _safe_float(r.get("decision_quality"), 0.0) or 0.0, reverse=True)
    warnings = []
    if decision_counts.get("Krever mer bevis", 0):
        warnings.append("Noen fond krever mer bevis før de bør brukes i forslag.")
    if role_counts.get("Grunnmur", 0) == 0:
        warnings.append("Ingen tydelig grunnmur-kandidat funnet.")
    return {
        "count": len(valid),
        "average_quality": avg,
        "grade_counts": grade_counts,
        "role_counts": role_counts,
        "decision_counts": decision_counts,
        "best_symbol": out_rows[0].get("symbol") if out_rows else "",
        "rows": out_rows,
        "warnings": warnings,
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
    selection_info: Optional[Mapping[str, Any]] = None,
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
    comparator = build_fund_comparator(ranked)
    decision_quality_summary = build_fund_decision_quality_summary(ranked)
    core_satellite = build_core_satellite_portfolio(ranked, profile=objective, max_positions=min(max_funds, 8))
    cost_impact = build_fund_cost_impact(ranked)
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
        "selection": dict(selection_info or {}),
        "budget": budget,
        "completed_tests": completed,
        "total_tests": total_tests,
        "interrupted": interrupted,
        "summary": summary,
        "ranked": ranked,
        "index_candidates": index_candidates,
        "active_candidates": active_candidates,
        "needs_proof": needs_proof,
        "comparator": comparator,
        "decision_quality_summary": decision_quality_summary,
        "active_evidence": comparator.get("active_evidence", []),
        "core_satellite": core_satellite,
        "cost_impact": cost_impact,
        "errors": errors,
    }
