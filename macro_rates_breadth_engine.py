"""
macro_rates_breadth_engine.py

v18.4.4 Macro/Rates/Breadth Engine

Legger til makro-, rente- og breadth-vurdering som støtte til markedsregime.
Ingen auto-trading-kobling.

Første versjon bruker proxyer:
- ^TNX  : US 10Y yield
- UUP   : dollar-proxy
- USO   : olje-proxy
- ^VIX  : volatilitet/frykt
- SPY/QQQ/IWM/DIA breadth-proxy
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class MacroRatesBreadthResult:
    macro_score: int
    rate_score: int
    breadth_score: int
    risk_score: int
    combined_score: int
    label: str
    risk_level: str
    explanation: str
    components: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clean(values: Sequence[float]) -> List[float]:
    out: List[float] = []
    for v in values:
        try:
            f = float(v)
            if f > 0:
                out.append(f)
        except Exception:
            continue
    return out


def _pct(values: Sequence[float], lookback: int) -> float:
    p = _clean(values)
    if len(p) <= lookback:
        return 0.0
    return (p[-1] / p[-lookback - 1] - 1.0) * 100.0


def _last(values: Sequence[float]) -> Optional[float]:
    p = _clean(values)
    return p[-1] if p else None


def _clamp_int(value: float, low: int = 0, high: int = 100) -> int:
    return int(round(max(low, min(high, value))))


def analyze_macro_rates_breadth(
    *,
    spy_prices: Sequence[float],
    qqq_prices: Optional[Sequence[float]] = None,
    iwm_prices: Optional[Sequence[float]] = None,
    dia_prices: Optional[Sequence[float]] = None,
    tnx_prices: Optional[Sequence[float]] = None,
    dollar_prices: Optional[Sequence[float]] = None,
    oil_prices: Optional[Sequence[float]] = None,
    vix_prices: Optional[Sequence[float]] = None,
) -> MacroRatesBreadthResult:
    """Analyze macro/rates/breadth proxies."""
    spy_1m = _pct(spy_prices, 21)
    qqq_1m = _pct(qqq_prices or spy_prices, 21)
    iwm_1m = _pct(iwm_prices or spy_prices, 21)
    dia_1m = _pct(dia_prices or spy_prices, 21)

    tnx_1m = _pct(tnx_prices or [], 21)
    dollar_1m = _pct(dollar_prices or [], 21)
    oil_1m = _pct(oil_prices or [], 21)
    vix_1m = _pct(vix_prices or [], 21)
    vix_last = _last(vix_prices or [])

    # Breadth proxy: how many major ETFs are positive over 1m.
    breadth_count = sum(1 for x in [spy_1m, qqq_1m, iwm_1m, dia_1m] if x > 0)
    breadth_score = _clamp_int(25 + breadth_count * 18 + max(-10, min(10, (spy_1m + qqq_1m) / 2)))

    # Rate score: falling/flat rates are easier; rising yields pressure growth assets.
    rate_score = 50.0
    if tnx_prices:
        rate_score -= max(-18.0, min(18.0, tnx_1m * 1.5))
    if dollar_prices:
        rate_score -= max(-10.0, min(10.0, dollar_1m * 1.2))
    rate_score = _clamp_int(rate_score)

    # Macro score: combines dollar/oil stability and equity momentum.
    macro_score = 50.0
    macro_score += max(-15.0, min(15.0, spy_1m * 1.2))
    macro_score += max(-10.0, min(10.0, qqq_1m * 0.8))
    if oil_prices and abs(oil_1m) > 12:
        macro_score -= 6
    if dollar_prices and dollar_1m > 4:
        macro_score -= 5
    macro_score = _clamp_int(macro_score)

    # Risk score: higher is more risk.
    risk_score = 30.0
    if vix_last is not None:
        if vix_last >= 35:
            risk_score += 40
        elif vix_last >= 28:
            risk_score += 28
        elif vix_last >= 22:
            risk_score += 16
        elif vix_last <= 15:
            risk_score -= 8
    if vix_1m > 20:
        risk_score += 10
    if tnx_prices and tnx_1m > 8:
        risk_score += 8
    if breadth_count <= 1:
        risk_score += 12
    risk_score = _clamp_int(risk_score)

    combined = _clamp_int(macro_score * 0.35 + rate_score * 0.25 + breadth_score * 0.30 + (100 - risk_score) * 0.10)

    if combined >= 70 and risk_score < 45:
        label = "Makro støtter risk-on"
        risk_level = "Lav/Medium"
    elif combined <= 40 or risk_score >= 70:
        label = "Makro/renter gir høy risiko"
        risk_level = "Høy"
    else:
        label = "Blandet makrobilde"
        risk_level = "Medium"

    explanation = (
        f"{label}. Breadth {breadth_count}/4 positive, SPY 1m {spy_1m:+.1f}%, "
        f"QQQ 1m {qqq_1m:+.1f}%, renteproxy 1m {tnx_1m:+.1f}%, "
        f"dollar 1m {dollar_1m:+.1f}%."
    )
    if vix_last is not None:
        explanation += f" VIX {vix_last:.1f}."

    return MacroRatesBreadthResult(
        macro_score=macro_score,
        rate_score=rate_score,
        breadth_score=breadth_score,
        risk_score=risk_score,
        combined_score=combined,
        label=label,
        risk_level=risk_level,
        explanation=explanation,
        components={
            "spy_1m_pct": round(spy_1m, 2),
            "qqq_1m_pct": round(qqq_1m, 2),
            "iwm_1m_pct": round(iwm_1m, 2),
            "dia_1m_pct": round(dia_1m, 2),
            "breadth_positive_count": breadth_count,
            "tnx_1m_pct": round(tnx_1m, 2),
            "dollar_1m_pct": round(dollar_1m, 2),
            "oil_1m_pct": round(oil_1m, 2),
            "vix_1m_pct": round(vix_1m, 2),
            "vix_level": round(vix_last, 2) if vix_last is not None else None,
        },
    )


def macro_adjustment_for_forecast(result: MacroRatesBreadthResult) -> Dict[str, Any]:
    """Map macro result to forecast adjustments."""
    if result.combined_score >= 70 and result.risk_score < 45:
        return {"market_regime_bias": "bull", "event_risk": False, "confidence_adjustment": 4}
    if result.combined_score <= 40 or result.risk_score >= 70:
        return {"market_regime_bias": "volatile", "event_risk": True, "confidence_adjustment": -8}
    return {"market_regime_bias": "neutral", "event_risk": False, "confidence_adjustment": 0}
