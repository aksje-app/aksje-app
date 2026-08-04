from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import datetime, timezone
from pathlib import Path

import currency_alert_service as fx

ROOT = Path(__file__).resolve().parents[1]


def _memory_store(monkeypatch, initial: dict):
    store = dict(initial)

    def load():
        return copy.deepcopy(store)

    def save(value):
        snapshot = copy.deepcopy(value)
        store.clear()
        store.update(snapshot)
        return True

    monkeypatch.setattr(fx, "load_settings", load)
    monkeypatch.setattr(fx, "save_settings", save)
    monkeypatch.setattr(fx, "_event", lambda *args, **kwargs: {})
    return store


def test_manual_refresh_uses_single_authoritative_result_without_notification(monkeypatch):
    settings = {
        "currency_alerts_v1863af": [{
            "pair": "BRL/NOK", "symbol": "BRLNOK=X", "lower": 1.86, "upper": 1.875,
            "active": True, "pushover": True, "check_interval_minutes": 15, "cooldown_minutes": 30,
        }],
        fx.STATE_KEY: {},
    }
    store = _memory_store(monkeypatch, settings)
    sent = []
    rows = fx._run_currency_alert_checks_locked(
        force=True,
        fetcher=lambda symbol: (1.8686, "", "2026-08-04T13:50:00+00:00"),
        sender=lambda *args, **kwargs: sent.append((args, kwargs)) or (True, ""),
        notify=False,
        source="manual_fetch",
    )
    assert sent == []
    assert rows[0]["rate"] == 1.8686
    assert rows[0]["status"] == "normal"
    assert rows[0]["reason"] == "normal"
    key = "BRL/NOK:BRLNOK=X"
    assert store[fx.STATE_KEY][key]["rate"] == 1.8686
    assert store[fx.STATE_KEY][key]["status"] == "normal"
    assert store["currency_alert_latest_rates_v1864s"]["BRLNOK=X"]["rate"] == 1.8686


def test_manual_cycle_does_not_fake_automatic_health_but_cron_cycle_does(monkeypatch):
    store = _memory_store(monkeypatch, {})

    @contextmanager
    def lock():
        yield True

    monkeypatch.setattr(fx, "_global_check_lock", lock)
    monkeypatch.setattr(
        fx,
        "_run_currency_alert_checks_locked",
        lambda **kwargs: [{"status": "normal", "sent": False, "rate": 1.87}],
    )

    fx.run_currency_alert_checks(force=True, notify=False, source="manual_fetch")
    assert fx.get_currency_alert_health()["state"] == "NOT_STARTED"
    assert store[fx.HEARTBEAT_KEY]["source"] == "manual_fetch"

    fx.run_currency_alert_checks(force=False, source="scheduled_cron")
    health = fx.get_currency_alert_health()
    assert health["healthy"] is True
    assert health["state"] == "COMPLETED"
    assert health["last_automatic_at"]


def test_provider_error_marks_automatic_health_degraded(monkeypatch):
    _memory_store(monkeypatch, {})

    @contextmanager
    def lock():
        yield True

    monkeypatch.setattr(fx, "_global_check_lock", lock)
    monkeypatch.setattr(
        fx,
        "_run_currency_alert_checks_locked",
        lambda **kwargs: [{"status": "error", "error": "Yahoo unavailable", "sent": False}],
    )
    rows = fx.run_currency_alert_checks(source="scheduled_cron")
    assert rows[0]["status"] == "error"
    health = fx.get_currency_alert_health()
    assert health["healthy"] is False
    assert health["state"] == "DEGRADED"
    assert "Yahoo unavailable" in health["last_error"]


def test_diagnostic_test_restores_real_runtime_cache_and_heartbeat(monkeypatch):
    original_runtime = {"BRL/NOK:BRLNOK=X": {"rate": 1.8686, "status": "normal"}}
    original_latest = {"BRLNOK=X": {"rate": 1.8686}}
    original_heartbeat = {"state": "COMPLETED", "last_automatic_state": "COMPLETED"}
    store = _memory_store(monkeypatch, {
        "currency_alerts_v1863af": [dict(fx.DEFAULT_ALERT)],
        fx.STATE_KEY: original_runtime,
        "currency_alert_latest_rates_v1864s": original_latest,
        fx.HEARTBEAT_KEY: original_heartbeat,
    })
    monkeypatch.setattr(fx, "_fetch", lambda symbol: (1.8686, "", "2026-08-04T13:50:00+00:00"))

    def fake_run(**kwargs):
        current = fx.load_settings()
        current[fx.STATE_KEY] = {"BRL/NOK:BRLNOK=X": {"rate": 99.0, "status": "breach_upper"}}
        current["currency_alert_latest_rates_v1864s"] = {"BRLNOK=X": {"rate": 99.0}}
        current[fx.HEARTBEAT_KEY] = {"state": "COMPLETED", "source": "diagnostic_test"}
        fx.save_settings(current)
        return [{"symbol": "BRLNOK=X", "status": "breach_upper", "sent": True}]

    monkeypatch.setattr(fx, "run_currency_alert_checks", fake_run)
    rows = fx.run_currency_alert_diagnostic_test("BRLNOK=X")
    assert rows[0]["sent"] is True
    assert store[fx.STATE_KEY] == original_runtime
    assert store["currency_alert_latest_rates_v1864s"] == original_latest
    assert store[fx.HEARTBEAT_KEY] == original_heartbeat


def test_render_cron_and_ui_use_one_currency_chain():
    scheduled = (ROOT / "scheduled_runner.py").read_text(encoding="utf-8")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert 'run_currency_alert_checks(force=False, source="scheduled_cron")' in scheduled
    assert 'schedule: "*/5 * * * *"' in render
    assert 'run_currency_alert_checks(force=True, notify=False, source="manual_fetch")' in app
    assert 'run_currency_alert_checks(force=True, notify=True, source="manual_check")' in app
    assert 'source="pushover_test_quote"' in app
    assert "get_currency_alert_health(max_age_minutes=20)" in app
    assert "runtime_background_status()" not in app[app.index("def render_currency_alerts_control_center_v1863af"):app.index("# v18.5.37")]
    assert "_fetch_fx_rate_v1863af(symbol_value)" not in app[app.index("def render_currency_alerts_control_center_v1863af"):app.index("# v18.5.37")]
    assert "fx-status-grid" in app
    assert "repeat(2,minmax(0,1fr))" in app
    assert "Teknisk valutastatus og logg" in app
    assert "Send Pushover-test med fersk kurs" in app


def test_version_identity_advances_to_rc6():
    from app_version import APP_VERSION, PREVIOUS_APP_VERSION

    assert APP_VERSION == "v19.22.0-rc6"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc5"
