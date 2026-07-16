"""Services package for AI Aksje Analyzer Pro."""

# v18.6.81 consolidated service facades
from services.app_state_service import AppStateService, get_app_state_service
from services.currency_service import CurrencyService, get_currency_service
from services.notification_service import NotificationService, get_notification_service
from services.review_queue_service import ReviewQueueService, get_review_queue_service
from services.trading_rule_service import TradingRuleService, get_trading_rule_service
