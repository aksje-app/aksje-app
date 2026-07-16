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
from services.app_state_service import get_app_state_service
from services.currency_service import get_currency_service
from services.notification_service import get_notification_service
from services.review_queue_service import get_review_queue_service
from services.trading_rule_service import get_trading_rule_service


class ServiceRegistry:
    def __init__(self, session_state: Optional[Any] = None, score_provider=None):
        self.state = get_state_service(session_state)
        self.app_state = get_app_state_service(session_state)
        self.storage = get_storage_service()
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
        self.currency = get_currency_service()
        self.notifications = get_notification_service()
        self.review_queue = get_review_queue_service()
        self.trading_rules = get_trading_rule_service()


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
