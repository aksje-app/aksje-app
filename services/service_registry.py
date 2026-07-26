from __future__ import annotations

from typing import Any, Optional

from services.state_service import get_state_service
from services.storage_service import get_storage_service
from services.universe_service import get_universe_service
from services.watchlist_service import get_watchlist_service
from services.top_picks_service import get_top_picks_service
from services.paper_trading_service import get_paper_trading_service
from services.portfolio_service import get_portfolio_service
from services.forecast_service import get_forecast_service
from services.persistence_service import get_persistence_service
from repositories.application import get_repository_registry
from services.strategy_registry_service import StrategyRegistryService
from services.market_snapshot_service import MarketSnapshotService
from services.technical_signal_service import TechnicalSignalService


class ServiceRegistry:
    def __init__(self, session_state: Optional[Any] = None, score_provider=None):
        self.state = get_state_service(session_state)
        self.storage = get_storage_service()
        self.persistence = get_persistence_service()
        self.repositories = get_repository_registry(self.storage)
        self.strategy_registry = StrategyRegistryService(self.repositories)
        self.market_snapshots = MarketSnapshotService(self.repositories)
        self.technical_signals = TechnicalSignalService(self.market_snapshots)
        self.universe = get_universe_service(
            state_service=self.state,
            storage_service=self.storage,
            score_provider=score_provider,
        )
        self.watchlist = get_watchlist_service(state_service=self.state, storage_service=self.storage)
        self.top_picks = get_top_picks_service(
            state_service=self.state,
            storage_service=self.storage,
            universe_service=self.universe,
        )
        self.paper_trading = get_paper_trading_service(state_service=self.state)
        self.portfolio = get_portfolio_service(state_service=self.state)
        self.forecast = get_forecast_service(universe_service=self.universe)


_default_registry: Optional[ServiceRegistry] = None


def get_service_registry(session_state: Optional[Any] = None) -> ServiceRegistry:
    global _default_registry
    if session_state is not None:
        return ServiceRegistry(session_state=session_state)
    if _default_registry is None:
        _default_registry = ServiceRegistry()
    return _default_registry


def build_service_registry(session_state: Optional[Any] = None, score_provider=None) -> ServiceRegistry:
    return ServiceRegistry(session_state=session_state, score_provider=score_provider)
