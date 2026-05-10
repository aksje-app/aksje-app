"""
services/universe_service.py

Unified universe service for Smart AI / Top Picks / Watchlist / Portfolio / Paper / Forecast.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from core_models import StockCandidate, UniverseRequest, UniverseResult, ServiceResult
from services.state_service import get_state_service


DEFAULT_US = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "AVGO", "PLTR"]
DEFAULT_NORWAY = ["EQNR.OL", "DNB.OL", "TEL.OL", "MOWI.OL", "ORK.OL", "AKRBP.OL", "NHY.OL", "KOG.OL"]
DEFAULT_SWEDEN = ["VOLV-B.ST", "ERIC-B.ST", "INVE-B.ST", "ATCO-A.ST", "SEB-A.ST", "HM-B.ST"]
DEFAULT_DENMARK = ["NOVO-B.CO", "MAERSK-B.CO", "DSV.CO", "VWS.CO", "CARL-B.CO"]


def _clean_ticker(value: Any) -> str:
    s = str(value or "").strip().upper()
    if not s or len(s) > 32:
        return ""
    if not all(ch.isalnum() or ch in ".-_/" for ch in s):
        return ""
    return s


def _extract_tickers(value: Any) -> List[str]:
    out: List[str] = []
    def add(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, str):
            # comma separated or single
            parts = [p.strip() for p in v.split(",")] if "," in v else [v]
            for part in parts:
                t = _clean_ticker(part)
                if t and t not in out:
                    out.append(t)
        elif isinstance(v, dict):
            for key in ("ticker", "symbol", "Ticker", "Symbol"):
                if key in v:
                    add(v.get(key))
            # dict of ticker -> data
            for k, val in v.items():
                add(k)
                if isinstance(val, (dict, list)):
                    add(val)
        elif isinstance(v, (list, tuple, set)):
            for item in v:
                add(item)
    add(value)
    return out


class UniverseService:
    def __init__(self, state_service=None):
        self.state = state_service or get_state_service()

    def defaults_for_market(self, market: str = "all") -> List[str]:
        m = (market or "all").lower()
        if m in ("us", "usa", "nasdaq", "nyse"):
            return DEFAULT_US
        if m in ("norway", "norge", "oslo", "ol"):
            return DEFAULT_NORWAY
        if m in ("sweden", "sverige", "stockholm", "st"):
            return DEFAULT_SWEDEN
        if m in ("denmark", "danmark", "copenhagen", "co"):
            return DEFAULT_DENMARK
        return DEFAULT_US + DEFAULT_NORWAY + DEFAULT_SWEDEN + DEFAULT_DENMARK

    def from_state_sources(self, sources: Sequence[str]) -> List[str]:
        tickers: List[str] = []
        for key in sources:
            for t in _extract_tickers(self.state.get(key)):
                if t not in tickers:
                    tickers.append(t)
        return tickers

    def resolve(self, request: UniverseRequest | Dict[str, Any] | None = None) -> ServiceResult:
        if request is None:
            request = UniverseRequest(mode="all")
        if isinstance(request, dict):
            request = UniverseRequest(**{k: v for k, v in request.items() if k in UniverseRequest.__dataclass_fields__})

        mode = (request.mode or "manual").lower()
        tickers: List[str] = []

        if mode == "manual":
            tickers = [_clean_ticker(t) for t in request.tickers]
        elif mode in ("watchlist", "watch"):
            tickers = self.from_state_sources(["watchlist", "watchlist_items"])
        elif mode in ("top_picks", "top picks", "smart_ai", "smart"):
            tickers = self.from_state_sources(["top_picks", "ai_ranking", "smart_ai_candidates"])
            if not tickers:
                tickers = self.defaults_for_market(request.market)
        elif mode in ("paper", "paper_trading"):
            tickers = self.from_state_sources(["paper_portfolio", "paper_positions", "paper_trading_positions"])
        elif mode in ("portfolio", "holdings", "positions"):
            tickers = self.from_state_sources(["portfolio", "holdings", "positions"])
        elif mode in ("market", "all"):
            tickers = self.defaults_for_market(request.market)
        else:
            tickers = self.from_state_sources([mode]) or self.defaults_for_market(request.market)

        # fallback
        tickers = [t for t in tickers if t]
        if not tickers:
            tickers = self.defaults_for_market(request.market)

        seen = set()
        candidates = []
        for i, ticker in enumerate(tickers):
            if ticker in seen:
                continue
            seen.add(ticker)
            if len(candidates) >= int(request.limit or 10):
                break
            candidates.append(StockCandidate(
                ticker=ticker,
                market=request.market,
                score=max(0.0, 100.0 - i),
                source=mode,
            ))

        return ServiceResult(ok=True, data=UniverseResult(candidates=candidates, source=mode))


_default_universe_service = UniverseService()


def get_universe_service() -> UniverseService:
    return _default_universe_service
