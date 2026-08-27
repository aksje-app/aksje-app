from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import notifier
import scanner_worker as sw
import scheduled_runner


def _high_memory():
    return {
        "cgroup_memory_current_mb": 666.0,
        "cgroup_memory_limit_mb": 720.0,
        "cgroup_memory_headroom_mb": 54.0,
        "process_rss_mb": 600.0,
    }


def test_memory_checkpoint_makes_at_least_one_ticker_progress(monkeypatch):
    checkpoints = []
    statuses = []
    monkeypatch.setattr(sw, "print_market_guard_summary", lambda: None)
    monkeypatch.setattr(sw, "market_status_lines", lambda: [])
    monkeypatch.setattr(sw, "open_markets", lambda: ["USA"])
    monkeypatch.setattr(sw, "load_settings", lambda: {"auto_trading_enabled": False})
    monkeypatch.setattr(sw, "get_watchlist", lambda: ["AAPL", "MSFT", "NVDA"])
    monkeypatch.setattr(sw, "load_scanner_checkpoint", lambda: {})
    monkeypatch.setattr(sw, "save_scanner_checkpoint", lambda value: checkpoints.append(dict(value)))
    monkeypatch.setattr(sw, "update_scanner_status", lambda **value: statuses.append(dict(value)))
    monkeypatch.setattr(sw, "release_process_memory", lambda reason="": {"after": _high_memory()})
    monkeypatch.setattr(sw, "should_process_ticker", lambda ticker: False)
    monkeypatch.setattr(
        sw, "get_market_snapshot_service",
        lambda: type("Snapshot", (), {"new_snapshot_id": lambda self, **kwargs: "SNAP"})(),
    )
    monkeypatch.setenv("SCANNER_MEMORY_SOFT_LIMIT_MB", "410")
    monkeypatch.setenv("SCANNER_MIN_TICKERS_PER_CYCLE", "1")

    assert sw._run_once_impl(force=True, check_currency_alerts=False) == 0
    assert checkpoints[-1]["next_index"] == 1
    assert any(row.get("tickers_processed") == 1 for row in statuses)
    assert statuses[-1]["state"] == "PARTIAL_CHECKPOINT"


def test_checkpoint_survives_changed_dynamic_watchlist(monkeypatch):
    checkpoints = []
    statuses = []
    existing = {
        "scan_run_id": "PAPER-SCAN-EXISTING",
        "tickers": ["AAPL", "MSFT", "NVDA"],
        "ticker_signature": "old-signature",
        "next_index": 1,
    }
    monkeypatch.setattr(sw, "print_market_guard_summary", lambda: None)
    monkeypatch.setattr(sw, "market_status_lines", lambda: [])
    monkeypatch.setattr(sw, "open_markets", lambda: ["USA"])
    monkeypatch.setattr(sw, "load_settings", lambda: {"auto_trading_enabled": False})
    monkeypatch.setattr(sw, "get_watchlist", lambda: ["TSLA", "AAPL"])
    monkeypatch.setattr(sw, "load_scanner_checkpoint", lambda: existing)
    monkeypatch.setattr(sw, "save_scanner_checkpoint", lambda value: checkpoints.append(dict(value)))
    monkeypatch.setattr(sw, "update_scanner_status", lambda **value: statuses.append(dict(value)))
    monkeypatch.setattr(sw, "release_process_memory", lambda reason="": {"after": _high_memory()})
    monkeypatch.setattr(sw, "should_process_ticker", lambda ticker: False)
    monkeypatch.setattr(
        sw, "get_market_snapshot_service",
        lambda: type("Snapshot", (), {"new_snapshot_id": lambda self, **kwargs: "SNAP"})(),
    )
    monkeypatch.setenv("SCANNER_MIN_TICKERS_PER_CYCLE", "1")

    sw._run_once_impl(force=True, check_currency_alerts=False)
    assert checkpoints[-1]["scan_run_id"] == "PAPER-SCAN-EXISTING"
    assert checkpoints[-1]["next_index"] == 2
    assert checkpoints[-1]["tickers"] == ["AAPL", "MSFT", "NVDA", "TSLA"]


def test_invalid_fund_name_is_never_used_as_scanner_ticker(monkeypatch):
    monkeypatch.setenv(
        "SCANNER_WATCHLIST",
        "AAPL,DNB FUND - DISRUPTIVE OPPORTUNITIES N NOK (ACC),AKER.OL,BRK-B",
    )
    assert sw.get_watchlist() == ["AAPL", "AKER.OL", "BRK-B"]
    assert sw.valid_scanner_ticker("DNB FUND - DISRUPTIVE OPPORTUNITIES N NOK (ACC)") is False


def test_closed_ui_buy_candidates_are_not_prioritized(monkeypatch):
    monkeypatch.delenv("SCANNER_WATCHLIST", raising=False)
    settings = {
        "latest_buy_now_candidates": [{"ticker": "AKER.OL"}, {"ticker": "AAPL"}],
        "max_tickers_per_market": 2,
        "scan_top_picks_only": True,
    }
    monkeypatch.setattr(sw, "load_settings", lambda: settings)
    monkeypatch.setattr(sw, "enabled_markets", lambda value: ["USA", "NORGE"])
    monkeypatch.setattr(sw, "open_markets", lambda: ["USA"])
    monkeypatch.setattr(sw, "_take", lambda fn, n: [])
    monkeypatch.setattr(sw, "load_portfolio", lambda: {"positions": {}})
    monkeypatch.setattr(sw, "US_FALLBACK", ["MSFT"])
    assert sw.get_watchlist()[:2] == ["AAPL", "MSFT"]
    assert "AKER.OL" not in sw.get_watchlist()


def test_identical_pushover_payload_is_suppressed_durably(monkeypatch):
    ledger = {}
    posts = []
    monkeypatch.setattr(notifier, "notifications_allowed", lambda: (True, "ok"))
    monkeypatch.setattr(notifier, "pushover_enabled", lambda: True)
    monkeypatch.setattr(notifier, "load_settings", lambda: {"pushover_enabled": True})
    monkeypatch.setattr(notifier, "read_json", lambda *args, **kwargs: dict(ledger))
    monkeypatch.setattr(notifier, "write_json", lambda key, path, value: ledger.update(value))
    monkeypatch.setattr(notifier, "_log_delivery", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        notifier.requests, "post",
        lambda *args, **kwargs: posts.append(kwargs) or type("Response", (), {"status_code": 200, "text": ""})(),
    )
    first = notifier.send_pushover_alert("Samme melding", title="Samme tittel")
    second = notifier.send_pushover_alert("Samme melding", title="Samme tittel")
    assert first[0] is True and second[0] is True
    assert "duplicate suppressed" in second[1]
    assert len(posts) == 1


def test_partial_checkpoint_is_visible_but_not_a_cron_failure(monkeypatch):
    monkeypatch.setattr(scheduled_runner, "run_once", lambda: {
        "state": "PARTIAL_CHECKPOINT",
        "paper_scanner": {"state": "PARTIAL_CHECKPOINT"},
    })
    assert scheduled_runner.main() == 0


def test_render_cron_matches_configured_fifteen_minute_interval():
    source = Path("render.yaml").read_text(encoding="utf-8")
    assert 'schedule: "*/15 * * * *"' in source
