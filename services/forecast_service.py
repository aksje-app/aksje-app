from __future__ import annotations

from typing import Any, Dict, List

from core_models import ForecastResult, ServiceResult
from services.universe_service import get_universe_service


def _ok(data: Any = None, message: str = "", status: str = "ok") -> ServiceResult:
    return ServiceResult(ok=True, status=status, message=message, data=data if data is not None else {})


def _fail(message: str, status: str = "error") -> ServiceResult:
    return ServiceResult(ok=False, status=status, message=message, data={}, errors=[{"error": message}])


class ForecastService:
    def __init__(self, universe_service=None):
        self.universe = universe_service or get_universe_service()

    def universe_for_forecast(self, mode: str = "manual", market: str = "all", tickers: List[str] | None = None, limit: int = 10) -> ServiceResult:
        scopes = ["Alle"] if market == "all" else [market]
        config = {
            "mode": mode,
            "scopes": scopes,
            "max_count": limit,
            "metadata": {"manual_list": tickers or []},
        }
        return self.universe.resolve(config)

    def normalize_result(self, payload: Dict[str, Any]) -> ServiceResult:
        try:
            summary = payload.get("summary", payload)
            item = ForecastResult(
                ticker=str(summary.get("ticker", payload.get("ticker", ""))).upper(),
                horizon=str(summary.get("horizon", "")),
                base_price=float(summary.get("base_price", 0) or 0),
                confidence=float(summary.get("confidence", 0) or 0),
                risk=str(summary.get("risk", "")),
                payload=dict(payload or {}),
            )
            return _ok(item)
        except Exception as exc:
            return _fail(str(exc))


_default_forecast_service = ForecastService()


def get_forecast_service(universe_service=None) -> ForecastService:
    if universe_service is not None:
        return ForecastService(universe_service=universe_service)
    return _default_forecast_service
