from __future__ import annotations

from typing import Any, List
from core_models import ServiceResult, WatchlistItem
from services.state_service import get_state_service
from services.universe_service import _extract_tickers


class WatchlistService:
    def __init__(self, state_service=None):
        self.state = state_service or get_state_service()

    def list_items(self) -> ServiceResult:
        tickers = _extract_tickers(self.state.get_first(["watchlist", "watchlist_items"], []))
        items = [WatchlistItem(ticker=t) for t in tickers]
        return ServiceResult(ok=True, data=items)

    def add(self, ticker: str) -> ServiceResult:
        ticker = str(ticker).strip().upper()
        current = _extract_tickers(self.state.get("watchlist", []))
        if ticker and ticker not in current:
            current.append(ticker)
        self.state.set("watchlist", current)
        return ServiceResult(ok=True, data=current)


_default_watchlist_service = WatchlistService()

def get_watchlist_service() -> WatchlistService:
    return _default_watchlist_service
