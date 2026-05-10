from __future__ import annotations

from core_models import ServiceResult, PaperTradePosition
from services.state_service import get_state_service
from services.universe_service import _extract_tickers


def _ok(data=None, message: str = "", status: str = "ok") -> ServiceResult:
    return ServiceResult(ok=True, status=status, message=message, data=data if data is not None else {})


class PaperTradingService:
    def __init__(self, state_service=None):
        self.state = state_service or get_state_service()

    def _raw_positions(self):
        raw = self.state.get_first(["paper_portfolio", "paper_positions", "paper_trading_positions"], {})
        if raw:
            return raw
        try:
            from paper_store import load_portfolio
            return (load_portfolio() or {}).get("positions", {})
        except Exception:
            return {}

    def list_positions(self) -> ServiceResult:
        tickers = _extract_tickers(self._raw_positions())
        positions = [PaperTradePosition(ticker=t) for t in tickers]
        return _ok(positions)

    def tickers(self) -> ServiceResult:
        positions = self.list_positions().data or []
        return _ok([p.ticker for p in positions])


_default_paper_service = PaperTradingService()


def get_paper_trading_service(state_service=None) -> PaperTradingService:
    if state_service is not None:
        return PaperTradingService(state_service=state_service)
    return _default_paper_service
