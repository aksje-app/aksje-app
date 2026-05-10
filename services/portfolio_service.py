from __future__ import annotations

from core_models import ServiceResult, PortfolioPosition
from services.state_service import get_state_service
from services.universe_service import _extract_tickers


def _ok(data=None, message: str = "", status: str = "ok") -> ServiceResult:
    return ServiceResult(ok=True, status=status, message=message, data=data if data is not None else {})


class PortfolioService:
    def __init__(self, state_service=None):
        self.state = state_service or get_state_service()

    def list_positions(self) -> ServiceResult:
        raw = self.state.get_first(["portfolio", "holdings", "positions"], {})
        tickers = _extract_tickers(raw)
        positions = [PortfolioPosition(ticker=t) for t in tickers]
        return _ok(positions)

    def tickers(self) -> ServiceResult:
        positions = self.list_positions().data or []
        return _ok([p.ticker for p in positions])


_default_portfolio_service = PortfolioService()


def get_portfolio_service(state_service=None) -> PortfolioService:
    if state_service is not None:
        return PortfolioService(state_service=state_service)
    return _default_portfolio_service
