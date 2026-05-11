"""Persistent storage status helpers for AI Kontrollsenter / Render smoke tests.

v18.5.29 verifies that the app state categories that matter for Render are
routed through StorageService/Postgres-first paths, with local JSON used only as
a development fallback.
"""

from __future__ import annotations

from typing import Any, Dict, List


def storage_status_snapshot() -> Dict[str, Any]:
    try:
        from services.storage_service import get_storage_service
        storage = get_storage_service()
        status = storage.status_dict()
    except Exception as exc:
        return {
            "backend": "unknown",
            "persistent": False,
            "ok": False,
            "message": f"StorageService ikke tilgjengelig: {exc}",
            "categories": [],
        }

    categories: List[Dict[str, Any]] = [
        {"category": "learning_stats", "key": "forecasts/forecast_learning_stats.json", "service": "forecast_store"},
        {"category": "forecast_logs", "key": "forecasts/forecast_log.jsonl", "service": "forecast_store"},
        {"category": "forecast_alerts/event_risk", "key": "forecasts/forecast_alerts.jsonl", "service": "forecast_store"},
        {"category": "score_explanations", "key": "score_explanations/history.jsonl", "service": "score_explanation_store"},
        {"category": "watchlist", "key": "watchlist.json", "service": "WatchlistService"},
        {"category": "paper_trading", "key": "paper_trading/portfolio.json", "service": "paper_store"},
        {"category": "active_smart_universe", "key": "active_universe.json", "service": "UniverseService"},
        {"category": "app_settings", "key": "settings/app_settings.json", "service": "settings_store"},
        {"category": "trading_rules", "key": "settings/trading_rules.json", "service": "trading_settings"},
        {"category": "strategy_testing", "key": "strategy_testing/logs.json", "service": "strategy_test_pro"},
        {"category": "signal_alert_state", "key": "alerts/signal_state.json", "service": "alert_state"},
    ]
    status["categories"] = categories
    return status


def compact_storage_status_rows() -> List[Dict[str, str]]:
    snapshot = storage_status_snapshot()
    backend = str(snapshot.get("backend", "unknown"))
    persistent = "Ja" if snapshot.get("persistent") else "Nei / fallback"
    rows = []
    for item in snapshot.get("categories", []):
        rows.append({
            "Område": str(item.get("category", "")),
            "Lagring": backend,
            "Persistent": persistent,
            "Service": str(item.get("service", "")),
        })
    return rows
