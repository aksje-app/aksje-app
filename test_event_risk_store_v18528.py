from pathlib import Path
from tempfile import TemporaryDirectory

import forecast_store
from forecast_store import build_and_store_all_horizons, compute_intelligent_alerts, load_latest_forecast, save_alerts, load_alerts


def test_event_risk_details_are_persisted_and_replayed_as_alerts():
    with TemporaryDirectory() as tmp:
        forecast_store.DATA_DIR = Path(tmp) / "data"
        forecast_store.FORECAST_DIR = forecast_store.DATA_DIR / "forecasts"
        forecast_store.FORECAST_LOG = forecast_store.FORECAST_DIR / "forecast_log.jsonl"
        forecast_store.FORECAST_ALERTS = forecast_store.FORECAST_DIR / "forecast_alerts.jsonl"
        forecast_store.LEARNING_STATS = forecast_store.FORECAST_DIR / "forecast_learning_stats.json"

        event_info = {
            "is_event_risk": True,
            "confidence_adjustment": -8,
            "alerts": [{
                "ticker": "AAPL",
                "horizon": "1m",
                "level": "yellow",
                "category": "earnings_event",
                "source": "Hendelsesrisiko",
                "message": "Earnings nær: AAPL har rapportdato 2026-05-12 (2 dager).",
            }],
            "diagnostics": {"earnings": {"available": True, "active": True}},
        }
        payload = build_and_store_all_horizons(
            "AAPL",
            [100 + i for i in range(90)],
            event_risk=True,
            event_confidence_adjustment=-8,
            event_risk_summary="Hendelsesrisiko nær: earnings",
            event_risk_details=event_info,
        )
        assert payload["event_risk"] is True
        assert payload["event_confidence_adjustment"] == -8
        assert payload["event_risk_details"]["alerts"][0]["category"] == "earnings_event"

        latest = load_latest_forecast("AAPL")
        assert latest is not None
        assert latest["event_risk_details"]["diagnostics"]["earnings"]["active"] is True

        alerts = compute_intelligent_alerts(payload)
        assert any(a.get("category") == "earnings_event" for a in alerts)
        save_alerts(alerts)
        persisted = load_alerts(limit=10)
        assert any(a.get("source") == "Hendelsesrisiko" for a in persisted)
