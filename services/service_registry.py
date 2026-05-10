from __future__ import annotations

from services.state_service import get_state_service
from services.storage_service import get_storage_service
from services.universe_service import get_universe_service
from services.watchlist_service import get_watchlist_service
from services.top_picks_service import get_top_picks_service
from services.paper_trading_service import get_paper_trading_service
from services.portfolio_service import get_portfolio_service
from services.forecast_service import get_forecast_service


class ServiceRegistry:
    def __init__(self):
        self.state = get_state_service()
        self.storage = get_storage_service()
        self.universe = get_universe_service()
        self.watchlist = get_watchlist_service()
        self.top_picks = get_top_picks_service()
        self.paper_trading = get_paper_trading_service()
        self.portfolio = get_portfolio_service()
        self.forecast = get_forecast_service()


_registry = ServiceRegistry()


def get_service_registry() -> ServiceRegistry:
    return _registry

def get_service_registry():
    return _registry

def build_service_registry():
    return get_service_registry()