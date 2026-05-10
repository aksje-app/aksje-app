from __future__ import annotations

from core_models import ServiceResult, PaperTradePosition
from services.state_service import get_state_service
from services.universe_service import _extract_tickers


class PaperTradingService:
    def __init__(self, state_service=None):
        self.state = state_service or get_state_service()

    def list_positions(self) -> ServiceResult:
        raw = self.state.get_first(["paper_portfolio", "paper_positions", "paper_trading_positions"], {})
        tickers = _extract_tickers(raw)
        positions = [PaperTradePosition(ticker=t) for t in tickers]
        return ServiceResult(ok=True, data=positions)

    def tickers(self) -> ServiceResult:
        positions = self.list_positions().data or []
        return ServiceResult(ok=True, data=[p.ticker for p in positions])


_default_paper_service = PaperTradingService()

def get_paper_trading_service() -> PaperTradingService:
    return _default_paper_service
