from __future__ import annotations

from typing import Any, Dict, Tuple


class NotificationService:
    """Unified notification facade; keeps existing notifier implementation."""

    def pushover_status(self) -> Dict[str, Any]:
        from notifier import pushover_enabled
        return {"provider": "pushover", "enabled": bool(pushover_enabled())}

    def send(self, message: str, title: str = "AI Aksje Analyzer") -> Tuple[bool, Any]:
        from notifier import send_pushover_alert
        return send_pushover_alert(message, title=title)

    def notify_trade(self, **payload: Any) -> Tuple[bool, Any]:
        from notifier import notify_trade
        return notify_trade(**payload)


_default_notification_service = NotificationService()


def get_notification_service() -> NotificationService:
    return _default_notification_service
