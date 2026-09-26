"""Quality Model v2 — shadow-only analytical layer.

This module may observe and compare quality evidence, but it must never create
BUY/SELL/HOLD decisions, alter V1.1 groups, send alerts, place orders, or mutate
portfolio state. Missing evidence is reported as NOT_DOCUMENTED.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Mapping, Sequence

MODEL_VERSION = "quality_v2@2.0-shadow"
MILESTONES = (10, 25, 50)


def _num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value == value and abs(value) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _series(values: Sequence[Any] | None, limit: int = 10) -> list[float]:
    out: list[float] = []
    for value in values or []:
        number = _num(value)
        if number is not None:
            out.append(number)
        if len(out) >= limit:
            break
    return out


def _trend(values: Sequence[float]) -> str:
    values = list(values)
    if len(values) < 3:
        return "NOT_DOCUMENTED"
    latest = values[0]
    older = median(values[1:min(len(values), 5)])
    delta = latest - older
    if delta >= 0.02:
        return "IMPROVING"
    if delta <= -0.02:
        return "WEAKENING"
    return "STABLE"


def _positive_ratio(values: Sequence[float]) -> float | None:
    values = list(values)
    if not values:
        return None
    return round(sum(1 for value in values if value > 0) / len(values), 3)


def _dispersion(values: Sequence[float]) -> float | None:
    values = list(values)
    if len(values) < 3:
        return None
    center = median(values)
    scale = abs(center)
    if scale < 1e-12:
        return None
    mad = median(abs(value - center) for value in values)
    return round(mad / scale, 3)


def evaluate_shadow(raw: Mapping[str, Any], v11: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate evidence without changing the active V1.1 result."""
    roce = _series(raw.get("roce_history"), 10)
    roe = _series(raw.get("roe_history"), 10)
    margins = _series(raw.get("operating_margin_history"), 10)
    is_financial = bool(raw.get("is_financial"))
    industry_text = (str(raw.get("industry") or "") + " " + str(raw.get("sector") or "")).lower()
    is_cyclical = any(word in industry_text for word in ("oil", "gas", "energy", "shipping", "marine", "metals", "mining", "steel", "commodity"))
    fcf = _series(raw.get("free_cash_flow_history"), 10)
    eps = _series(raw.get("annual_eps"), 10)
    latest_roce = roce[0] if roce else _num(raw.get("roce"))
    latest_roe = roe[0] if roe else None
    median_roe = median(roe[:5]) if len(roe) >= 3 else latest_roe
    roe_trend = _trend(roe)
    median_roce = median(roce[:5]) if len(roce) >= 3 else latest_roce
    roce_trend = _trend(roce)
    fcf_ratio = _positive_ratio(fcf)
    roce_dispersion = _dispersion(roce)
    eps_dispersion = _dispersion(eps)

    wacc = _num(raw.get("wacc"))
    roic_history = _series(raw.get("roic_history"), 10)
    roic = roic_history[0] if roic_history else _num(raw.get("roic"))
    roic_wacc_spread = (roic - wacc) if roic is not None and wacc is not None else None

    if is_financial:
        if len(roe) < 3:
            quality_band = "NOT_DOCUMENTED"
        elif median_roe is not None and median_roe >= 0.15:
            quality_band = "STRONG"
        elif roe_trend == "IMPROVING" and latest_roe is not None and latest_roe >= 0.12:
            quality_band = "IMPROVING"
        elif median_roe is not None and median_roe >= 0.10:
            quality_band = "STABLE_QUALITY"
        else:
            quality_band = "WATCH"
    elif len(roce) < 3:
        quality_band = "NOT_DOCUMENTED"
    elif median_roce is not None and median_roce >= 0.15 and (fcf_ratio is None or fcf_ratio >= 0.80):
        quality_band = "STRONG"
    elif roce_trend == "IMPROVING" and latest_roce is not None and latest_roce >= 0.12:
        quality_band = "IMPROVING"
    elif median_roce is not None and median_roce >= 0.12:
        quality_band = "STABLE_QUALITY"
    elif median_roce is not None and median_roce >= 0.09:
        quality_band = "WATCH"
    else:
        quality_band = "WEAK"

    if fcf_ratio is None:
        fcf_quality = "NOT_DOCUMENTED"
    elif fcf_ratio >= 0.80:
        fcf_quality = "CONSISTENT"
    elif fcf_ratio >= 0.60:
        fcf_quality = "MIXED"
    else:
        fcf_quality = "WEAK"

    # Structural moat claims require explicit evidence. Accounting persistence
    # alone is evidence of quality, not proof of a competitive moat.
    explicit_moat = raw.get("moat_evidence") if isinstance(raw.get("moat_evidence"), Mapping) else {}
    moat_dimensions = {
        key: value for key, value in explicit_moat.items()
        if key in {"cost_advantage", "intangibles", "switching_costs", "network_effect", "efficient_scale"}
        and value not in (None, "", False)
    }
    moat_evidence = "DOCUMENTED" if moat_dimensions else "NOT_DOCUMENTED"

    cyclical_normalization = "NOT_APPLICABLE"
    if is_cyclical:
        if len(margins) < 3 or len(fcf) < 3:
            cyclical_normalization = "NOT_DOCUMENTED"
        else:
            margin_trend = _trend(margins)
            fcf_trend = _trend(fcf)
            cyclical_normalization = "CYCLE_PEAK_RISK" if margin_trend == "WEAKENING" or fcf_trend == "WEAKENING" else "MULTI_PERIOD_AVAILABLE"

    reasons: list[str] = []
    if is_financial:
        reasons.append("Finanssektor vurderes med flerårig ROE-evidens; industriell ROCE brukes ikke.")
    if cyclical_normalization == "CYCLE_PEAK_RISK":
        reasons.append("Syklisk normalisering flagger mulig toppnivå: margin/FCF svekkes mot flerårig historikk.")
    elif cyclical_normalization == "NOT_DOCUMENTED":
        reasons.append("Syklisk normalisering mangler minst tre sammenlignbare perioder med margin og FCF.")
    active_state = str(v11.get("quality_state") or "")
    if quality_band in {"STRONG", "IMPROVING", "STABLE_QUALITY"} and active_state in {"WEAK", "INSUFFICIENT"}:
        reasons.append("V2 ser sterkere eller forbedrende kapitalavkastning enn aktiv V1.1-status.")
    if roce_trend == "WEAKENING":
        reasons.append("Nyeste kapitalavkastning er klart svakere enn nyere historikk.")
    if fcf_quality == "WEAK":
        reasons.append("Fri kontantstrøm er ustabil eller ofte negativ.")
    if moat_evidence == "NOT_DOCUMENTED":
        reasons.append("Strukturell moat er ikke dokumentert; regnskapstall alene brukes ikke som moat-bevis.")
    if roic_wacc_spread is None:
        reasons.append("ROIC-WACC kan ikke beregnes uten eksplisitt ROIC- og WACC-grunnlag.")

    return {
        "ticker": str(v11.get("ticker") or raw.get("ticker") or ""),
        "model_version": MODEL_VERSION,
        "shadow_only": True,
        "production_effect": False,
        "quality_band": quality_band,
        "sector_policy": "FINANCIAL_ROE" if is_financial else "INDUSTRIAL_CAPITAL_RETURN",
        "roe_latest_pct": round(latest_roe * 100, 2) if latest_roe is not None else None,
        "roe_median_pct": round(median_roe * 100, 2) if median_roe is not None else None,
        "roe_trend": roe_trend,
        "cyclical": is_cyclical,
        "cyclical_normalization": cyclical_normalization,
        "roce_latest_pct": round(latest_roce * 100, 2) if latest_roce is not None else None,
        "roce_median_pct": round(median_roce * 100, 2) if median_roce is not None else None,
        "roce_trend": roce_trend,
        "roce_dispersion": roce_dispersion,
        "eps_dispersion": eps_dispersion,
        "fcf_positive_ratio": fcf_ratio,
        "fcf_quality": fcf_quality,
        "roic_pct": round(roic * 100, 2) if roic is not None else None,
        "wacc_pct": round(wacc * 100, 2) if wacc is not None else None,
        "roic_minus_wacc_pct_points": round(roic_wacc_spread * 100, 2) if roic_wacc_spread is not None else None,
        "moat_evidence": moat_evidence,
        "moat_dimensions": moat_dimensions,
        "active_v11_group": v11.get("group"),
        "active_v11_quality_state": active_state,
        "reasons": reasons,
    }


def summarize_shadow(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = [dict(row) for row in rows]
    disagreements = [
        row for row in items
        if row.get("reasons") and any("V2 ser sterkere" in reason or "svakere" in reason for reason in row.get("reasons") or [])
    ]
    try:
        from quality_v2_benchmark import compare_reference
        benchmark = compare_reference(items)
    except Exception:
        benchmark = {"production_effect": False, "state": "UNAVAILABLE"}
    return {
        "model_version": MODEL_VERSION,
        "shadow_only": True,
        "production_effect": False,
        "evaluated": len(items),
        "disagreement_count": len(disagreements),
        "strong_or_improving": sum(1 for row in items if row.get("quality_band") in {"STRONG", "IMPROVING"}),
        "weakening_count": sum(1 for row in items if row.get("roce_trend") == "WEAKENING"),
        "moat_documented_count": sum(1 for row in items if row.get("moat_evidence") == "DOCUMENTED"),
        "benchmark": benchmark,
        "rows": items,
    }
