from __future__ import annotations

import scanner_worker as sw


def _low_memory():
    return {
        "cgroup_memory_current_mb": 200.0,
        "cgroup_memory_limit_mb": 2048.0,
        "cgroup_memory_headroom_mb": 1848.0,
        "process_rss_mb": 180.0,
    }


def test_completed_checkpoint_resumes_finalization_not_ticker_31(monkeypatch, capsys):
    checkpoints = []
    cleared = []
    existing = {
        "scan_run_id": "PAPER-SCAN-EXISTING",
        "market_snapshot_id": "MS-STABLE",
        "phase": "SCANNING",  # backward-compatible interrupted bb checkpoint
        "tickers": ["AAPL", "MSFT"],
        "ticker_signature": "legacy-signature",
        "next_index": 2,
        "candidate_snapshots": [],
        "latest_prices": {"AAPL": 1.0, "MSFT": 2.0},
        "trades_executed": 0,
    }
    monkeypatch.setattr(sw, "print_market_guard_summary", lambda: None)
    monkeypatch.setattr(sw, "market_status_lines", lambda *args, **kwargs: [])
    monkeypatch.setattr(sw, "open_markets", lambda *args, **kwargs: ["USA"])
    monkeypatch.setattr(sw, "load_settings", lambda: {"auto_trading_enabled": False})
    monkeypatch.setattr(sw, "get_watchlist", lambda: ["AAPL", "MSFT"])
    monkeypatch.setattr(sw, "load_scanner_checkpoint", lambda: existing)
    monkeypatch.setattr(sw, "save_scanner_checkpoint", lambda value: checkpoints.append(dict(value)))
    monkeypatch.setattr(sw, "clear_scanner_checkpoint", lambda: cleared.append(True))
    monkeypatch.setattr(sw, "update_scanner_status", lambda **value: value)
    monkeypatch.setattr(sw, "release_process_memory", lambda reason="": {"after": _low_memory()})
    monkeypatch.setattr(sw, "load_portfolio", lambda: {"cash": 100.0, "positions": {}, "trades": []})
    monkeypatch.setattr(sw, "portfolio_value", lambda portfolio, prices: 100.0)
    monkeypatch.setattr(sw, "get_market_snapshot_service", lambda: type("Snapshot", (), {
        "new_snapshot_id": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("must reuse checkpoint snapshot id"))
    })())
    monkeypatch.setattr(sw, "get_strategy_account_service", lambda: type("Accounts", (), {
        "sync_legacy_account": lambda self, *args, **kwargs: {"account_id": "technical_benchmark_main"}
    })())
    monkeypatch.setattr(sw, "get_simulated_execution_service", lambda: type("Execution", (), {
        "mirror_legacy_trade": lambda self, *args, **kwargs: {"mirrored": False}
    })())

    assert sw._run_once_impl(force=True, check_currency_alerts=False) == 0
    out = capsys.readouterr().out
    assert "Gjenopptar sluttbehandling etter 2/2" in out
    assert "3/2" not in out
    assert checkpoints[-1]["phase"] == "FINALIZING"
    assert checkpoints[-1]["next_index"] == 2
    assert checkpoints[-1]["market_snapshot_id"] == "MS-STABLE"
    assert cleared == [True]


def test_noncritical_learning_maintenance_runs_after_paper_scanner_in_scheduler_source():
    source = open("scheduled_runner.py", encoding="utf-8").read()
    assert source.index("scheduled_runner:before_paper_scanner") < source.index(
        "scheduled_runner:before_learning_observations"
    )
