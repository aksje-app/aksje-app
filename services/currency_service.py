from __future__ import annotations

from typing import Any, Dict, Iterable, List


class CurrencyService:
    """Facade for currency quote and alert evaluation modules.

    Imports are deliberately lazy to avoid UI/service import cycles.
    """

    def evaluate_alerts(self, *args: Any, **kwargs: Any) -> Any:
        from currency_alert_service import run_currency_alert_checks
        return run_currency_alert_checks(*args, **kwargs)

    def check_now(self, *args: Any, **kwargs: Any) -> Any:
        from currency_alert_service import run_currency_alert_checks
        kwargs.setdefault("force", True)
        return run_currency_alert_checks(*args, **kwargs)


_default_currency_service = CurrencyService()


def get_currency_service() -> CurrencyService:
    return _default_currency_service
