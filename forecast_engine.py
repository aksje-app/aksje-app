"""
forecast_engine.py

Bygg 1: Datagrunnlag + enkel prognosemotor.

Dette er en isolert motor uten UI-endringer. Den lager teoretiske scenarioer
for én aksje basert på historiske priser, trend, volatilitet og valgfrie
score-inputs.

Viktig:
- Dette er scenarioanalyse, ikke fasit.
- Ingen auto-trading-kobling i Bygg 1.
- UI-integrasjon kommer i senere bygg.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from math import exp, log, sqrt
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SUPPORTED_HORIZONS: Dict[str, int] = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
}


@dataclass(frozen=True)
class ForecastPoint:
    step: int
    date_label: str
    bear: float
    base: float
    bull: float
    lower_band: float
    upper_band: float


@dataclass(frozen=True)
class ForecastSummary:
    ticker: str
    horizon: str
    days: int
    current_price: float
    base_price: float
    bull_price: float
    bear_price: float
    base_pct: float
    bull_pct: float
    bear_pct: float
    confidence: int
    risk: str
    trend_score: float
    volatility_annual: float
    explanation: str


@dataclass(frozen=True)
class ForecastResult:
    ticker: str
    generated_at: str
    summary: ForecastSummary
    points: List[ForecastPoint]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "generated_at": self.generated_at,
            "summary": asdict(self.summary),
            "points": [asdict(p) for p in self.points],
            "warnings": list(self.warnings),
        }


def _clean_prices(prices: Sequence[float]) -> List[float]:
    cleaned: List[float] = []
    for value in prices:
        try:
            f = float(value)
            if f > 0:
                cleaned.append(f)
        except Exception:
            continue
    return cleaned


def _daily_returns(prices: Sequence[float]) -> List[float]:
    values = _clean_prices(prices)
    returns: List[float] = []
    for prev, cur in zip(values[:-1], values[1:]):
        if prev > 0 and cur > 0:
            returns.append(log(cur / prev))
    return returns


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _risk_from_vol(vol_annual: float) -> str:
    if vol_annual < 0.22:
        return "Lav"
    if vol_annual < 0.45:
        return "Medium"
    return "Høy"


def _confidence_score(
    sample_size: int,
    vol_annual: float,
    trend_strength: float,
    ai_score: Optional[float] = None,
    sentiment_score: Optional[float] = None,
) -> int:
    # Start moderat. Øk med datamengde/trend, trekk for høy volatilitet.
    score = 48.0
    score += _clamp(sample_size / 220.0, 0.0, 1.0) * 18.0
    score += _clamp(abs(trend_strength) * 100.0, 0.0, 12.0)
    score -= _clamp(vol_annual * 20.0, 0.0, 18.0)

    if ai_score is not None:
        # ai_score forventes ca 0-100
        score += (_clamp(float(ai_score), 0.0, 100.0) - 50.0) * 0.12
    if sentiment_score is not None:
        # sentiment forventes -1 til +1
        score += _clamp(float(sentiment_score), -1.0, 1.0) * 6.0

    return int(round(_clamp(score, 15.0, 92.0)))


def _explanation(
    trend_strength: float,
    vol_annual: float,
    confidence: int,
    risk: str,
    ai_score: Optional[float],
    sentiment_score: Optional[float],
) -> str:
    if trend_strength > 0.002:
        trend_txt = "positiv trend"
    elif trend_strength < -0.002:
        trend_txt = "negativ trend"
    else:
        trend_txt = "sideveis trend"

    parts = [
        f"Scenarioet bygger på {trend_txt}, historisk volatilitet og siste prisutvikling.",
        f"Risiko vurderes som {risk.lower()} med annualisert volatilitet på ca. {vol_annual:.1%}.",
        f"Confidence er {confidence}%."
    ]
    if ai_score is not None:
        parts.append(f"AI-score er tatt med som justering ({float(ai_score):.0f}/100).")
    if sentiment_score is not None:
        parts.append(f"Sentiment er tatt med som justering ({float(sentiment_score):+.2f}).")
    parts.append("Dette er teoretiske scenarioer, ikke en garanti for fremtidig kurs.")
    return " ".join(parts)


def build_forecast(
    ticker: str,
    prices: Sequence[float],
    horizon: str = "1m",
    *,
    ai_score: Optional[float] = None,
    sentiment_score: Optional[float] = None,
    start_date: Optional[datetime] = None,
) -> ForecastResult:
    """Lag bull/base/bear-scenario for én aksje.

    Args:
        ticker: Symbol/navn.
        prices: Historiske sluttkurser i stigende datoorden.
        horizon: En av 1d, 1w, 1m, 3m, 6m.
        ai_score: Valgfri score 0-100.
        sentiment_score: Valgfri score -1 til +1.
        start_date: Valgfri startdato for punktene.

    Returns:
        ForecastResult med summary og grafpunkter.
    """
    if horizon not in SUPPORTED_HORIZONS:
        raise ValueError(f"Ukjent horisont: {horizon}. Bruk en av {list(SUPPORTED_HORIZONS)}")

    clean = _clean_prices(prices)
    if len(clean) < 30:
        raise ValueError("Trenger minst 30 gyldige prisobservasjoner for enkel prognose.")

    returns = _daily_returns(clean)
    current = clean[-1]
    days = SUPPORTED_HORIZONS[horizon]
    warnings: List[str] = []

    lookback = min(63, len(returns))
    recent_returns = returns[-lookback:] if lookback > 0 else returns

    drift_daily = mean(recent_returns) if recent_returns else 0.0
    vol_daily = pstdev(recent_returns) if len(recent_returns) >= 2 else 0.0
    vol_annual = vol_daily * sqrt(252)

    # Juster drift moderat med AI-score og sentiment. Små justeringer for å unngå overfitting.
    drift_adjust = 0.0
    if ai_score is not None:
        drift_adjust += (_clamp(float(ai_score), 0.0, 100.0) - 50.0) / 100.0 * 0.0008
    if sentiment_score is not None:
        drift_adjust += _clamp(float(sentiment_score), -1.0, 1.0) * 0.0006

    adjusted_drift = drift_daily + drift_adjust

    if len(clean) < 90:
        warnings.append("Kort historikk: confidence kan være lavere.")
    if vol_annual > 0.65:
        warnings.append("Høy volatilitet: scenarioene har stor usikkerhet.")

    confidence = _confidence_score(
        sample_size=len(clean),
        vol_annual=vol_annual,
        trend_strength=adjusted_drift,
        ai_score=ai_score,
        sentiment_score=sentiment_score,
    )
    risk = _risk_from_vol(vol_annual)

    # Scenario-spread: volatilitetsskalert. Bull/bear går ca +/- 0.8 sigma fra base i v1.
    scenario_sigma = vol_daily * sqrt(days)
    bull_terminal = current * exp(adjusted_drift * days + 0.80 * scenario_sigma)
    base_terminal = current * exp(adjusted_drift * days)
    bear_terminal = current * exp(adjusted_drift * days - 0.80 * scenario_sigma)

    # Usikkerhetsbånd litt bredere enn bull/bear.
    band_sigma = 1.25

    start = start_date or datetime.utcnow()
    points: List[ForecastPoint] = []
    for step in range(0, days + 1):
        frac = step / days if days else 1.0
        sigma_step = vol_daily * sqrt(max(step, 0))
        base = current * exp(adjusted_drift * step)
        bull = current * exp(adjusted_drift * step + 0.80 * sigma_step)
        bear = current * exp(adjusted_drift * step - 0.80 * sigma_step)
        lower = current * exp(adjusted_drift * step - band_sigma * sigma_step)
        upper = current * exp(adjusted_drift * step + band_sigma * sigma_step)
        date_label = (start + timedelta(days=step)).strftime("%Y-%m-%d")
        points.append(
            ForecastPoint(
                step=step,
                date_label=date_label,
                bear=round(bear, 4),
                base=round(base, 4),
                bull=round(bull, 4),
                lower_band=round(lower, 4),
                upper_band=round(upper, 4),
            )
        )

    summary = ForecastSummary(
        ticker=ticker.upper(),
        horizon=horizon,
        days=days,
        current_price=round(current, 4),
        base_price=round(base_terminal, 4),
        bull_price=round(bull_terminal, 4),
        bear_price=round(bear_terminal, 4),
        base_pct=round((base_terminal / current - 1.0) * 100.0, 2),
        bull_pct=round((bull_terminal / current - 1.0) * 100.0, 2),
        bear_pct=round((bear_terminal / current - 1.0) * 100.0, 2),
        confidence=confidence,
        risk=risk,
        trend_score=round(adjusted_drift * 100.0, 4),
        volatility_annual=round(vol_annual, 4),
        explanation=_explanation(adjusted_drift, vol_annual, confidence, risk, ai_score, sentiment_score),
    )

    return ForecastResult(
        ticker=ticker.upper(),
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        summary=summary,
        points=points,
        warnings=warnings,
    )


def build_all_horizons(
    ticker: str,
    prices: Sequence[float],
    *,
    ai_score: Optional[float] = None,
    sentiment_score: Optional[float] = None,
) -> Dict[str, Dict[str, Any]]:
    """Lag prognose for alle støttede horisonter."""
    return {
        horizon: build_forecast(
            ticker,
            prices,
            horizon,
            ai_score=ai_score,
            sentiment_score=sentiment_score,
        ).to_dict()
        for horizon in SUPPORTED_HORIZONS
    }
