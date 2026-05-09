"""
market_regime_engine.py

v18.4.0 Market Regime Engine

Automatisk markedsregime-deteksjon basert på prisdata for brede markedsproxyer.
Ingen auto-trading-kobling.

Regimer:
- bull
- neutral
- bear
- stress

Første versjon bruker:
- SPY trend/momentum/drawdown/volatilitet
- QQQ trend/momentum
- VIX nivå/endring hvis tilgjengelig
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import log, sqrt
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class MarketRegimeResult:
    regime: str
    label: str
    score: int
    confidence: int
    risk_level: str
    spy_trend_pct: float
    qqq_trend_pct: float
    spy_drawdown_pct: float
    volatility_annual: float
    vix_level: Optional[float]
    explanation: str
    components: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clean_prices(values: Sequence[float]) -> List[float]:
    out: List[float] = []
    for v in values:
        try:
            f = float(v)
            if f > 0:
                out.append(f)
        except Exception:
            continue
    return out


def _returns(values: Sequence[float]) -> List[float]:
    p = _clean_prices(values)
    out: List[float] = []
    for a, b in zip(p[:-1], p[1:]):
        if a > 0 and b > 0:
            out.append(log(b / a))
    return out


def _pct_change(values: Sequence[float], lookback: int) -> float:
    p = _clean_prices(values)
    if len(p) <= lookback:
        return 0.0
    return (p[-1] / p[-lookback - 1] - 1.0) * 100.0


def _drawdown(values: Sequence[float], lookback: int = 63) -> float:
    p = _clean_prices(values)
    if not p:
        return 0.0
    p = p[-lookback:]
    peak = max(p)
    if peak <= 0:
        return 0.0
    return (p[-1] / peak - 1.0) * 100.0


def _annual_vol(values: Sequence[float], lookback: int = 63) -> float:
    r = _returns(values)
    r = r[-lookback:]
    if len(r) < 2:
        return 0.0
    return pstdev(r) * sqrt(252)


def detect_market_regime(
    spy_prices: Sequence[float],
    qqq_prices: Optional[Sequence[float]] = None,
    vix_prices: Optional[Sequence[float]] = None,
) -> MarketRegimeResult:
    """Detect market regime from broad-market proxy prices."""
    spy = _clean_prices(spy_prices)
    qqq = _clean_prices(qqq_prices or spy_prices)
    vix = _clean_prices(vix_prices or [])

    if len(spy) < 40:
        raise ValueError("Trenger minst 40 SPY/markedspris-observasjoner for regime-deteksjon.")

    spy_1m = _pct_change(spy, 21)
    spy_3m = _pct_change(spy, 63)
    qqq_1m = _pct_change(qqq, 21)
    qqq_3m = _pct_change(qqq, 63)
    dd = _drawdown(spy, 63)
    vol = _annual_vol(spy, 63)
    vix_level = vix[-1] if vix else None
    vix_1m = _pct_change(vix, 21) if len(vix) > 22 else 0.0

    score = 50.0

    # Trend/momentum
    score += max(-18.0, min(18.0, spy_3m * 1.2))
    score += max(-10.0, min(10.0, spy_1m * 1.0))
    score += max(-10.0, min(10.0, qqq_1m * 0.8))

    # Drawdown and volatility penalties
    score += max(-20.0, min(0.0, dd * 1.4))
    score -= max(0.0, min(16.0, vol * 22.0))

    # VIX
    if vix_level is not None:
        if vix_level >= 35:
            score -= 22
        elif vix_level >= 28:
            score -= 14
        elif vix_level >= 22:
            score -= 7
        elif vix_level <= 15:
            score += 5
        if vix_1m > 20:
            score -= 6

    score_i = int(round(max(0, min(100, score))))

    # Classification
    if (vix_level is not None and vix_level >= 32) or dd <= -10 or (vol >= 0.35 and spy_1m < -4):
        regime = "stress"
        label = "Stress / Panic"
        risk = "Høy"
    elif score_i >= 62 and spy_1m > 0 and spy_3m > 0:
        regime = "bull"
        label = "Bull / Risk-On"
        risk = "Lav" if vol < 0.22 else "Medium"
    elif score_i <= 38 or spy_3m < -5:
        regime = "bear"
        label = "Bear / Risk-Off"
        risk = "Høy" if vol >= 0.28 or dd <= -6 else "Medium"
    else:
        regime = "neutral"
        label = "Nøytral / Sideways"
        risk = "Medium"

    # Confidence in regime classification
    confidence = 50
    confidence += min(20, abs(score_i - 50) // 2)
    if len(spy) >= 120:
        confidence += 10
    if vix_level is not None:
        confidence += 8
    if abs(spy_1m) > 3 or abs(spy_3m) > 6:
        confidence += 7
    confidence = int(max(20, min(95, confidence)))

    explanation = (
        f"Regime: {label}. SPY 1m {spy_1m:+.1f}%, SPY 3m {spy_3m:+.1f}%, "
        f"QQQ 1m {qqq_1m:+.1f}%, drawdown {dd:.1f}%, vol {vol:.1%}."
    )
    if vix_level is not None:
        explanation += f" VIX {vix_level:.1f}."

    return MarketRegimeResult(
        regime=regime,
        label=label,
        score=score_i,
        confidence=confidence,
        risk_level=risk,
        spy_trend_pct=round(spy_3m, 2),
        qqq_trend_pct=round(qqq_3m, 2),
        spy_drawdown_pct=round(dd, 2),
        volatility_annual=round(vol, 4),
        vix_level=round(vix_level, 2) if vix_level is not None else None,
        explanation=explanation,
        components={
            "spy_1m_pct": round(spy_1m, 2),
            "spy_3m_pct": round(spy_3m, 2),
            "qqq_1m_pct": round(qqq_1m, 2),
            "qqq_3m_pct": round(qqq_3m, 2),
            "vix_1m_pct": round(vix_1m, 2),
        },
    )


def regime_to_forecast_inputs(result: MarketRegimeResult) -> Dict[str, Any]:
    """Map regime result to existing forecast_engine inputs."""
    market_regime = "neutral"
    event_risk = False

    if result.regime == "bull":
        market_regime = "bull"
    elif result.regime == "bear":
        market_regime = "bear"
    elif result.regime == "stress":
        market_regime = "volatile"
        event_risk = True
    elif result.regime == "neutral":
        market_regime = "neutral"

    return {
        "market_regime": market_regime,
        "event_risk": event_risk,
        "regime_score": result.score,
        "regime_confidence": result.confidence,
        "risk_level": result.risk_level,
    }
