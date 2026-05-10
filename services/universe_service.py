from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

SMART_RESULT_KEY = "smart_universe_result"
AI_UNIVERSE_SMART_RESULT_KEY = SMART_RESULT_KEY
TOP_PICKS_RESULT_KEY = "top_picks_result"
WATCHLIST_RESULT_KEY = "watchlist_result"

try:
    from core_models import ServiceResult, UniverseRequest, UniverseResult, StockCandidate
except Exception:
    @dataclass
    class ServiceResult:
        ok: bool
        data: Any = None
        error: str | None = None

    @dataclass
    class UniverseRequest:
        mode: str = "market"
        market: str = "all"
        tickers: List[str] = field(default_factory=list)
        limit: int = 10

    @dataclass
    class StockCandidate:
        ticker: str
        market: str = ""
        score: float = 0
        source: str = ""

    @dataclass
    class UniverseResult:
        candidates: List[StockCandidate] = field(default_factory=list)
        source: str = ""


DEFAULTS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "EQNR.OL", "DNB.OL", "STB.OL", "NOVO-B.CO"]


def _extract_tickers(value):
    out = []

    def add(v):
        if v is None:
            return
        if isinstance(v, str):
            for p in v.split(","):
                t = p.strip().upper()
                if t and t not in out:
                    out.append(t)
        elif isinstance(v, dict):
            for k, val in v.items():
                add(k)
                if isinstance(val, (dict, list, tuple, set)):
                    add(val)
        elif isinstance(v, (list, tuple, set)):
            for i in v:
                add(i)

    add(value)
    return out


class UniverseService:
    def resolve(self, request=None):
        if request is None:
            request = UniverseRequest()
        if isinstance(request, dict):
            request = UniverseRequest(**{k: v for k, v in request.items() if k in UniverseRequest.__dataclass_fields__})

        tickers = list(getattr(request, "tickers", []) or [])
        if not tickers:
            tickers = DEFAULTS

        limit = int(getattr(request, "limit", 10) or 10)
        mode = getattr(request, "mode", "market")
        market = getattr(request, "market", "all")

        candidates = [
            StockCandidate(ticker=str(t).upper(), market=market, score=100 - i, source=mode)
            for i, t in enumerate(tickers[:limit])
        ]
        return ServiceResult(ok=True, data=UniverseResult(candidates=candidates, source=mode))

    def get_universe(self, request=None):
        return self.resolve(request)

    def smart_universe(self, market="all", limit=10):
        return self.resolve(UniverseRequest(mode="smart_ai", market=market, limit=limit))

    def top_picks(self, market="all", limit=10):
        return self.resolve(UniverseRequest(mode="top_picks", market=market, limit=limit))


_default = UniverseService()


def get_universe_service():
    return _default
