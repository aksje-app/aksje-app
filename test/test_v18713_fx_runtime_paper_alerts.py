from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sys
import types

sys.modules.setdefault("requests", types.SimpleNamespace(post=lambda *args, **kwargs: None))
import currency_alert_service as fx


def test_changed_threshold_is_evaluated_immediately_and_resets_stale_breach(monkeypatch):
    key = "BRL/NOK:BRLNOK=X"
    settings = {
        "currency_alerts_v1863af": [{
            "pair": "BRL/NOK", "symbol": "BRLNOK=X", "lower": 1.88, "upper": 1.89,
            "active": True, "pushover": True, "check_interval_minutes": 10, "cooldown_minutes": 15,
        }],
        fx.STATE_KEY: {key: {
            "status": "breach_lower", "last_checked_at": datetime.now(timezone.utc).isoformat(),
            "last_sent_at": datetime.now(timezone.utc).isoformat(),
            "config_signature": "BRLNOK=X|1.70000000|2.20000000|1",
        }},
    }
    saved = {}
    monkeypatch.setattr(fx, "load_settings", lambda: settings)
    monkeypatch.setattr(fx, "save_settings", lambda value: saved.update(value) or True)
    monkeypatch.setattr(fx, "_event", lambda *args, **kwargs: {})
    rows = fx._run_currency_alert_checks_locked(fetcher=lambda symbol: (1.8835, ""))
    assert rows[0]["status"] == "normal"
    assert rows[0]["previous_status"] == "normal"
    assert saved[fx.STATE_KEY][key].get("last_sent_at") is None


def test_new_breach_sends_pushover_after_configuration_change(monkeypatch):
    settings = {
        "currency_alerts_v1863af": [{
            "pair": "BRL/NOK", "symbol": "BRLNOK=X", "lower": 1.88, "upper": 1.89,
            "active": True, "pushover": True, "check_interval_minutes": 10, "cooldown_minutes": 15,
        }],
        fx.STATE_KEY: {},
    }
    sent = []
    monkeypatch.setattr(fx, "load_settings", lambda: settings)
    monkeypatch.setattr(fx, "save_settings", lambda value: True)
    monkeypatch.setattr(fx, "_event", lambda *args, **kwargs: {})
    rows = fx._run_currency_alert_checks_locked(
        fetcher=lambda symbol: (1.87, ""),
        sender=lambda message, title=None: sent.append((title, message)) or (True, None),
    )
    assert rows[0]["status"] == "breach_lower"
    assert rows[0]["sent"] is True
    assert len(sent) == 1


def test_runtime_worker_and_paper_signature_are_wired_into_app():
    app_source = Path("app.py").read_text(encoding="utf-8")
    runtime_source = Path("runtime_background.py").read_text(encoding="utf-8")
    assert "ensure_runtime_background_services()" in app_source
    assert 'name="fx-alert-runtime"' in runtime_source
    assert "position_rows: list[dict] | None = None" in app_source
    assert "position_rows=position_rows, rules=rules" in app_source


def test_global_lock_skips_when_another_worker_holds_database_lock(monkeypatch):
    @contextmanager
    def unavailable():
        yield False

    monkeypatch.setattr(fx, "_global_check_lock", unavailable)
    monkeypatch.setattr(fx, "_event", lambda *args, **kwargs: {})
    assert fx.run_currency_alert_checks() == []


def test_intraday_threshold_crossing_sends_even_if_saved_status_is_stale(monkeypatch):
    key = "BRL/NOK:BRLNOK=X"
    settings = {
        "currency_alerts_v1863af": [{
            "pair": "BRL/NOK", "symbol": "BRLNOK=X", "lower": 1.89, "upper": 1.90,
            "active": True, "pushover": True, "check_interval_minutes": 10, "cooldown_minutes": 30,
        }],
        fx.STATE_KEY: {key: {
            "status": "breach_upper",
            "rate": 1.8977,
            "last_rate": 1.8977,
            "last_sent_at": datetime.now(timezone.utc).isoformat(),
            "config_signature": "BRLNOK=X|1.89000000|1.90000000|1",
        }},
    }
    sent = []
    monkeypatch.setattr(fx, "load_settings", lambda: settings)
    monkeypatch.setattr(fx, "save_settings", lambda value: True)
    monkeypatch.setattr(fx, "_event", lambda *args, **kwargs: {})
    rows = fx._run_currency_alert_checks_locked(
        force=True,
        fetcher=lambda symbol: (1.9012, "", "2026-07-21T21:59:00+02:00"),
        sender=lambda message, title=None: sent.append(message) or (True, ""),
    )
    assert rows[0]["crossed_threshold"] is True
    assert rows[0]["sent"] is True
    assert sent


def test_fetch_prefers_intraday_history(monkeypatch):
    calls = []

    class CloseSeries:
        empty = False
        index = [datetime(2026, 7, 21, 20, 1, tzinfo=timezone.utc)]
        @property
        def iloc(self):
            return self
        def __getitem__(self, idx):
            return 1.9011
        def dropna(self):
            return self

    class History:
        empty = False
        def __contains__(self, key):
            return key == "Close"
        def __getitem__(self, key):
            return CloseSeries()

    class Ticker:
        def history(self, **kwargs):
            calls.append(kwargs)
            return History()

    monkeypatch.setattr(fx, "yf", types.SimpleNamespace(Ticker=lambda symbol: Ticker()))
    rate, error, quote_time = fx._fetch("BRLNOK=X")
    assert rate == 1.9011
    assert error == ""
    assert calls[0]["interval"] == "1m"
    assert quote_time
