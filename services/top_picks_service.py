from __future__ import annotations

from core_models import ServiceResult, TopPickItem, UniverseRequest
from services.universe_service import get_universe_service


class TopPicksService:
    def __init__(self, universe_service=None):
        self.universe = universe_service or get_universe_service()

    def get_top_picks(self, market: str = "all", limit: int = 10) -> ServiceResult:
        result = self.universe.resolve(UniverseRequest(mode="top_picks", market=market, limit=limit))
        if not result.ok:
            return result
        items = [
            TopPickItem(ticker=c.ticker, score=c.score, reason="Smart AI service candidate", source=c.source)
            for c in result.data.candidates
        ]
        return ServiceResult(ok=True, data=items)


_default_top_picks_service = TopPicksService()

def get_top_picks_service() -> TopPicksService:
    return _default_top_picks_service
