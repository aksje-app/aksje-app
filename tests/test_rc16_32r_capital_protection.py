from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _load_stop_functions() -> dict:
    source = _source("super_portfolio.py")
    tree = ast.parse(source)
    wanted = {
        "_f", "_volatility", "dynamic_stop_levels", "_stop_status",
        "stop_pressure", "_automatic_stop_exit", "_stop_alerts",
    }
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    namespace = {
        "Any": Any, "Mapping": Mapping, "Sequence": Sequence,
        "isfinite": isfinite, "SuperPortfolioConfig": object,
        "MAX_TRAILING_STOP_PCT": 3.0, "STOP_WARNING_PCT": 1.5, "STOP_NEAR_PCT": 2.25,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), "super_portfolio.py", "exec"), namespace)
    return namespace


def _cfg(**overrides: float) -> SimpleNamespace:
    values = {
        "hard_stop_drawdown_pct": 3.0,
        "warning_drawdown_pct": 1.5,
        "near_stop_drawdown_pct": 2.25,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_high_volatility_cannot_widen_three_percent_stop() -> None:
    functions = _load_stop_functions()
    levels = functions["dynamic_stop_levels"](
        {"entry_price": 100, "peak_price": 110, "volatility_pct": 100},
        _cfg(hard_stop_drawdown_pct=18.0),
    )
    assert levels["hard_stop_drawdown_pct"] == 3.0
    assert levels["warning_drawdown_pct"] == 1.5
    assert levels["near_stop_drawdown_pct"] == 2.25


def test_trailing_stop_protects_profit_after_ten_percent_rise() -> None:
    functions = _load_stop_functions()
    status = functions["_stop_status"](
        {"entry_price": 100, "peak_price": 110, "last_price": 107.0}, _cfg()
    )
    assert status["hard_stop_price"] == 106.7
    assert status["pnl_pct"] == 7.0
    assert status["stop_status"] == "NEAR STOP"
    assert 0 < status["distance_to_hard_stop_pct"] < 1


def test_confirmed_fall_exits_before_hard_stop() -> None:
    functions = _load_stop_functions()
    position = {"ticker": "TEST", "entry_price": 100, "peak_price": 110, "last_price": 107.0}
    position.update(functions["_stop_status"](position, _cfg()))
    pressure = functions["stop_pressure"](
        position, [{"positions": [{"ticker": "TEST", "distance_to_hard_stop_pct": 2.5}]}], _cfg()
    )
    position.update({
        "stop_direction_arrow": pressure["direction_arrow"],
        "stop_distance_change_pct": pressure["distance_change_pct"],
    })
    decision = functions["_automatic_stop_exit"](position)
    assert pressure["direction_arrow"] == "↓↓"
    assert decision and decision[0] == "CONFIRMED_EARLY_TRAILING_EXIT"


def test_hard_stop_triggers_at_three_percent_from_peak() -> None:
    functions = _load_stop_functions()
    position = {"entry_price": 100, "peak_price": 110, "last_price": 106.7}
    position.update(functions["_stop_status"](position, _cfg()))
    assert position["stop_status"] == "STOP TRIGGERED"
    assert functions["_automatic_stop_exit"](position)[0] == "HARD_STOP"


def test_hard_stop_starts_three_percent_below_purchase() -> None:
    functions = _load_stop_functions()
    position = {"entry_price": 100, "peak_price": 100, "last_price": 97}
    position.update(functions["_stop_status"](position, _cfg()))
    assert position["hard_stop_price"] == 97.0
    assert position["stop_status"] == "STOP TRIGGERED"


def test_executed_early_exit_alerts_even_when_status_did_not_change() -> None:
    functions = _load_stop_functions()
    previous = {"TEST": {"stop_status": "NEAR STOP"}}
    current = {"TEST": {
        "stop_status": "NEAR STOP", "stop_exit_reason_code": "CONFIRMED_EARLY_TRAILING_EXIT",
        "entry_price": 100, "peak_price": 110, "last_price": 107,
    }}
    alerts = functions["_stop_alerts"](previous, current)
    assert len(alerts) == 1
    assert alerts[0]["transition"] == "EXIT"
    assert alerts[0]["action"] == "SHADOW SELL UTFØRT"


def test_pushover_contains_decision_prices_and_recovery() -> None:
    source = _source("super_portfolio.py")
    assert "Kjøp {_f(row.get('entry_price')):.2f}" in source
    assert "topp {_f(row.get('peak_price')):.2f}" in source
    assert "nå {_f(row.get('current_price')):.2f}" in source
    assert "Stop {_f(row.get('stop_price')):.2f}" in source
    assert "BEDRET STOPSTATUS" in source
    assert "pp margin" in source
    assert 'priority=priority' in source


def test_legacy_state_is_migrated_and_reentry_is_gated() -> None:
    source = _source("super_portfolio.py")
    assert '"hard_stop_drawdown_pct": MAX_TRAILING_STOP_PCT' in source
    assert '"risk_exit_cooldown_days": 1' in source
    assert '"risk_reentry_confirmation_runs": 2' in source
    assert 'persistence.pop(ticker, None)' in source
    assert '("manual_exit_cooldown", "risk_exit_cooldown")' in source
    assert 'RISK_REENTRY_CONFIRMATION_BLOCKED' in source
    assert 'RISK_REENTRY_FRESHNESS_UNKNOWN' in source
    assert 'if not previous and not (state.get("risk_reentry_confirmation") or {})' in source
    assert 'price_improving and score_not_worse' in source


def test_lightweight_surveillance_closes_twelve_hour_stop_gap() -> None:
    source = _source("super_portfolio.py")
    jobs_source = _source("super_portfolio_jobs.py")
    assert "stop_surveillance_minutes: int = 15" in source
    assert '"action": "NO_SALE_FAIL_CLOSED"' in source
    assert '"mode": "STOP_SURVEILLANCE"' in source
    assert "run_lightweight_stop_surveillance(state=state, now=now_dt)" in source
    assert '"event": "LIGHTWEIGHT_STOP_SURVEILLANCE"' in source
    assert 'data["positions"] = positions' in source
    assert "_automatic_stop_exit(pos)" in source
    assert "run_lightweight_stop_surveillance(now=now)" in jobs_source
    assert 'surveillance["mode"] = "STOP_SURVEILLANCE"' in jobs_source


def test_lightweight_surveillance_executes_and_notifies_confirmed_exit() -> None:
    source = _source("super_portfolio.py")
    tree = ast.parse(source)
    wanted = {
        "_f", "_volatility", "dynamic_stop_levels", "_stop_status", "stop_pressure",
        "_automatic_stop_exit", "_stop_alerts", "run_lightweight_stop_surveillance",
    }
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]

    class Config:
        __dataclass_fields__ = {
            "hard_stop_drawdown_pct": None, "stop_surveillance_minutes": None,
            "risk_exit_cooldown_days": None,
        }

        def __init__(self, **values: object) -> None:
            self.hard_stop_drawdown_pct = float(values.get("hard_stop_drawdown_pct", 3.0))
            self.stop_surveillance_minutes = int(values.get("stop_surveillance_minutes", 15))
            self.risk_exit_cooldown_days = int(values.get("risk_exit_cooldown_days", 1))

    saved: list[dict] = []
    notified: list[list[dict]] = []
    namespace = {
        "Any": Any, "Mapping": Mapping, "Sequence": Sequence,
        "datetime": datetime, "timedelta": timedelta, "timezone": timezone,
        "isfinite": isfinite, "SuperPortfolioConfig": Config,
        "MAX_TRAILING_STOP_PCT": 3.0, "STOP_WARNING_PCT": 1.5, "STOP_NEAR_PCT": 2.25,
        "_coarse_market_snapshot": lambda tickers, market: {"VLO": {"last_price": 107.0}},
        "load_state": lambda: {}, "save_state": lambda value: saved.append(dict(value)),
        "append_event": lambda *args, **kwargs: None, "AUDIT_KEY": "audit", "AUDIT_PATH": "audit.jsonl",
        "_now": lambda: "2026-09-23T12:00:00+00:00",
        "portfolio_health": lambda rows: {"score": 0 if not rows else 100},
        "notify_stop_alerts": lambda alerts, state: (notified.append(list(alerts)) is None, "ok"),
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), "super_portfolio.py", "exec"), namespace)
    state = {
        "config": {"auto_pushover": True},
        "positions": {"VLO": {
            "ticker": "VLO", "entry_price": 100, "peak_price": 110, "last_price": 108,
            "target_weight_pct": 10, "stop_status": "WATCH", "portfolio_score": 70,
        }},
        "stop_surveillance_history": [{"positions": [{"ticker": "VLO", "distance_to_hard_stop_pct": 2.0}]}],
    }
    result = namespace["run_lightweight_stop_surveillance"](
        state=state, now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    )
    assert result["state"] == "COMPLETED"
    assert result["changes"][0]["reason_code"] == "CONFIRMED_EARLY_TRAILING_EXIT"
    assert saved[-1]["positions"] == {}
    assert notified and notified[0][0]["action"] == "SHADOW SELL UTFØRT"


def test_cron_routes_non_broad_cycles_to_lightweight_surveillance(monkeypatch) -> None:
    import super_portfolio as sp
    import super_portfolio_jobs as jobs

    monkeypatch.setattr(jobs, "recover_stale_job", lambda now=None: {"job_id": "SPJ-OLD", "state": "COMPLETED"})
    monkeypatch.setattr(jobs, "_scheduled_job_due", lambda now=None: (False, "NOT_DUE"))
    monkeypatch.setattr(sp, "run_lightweight_stop_surveillance", lambda now=None: {
        "state": "COMPLETED", "checked_positions": 3, "changes": [], "stop_alerts": [],
    })

    result = jobs.run_or_resume_scheduled_job(datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc))
    assert result["state"] == "COMPLETED"
    assert result["mode"] == "STOP_SURVEILLANCE"
    assert result["checked_positions"] == 3
    assert result["schedule_reason"] == "NOT_DUE"
