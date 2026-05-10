from __future__ import annotations

from typing import Any, List, Mapping

from core_models import ServiceResult, WatchlistItem, normalize_ticker
from services.state_service import get_state_service
from services.storage_service import get_storage_service
from services.universe_service import _extract_tickers


def _ok(data: Any = None, message: str = "", status: str = "ok") -> ServiceResult:
    return ServiceResult(ok=True, status=status, message=message, data=data if data is not None else {})


class WatchlistService:
    def __init__(self, state_service=None, storage_service=None):
        self.state = state_service or get_state_service()
        self.storage = storage_service or get_storage_service()

    def _load_tickers(self) -> List[str]:
        tickers = _extract_tickers(self.state.get_first(["latest_watchlist_tickers_v156", "watchlist", "watchlist_items"], []))
        if not tickers:
            stored = self.storage.read_json("watchlist.json", default=[])
            tickers = _extract_tickers(stored)
        return tickers

    def _save_tickers(self, tickers: List[str]) -> None:
        clean: List[str] = []
        for ticker in tickers:
            t = normalize_ticker(ticker)
            if t and t not in clean:
                clean.append(t)
        self.state.set("latest_watchlist_tickers_v156", clean)
        self.state.set("watchlist", clean)
        self.storage.write_json("watchlist.json", clean)

    def list_items(self) -> ServiceResult:
        items = [WatchlistItem(ticker=t) for t in self._load_tickers()]
        return _ok(items)

    def add(self, ticker: str) -> ServiceResult:
        ticker = normalize_ticker(ticker)
        current = self._load_tickers()
        if ticker and ticker not in current:
            current.append(ticker)
        self._save_tickers(current)
        return _ok(current, message=f"{ticker} lagt til i watchlist." if ticker else "Watchlist lagret.")

    def set_from_candidates(self, result: Mapping[str, Any], limit: int = 30) -> ServiceResult:
        rows = result.get("top_picks") or result.get("candidates") or []
        tickers = _extract_tickers(rows)[: max(1, int(limit or 30))]
        self._save_tickers(tickers)
        payload = {"tickers": tickers, "source": "Smart AI", "matched_candidates": len(tickers)}
        self.state.set("watchlist_result", payload)
        self.storage.write_json("watchlist_result.json", payload)
        return _ok(payload, message=f"{len(tickers)} tickere lagt inn i watchlist.")


_default_watchlist_service = WatchlistService()


def get_watchlist_service(state_service=None, storage_service=None) -> WatchlistService:
    if state_service is not None or storage_service is not None:
        return WatchlistService(state_service=state_service, storage_service=storage_service)
    return _default_watchlist_service
