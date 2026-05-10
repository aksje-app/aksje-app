from __future__ import annotations

from typing import Any, Dict, List
from core_models import ServiceResult, ForecastResult
from services.universe_service import get_universe_service, UniverseRequest


class ForecastService:
    def __init__(self, universe_service=None):
        self.universe = universe_service or get_universe_service()

    def universe_for_forecast(self, mode: str = "manual", market: str = "all", tickers: List[str] | None = None, limit: int = 10) -> ServiceResult:
        return self.universe.resolve(UniverseRequest(mode=mode, market=market, tickers=tickers or [], limit=limit))

    def normalize_result(self, payload: Dict[str, Any]) -> ServiceResult:
        try:
            summary = payload.get("summary", payload)
            item = ForecastResult(
                ticker=str(summary.get("ticker", payload.get("ticker", ""))).upper(),
                horizon=str(summary.get("horizon", "")),
                base_pct=float(summary.get("base_pct", 0)),
                bull_pct=float(summary.get("bull_pct", 0)),
                bear_pct=float(summary.get("bear_pct", 0)),
                confidence=float(summary.get("confidence", 0)),
                strength=float(summary.get("forecast_strength", summary.get("strength", 0))),
                risk=str(summary.get("risk", "")),
            )
            return ServiceResult(ok=True, data=item)
        except Exception as exc:
            return ServiceResult(ok=False, error=str(exc))


_default_forecast_service = ForecastService()

def get_forecast_service() -> ForecastService:
    return _default_forecast_service
