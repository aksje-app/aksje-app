"""Autonomous Learning Portfolio Foundation v18.6.88.

A fully isolated, theoretical portfolio that can execute simulated BUY, HOLD,
REDUCE and SELL decisions from the latest Investment Pipeline output. It uses a
fixed, user-controlled parameter set. Self-modifying parameters are explicitly
out of scope for this version.
"""
from __future__ import annotations

import io
import json
from copy import deepcopy
import math
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from services.strategy_binding import stamp_strategy_metadata
from services.market_snapshot_service import get_market_snapshot_service
from services.parallel_strategy_service import get_parallel_strategy_service
from services.strategy_account_service import get_strategy_account_service
from services.simulated_execution_service import get_simulated_execution_service
from services.autonomy_learning_account_service import get_autonomy_learning_account_service
from services.autonomy_activation_service import get_autonomy_activation_service
from services.evaluation_export_service import get_evaluation_export_service
from services.autonomy_technical_contribution_service import get_autonomy_technical_contribution_service

from storage_architecture import runtime_data_path
from persistent_config_store import read_persistent_json, write_persistent_json, persistence_status
from configuration_framework import export_bundle, import_bundle, status as configuration_status
from durable_runtime import append_event, read_events, read_json as durable_read_json, write_json as durable_write_json

from app_version import APP_VERSION

VERSION = APP_VERSION
ROOT = runtime_data_path("autonomous_portfolio")
PORTFOLIO_PATH = ROOT / "portfolio.json"
PARAMETERS_PATH = ROOT / "parameters.json"
TRADES_PATH = ROOT / "trades.json"
DECISIONS_PATH = ROOT / "decisions.json"
NOTIFICATIONS_PATH = ROOT / "notifications.json"
AUDIT_PATH = ROOT / "audit.jsonl"
PERFORMANCE_PATH = ROOT / "performance.json"
EQUITY_HISTORY_PATH = ROOT / "equity_history.json"
LEARNING_PORTFOLIO_PATH = ROOT / "learning_portfolio.json"
LEARNING_TRADES_PATH = ROOT / "learning_trades.json"
LEARNING_DECISIONS_PATH = ROOT / "learning_decisions.json"
LEARNING_EQUITY_HISTORY_PATH = ROOT / "learning_equity_history.json"
LEARNING_PERFORMANCE_PATH = ROOT / "learning_performance.json"
LEARNING_OBSERVATIONS_PATH = ROOT / "learning_observations.json"
LEGACY_MIXED_EQUITY_HISTORY_PATH = ROOT / "equity_history_pre_separation.json"
LATEST_PIPELINE_PATH = runtime_data_path("investment_pipeline") / "latest_run.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


_PERSISTENT_PATH_KEYS = {
    PARAMETERS_PATH: "autonomous_portfolio/parameters.json",
    PORTFOLIO_PATH: "autonomous_portfolio/portfolio.json",
    TRADES_PATH: "autonomous_portfolio/trades.json",
    DECISIONS_PATH: "autonomous_portfolio/decisions.json",
    NOTIFICATIONS_PATH: "autonomous_portfolio/notifications.json",
    PERFORMANCE_PATH: "autonomous_portfolio/performance.json",
    EQUITY_HISTORY_PATH: "autonomous_portfolio/equity_history.json",
    LEARNING_PORTFOLIO_PATH: "autonomous_portfolio/learning_portfolio.json",
    LEARNING_TRADES_PATH: "autonomous_portfolio/learning_trades.json",
    LEARNING_DECISIONS_PATH: "autonomous_portfolio/learning_decisions.json",
    LEARNING_EQUITY_HISTORY_PATH: "autonomous_portfolio/learning_equity_history.json",
    LEARNING_PERFORMANCE_PATH: "autonomous_portfolio/learning_performance.json",
    LEARNING_OBSERVATIONS_PATH: "autonomous_portfolio/learning_observations.json",
    LEGACY_MIXED_EQUITY_HISTORY_PATH: "autonomous_portfolio/equity_history_pre_separation.json",
    LATEST_PIPELINE_PATH: "investment_pipeline/latest_run.json",
}


def _read(path: Path, default: Any) -> Any:
    persistent_key = _PERSISTENT_PATH_KEYS.get(path)
    if persistent_key:
        return durable_read_json(persistent_key, path, default)
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if persistent_key:
                write_persistent_json(persistent_key, value)
            return value
    except Exception:
        pass
    return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
    persistent_key = _PERSISTENT_PATH_KEYS.get(path)
    if persistent_key:
        durable_write_json(persistent_key, path, value)


def _append_audit(event: str, payload: Mapping[str, Any]) -> None:
    row = {"timestamp": _now(), "version": VERSION, "event": event, "payload": dict(payload)}
    append_event("autonomous_portfolio/audit.jsonl", AUDIT_PATH, row)


def load_audit(limit: int = 1000) -> list[dict[str, Any]]:
    return read_events("autonomous_portfolio/audit.jsonl", AUDIT_PATH, limit=limit)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def production_buy_authorization(candidate: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Hard execution gate for ordinary Autonomi buys.

    A score can never authorize an order by itself. The completed candidate must
    explicitly be a Kjøpskandidat, have BUY as final portfolio action, and have
    both valid market data and decision-valid evidence.
    """
    reasons: list[str] = []
    outcome = str(candidate.get("autonomy_outcome_code") or "").upper()
    action = str(candidate.get("portfolio_action") or "").upper()
    if outcome != "KJØPSKANDIDAT":
        reasons.append("Autonomiutfallet er ikke Kjøpskandidat")
    if action not in {"BUY", "KJØP"}:
        reasons.append("Endelig porteføljehandling er ikke KJØP")
    if candidate.get("valid_for_decision") is not True:
        reasons.append("Markedsdata er ikke beslutningsgyldige")
    if candidate.get("evidence_valid_for_decision") is not True:
        reasons.append("Evidensgrunnlaget er ikke beslutningsgyldig")
    if candidate.get("final_decision_ready") is False:
        reasons.append("Kandidaten er ikke endelig kjøpsklar")
    return not reasons, reasons


def _validate_execution_integrity(
    trades: Sequence[Mapping[str, Any]], candidates: Mapping[str, Mapping[str, Any]],
    portfolio: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    actions_by_ticker: dict[str, set[str]] = {}
    for trade in trades:
        ticker = str(trade.get("ticker") or "").upper()
        action = str(trade.get("action") or "").upper()
        if not ticker or action not in {"BUY", "SELL"}:
            continue
        actions_by_ticker.setdefault(ticker, set()).add(action)
        if action == "BUY":
            allowed, reasons = production_buy_authorization(candidates.get(ticker, {}))
            if not allowed:
                errors.append(f"{ticker}: kjøp uten godkjent beslutningsport ({'; '.join(reasons)})")
            if ticker not in dict(portfolio.get("positions") or {}):
                errors.append(f"{ticker}: kjøp finnes ikke i sluttporteføljen")
        elif ticker in dict(portfolio.get("positions") or {}):
            errors.append(f"{ticker}: salg er registrert, men posisjonen står fortsatt åpen")
    for ticker, actions in actions_by_ticker.items():
        if {"BUY", "SELL"} <= actions:
            errors.append(f"{ticker}: både kjøp og salg i samme kjøring")
    return {
        "ok": not errors,
        "errors": errors,
        "ordinary_trade_count": len([row for row in trades if str(row.get("action") or "").upper() in {"BUY", "SELL"}]),
        "buy_tickers": sorted(t for t, actions in actions_by_ticker.items() if "BUY" in actions),
        "sell_tickers": sorted(t for t, actions in actions_by_ticker.items() if "SELL" in actions),
        "gate": "KJØPSKANDIDAT + KJØP + gyldige data + gyldig evidens",
    }


@dataclass
class AutonomousParameters:
    initial_cash: float = 500000.0
    minimum_investment_score: float = 73.0
    minimum_data_quality: float = 70.0
    maximum_risk_score: float = 65.0
    maximum_position_pct: float = 3.0
    maximum_sector_pct: float = 20.0
    maximum_open_positions: int = 20
    reserve_cash_pct: float = 10.0
    stop_loss_pct: float = 5.0
    trailing_stop_pct: float = 7.0
    take_profit_pct: float = 14.0
    score_exit_threshold: float = 55.0
    maximum_drawdown_pct: float = 12.0
    daily_loss_limit_pct: float = 4.0
    allow_additions: bool = False
    enable_learning_probe_buys: bool = True
    learning_probe_minimum_score: float = 63.0
    learning_probe_maximum_risk_score: float = 75.0
    learning_probe_max_buys: int = 3
    learning_probe_notional_value: float = 15000.0
    learning_probe_horizon_days: int = 60
    learning_policy_profile_version: str = "2.0"
    notify_trades: bool = True
    notify_risk_events: bool = True

    def normalized(self) -> "AutonomousParameters":
        return AutonomousParameters(
            initial_cash=max(1000.0, _f(self.initial_cash, 500000.0)),
            minimum_investment_score=max(0.0, min(100.0, _f(self.minimum_investment_score, 73.0))),
            minimum_data_quality=max(0.0, min(100.0, _f(self.minimum_data_quality, 70.0))),
            maximum_risk_score=max(0.0, min(100.0, _f(self.maximum_risk_score, 65.0))),
            maximum_position_pct=max(0.1, min(25.0, _f(self.maximum_position_pct, 3.0))),
            maximum_sector_pct=max(1.0, min(100.0, _f(self.maximum_sector_pct, 20.0))),
            maximum_open_positions=max(1, min(100, int(self.maximum_open_positions))),
            reserve_cash_pct=max(0.0, min(95.0, _f(self.reserve_cash_pct, 10.0))),
            stop_loss_pct=max(0.1, min(50.0, _f(self.stop_loss_pct, 5.0))),
            trailing_stop_pct=max(0.1, min(50.0, _f(self.trailing_stop_pct, 7.0))),
            take_profit_pct=max(0.1, min(300.0, _f(self.take_profit_pct, 14.0))),
            score_exit_threshold=max(0.0, min(100.0, _f(self.score_exit_threshold, 55.0))),
            maximum_drawdown_pct=max(0.5, min(80.0, _f(self.maximum_drawdown_pct, 12.0))),
            daily_loss_limit_pct=max(0.1, min(50.0, _f(self.daily_loss_limit_pct, 4.0))),
            allow_additions=bool(self.allow_additions),
            enable_learning_probe_buys=bool(self.enable_learning_probe_buys),
            learning_probe_minimum_score=max(60.0, min(65.0, _f(self.learning_probe_minimum_score, 63.0))),
            learning_probe_maximum_risk_score=max(0.0, min(75.0, _f(self.learning_probe_maximum_risk_score, 75.0))),
            learning_probe_max_buys=max(0, min(10, int(self.learning_probe_max_buys))),
            learning_probe_notional_value=max(100.0, min(100000.0, _f(self.learning_probe_notional_value, 15000.0))),
            learning_probe_horizon_days=max(1, min(365, int(self.learning_probe_horizon_days))),
            learning_policy_profile_version="2.0",
            notify_trades=bool(self.notify_trades),
            notify_risk_events=bool(self.notify_risk_events),
        )


def load_parameters() -> AutonomousParameters:
    raw = _read(PARAMETERS_PATH, {})
    try:
        values = {k: raw[k] for k in AutonomousParameters.__dataclass_fields__ if k in raw}
        if str(raw.get("learning_policy_profile_version") or "1.0") != "2.0":
            values.update({
                "enable_learning_probe_buys": True,
                "learning_probe_minimum_score": 63.0,
                "learning_probe_maximum_risk_score": 75.0,
                "learning_probe_max_buys": 3,
                "learning_probe_notional_value": 15000.0,
                "learning_probe_horizon_days": 60,
                "learning_policy_profile_version": "2.0",
            })
        loaded = AutonomousParameters(**values).normalized()
        legacy_signature = {
            "minimum_investment_score": 73.0,
            "minimum_data_quality": 55.0,
            "maximum_risk_score": 65.0,
            "maximum_position_pct": 3.0,
            "maximum_sector_pct": 20.0,
            "maximum_open_positions": 30.0,
            "reserve_cash_pct": 5.0,
            "stop_loss_pct": 3.5,
            "trailing_stop_pct": 4.5,
            "take_profit_pct": 14.0,
        }
        if raw and all(
            key in raw and abs(_f(raw.get(key), expected) - expected) < 0.0001
            for key, expected in legacy_signature.items()
        ):
            migrated = recommended_production_profile(loaded)
            _write(PARAMETERS_PATH, asdict(migrated))
            _append_audit("PARAMETERS_MIGRATED_RC16_31H", {
                "reason": "Kjent eldre produksjonsprofil hadde for lav datakvalitet, reserve og tapsmarginer.",
                "before": asdict(loaded),
                "after": asdict(migrated),
            })
            return migrated
        return loaded
    except Exception:
        return AutonomousParameters()


def save_parameters(params: AutonomousParameters) -> AutonomousParameters:
    params = params.normalized()
    previous = _read(PARAMETERS_PATH, {})
    _write(PARAMETERS_PATH, asdict(params))
    if previous and previous != asdict(params):
        _append_audit("PARAMETERS_CHANGED_BY_USER", {"before": previous, "after": asdict(params)})
    return params


def recommended_production_profile(current: AutonomousParameters) -> AutonomousParameters:
    """Return the reviewed production profile without changing reset capital or notifications."""
    return AutonomousParameters(
        initial_cash=current.initial_cash,
        minimum_investment_score=73.0,
        minimum_data_quality=70.0,
        maximum_risk_score=65.0,
        maximum_position_pct=3.0,
        maximum_sector_pct=20.0,
        maximum_open_positions=20,
        reserve_cash_pct=10.0,
        stop_loss_pct=5.0,
        trailing_stop_pct=7.0,
        take_profit_pct=14.0,
        score_exit_threshold=55.0,
        maximum_drawdown_pct=12.0,
        daily_loss_limit_pct=current.daily_loss_limit_pct,
        allow_additions=current.allow_additions,
        enable_learning_probe_buys=current.enable_learning_probe_buys,
        learning_probe_minimum_score=current.learning_probe_minimum_score,
        learning_probe_maximum_risk_score=current.learning_probe_maximum_risk_score,
        learning_probe_max_buys=current.learning_probe_max_buys,
        learning_probe_notional_value=current.learning_probe_notional_value,
        learning_probe_horizon_days=current.learning_probe_horizon_days,
        learning_policy_profile_version=current.learning_policy_profile_version,
        notify_trades=current.notify_trades,
        notify_risk_events=current.notify_risk_events,
    ).normalized()



RC16_RECOMMENDED_LEARNING_NOTIONAL = 15000.0
RC16_RECOMMENDED_LEARNING_MAX_BUYS = 3
RC16_RECOMMENDED_LEARNING_HORIZON_DAYS = 60
RC16_RECOMMENDED_LEARNING_MINIMUM_SCORE = 63.0
RC16_RECOMMENDED_LEARNING_MAXIMUM_RISK = 75.0


def recommended_learning_profile(params: AutonomousParameters | None = None) -> AutonomousParameters:
    """Return the explicit RC16 learning-only profile without persisting it.

    Existing installations keep their stored values until the operator presses
    the dedicated confirmation button in the UI.  The profile never changes
    ordinary Autonomy position limits or production-trading authorization.
    """
    current = (params or load_parameters()).normalized()
    values = asdict(current)
    values.update({
        "enable_learning_probe_buys": True,
        "learning_probe_minimum_score": RC16_RECOMMENDED_LEARNING_MINIMUM_SCORE,
        "learning_probe_maximum_risk_score": RC16_RECOMMENDED_LEARNING_MAXIMUM_RISK,
        "learning_probe_notional_value": RC16_RECOMMENDED_LEARNING_NOTIONAL,
        "learning_probe_max_buys": RC16_RECOMMENDED_LEARNING_MAX_BUYS,
        "learning_probe_horizon_days": RC16_RECOMMENDED_LEARNING_HORIZON_DAYS,
        "learning_policy_profile_version": "2.0",
    })
    return AutonomousParameters(**values).normalized()

def default_portfolio(params: AutonomousParameters | None = None) -> dict[str, Any]:
    p = (params or load_parameters()).normalized()
    return {
        "version": VERSION,
        "account_id": "AUTONOMOUS-LEARNING-PORTFOLIO",
        "mode": "THEORETICAL_ONLY",
        "status": "PAUSED",
        "created_at": _now(),
        "updated_at": _now(),
        "initial_cash": p.initial_cash,
        "cash": p.initial_cash,
        "positions": {},
        "realized_pnl": 0.0,
        "high_watermark": p.initial_cash,
        "last_equity": p.initial_cash,
        "last_run_id": None,
        "pause_reason": "Ikke aktivert av bruker",
    }


def default_learning_portfolio(params: AutonomousParameters | None = None) -> dict[str, Any]:
    p = (params or load_parameters()).normalized()
    return {
        "version": VERSION,
        "account_id": "AUTONOMY-LEARNING-OBSERVATION-PORTFOLIO",
        "mode": "LEARNING_ONLY",
        "status": "ACTIVE" if p.enable_learning_probe_buys else "PAUSED",
        "created_at": _now(),
        "updated_at": _now(),
        "positions": {},
        "closed_positions": [],
        "realized_pnl": 0.0,
        "total_entry_notional": 0.0,
        "last_run_id": None,
        "purpose": "Skyggeposisjoner for læring. Påvirker ikke autonom portefølje, kontanter, risiko eller posisjonsgrenser.",
    }


def _split_legacy_learning_rows(primary_path: Path, learning_path: Path) -> None:
    primary_rows = _read(primary_path, [])
    learning_rows = _read(learning_path, [])
    if not isinstance(primary_rows, list):
        primary_rows = []
    if not isinstance(learning_rows, list):
        learning_rows = []
    existing_ids = {str(r.get("trade_id") or r.get("decision_id") or "") for r in learning_rows if isinstance(r, Mapping)}
    keep, moved = [], []
    for row in primary_rows:
        if isinstance(row, Mapping) and row.get("learning_probe"):
            key = str(row.get("trade_id") or row.get("decision_id") or "")
            if not key or key not in existing_ids:
                moved.append(dict(row))
        else:
            keep.append(row)
    if moved:
        _write(primary_path, keep)
        _write(learning_path, moved + learning_rows)


def ensure_portfolio_separation() -> dict[str, int]:
    """Migrate legacy learning probes out of the ordinary autonomous portfolio.

    v19.0.18 stored learning probes as normal positions and deducted their value
    from ordinary portfolio cash. v19.0.18b separates the ledgers and restores
    the exact cost basis to the ordinary theoretical portfolio. The migration is
    idempotent and leaves an explicit audit record.
    """
    params = load_parameters()
    primary = _read(PORTFOLIO_PATH, None)
    primary_created = not isinstance(primary, dict)
    if primary_created:
        primary = default_portfolio(params)
    learning = _read(LEARNING_PORTFOLIO_PATH, None)
    learning_created = not isinstance(learning, dict)
    if learning_created:
        learning = default_learning_portfolio(params)
    primary.setdefault("positions", {})
    learning.setdefault("positions", {})
    moved = 0
    restored = 0.0
    for ticker, raw in list(primary["positions"].items()):
        position = dict(raw) if isinstance(raw, Mapping) else {}
        if not position.get("learning_probe"):
            continue
        entry_value = _f(position.get("quantity")) * _f(position.get("average_price"))
        position["portfolio_type"] = "LEARNING"
        position["origin"] = position.get("origin") or "AUTONOMY_LEARNING_PROBE"
        position["migrated_from_primary_at"] = _now()
        learning["positions"][ticker] = position
        del primary["positions"][ticker]
        primary["cash"] = _f(primary.get("cash")) + entry_value
        learning["total_entry_notional"] = _f(learning.get("total_entry_notional")) + entry_value
        restored += entry_value
        moved += 1
    if moved:
        primary["updated_at"] = _now()
        learning["updated_at"] = _now()
        ordinary_equity = _f(primary.get("cash")) + sum(
            _f(pos.get("quantity")) * _f(pos.get("last_price", pos.get("average_price")))
            for pos in (primary.get("positions") or {}).values()
        )
        primary["last_equity"] = ordinary_equity
        primary["high_watermark"] = max(_f(primary.get("initial_cash"), ordinary_equity), ordinary_equity)
        legacy_history = _read(EQUITY_HISTORY_PATH, [])
        if isinstance(legacy_history, list) and legacy_history and not _read(LEGACY_MIXED_EQUITY_HISTORY_PATH, []):
            _write(LEGACY_MIXED_EQUITY_HISTORY_PATH, legacy_history)
            _write(EQUITY_HISTORY_PATH, [])
        _write(PORTFOLIO_PATH, primary)
        _write(LEARNING_PORTFOLIO_PATH, learning)
        _split_legacy_learning_rows(TRADES_PATH, LEARNING_TRADES_PATH)
        _split_legacy_learning_rows(DECISIONS_PATH, LEARNING_DECISIONS_PATH)
        _write(PERFORMANCE_PATH, calculate_performance(primary))
        _write(LEARNING_PERFORMANCE_PATH, learning_portfolio_performance(learning))
        _append_audit("LEARNING_PORTFOLIO_SEPARATED", {"positions_moved": moved, "cash_restored": round(restored, 2), "ordinary_equity_reset": round(ordinary_equity, 2), "legacy_history_archived": bool(legacy_history)})
    else:
        if primary_created:
            _write(PORTFOLIO_PATH, primary)
        if learning_created:
            _write(LEARNING_PORTFOLIO_PATH, learning)
    return {"positions_moved": moved, "cash_restored": round(restored, 2)}


def load_portfolio() -> dict[str, Any]:
    ensure_portfolio_separation()
    params = load_parameters()
    value = _read(PORTFOLIO_PATH, None)
    if not isinstance(value, dict):
        value = default_portfolio(params)
        _write(PORTFOLIO_PATH, value)
    value.setdefault("positions", {})
    value["positions"] = _normalise_runtime_positions(value.get("positions"))
    return value


def load_learning_portfolio() -> dict[str, Any]:
    ensure_portfolio_separation()
    params = load_parameters()
    value = _read(LEARNING_PORTFOLIO_PATH, None)
    if not isinstance(value, dict):
        value = default_learning_portfolio(params)
        _write(LEARNING_PORTFOLIO_PATH, value)
    value.setdefault("positions", {})
    value["positions"] = _normalise_runtime_positions(value.get("positions"))
    value.setdefault("closed_positions", [])
    return value


def _normalise_runtime_positions(value: Any) -> dict[str, dict[str, Any]]:
    """Normalise legacy/null numeric portfolio state before comparisons."""
    if not isinstance(value, Mapping):
        return {}
    numeric_defaults = {
        "quantity": 0.0, "average_price": 0.0, "last_price": 0.0,
        "highest_price": 0.0, "entry_score": 0.0, "entry_risk_score": 100.0,
        "entry_data_quality": 0.0, "observation_days": 0.0,
        "observation_horizon_days": 60.0,
    }
    result: dict[str, dict[str, Any]] = {}
    for ticker, raw in value.items():
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        for key, default in numeric_defaults.items():
            row[key] = _f(row.get(key), default)
        result[str(ticker).upper()] = row
    return result


def candidate_price(candidate: Mapping[str, Any], existing: Mapping[str, Any] | None = None) -> float:
    """Resolve the canonical execution price used by every purchase gate."""
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    for key in ("price", "current_price", "last_price", "close", "regularMarketPrice", "last"):
        value = _f(candidate.get(key, raw.get(key)), 0.0)
        if value > 0:
            return value
    if existing:
        value = _f(existing.get("last_price", existing.get("average_price")), 0.0)
        if value > 0:
            return value
    return 0.0


# Backwards-compatible private name used by the established execution engine.
_candidate_price = candidate_price


def _candidate_score(candidate: Mapping[str, Any], default: float = 0.0) -> float:
    """Original Autonomi score. Existing-position exits remain bound to this score."""
    for key in ("autonomy_base_investment_score", "investment_score", "score", "combined_score", "decision_score"):
        value = _f(candidate.get(key), float("nan"))
        if math.isfinite(value):
            return value
    return default


def _candidate_entry_score(candidate: Mapping[str, Any], default: float = 0.0) -> float:
    """Entry-only score after the bounded v19.9.0 technical contribution."""
    value = _f(candidate.get("autonomy_adjusted_investment_score"), float("nan"))
    return value if math.isfinite(value) else _candidate_score(candidate, default)


def _technical_contribution_metadata(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    row = dict(candidate or {})
    keys = (
        "autonomy_base_investment_score", "autonomy_adjusted_investment_score",
        "technical_contribution_points", "technical_contribution_applied",
        "technical_contribution_reason", "technical_score_100",
        "technical_signal_action", "technical_signal_raw_decision",
        "technical_signal_confidence", "technical_timing", "technical_entry_wait",
        "technical_entry_wait_reason", "technical_strategy_version_id",
        "technical_strategy_version", "technical_model_version",
        "technical_parameter_version", "technical_contribution_policy_version",
        "technical_contribution_service_version", "technical_hard_gates_unchanged",
        "technical_can_authorize_execution",
    )
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "")}


def _paper_learning_signal(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a compact, non-authorising Paper signal for learning decisions."""
    paper = dict((candidate or {}).get("paper_engine_input") or {})
    decisions = [
        dict(row) for row in list(paper.get("technical_decisions") or [])
        if isinstance(row, Mapping)
    ]
    actions = [str(row.get("action") or row.get("raw_decision") or "").upper() for row in decisions]
    action = "BUY" if any(value in {"BUY", "KJØP"} for value in actions) else "SELL" if any(value in {"SELL", "SALG"} for value in actions) else "NEUTRAL"
    confidence = max((_f(row.get("confidence")) for row in decisions), default=0.0)
    return {
        "paper_signal_available": bool(decisions),
        "paper_signal_action": action,
        "paper_signal_confidence": confidence,
        "paper_signal_source_run_id": paper.get("source_run_id") or paper.get("run_id"),
        "paper_signal_execution_authorized": False,
    }


def _production_blockers_for_learning(candidate: Mapping[str, Any], params: "AutonomousParameters") -> list[str]:
    """Freeze why the same candidate was not a production buy at learning entry."""
    blockers = list(production_buy_authorization(candidate)[1])
    score = _candidate_entry_score(candidate)
    risk = _candidate_risk(candidate)
    quality = _candidate_quality(candidate)
    if score < params.minimum_investment_score:
        blockers.append(f"Produksjonsscore {score:.1f} under {params.minimum_investment_score:.1f}")
    if risk > params.maximum_risk_score:
        blockers.append(f"Produksjonsrisiko {risk:.1f} over {params.maximum_risk_score:.1f}")
    if quality < params.minimum_data_quality:
        blockers.append(f"Produksjonsdatakvalitet {quality:.1f} under {params.minimum_data_quality:.1f}")
    return list(dict.fromkeys(blockers))


LEARNING_OUTCOME_HORIZONS = (5, 10, 20, 60)


def load_learning_observations(limit: int = 5000) -> list[dict[str, Any]]:
    """Return isolated, non-trading candidate observations.

    These rows are evidence for controlled learning only. They never reserve
    cash, create an order, or enter either the ordinary or Paper portfolio.
    """
    rows = _read(LEARNING_OBSERVATIONS_PATH, [])
    return [dict(row) for row in rows[:max(0, limit)] if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _update_candidate_observations(
    candidates: Sequence[Mapping[str, Any]], decisions: Sequence[Mapping[str, Any]],
    run_id: str, market_snapshot: Mapping[str, Any] | None,
) -> dict[str, int]:
    rows = load_learning_observations()
    params = load_parameters().normalized()
    # Production decisions are passed first and must win over an optional
    # LEARNING_ONLY decision for the same ticker.
    decision_by_ticker: dict[str, dict[str, Any]] = {}
    for row in decisions:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").upper()
        if ticker and ticker not in decision_by_ticker:
            decision_by_ticker[ticker] = dict(row)
    candidate_by_ticker = {
        str(row.get("ticker") or "").upper(): dict(row) for row in candidates if isinstance(row, Mapping) and row.get("ticker")
    }
    today = str((market_snapshot or {}).get("market_date") or (market_snapshot or {}).get("as_of_date") or _now()[:10])[:10]
    updated = matured = 0
    # Update every still-open cohort with a current price when the ticker is present.
    for obs in rows:
        if obs.get("status") == "CLOSED":
            continue
        candidate = candidate_by_ticker.get(str(obs.get("ticker") or "").upper())
        if not candidate:
            continue
        price = _candidate_price(candidate)
        if price <= 0:
            continue
        dates = list(obs.get("evaluation_dates") or [])
        if today and today not in dates:
            dates.append(today)
        obs["evaluation_dates"] = dates[-120:]
        obs["observation_days"] = len(dates)
        obs["last_price"] = round(price, 4)
        obs["last_evaluated_at"] = _now()
        entry = _f(obs.get("entry_price"), price)
        obs["highest_price"] = round(max(_f(obs.get("highest_price"), entry), price), 4)
        obs["lowest_price"] = round(min(_f(obs.get("lowest_price"), entry), price), 4)
        obs["maximum_gain_pct"] = round((obs["highest_price"] / entry - 1) * 100, 4) if entry else 0.0
        obs["maximum_drawdown_pct"] = round((obs["lowest_price"] / entry - 1) * 100, 4) if entry else 0.0
        current_return = round((price / entry - 1) * 100, 4) if entry else 0.0
        peak_drawdown = round((price / _f(obs.get("highest_price"), price) - 1) * 100, 4)
        simulated_exits = dict(obs.get("simulated_exit_outcomes") or {})
        exit_rules = (
            ("STOP_LOSS", current_return <= -params.stop_loss_pct, f"Avkastning {current_return:.2f}% <= -{params.stop_loss_pct:.2f}%"),
            ("TAKE_PROFIT", current_return >= params.take_profit_pct, f"Avkastning {current_return:.2f}% >= {params.take_profit_pct:.2f}%"),
            ("TRAILING_STOP", peak_drawdown <= -params.trailing_stop_pct, f"Fall fra topp {peak_drawdown:.2f}% <= -{params.trailing_stop_pct:.2f}%"),
        )
        for rule, triggered, reason in exit_rules:
            if triggered and rule not in simulated_exits:
                simulated_exits[rule] = {
                    "triggered_at": _now(), "market_date": today,
                    "price": round(price, 4), "return_pct": current_return,
                    "reason": reason, "production_applied": False,
                }
        obs["simulated_exit_outcomes"] = simulated_exits
        measurements = list(obs.get("outcome_measurements") or [])
        measured = {int(item.get("horizon_days") or 0) for item in measurements if isinstance(item, Mapping)}
        for horizon in LEARNING_OUTCOME_HORIZONS:
            if len(dates) >= horizon and horizon not in measured:
                measurements.append({
                    "horizon_days": horizon, "measured_at": _now(), "market_date": today,
                    "price": round(price, 4),
                    "return_pct": round((price / entry - 1) * 100, 4) if entry else 0.0,
                    "maximum_gain_pct": obs["maximum_gain_pct"],
                    "maximum_drawdown_pct": obs["maximum_drawdown_pct"],
                })
                matured += 1
        obs["outcome_measurements"] = measurements
        if 60 in {int(item.get("horizon_days") or 0) for item in measurements if isinstance(item, Mapping)}:
            obs["status"] = "MATURED"
        updated += 1
    # One cohort per ticker and source run; retries are therefore idempotent.
    existing = {(str(row.get("ticker") or "").upper(), str(row.get("source_run_id") or "")) for row in rows}
    created = 0
    for ticker, candidate in candidate_by_ticker.items():
        if (ticker, run_id) in existing:
            continue
        price = _candidate_price(candidate)
        if price <= 0:
            continue
        decision = decision_by_ticker.get(ticker, {})
        action = str(decision.get("action") or "OBSERVE").upper()
        outcome = "PRODUCTION_BUY" if action == "BUY" else ("MONITOR" if action in {"WAIT", "HOLD", "OBSERVE"} else "REJECTED")
        rows.insert(0, {
            "observation_id": f"LO-{run_id}-{ticker}", "ticker": ticker, "created_at": _now(),
            "source_run_id": run_id, "program_version": APP_VERSION, "status": "OPEN",
            "decision_outcome": outcome, "decision_action": action,
            "decision_reason": str(decision.get("reason") or "Ingen eksplisitt beslutningsrad"),
            "entry_price": round(price, 4), "last_price": round(price, 4),
            "highest_price": round(price, 4), "lowest_price": round(price, 4),
            "maximum_gain_pct": 0.0, "maximum_drawdown_pct": 0.0,
            "entry_score": round(_candidate_entry_score(candidate), 2),
            "entry_risk": round(_candidate_risk(candidate), 2),
            "entry_data_quality": round(_candidate_quality(candidate), 2),
            "evidence_valid_at_entry": candidate.get("evidence_valid_for_decision") is True,
            "evaluation_dates": [today] if today else [], "observation_days": 1 if today else 0,
            "outcome_measurements": [], "production_applied": False,
            "simulated_exit_outcomes": {},
            **_candidate_snapshot_metadata(candidate, market_snapshot),
        })
        created += 1
    # Keep detailed recent cohorts bounded; matured aggregate evidence remains in each row.
    _write(LEARNING_OBSERVATIONS_PATH, rows[:2000])
    return {"created": created, "updated": updated, "matured_measurements": matured, "total": min(len(rows), 2000)}


def _record_learning_outcome_measurement(position: dict[str, Any], candidate: Mapping[str, Any], price: float) -> None:
    """Store one mark per observed market date and immutable horizon measurements."""
    market_date = str(
        candidate.get("market_date") or candidate.get("price_date") or
        candidate.get("as_of_date") or candidate.get("trading_date") or _now()[:10]
    )[:10]
    dates = list(position.get("evaluation_dates") or [])
    if market_date and market_date not in dates:
        dates.append(market_date)
    position["evaluation_dates"] = dates[-120:]
    position["observation_days"] = len(dates)
    entry = _f(position.get("average_price"), price)
    measured = {int(row.get("horizon_days") or 0) for row in list(position.get("outcome_measurements") or []) if isinstance(row, Mapping)}
    for horizon in LEARNING_OUTCOME_HORIZONS:
        if len(dates) >= horizon and horizon not in measured:
            position.setdefault("outcome_measurements", []).append({
                "horizon_days": horizon,
                "measured_at": _now(),
                "market_date": market_date,
                "price": round(price, 4),
                "return_pct": round((price / entry - 1) * 100, 4) if entry else 0.0,
                "score": round(_candidate_score(candidate, _f(position.get("entry_score"))), 2),
            })


def _candidate_quality(candidate: Mapping[str, Any], default: float = 100.0) -> float:
    raw = candidate.get("combined_data_quality") if isinstance(candidate.get("combined_data_quality"), Mapping) else {}
    evidence = candidate.get("evidence_coverage") if isinstance(candidate.get("evidence_coverage"), Mapping) else {}
    for value in (
        candidate.get("data_quality_score"),
        candidate.get("data_quality"),
        raw.get("score"), raw.get("quality"),
        evidence.get("score"), evidence.get("coverage_pct"),
        candidate.get("confidence_score"),
    ):
        number = _f(value, float("nan"))
        if math.isfinite(number):
            return max(0.0, min(100.0, number))
    return default


def _candidate_risk(candidate: Mapping[str, Any], default: float = 40.0) -> float:
    for key in ("risk_score", "portfolio_risk", "risk"):
        value = _f(candidate.get(key), float("nan"))
        if math.isfinite(value):
            return max(0.0, min(100.0, value))
    return default


def _candidate_strategy(candidate: Mapping[str, Any]) -> str:
    strategy = candidate.get("strategy_match") or candidate.get("strategy")
    if not strategy and isinstance(candidate.get("strategy_matches"), list) and candidate.get("strategy_matches"):
        strategy = candidate.get("strategy_matches")[0]
    return str(strategy or "Learning Probe")

def _candidate_snapshot_metadata(candidate: Mapping[str, Any] | None, market_snapshot: Mapping[str, Any] | None = None) -> dict[str, Any]:
    candidate = dict(candidate or {})
    market_snapshot = dict(market_snapshot or {})
    return {
        "market_snapshot_id": str(candidate.get("market_snapshot_id") or market_snapshot.get("snapshot_id") or ""),
        "candidate_snapshot_id": str(candidate.get("candidate_snapshot_id") or ""),
        "snapshot_checksum": str(candidate.get("snapshot_checksum") or candidate.get("checksum") or ""),
        "snapshot_schema_version": str(candidate.get("snapshot_schema_version") or candidate.get("schema_version") or ""),
        "market_snapshot_checksum": str(market_snapshot.get("checksum") or ""),
    }


def _attach_snapshot_metadata(rows: Sequence[Mapping[str, Any]], candidate_map: Mapping[str, Mapping[str, Any]], market_snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw or {})
        ticker = str(row.get("ticker") or "").upper()
        for key, value in _candidate_snapshot_metadata(candidate_map.get(ticker), market_snapshot).items():
            if value:
                row.setdefault(key, value)
        output.append(row)
    return output


def _append_equity_history(portfolio: Mapping[str, Any], run_id: str, *, trades: int, decisions: int) -> None:
    history = _read(EQUITY_HISTORY_PATH, [])
    if not isinstance(history, list):
        history = []
    equity = portfolio_equity(portfolio)
    history.insert(0, {
        "timestamp": _now(), "run_id": run_id, "equity": round(equity, 2),
        "cash": round(_f(portfolio.get("cash")), 2),
        "open_positions": len(portfolio.get("positions") or {}),
        "total_return_pct": round((equity / max(_f(portfolio.get("initial_cash"), 1.0), 1.0) - 1) * 100, 4),
        "trades": trades, "decisions": decisions, "mode": "THEORETICAL_ONLY",
    })
    _write(EQUITY_HISTORY_PATH, history[:2000])


def load_equity_history(limit: int = 200) -> list[dict[str, Any]]:
    rows = _read(EQUITY_HISTORY_PATH, [])
    return list(rows[:limit]) if isinstance(rows, list) else []


def learning_portfolio_performance(portfolio: Mapping[str, Any] | None = None) -> dict[str, Any]:
    portfolio = dict(portfolio or load_learning_portfolio())
    positions = portfolio.get("positions") or {}
    entry_open = sum(_f(p.get("quantity")) * _f(p.get("average_price")) for p in positions.values())
    current_open = sum(_f(p.get("quantity")) * _f(p.get("last_price", p.get("average_price"))) for p in positions.values())
    unrealized = current_open - entry_open
    realized = _f(portfolio.get("realized_pnl"))
    total_entry = max(_f(portfolio.get("total_entry_notional")), entry_open)
    total_pnl = realized + unrealized
    return {
        "updated_at": _now(), "open_positions": len(positions),
        "entry_notional": round(entry_open, 2), "current_value": round(current_open, 2),
        "unrealized_pnl": round(unrealized, 2), "realized_pnl": round(realized, 2),
        "total_pnl": round(total_pnl, 2),
        "return_pct": round(total_pnl / total_entry * 100, 2) if total_entry else 0.0,
        "total_observations": len(positions) + len(portfolio.get("closed_positions") or []),
    }


def _append_learning_equity_history(portfolio: Mapping[str, Any], run_id: str, *, trades: int, decisions: int) -> None:
    history = _read(LEARNING_EQUITY_HISTORY_PATH, [])
    if not isinstance(history, list):
        history = []
    perf = learning_portfolio_performance(portfolio)
    history.insert(0, {"timestamp": _now(), "run_id": run_id, **perf, "trades": trades, "decisions": decisions, "mode": "LEARNING_ONLY"})
    _write(LEARNING_EQUITY_HISTORY_PATH, history[:2000])


def load_learning_equity_history(limit: int = 200) -> list[dict[str, Any]]:
    rows = _read(LEARNING_EQUITY_HISTORY_PATH, [])
    return list(rows[:limit]) if isinstance(rows, list) else []


def _record_learning_trade(trade: dict[str, Any]) -> None:
    trade = stamp_strategy_metadata(trade, "autonomy")
    trade.setdefault("strategy_role", "LEARNING_PORTFOLIO")
    rows = _read(LEARNING_TRADES_PATH, [])
    if not isinstance(rows, list):
        rows = []
    rows.insert(0, trade)
    _write(LEARNING_TRADES_PATH, rows)
    _append_audit("LEARNING_SIMULATED_TRADE", trade)


def _record_learning_decisions(rows: Sequence[Mapping[str, Any]]) -> None:
    current = _read(LEARNING_DECISIONS_PATH, [])
    if not isinstance(current, list):
        current = []
    normalized = []
    for raw in rows:
        row = stamp_strategy_metadata(raw, "autonomy")
        row.setdefault("strategy_role", "LEARNING_PORTFOLIO")
        normalized.append(row)
    _write(LEARNING_DECISIONS_PATH, normalized + current[:5000])


def _days_opened(value: Any) -> int:
    try:
        opened = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - opened.astimezone(timezone.utc)).days)
    except Exception:
        return 0


def _close_learning_position(portfolio: dict[str, Any], ticker: str, price: float, reason: str, run_id: str) -> dict[str, Any] | None:
    pos = (portfolio.get("positions") or {}).get(ticker)
    if not pos or price <= 0:
        return None
    quantity = _f(pos.get("quantity"))
    entry = _f(pos.get("average_price"), price)
    pnl = quantity * (price - entry)
    portfolio["realized_pnl"] = _f(portfolio.get("realized_pnl")) + pnl
    closed = {**dict(pos), "closed_at": _now(), "close_price": price, "close_reason": reason, "pnl": round(pnl, 2), "pnl_pct": round((price / entry - 1) * 100, 2) if entry else 0.0}
    portfolio.setdefault("closed_positions", []).insert(0, closed)
    del portfolio["positions"][ticker]
    trade = {
        "trade_id": f"LT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", "timestamp": _now(), "run_id": run_id,
        "action": "SELL", "ticker": ticker, "price": round(price, 4), "quantity": round(quantity, 8),
        "value": round(quantity * price, 2), "pnl": round(pnl, 2), "pnl_pct": closed["pnl_pct"],
        "reason": reason, "strategy": pos.get("strategy"), "mode": "LEARNING_ONLY", "learning_probe": True,
        **_candidate_snapshot_metadata(pos),
    }
    _record_learning_trade(trade)
    return trade


def _update_learning_positions(portfolio: dict[str, Any], candidate_map: Mapping[str, Mapping[str, Any]], run_id: str, params: AutonomousParameters) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    for ticker, pos in list((portfolio.get("positions") or {}).items()):
        candidate = candidate_map.get(ticker, {})
        if not candidate:
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": "Ikke med i dagens kandidatsett; siste markering beholdes", "learning_probe": True})
            continue
        price = _candidate_price(candidate, pos)
        if price <= 0:
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": "Mangler ny pris; læringsposisjonen beholdes", "learning_probe": True})
            continue
        pos["last_price"] = price
        pos["highest_price"] = max(_f(pos.get("highest_price"), price), price)
        pos["last_evaluated_at"] = _now()
        _record_learning_outcome_measurement(pos, candidate, price)
        avg = _f(pos.get("average_price"), price)
        score = _candidate_score(candidate, _f(pos.get("entry_score"), 100.0))
        age = _days_opened(pos.get("opened_at"))
        reason = None
        if price <= avg * (1 - params.stop_loss_pct / 100):
            reason = "Læringsobservasjon: stop loss"
        elif price <= _f(pos.get("highest_price"), price) * (1 - params.trailing_stop_pct / 100):
            reason = "Læringsobservasjon: trailing stop"
        elif price >= avg * (1 + params.take_profit_pct / 100):
            reason = "Læringsobservasjon: gevinstmål"
        elif _paper_learning_signal(candidate)["paper_signal_action"] == "SELL":
            reason = "Læringsobservasjon: Paper-motoren ga salgssignal"
        elif candidate and score < params.score_exit_threshold:
            reason = f"Læringsobservasjon: score falt til {score:.1f}"
        elif age >= params.learning_probe_horizon_days:
            reason = f"Læringshorisont {params.learning_probe_horizon_days} dager fullført"
        if reason:
            trade = _close_learning_position(portfolio, ticker, price, reason, run_id)
            if trade:
                trades.append(trade)
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "CLOSE_OBSERVATION", "reason": reason, "price": price, "score": score, "learning_probe": True})
        else:
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": f"Følges videre; dag {age}/{params.learning_probe_horizon_days}", "price": price, "score": score, "learning_probe": True})
    return decisions, trades


def portfolio_status_summary(latest_chain: Mapping[str, Any] | None = None) -> dict[str, Any]:
    portfolio = load_portfolio()
    learning_portfolio = load_learning_portfolio()
    params = load_parameters()
    latest_chain = dict(latest_chain or {})
    stages = latest_chain.get("stages") if isinstance(latest_chain.get("stages"), list) else []
    market = next((s for s in stages if s.get("name") == "MARKET_SCAN"), {})
    auto = next((s for s in stages if s.get("name") == "AUTONOMOUS_PORTFOLIO"), {})
    market_detail = market.get("detail") if isinstance(market.get("detail"), Mapping) else {}
    auto_detail = auto.get("detail") if isinstance(auto.get("detail"), Mapping) else {}
    handoff = market_detail.get("handoff_input") if isinstance(market_detail.get("handoff_input"), Mapping) else {}
    received = int(market_detail.get("candidates") or handoff.get("forwarded_candidates") or 0)
    total_buys = int(auto_detail.get("buys") or 0)
    learning_buys = int(auto_detail.get("learning_buys") or 0)
    ordinary_buys = int(auto_detail.get("ordinary_buys") if auto_detail.get("ordinary_buys") is not None else max(0, total_buys - learning_buys))
    reason = str(auto_detail.get("reason") or auto_detail.get("warning") or auto.get("status") or "Ingen siste kjøring")
    if received == 0:
        reason = str(auto_detail.get("reason") or "Ingen kandidater fra skanning")
    elif ordinary_buys == 0 and learning_buys:
        reason = "Ingen ordinære porteføljekjøp; læringsposisjoner ble opprettet separat"
    elif ordinary_buys:
        reason = "Ordinære teoretiske porteføljekjøp opprettet"
    return {
        "Autonomi-runner": "Aktiv" if portfolio.get("status") == "ACTIVE" else "Pauset",
        "Planlegger": "Aktiv" if latest_chain else "Ukjent",
        "Paper trading": "Aktiv",
        "Ekte handel": "Deaktivert",
        "Kandidater mottatt": received,
        "Ordinære porteføljekjøp": ordinary_buys,
        "Læringsposisjoner opprettet": learning_buys,
        "Teoretiske kjøp": ordinary_buys,
        "Læringskjøp": learning_buys,
        "Åpne autonome posisjoner": len(portfolio.get("positions") or {}),
        "Åpne læringsposisjoner": len(learning_portfolio.get("positions") or {}),
        "Årsak til ingen kjøp": reason,
        "Minimum ordinær score": params.minimum_investment_score,
        "Minimum læringsscore": params.learning_probe_minimum_score,
        "Maksimal læringsrisiko": params.learning_probe_maximum_risk_score,
        "Læringskjøp aktivert": bool(params.enable_learning_probe_buys),
        "Replaystatus siste kjøring": str(auto_detail.get("replay_level") or "Ikke registrert"),
        "Replaymangler": list(auto_detail.get("full_replay_missing") or []),
    }


def portfolio_equity(portfolio: Mapping[str, Any]) -> float:
    positions = portfolio.get("positions") or {}
    market_value = sum(_f(p.get("quantity")) * _f(p.get("last_price", p.get("average_price"))) for p in positions.values())
    return _f(portfolio.get("cash")) + market_value


def _sector_value(portfolio: Mapping[str, Any], sector: str) -> float:
    return sum(
        _f(p.get("quantity")) * _f(p.get("last_price", p.get("average_price")))
        for p in (portfolio.get("positions") or {}).values()
        if str(p.get("sector") or "Unknown") == sector
    )


def _notification(kind: str, title: str, message: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = _read(NOTIFICATIONS_PATH, [])
    if not isinstance(rows, list):
        rows = []
    created_at = _now()
    item = {"notification_id": f"AN-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", "timestamp": created_at,
            "created_at": created_at, "scheduled_at": created_at, "attempted_at": "", "sent_at": "",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(timespec="seconds"),
            "kind": kind, "title": title, "message": message, "payload": dict(payload),
            "report_id": str(payload.get("report_id") or ""), "run_id": str(payload.get("run_id") or ""),
            "triggered_by": str(payload.get("triggered_by") or "AUTONOMY"), "status": "PENDING", "delivery": "LOCAL_QUEUE"}
    rows.insert(0, item); _write(NOTIFICATIONS_PATH, rows[:1000])
    try:
        from notifier import normalize_notification_result, send_pushover_alert
        item["attempted_at"] = _now()
        ok, detail = normalize_notification_result(send_pushover_alert(message, title=title))
        item["status"] = "SENT" if ok else "FAILED"
        item["delivery"] = "PUSHOVER_SENT" if ok else "PUSHOVER_FAILED"
        if ok:
            item["sent_at"] = _now()
        else:
            item["error"] = str(detail or "Pushover-sender returnerte False")[:500]
    except Exception as exc:
        item["attempted_at"] = _now(); item["status"] = "FAILED"; item["delivery"] = "PUSHOVER_FAILED"; item["error"] = str(exc)[:500]
    _write(NOTIFICATIONS_PATH, rows[:1000])
    return dict(item)


def _record_trade(trade: dict[str, Any]) -> None:
    trade = stamp_strategy_metadata(trade, "autonomy")
    trade.setdefault("strategy_role", "AUTONOMY_MAIN")
    trades = _read(TRADES_PATH, [])
    if not isinstance(trades, list):
        trades = []
    trades.insert(0, trade)
    _write(TRADES_PATH, trades)
    _append_audit("SIMULATED_TRADE", trade)


def _record_decisions(rows: Sequence[Mapping[str, Any]]) -> None:
    current = _read(DECISIONS_PATH, [])
    if not isinstance(current, list):
        current = []
    normalized = []
    for raw in rows:
        row = stamp_strategy_metadata(raw, "autonomy")
        row.setdefault("strategy_role", "AUTONOMY_MAIN")
        action = str(row.get("action") or "").upper()
        row.setdefault("sent_to_autonomy", True)
        row.setdefault("portfolio_check_completed", True)
        row.setdefault("order_intent_created", action in {"BUY", "SELL"})
        row.setdefault("order_executed", action in {"BUY", "SELL"})
        row.setdefault("stop_reason", "" if action in {"BUY", "SELL"} else str(row.get("reason") or "Ikke handlet"))
        row.setdefault("execution_stage", "ORDER_EXECUTED" if action in {"BUY", "SELL"} else "PORTFOLIO_GATE_STOPPED")
        normalized.append(row)
    _write(DECISIONS_PATH, normalized + current[:5000])


def recover_missing_position_history(portfolio: Mapping[str, Any] | None = None) -> int:
    """Reconstruct transparent placeholder entries after legacy runtime loss.

    Exact historical events cannot be recreated. These rows are explicitly
    marked RECOVERED so analytics and users never confuse them with original
    execution logs.
    """
    portfolio = dict(portfolio or load_portfolio())
    positions = portfolio.get("positions") or {}
    trades = _read(TRADES_PATH, [])
    if trades or not isinstance(positions, Mapping) or not positions:
        return 0
    recovered_trades = []
    recovered_decisions = []
    for ticker, raw in positions.items():
        position = dict(raw) if isinstance(raw, Mapping) else {}
        price = _f(position.get("average_price"))
        quantity = _f(position.get("quantity"))
        timestamp = str(position.get("opened_at") or _now())
        row = {
            "trade_id": f"RECOVERED-{str(ticker).upper()}", "timestamp": timestamp,
            "run_id": position.get("source_run_id") or "LEGACY-RUNTIME-RECOVERY",
            "action": "BUY", "ticker": str(ticker).upper(), "price": price,
            "quantity": quantity, "value": round(price * quantity, 2), "pnl": 0.0,
            "reason": "Rekonstruert fra persistent åpen posisjon etter tap av lokal runtime",
            "strategy": position.get("strategy"), "mode": "THEORETICAL_ONLY",
            "recovered": True, "recovery_source": "PERSISTED_OPEN_POSITION",
        }
        recovered_trades.append(row)
        recovered_decisions.append({"timestamp": timestamp, "run_id": row["run_id"], "ticker": row["ticker"], "action": "RECOVERED", "reason": row["reason"], "recovered": True})
    _write(TRADES_PATH, recovered_trades)
    existing_decisions = _read(DECISIONS_PATH, [])
    _write(DECISIONS_PATH, recovered_decisions + (existing_decisions if isinstance(existing_decisions, list) else []))
    _append_audit("LEGACY_POSITION_HISTORY_RECOVERED", {"positions": len(recovered_trades), "accuracy": "APPROXIMATE_FROM_CURRENT_STATE"})
    return len(recovered_trades)


def _sell(portfolio: dict[str, Any], ticker: str, price: float, reason: str, run_id: str,
          params: AutonomousParameters, *, commit: bool = True) -> dict[str, Any] | None:
    pos = (portfolio.get("positions") or {}).get(ticker)
    if not pos or price <= 0:
        return None
    quantity = _f(pos.get("quantity"))
    proceeds = quantity * price
    cost = quantity * _f(pos.get("average_price"))
    pnl = proceeds - cost
    portfolio["cash"] = _f(portfolio.get("cash")) + proceeds
    portfolio["realized_pnl"] = _f(portfolio.get("realized_pnl")) + pnl
    del portfolio["positions"][ticker]
    trade = {
        "trade_id": f"AT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", "timestamp": _now(), "run_id": run_id,
        "action": "SELL", "ticker": ticker, "price": round(price, 4), "quantity": round(quantity, 8),
        "value": round(proceeds, 2), "pnl": round(pnl, 2), "pnl_pct": round((price / _f(pos.get('average_price'), price) - 1) * 100, 2),
        "reason": reason, "strategy": pos.get("strategy"), "mode": "THEORETICAL_ONLY",
        **_candidate_snapshot_metadata(pos),
    }
    if commit:
        _record_trade(trade)
        if params.notify_trades:
            _notification("TRADE", f"AUTONOMOUS SELL {ticker}", f"{reason}. Teoretisk resultat {trade['pnl_pct']:+.2f}% ({pnl:+.2f}).", trade)
    return trade


def run_autonomous_cycle(
    candidates: Sequence[Mapping[str, Any]], run_id: str | None = None,
    *, progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    params = load_parameters().normalized()
    portfolio = load_portfolio()
    learning_portfolio = load_learning_portfolio()
    starting_portfolio = deepcopy(portfolio)
    run_id = run_id or f"ALP-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    decisions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    learning_decisions: list[dict[str, Any]] = []
    learning_trades: list[dict[str, Any]] = []
    exited_this_cycle: set[str] = set()
    entry_tickers_seen: set[str] = set()
    replay_snapshot_result: dict[str, Any] = {
        "replay_level": "DECISION_REPLAY",
        "missing": ["FULL_REPLAY_SNAPSHOT_NOT_FINALIZED"],
    }

    def emit_progress(completed: int, total: int, message: str, *, ticker: str = "") -> None:
        if progress_callback is not None:
            # Do not swallow ExecutionCancelled: the callback is also the
            # worker-lease checkpoint that prevents late writes after timeout.
            progress_callback({
                "phase": "AUTONOMOUS", "substage": "AUTONOMOUS_PORTFOLIO",
                "completed": completed, "total": total,
                "message": message, "ticker": ticker,
            })

    progress_total = 10
    emit_progress(0, progress_total, "Klargjør Autonomi-porteføljer og læringskonto")

    original_candidates = [dict(c) for c in (candidates or []) if isinstance(c, Mapping)]
    market_snapshot_row: dict[str, Any] = {}
    parallel_strategy_run: dict[str, Any] = {}
    technical_contribution: dict[str, Any] = {}
    try:
        snapshot_service = get_market_snapshot_service()
        market_snapshot = snapshot_service.build_market_snapshot(
            original_candidates, run_id=run_id, source="autonomy_cycle",
            metadata={"strategy_family": "autonomy", "candidate_count": len(original_candidates)},
        )
        market_snapshot_row = market_snapshot.to_dict()
        snapshot_service.save(market_snapshot)
        snapshots_by_ticker = {str(row.get("ticker") or "").upper(): row for row in market_snapshot_row.get("candidates", [])}
        enriched_candidates = []
        for candidate in original_candidates:
            row = dict(candidate)
            snapshot_row = snapshots_by_ticker.get(str(row.get("ticker") or "").upper(), {})
            for key, value in _candidate_snapshot_metadata(snapshot_row, market_snapshot_row).items():
                if value:
                    row.setdefault(key, value)
            enriched_candidates.append(row)
        candidates = enriched_candidates
        emit_progress(1, progress_total, "Markedssnapshot er lagret")
        try:
            technical_portfolio = {}
            try:
                from paper_trading import load_portfolio as load_paper_portfolio
                technical_portfolio = load_paper_portfolio() or {}
            except Exception:
                technical_portfolio = {}
            parallel_strategy_run = get_parallel_strategy_service().evaluate_snapshot(
                market_snapshot,
                run_id=run_id,
                source="autonomy_cycle_parallel",
                purpose="AUTONOMY_CYCLE_PARALLEL",
                portfolio_states={"autonomy": portfolio, "technical": technical_portfolio},
                families=["technical", "autonomy"],
                context_metadata={"autonomy_parameters": params},
            )
            _append_audit("PARALLEL_STRATEGY_CYCLE_COMPLETED", {
                "run_id": run_id,
                "strategy_run_id": parallel_strategy_run.get("strategy_run_id"),
                "strategies": parallel_strategy_run.get("strategy_count"),
                "decisions": parallel_strategy_run.get("decision_count"),
                "errors": parallel_strategy_run.get("error_count"),
                "execution_authorized": False,
            })
            emit_progress(2, progress_total, "Parallelle strategier er vurdert")
        except Exception as parallel_exc:
            # A benchmark/challenger failure must never stop Autonomi production.
            _append_audit("PARALLEL_STRATEGY_CYCLE_FAILED", {
                "run_id": run_id, "error": f"{type(parallel_exc).__name__}: {str(parallel_exc)[:500]}"
            })
        try:
            contribution_result = get_autonomy_technical_contribution_service().apply(
                candidates, parallel_strategy_run=parallel_strategy_run, run_id=run_id,
                minimum_investment_score=float(params.minimum_investment_score),
            )
            candidates = list(contribution_result.get("candidates") or candidates)
            technical_contribution = dict(contribution_result.get("summary") or {})
            _append_audit("AUTONOMY_TECHNICAL_CONTRIBUTION_COMPLETED", {
                "run_id": run_id,
                "applied": technical_contribution.get("applied_count", 0),
                "wait": technical_contribution.get("wait_count", 0),
                "threshold_crossings": technical_contribution.get("threshold_crossings", 0),
                "hard_gates_unchanged": True,
                "execution_authorized": False,
            })
            emit_progress(3, progress_total, "Teknisk strategibidrag er kontrollert")
        except Exception as technical_exc:
            # Missing technical contribution must never stop the base Autonomi engine.
            technical_contribution = {
                "run_id": run_id, "status": "FAILED_OPEN",
                "error": f"{type(technical_exc).__name__}: {str(technical_exc)[:500]}",
                "hard_gates_unchanged": True, "execution_authorized": False,
            }
            _append_audit("AUTONOMY_TECHNICAL_CONTRIBUTION_FAILED_OPEN", technical_contribution)
    except Exception as exc:
        _append_audit("MARKET_SNAPSHOT_FAILED", {"run_id": run_id, "error": str(exc)[:500]})
        candidates = original_candidates
    candidate_map = {str(c.get("ticker") or "").upper(): c for c in candidates if str(c.get("ticker") or "").strip()}

    # Learning observations have their own ledger and never affect ordinary
    # portfolio cash, position limits, sector exposure or performance.
    observed_decisions, observed_trades = _update_learning_positions(learning_portfolio, candidate_map, run_id, params)
    learning_decisions.extend(observed_decisions)
    learning_trades.extend(observed_trades)
    emit_progress(4, progress_total, "Eksisterende læringsposisjoner er oppdatert")

    # Mark ordinary autonomous positions and evaluate hard exits first.
    for ticker, pos in list((portfolio.get("positions") or {}).items()):
        candidate = candidate_map.get(ticker, {})
        price = _candidate_price(candidate, pos)
        if price <= 0:
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "HOLD", "reason": "Mangler ny pris; eksisterende markering beholdes"})
            continue
        pos["last_price"] = price
        pos["highest_price"] = max(_f(pos.get("highest_price"), price), price)
        avg = _f(pos.get("average_price"), price)
        score = _candidate_score(candidate, 100.0)
        reason = None
        if price <= avg * (1 - params.stop_loss_pct / 100):
            reason = "STOP LOSS"
        elif price <= _f(pos.get("highest_price"), price) * (1 - params.trailing_stop_pct / 100):
            reason = "TRAILING STOP"
        elif price >= avg * (1 + params.take_profit_pct / 100):
            reason = "TAKE PROFIT"
        elif candidate and score < params.score_exit_threshold:
            reason = f"Investment Score falt til {score:.1f}"
        if reason:
            trade = _sell(portfolio, ticker, price, reason, run_id, params, commit=False)
            if trade:
                trades.append(trade)
                exited_this_cycle.add(ticker)
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SELL", "reason": reason, "price": price, "score": score})
        else:
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "HOLD", "reason": "Ingen exitregel utløst", "price": price, "score": score})
    emit_progress(5, progress_total, "Salgs- og holdbeslutninger er kontrollert")

    equity_before_buys = portfolio_equity(portfolio)
    high = max(_f(portfolio.get("high_watermark"), equity_before_buys), equity_before_buys)
    drawdown = max(0.0, (1 - equity_before_buys / high) * 100) if high else 0.0
    if drawdown >= params.maximum_drawdown_pct:
        portfolio["status"] = "PAUSED"
        portfolio["pause_reason"] = f"Maks drawdown overskredet ({drawdown:.2f}%)"
        if params.notify_risk_events:
            _notification("RISK", "AUTONOMOUS PORTFOLIO PAUSED", portfolio["pause_reason"], {"drawdown_pct": drawdown, "run_id": run_id})
        _append_audit("PORTFOLIO_AUTO_PAUSED", {"reason": portfolio["pause_reason"], "run_id": run_id})

    # New buys only when explicitly active. Every received candidate still gets
    # a ledger row, so a paused portfolio can never look like a missing handoff.
    if portfolio.get("status") != "ACTIVE":
        pause_reason = str(portfolio.get("pause_reason") or f"Autonom portefølje er {portfolio.get('status') or 'PAUSED'}")
        held = set((portfolio.get("positions") or {}).keys())
        for candidate in sorted(candidates, key=lambda c: _candidate_entry_score(c), reverse=True):
            ticker = str(candidate.get("ticker") or "").upper()
            if not ticker or ticker in held:
                continue
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP",
                              "reason": pause_reason, "score": _candidate_entry_score(candidate), "base_score": _candidate_score(candidate),
                              **_technical_contribution_metadata(candidate),
                              "sent_to_autonomy": True, "portfolio_check_completed": True,
                              "order_intent_created": False, "order_executed": False,
                              "execution_stage": "PORTFOLIO_PAUSED"})
    if portfolio.get("status") == "ACTIVE":
        ranked = sorted(candidates, key=lambda c: _candidate_entry_score(c), reverse=True)
        for candidate in ranked:
            ticker = str(candidate.get("ticker") or "").upper()
            if not ticker:
                continue
            if ticker in entry_tickers_seen:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP",
                                  "reason": "Duplikat kandidat i samme beslutningssyklus", "order_intent_created": False,
                                  "order_executed": False, "execution_stage": "DUPLICATE_CANDIDATE_BLOCKED"})
                continue
            entry_tickers_seen.add(ticker)
            authorized, authorization_reasons = production_buy_authorization(candidate)
            if not authorized:
                decisions.append({
                    "timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP",
                    "reason": "; ".join(authorization_reasons), "score": _candidate_entry_score(candidate),
                    "base_score": _candidate_score(candidate), "sent_to_autonomy": True,
                    "portfolio_check_completed": True, "order_intent_created": False,
                    "order_executed": False, "execution_stage": "DECISION_GATE_BLOCKED",
                    "required_outcome": "Kjøpskandidat",
                })
                continue
            if ticker in exited_this_cycle:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": "Ingen gjeninntreden i samme beslutningssyklus"})
                continue
            base_score = _candidate_score(candidate)
            score = _candidate_entry_score(candidate)
            quality = _candidate_quality(candidate)
            risk = _candidate_risk(candidate)
            price = _candidate_price(candidate)
            if ticker in portfolio["positions"] and not params.allow_additions:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP",
                                  "reason": "Finnes allerede i porteføljen; tilleggskjøp er deaktivert", "score": score,
                                  "sent_to_autonomy": True, "portfolio_check_completed": True,
                                  "order_intent_created": False, "order_executed": False,
                                  "execution_stage": "PORTFOLIO_GATE_STOPPED"})
                continue
            rejection = None
            execution_stage = "ENTRY_GATE_STOPPED"
            if quality < params.minimum_data_quality:
                rejection = f"Datakvalitet {quality:.1f} under terskel"
            elif risk > params.maximum_risk_score:
                rejection = f"Risiko {risk:.1f} over grense"
            elif price <= 0:
                rejection = "Mangler gyldig markedspris"
            elif len(portfolio["positions"]) >= params.maximum_open_positions:
                rejection = "Maks antall åpne posisjoner"
            elif bool(candidate.get("technical_entry_wait")):
                rejection = str(candidate.get("technical_entry_wait_reason") or "Teknisk timing gir VENT")
                execution_stage = "TECHNICAL_TIMING_WAIT"
            elif score < params.minimum_investment_score:
                rejection = f"Justert score {score:.1f} under terskel (base {base_score:.1f})"
            if rejection:
                decisions.append({
                    "timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "WAIT" if execution_stage == "TECHNICAL_TIMING_WAIT" else "SKIP",
                    "reason": rejection, "score": score, "base_score": base_score,
                    "sent_to_autonomy": True, "portfolio_check_completed": True,
                    "order_intent_created": False, "order_executed": False,
                    "execution_stage": execution_stage,
                    **_technical_contribution_metadata(candidate),
                })
                continue

            equity = portfolio_equity(portfolio)
            reserve = equity * params.reserve_cash_pct / 100
            available = max(0.0, _f(portfolio.get("cash")) - reserve)
            proposed = min(params.maximum_position_pct, max(0.5, _f(candidate.get("proposed_position_pct"), params.maximum_position_pct)))
            target_value = equity * proposed / 100
            sector = str(candidate.get("sector") or "Unknown")
            sector_room = max(0.0, equity * params.maximum_sector_pct / 100 - _sector_value(portfolio, sector))
            value = min(target_value, available, sector_room)
            quantity = math.floor(value / price * 10000) / 10000 if price > 0 else 0
            value = quantity * price
            if quantity <= 0 or value < 100:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": "Utilstrekkelig kapital eller sektorrom", "score": score})
                continue

            if ticker in learning_portfolio.get("positions", {}):
                promoted = _close_learning_position(learning_portfolio, ticker, price, "Promotert til ordinær autonom portefølje", run_id)
                if promoted:
                    learning_trades.append(promoted)
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "PROMOTED", "reason": "Kandidaten bestod ordinære kjøpsporter og ble flyttet til Autonom portefølje", "price": price, "score": score, "learning_probe": True})
            portfolio["cash"] = _f(portfolio.get("cash")) - value
            portfolio["positions"][ticker] = {
                "ticker": ticker, "name": candidate.get("name", ticker), "sector": sector,
                "quantity": quantity, "average_price": price, "last_price": price, "highest_price": price,
                "opened_at": _now(), "strategy": _candidate_strategy(candidate),
                "entry_score": score, "entry_base_score": base_score, "entry_risk_score": risk, "entry_data_quality": quality,
                **_technical_contribution_metadata(candidate),
                "source_run_id": run_id,
                **_candidate_snapshot_metadata(candidate, market_snapshot_row),
                "entry_confidence": _f(candidate.get("confidence_score")),
                "entry_components": {
                    "discovery": _f(candidate.get("discovery_score")),
                    "fundamental": _f(candidate.get("fundamental_score")),
                    "research": _f(candidate.get("research_score")),
                    "validation": _f(candidate.get("validation_score")),
                    "portfolio_fit": _f(candidate.get("portfolio_fit_score")),
                    "risk_adjustment": 100.0 - risk,
                },
            }
            trade = {
                "trade_id": f"AT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", "timestamp": _now(), "run_id": run_id,
                "action": "BUY", "ticker": ticker, "price": round(price, 4), "quantity": quantity,
                "value": round(value, 2), "pnl": 0.0, "reason": f"Justert score {score:.1f} (base {base_score:.1f}), risiko {risk:.1f}, datakvalitet {quality:.1f}",
                "strategy": _candidate_strategy(candidate), "mode": "THEORETICAL_ONLY",
                **_candidate_snapshot_metadata(candidate, market_snapshot_row),
                **_technical_contribution_metadata(candidate),
                "entry_confidence": _f(candidate.get("confidence_score")),
                "entry_components": {
                    "discovery": _f(candidate.get("discovery_score")),
                    "fundamental": _f(candidate.get("fundamental_score")),
                    "research": _f(candidate.get("research_score")),
                    "validation": _f(candidate.get("validation_score")),
                    "portfolio_fit": _f(candidate.get("portfolio_fit_score")),
                    "risk_adjustment": 100.0 - risk,
                },
            }
            trades.append(trade)
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "BUY", "reason": trade["reason"], "price": price, "score": score, "base_score": base_score, "order_intent_created": True, "order_executed": True, "execution_stage": "EXECUTED_AFTER_DECISION_GATE", **_technical_contribution_metadata(candidate)})

        # v19.0.18: Learning guarantee. If an active theoretical portfolio
        # received candidates but the ordinary production gates created no BUY,
        # create a small number of explicitly marked learning-probe positions.
        # This does not alter real trading, production thresholds or risk limits;
        # it prevents a week of Autonomi runs from producing zero learning data.
        normal_buys_this_cycle = [t for t in trades if t.get("action") == "BUY" and not t.get("learning_probe")]
        if params.enable_learning_probe_buys and not normal_buys_this_cycle and candidates:
            learning_ranked = sorted(candidates, key=lambda c: _candidate_entry_score(c), reverse=True)
            learning_count = 0
            for candidate in learning_ranked:
                ticker = str(candidate.get("ticker") or "").upper()
                if not ticker:
                    continue
                if ticker in portfolio["positions"] or ticker in learning_portfolio["positions"] or ticker in exited_this_cycle:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": "Finnes allerede i ordinær portefølje, læringsportefølje eller ble lukket i samme syklus", "learning_probe": True})
                    continue
                if learning_count >= params.learning_probe_max_buys:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": f"Maks {params.learning_probe_max_buys} nye læringsposisjoner per kjøring er nådd", "learning_probe": True})
                    continue
                base_score = _candidate_score(candidate)
                score = _candidate_entry_score(candidate)
                paper_signal = _paper_learning_signal(candidate)
                paper_buy = paper_signal["paper_signal_action"] == "BUY"
                if bool(candidate.get("technical_entry_wait")) and not paper_buy:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "WAIT", "reason": str(candidate.get("technical_entry_wait_reason") or "Teknisk timing gir VENT"), "score": score, "base_score": base_score, **_technical_contribution_metadata(candidate)})
                    continue
                if score < params.learning_probe_minimum_score:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": f"Under læringsgrense {score:.1f} < {params.learning_probe_minimum_score:.1f} (base {base_score:.1f})", "score": score, "base_score": base_score, **_technical_contribution_metadata(candidate)})
                    continue
                price = _candidate_price(candidate)
                if price <= 0:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": "Mangler gyldig pris for læringskjøp", "score": score})
                    continue
                risk = _candidate_risk(candidate)
                quality = _candidate_quality(candidate)
                if candidate.get("valid_for_decision") is not True:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": "Markedsdata er ikke beslutningsgyldige for læringskjøp", "score": score, "risk": risk, "learning_probe": True, **paper_signal})
                    continue
                if risk > params.learning_probe_maximum_risk_score:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": f"Risiko {risk:.1f} over læringsgrense {params.learning_probe_maximum_risk_score:.1f}", "score": score, "risk": risk, "learning_probe": True, **paper_signal})
                    continue
                production_blockers = _production_blockers_for_learning(candidate, params)
                # A learning position is a shadow observation with fixed notional.
                # It does not reserve or deduct ordinary portfolio cash.
                value = params.learning_probe_notional_value
                quantity = math.floor(value / price * 10000) / 10000 if price > 0 else 0
                value = quantity * price
                sector = str(candidate.get("sector") or "Unknown")
                if quantity <= 0 or value < 100:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": "Ugyldig notional for læringsposisjon", "score": score, "learning_probe": True})
                    continue
                learning_portfolio["positions"][ticker] = {
                    "ticker": ticker, "name": candidate.get("name", ticker), "sector": sector,
                    "quantity": quantity, "average_price": price, "last_price": price, "highest_price": price,
                    "opened_at": _now(), "strategy": _candidate_strategy(candidate),
                    "entry_score": score, "entry_base_score": base_score, "entry_risk_score": risk, "entry_data_quality": quality,
                    "source_run_id": run_id, **_candidate_snapshot_metadata(candidate, market_snapshot_row), **_technical_contribution_metadata(candidate), "learning_probe": True, "origin": "AUTONOMY_LEARNING_PROBE", "portfolio_type": "LEARNING",
                    "observation_horizon_days": params.learning_probe_horizon_days,
                    "entry_confidence": _f(candidate.get("confidence_score")),
                    "production_blockers_at_entry": production_blockers,
                    "evidence_valid_at_entry": candidate.get("evidence_valid_for_decision") is True,
                    "evaluation_dates": [], "observation_days": 0, "outcome_measurements": [],
                    **paper_signal,
                    "entry_components": {
                        "discovery": _f(candidate.get("discovery_score")),
                        "fundamental": _f(candidate.get("fundamental_score")),
                        "research": _f(candidate.get("research_score")),
                        "validation": _f(candidate.get("validation_score")),
                        "portfolio_fit": _f(candidate.get("portfolio_fit_score")),
                        "risk_adjustment": 100.0 - risk,
                    },
                }
                trade = {
                    "trade_id": f"LT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", "timestamp": _now(), "run_id": run_id,
                    "action": "BUY", "ticker": ticker, "price": round(price, 4), "quantity": quantity,
                    "value": round(value, 2), "pnl": 0.0,
                    "reason": f"Læringskjøp: ingen ordinære kjøp ble utløst. Score {score:.1f}, risiko {risk:.1f}, datakvalitet {quality:.1f}",
                    "strategy": _candidate_strategy(candidate), "mode": "LEARNING_ONLY", "learning_probe": True, "portfolio_type": "LEARNING",
                    **_candidate_snapshot_metadata(candidate, market_snapshot_row),
                    **_technical_contribution_metadata(candidate),
                    "entry_confidence": _f(candidate.get("confidence_score")),
                    "production_blockers_at_entry": production_blockers,
                    "evidence_valid_at_entry": candidate.get("evidence_valid_for_decision") is True,
                    **paper_signal,
                    "entry_components": {
                        "discovery": _f(candidate.get("discovery_score")),
                        "fundamental": _f(candidate.get("fundamental_score")),
                        "research": _f(candidate.get("research_score")),
                        "validation": _f(candidate.get("validation_score")),
                        "portfolio_fit": _f(candidate.get("portfolio_fit_score")),
                        "risk_adjustment": 100.0 - risk,
                    },
                }
                if params.notify_trades:
                    trade["notification"] = _notification(
                        "TRADE", f"AUTONOMY LEARNING BUY {ticker}",
                        f"Teoretisk læringskjøp {quantity:g} @ {price:.2f}. {trade['reason']}", trade,
                    )
                else:
                    trade["notification"] = {"status": "SKIPPED_POLICY", "detail": "Læringsvarsling deaktivert"}
                _record_learning_trade(trade)
                learning_trades.append(trade)
                learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "ADD_OBSERVATION", "reason": trade["reason"], "price": price, "score": score, "risk": risk, "learning_probe": True, "production_blockers_at_entry": production_blockers, "notification": dict(trade["notification"]), **paper_signal})
                learning_portfolio["total_entry_notional"] = _f(learning_portfolio.get("total_entry_notional")) + value
                learning_count += 1

    emit_progress(6, progress_total, "Kjøps- og læringsbeslutninger er ferdige")

    execution_integrity = _validate_execution_integrity(trades, candidate_map, portfolio)
    if not execution_integrity["ok"]:
        # Atomic safety fallback: no ordinary portfolio mutation or order ledger is
        # committed when the completed cycle is internally inconsistent.
        portfolio = starting_portfolio
        for decision in decisions:
            if str(decision.get("action") or "").upper() in {"BUY", "SELL"}:
                decision["action"] = "BLOCKED"
                decision["order_executed"] = False
                decision["execution_stage"] = "EXECUTION_INTEGRITY_BLOCKED"
                decision["reason"] = "Handelen ble tilbakeført: " + "; ".join(execution_integrity["errors"])
        trades = []
        _append_audit("AUTONOMOUS_EXECUTION_BLOCKED", {"run_id": run_id, "errors": execution_integrity["errors"]})
    else:
        for trade in trades:
            _record_trade(dict(trade))
            if params.notify_trades:
                ticker = str(trade.get("ticker") or "")
                if str(trade.get("action") or "").upper() == "BUY":
                    _notification("TRADE", f"AUTONOMOUS BUY {ticker}", f"Teoretisk kjøp {trade.get('quantity', 0):g} @ {trade.get('price', 0):.2f}. {trade.get('reason', '')}", trade)
                else:
                    _notification("TRADE", f"AUTONOMOUS SELL {ticker}", f"{trade.get('reason', '')}. Teoretisk resultat {float(trade.get('pnl_pct') or 0):+.2f}% ({float(trade.get('pnl') or 0):+.2f}).", trade)

    equity = portfolio_equity(portfolio)
    portfolio["updated_at"] = _now()
    portfolio["last_run_id"] = run_id
    portfolio["last_equity"] = equity
    portfolio["high_watermark"] = max(_f(portfolio.get("high_watermark"), equity), equity)
    learning_portfolio["updated_at"] = _now()
    learning_portfolio["last_run_id"] = run_id
    _write(PORTFOLIO_PATH, portfolio)
    _write(LEARNING_PORTFOLIO_PATH, learning_portfolio)
    decisions = _attach_snapshot_metadata(decisions, candidate_map, market_snapshot_row)
    learning_decisions = _attach_snapshot_metadata(learning_decisions, candidate_map, market_snapshot_row)
    observation_progress = _update_candidate_observations(candidates, decisions + learning_decisions, run_id, market_snapshot_row)
    _record_decisions(decisions)
    _record_learning_decisions(learning_decisions)
    _append_equity_history(portfolio, run_id, trades=len(trades), decisions=len(decisions))
    _append_learning_equity_history(learning_portfolio, run_id, trades=len(learning_trades), decisions=len(learning_decisions))
    perf = calculate_performance(portfolio)
    learning_perf = learning_portfolio_performance(learning_portfolio)
    _write(PERFORMANCE_PATH, perf)
    _write(LEARNING_PERFORMANCE_PATH, learning_perf)
    emit_progress(7, progress_total, "Porteføljer, beslutninger og ytelse er lagret")

    shared_account_sync: dict[str, Any] = {}
    learning_account_result: dict[str, Any] = {}
    activation_analysis: dict[str, Any] = {}
    try:
        emit_progress(8, progress_total, "Synkroniserer delte strategi- og læringskontoer")
        account_service = get_strategy_account_service()
        execution_service = get_simulated_execution_service()
        main_account = account_service.sync_legacy_account(
            "autonomy_main", portfolio, strategy_family="autonomy", strategy_id="autonomy_main",
            strategy_version_id="autonomy_main@1.0.0", display_name="Autonomi hovedstrategi",
            role="PRODUCTION", status=str(portfolio.get("status") or "PAUSED"), run_id=run_id,
            metadata={"source": "autonomous_portfolio", "shared_engine_bridge": True},
        )
        mirrored = 0
        for legacy_trade in trades:
            mirror = execution_service.mirror_legacy_trade(account_id="autonomy_main", trade=legacy_trade, run_id=run_id)
            mirrored += int(bool(mirror.get("mirrored")))
        shared_account_sync = {"account_id": main_account.get("account_id"), "mirrored_trades": mirrored}

        # The established learning portfolio has already applied exits, buys,
        # persistence and notification exactly once above.  Synchronise that
        # final state into the shared account and mirror its trades to the
        # common order/fill ledger.  Running a second learning policy here used
        # to create a contradictory SKIP decision for a ticker already filled
        # by the established learning portfolio.
        learning_account = account_service.sync_legacy_account(
            "autonomy_learning", learning_portfolio,
            strategy_family="autonomy", strategy_id="autonomy_learning",
            strategy_version_id="autonomy_learning@2.0.0",
            display_name="Autonomi læringskonto", role="LEARNING",
            status=str(learning_portfolio.get("status") or "ACTIVE"), run_id=run_id,
            metadata={"source": "autonomous_portfolio", "canonical_learning_bridge": True},
        )
        learning_orders: list[dict[str, Any]] = []
        learning_fills: list[dict[str, Any]] = []
        for legacy_trade in learning_trades:
            mirror = execution_service.mirror_legacy_trade(
                account_id="autonomy_learning", trade=legacy_trade, run_id=run_id,
            )
            if isinstance(mirror.get("order"), Mapping):
                learning_orders.append(dict(mirror["order"]))
            if isinstance(mirror.get("fill"), Mapping):
                fill = dict(mirror["fill"])
                fill.update({
                    "action": str(legacy_trade.get("action") or fill.get("side") or "").upper(),
                    "price": legacy_trade.get("price", fill.get("fill_price")),
                    "quantity": legacy_trade.get("quantity", fill.get("quantity")),
                    "score": legacy_trade.get("autonomy_adjusted_investment_score", legacy_trade.get("score")),
                    "risk": legacy_trade.get("risk", legacy_trade.get("entry_risk_score")),
                    "data_quality": legacy_trade.get("data_quality", legacy_trade.get("entry_data_quality")),
                    "reason": legacy_trade.get("reason"),
                    "production_blockers_at_entry": list(legacy_trade.get("production_blockers_at_entry") or []),
                    "notification": dict(legacy_trade.get("notification") or {}),
                })
                learning_fills.append(fill)
        learning_account_result = {
            "run_id": run_id, "status": "SYNCED_FROM_CANONICAL_LEARNING_PORTFOLIO",
            "policy": {"source": "established_learning_portfolio", "parameter_change_applied": False},
            "decisions": [dict(row) for row in learning_decisions],
            "orders": learning_orders, "fills": learning_fills,
            "buy_count": sum(str(row.get("side") or row.get("action") or "").upper() == "BUY" for row in learning_fills),
            "sell_count": sum(str(row.get("side") or row.get("action") or "").upper() == "SELL" for row in learning_fills),
            "account_metrics": account_service.metrics("autonomy_learning"),
            "parameter_change_applied": False,
            "hard_production_gates_unchanged": True,
            "service_version": "CANONICAL_LEARNING_BRIDGE_1.0",
            "account": learning_account,
        }
        analysis_rows = []
        for decision in list(decisions):
            ticker = str(decision.get("ticker") or "").upper()
            analysis_rows.append({**dict(candidate_map.get(ticker) or {}), **dict(decision)})
        activation_analysis = get_autonomy_activation_service().analyse(
            analysis_rows, run_id=run_id, parameters=asdict(params),
            account_metrics=account_service.comparison(), persist=True,
        )
        _append_audit("SHARED_STRATEGY_ACCOUNTS_UPDATED", {
            "run_id": run_id, "main_account": shared_account_sync,
            "learning_buys": learning_account_result.get("buy_count", 0),
            "learning_sells": learning_account_result.get("sell_count", 0),
            "activation_analysis_id": activation_analysis.get("analysis_id"),
            "parameter_change_applied": False,
        })
    except Exception as shared_exc:
        _append_audit("SHARED_STRATEGY_ACCOUNTS_FAILED", {"run_id": run_id, "error": f"{type(shared_exc).__name__}: {str(shared_exc)[:500]}"})

    # Persist the immutable replay contract only after the ordinary portfolio
    # cycle is finalized.  Failure never fabricates FULL_REPLAY and never
    # changes the already evaluated trading rules or parameters.
    try:
        emit_progress(9, progress_total, "Bygger uforanderlig replay- og revisjonsspor")
        from autonomi_core.portfolio_decisions.layer import build_portfolio_context
        from replay_contract import build_snapshot, persist_snapshot

        frozen_context = build_portfolio_context(starting_portfolio)
        replay_bundle = build_snapshot(
            run_id=run_id,
            candidates=candidates,
            portfolio_before=starting_portfolio,
            portfolio_after=portfolio,
            portfolio_context=frozen_context,
            parameters=asdict(params),
            market_snapshot=market_snapshot_row,
            actions=trades,
        )
        persisted_replay = persist_snapshot(replay_bundle)
        replay_manifest = dict(persisted_replay.get("manifest") or {})
        replay_audit = dict(persisted_replay.get("audit") or replay_manifest.get("audit") or {})
        replay_snapshot_result = {
            "replay_level": str(replay_manifest.get("replay_level") or "DECISION_REPLAY"),
            "schema_version": replay_manifest.get("schema_version"),
            "contract": replay_manifest.get("contract"),
            "stored": bool(persisted_replay.get("stored")),
            "reused": bool(persisted_replay.get("reused")),
            "audit": replay_audit,
            "missing": list(replay_audit.get("errors") or []),
        }
        _append_audit("FULL_REPLAY_SNAPSHOT_FINALIZED", {
            "run_id": run_id,
            "replay_level": replay_snapshot_result["replay_level"],
            "audit_ok": bool(replay_audit.get("ok")),
            "errors": replay_snapshot_result["missing"],
        })
    except Exception as replay_exc:
        replay_snapshot_result = {
            "replay_level": "DECISION_REPLAY",
            "missing": [f"FULL_REPLAY_SNAPSHOT_FAILED:{type(replay_exc).__name__}"],
            "error": str(replay_exc),
        }
        _append_audit("FULL_REPLAY_SNAPSHOT_FAILED", {
            "run_id": run_id,
            "error": f"{type(replay_exc).__name__}: {str(replay_exc)[:500]}",
        })

    _append_audit("AUTONOMOUS_CYCLE_COMPLETED", {"run_id": run_id, "decisions": len(decisions), "ordinary_trades": len(trades), "learning_decisions": len(learning_decisions), "learning_trades": len(learning_trades), "equity": equity, "status": portfolio.get("status"), "execution_integrity": execution_integrity, "shared_learning_buys": learning_account_result.get("buy_count", 0), "activation_analysis_id": activation_analysis.get("analysis_id")})
    learning_result = None
    try:
        emit_progress(10, progress_total, "Kjører kontrollert parameterlæring og sluttkontroll")
        from controlled_parameter_learning import run_automatic_learning_if_due
        learning_result = run_automatic_learning_if_due(trigger="AUTONOMOUS_CYCLE", force=False)
    except Exception as exc:
        _append_audit("AUTOMATIC_LEARNING_HOOK_FAILED", {"run_id": run_id, "error": str(exc)})
    return {"run_id": run_id, "market_snapshot": market_snapshot_row, "market_snapshot_id": market_snapshot_row.get("snapshot_id", ""), "parallel_strategy_run": parallel_strategy_run, "technical_contribution": technical_contribution, "portfolio": portfolio, "learning_portfolio": learning_portfolio, "decisions": decisions + learning_decisions + list(learning_account_result.get("decisions") or []), "portfolio_decisions": decisions, "learning_decisions": learning_decisions, "learning_observations": observation_progress, "trades": trades + learning_trades, "portfolio_trades": trades, "learning_trades": learning_trades, "performance": perf, "learning_performance": learning_perf, "learning": learning_result, "strategy_accounts": get_strategy_account_service().comparison() if shared_account_sync else [], "shared_account_sync": shared_account_sync, "autonomy_learning_account": learning_account_result, "activation_analysis": activation_analysis, "execution_integrity": execution_integrity, "full_replay": replay_snapshot_result, "replay_level": replay_snapshot_result.get("replay_level", "DECISION_REPLAY")}


def calculate_performance(portfolio: Mapping[str, Any] | None = None) -> dict[str, Any]:
    portfolio = dict(portfolio or load_portfolio())
    trades = _read(TRADES_PATH, [])
    sells = [t for t in trades if t.get("action") == "SELL"] if isinstance(trades, list) else []
    wins = [t for t in sells if _f(t.get("pnl")) > 0]
    losses = [t for t in sells if _f(t.get("pnl")) < 0]
    gross_profit = sum(_f(t.get("pnl")) for t in wins)
    gross_loss = abs(sum(_f(t.get("pnl")) for t in losses))
    equity = portfolio_equity(portfolio)
    initial = _f(portfolio.get("initial_cash"), 1.0)
    high = max(_f(portfolio.get("high_watermark"), equity), equity)
    return {
        "updated_at": _now(), "equity": round(equity, 2), "cash": round(_f(portfolio.get("cash")), 2),
        "total_return_pct": round((equity / initial - 1) * 100, 2) if initial else 0.0,
        "realized_pnl": round(_f(portfolio.get("realized_pnl")), 2),
        "open_positions": len(portfolio.get("positions") or {}), "closed_trades": len(sells),
        "win_rate_pct": round(len(wins) / len(sells) * 100, 2) if sells else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else (999.0 if gross_profit else 0.0),
        "drawdown_pct": round(max(0.0, (1 - equity / high) * 100), 2) if high else 0.0,
    }


def set_status(active: bool, reason: str = "Brukerhandling") -> dict[str, Any]:
    portfolio = load_portfolio()
    portfolio["status"] = "ACTIVE" if active else "PAUSED"
    portfolio["pause_reason"] = "" if active else reason
    portfolio["updated_at"] = _now()
    _write(PORTFOLIO_PATH, portfolio)
    _append_audit("PORTFOLIO_STATUS_CHANGED", {"status": portfolio["status"], "reason": reason})
    return portfolio


def reset_portfolio(confirmation: str) -> dict[str, Any]:
    if confirmation.strip().upper() != "RESET":
        raise ValueError("Skriv RESET for å bekrefte.")
    params = load_parameters()
    portfolio = default_portfolio(params)
    _write(PORTFOLIO_PATH, portfolio)
    for path in (TRADES_PATH, DECISIONS_PATH, NOTIFICATIONS_PATH, EQUITY_HISTORY_PATH, PERFORMANCE_PATH):
        _write(path, [] if path != PERFORMANCE_PATH else calculate_performance(portfolio))
    _append_audit("PORTFOLIO_RESET", {"initial_cash": params.initial_cash})
    return portfolio


def build_activation_analysis(*, persist: bool = True) -> dict[str, Any]:
    """Build the latest understandable Autonomy activation funnel."""
    decisions = _read(DECISIONS_PATH, [])
    pipeline = _read(LATEST_PIPELINE_PATH, {})
    candidates = pipeline.get("candidates") or pipeline.get("proposals") or []
    candidate_map = {str(row.get("ticker") or "").upper(): dict(row) for row in candidates if isinstance(row, Mapping)}
    enriched = []
    for raw in decisions if isinstance(decisions, list) else []:
        row = dict(raw) if isinstance(raw, Mapping) else {}
        ticker = str(row.get("ticker") or "").upper()
        enriched.append({**dict(candidate_map.get(ticker) or {}), **row})
    latest_run_id = str(enriched[0].get("run_id") or pipeline.get("run_id") or "") if enriched else str(pipeline.get("run_id") or "")
    accounts = get_strategy_account_service()
    accounts.ensure_defaults()
    return get_autonomy_activation_service().analyse(
        enriched, run_id=latest_run_id, parameters=asdict(load_parameters()),
        account_metrics=accounts.comparison(), persist=persist,
    )


def build_evaluation_bundle() -> bytes:
    """Create the v19.9.0 sanitised ZIP for direct sharing and evaluation."""
    analysis = build_activation_analysis(persist=True)
    errors = []
    for row in load_audit(1000):
        event = str(row.get("event") or "").upper()
        if "FAILED" in event or "ERROR" in event:
            errors.append(row)
    return get_evaluation_export_service().build_zip(
        analysis=analysis, errors=errors,
        additional_metadata={
            "legacy_observation_portfolio_present": True,
            "canonical_learning_account": "autonomy_learning",
            "export_source": "autonomous_portfolio_ui",
        },
    )


def _navigate_autonomy_workspace(slug: str) -> None:
    import streamlit as st
    st.session_state["autonomy_core_workspace_slug_v1882"] = slug
    st.rerun()


def render_learning_portfolio() -> None:
    import pandas as pd
    import streamlit as st

    portfolio = load_learning_portfolio()
    perf = learning_portfolio_performance(portfolio)
    params = load_parameters()
    st.markdown("#### 🧪 Læringsportefølje")
    st.caption("Separate skyggeposisjoner for å måle hva som skjer med kandidater som ikke ble ordinært kjøpt. Disse posisjonene påvirker ikke Autonom portefølje, kontanter, risiko, sektorgrenser eller ekte handel.")
    b1, b2 = st.columns(2)
    if b1.button("📈 Åpne autonom portefølje", width="stretch", key="learning_to_autonomous_v19018b"):
        _navigate_autonomy_workspace("autonomous_portfolio")
    if b2.button("🧭 Til Autonomi Oversikt", width="stretch", key="learning_to_overview_v19018b"):
        _navigate_autonomy_workspace("overview")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Åpne læringsposisjoner", perf["open_positions"])
    c2.metric("Inngangsnotional", f"{perf['entry_notional']:,.0f}")
    c3.metric("Nåverdi", f"{perf['current_value']:,.0f}")
    c4.metric("Samlet P/L", f"{perf['total_pnl']:+,.0f}")
    c5.metric("Læringsavkastning", f"{perf['return_pct']:+.2f}%")
    st.info(f"Fast notional per ny læringsposisjon: {params.learning_probe_notional_value:,.0f}. Normal observasjonshorisont: {params.learning_probe_horizon_days} dager.")
    if abs(float(params.learning_probe_notional_value) - RC16_RECOMMENDED_LEARNING_NOTIONAL) > 0.01:
        st.caption("RC16 anbefaler 15 000 i rent teoretisk notional per læringsposisjon for mer realistiske kostnads-, valuta- og porteføljeobservasjoner. Eksisterende verdi endres ikke automatisk.")
        confirm_profile = st.checkbox(
            "Bekreft anbefalt RC16-læringsprofil (kun LEARNING_ONLY)",
            key="learning_confirm_rc16_profile_v19220",
        )
        if st.button(
            "Bruk anbefalt RC16-læringsprofil",
            key="learning_apply_rc16_profile_v19220",
            disabled=not confirm_profile,
            width="content",
        ):
            save_parameters(recommended_learning_profile(params))
            st.success("Læringsprofilen er lagret: 15 000 per skyggeposisjon, maks 3 nye per syklus og 30 dagers normalhorisont. Ordinær Autonomi og ekte handel er uendret.")
            st.rerun()

    history = load_learning_equity_history(200)
    st.markdown("##### Utvikling i læringsporteføljen")
    if history:
        hist_df = pd.DataFrame(history).sort_values("timestamp")
        chart_cols = [c for c in ("total_pnl", "return_pct") if c in hist_df.columns]
        if chart_cols:
            st.line_chart(hist_df.set_index("timestamp")[chart_cols], width="stretch")
        st.dataframe(hist_df.sort_values("timestamp", ascending=False).head(25), width="stretch", hide_index=True)
    else:
        st.info("Ingen læringshistorikk ennå. Historikk opprettes etter neste autonome beslutningssyklus.")

    positions = list((portfolio.get("positions") or {}).values())
    st.markdown("##### Åpne læringsposisjoner")
    if positions:
        rows = []
        for pos in positions:
            avg, last, qty = _f(pos.get("average_price")), _f(pos.get("last_price")), _f(pos.get("quantity"))
            rows.append({
                "Ticker": pos.get("ticker"), "Sektor": pos.get("sector"), "Strategi": pos.get("strategy"),
                "Inngang": avg, "Siste": last, "Notional": qty * avg, "Nåverdi": qty * last,
                "P/L": qty * (last - avg), "P/L %": (last / avg - 1) * 100 if avg else 0,
                "Inngangsscore": pos.get("entry_score"), "Åpnet": pos.get("opened_at"),
                "Sist vurdert": pos.get("last_evaluated_at"), "Horisont dager": pos.get("observation_horizon_days", params.learning_probe_horizon_days),
                "Opprinnelse": "Autonomi læringsobservasjon",
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("Ingen åpne læringsposisjoner.")

    learning_trades = _read(LEARNING_TRADES_PATH, [])
    learning_decisions = _read(LEARNING_DECISIONS_PATH, [])
    closed = portfolio.get("closed_positions") or []
    t1, t2, t3 = st.tabs(["Læringshandler", "Observasjonsbeslutninger", "Lukkede observasjoner"])
    with t1:
        st.dataframe(pd.DataFrame(learning_trades[:500]), width="stretch", hide_index=True) if learning_trades else st.caption("Ingen læringshandler registrert.")
    with t2:
        st.dataframe(pd.DataFrame(learning_decisions[:1000]), width="stretch", hide_index=True) if learning_decisions else st.caption("Ingen observasjonsbeslutninger registrert.")
    with t3:
        st.dataframe(pd.DataFrame(closed[:500]), width="stretch", hide_index=True) if closed else st.caption("Ingen lukkede læringsobservasjoner.")



def _fmt_nb_money(value: Any) -> str:
    try:
        whole, decimals = f"{float(value):,.2f}".split(".")
        return f"{whole.replace(',', ' ')},{decimals} kr"
    except Exception:
        return "-"


def _fmt_nb_number(value: Any, decimals: int = 2) -> str:
    try:
        whole, fraction = f"{float(value):,.{decimals}f}".split(".")
        return f"{whole.replace(',', ' ')},{fraction}"
    except Exception:
        return "-"


def _round_financial_columns(frame: Any, columns: Sequence[str], decimals: int = 2) -> Any:
    """Round financial display columns while leaving counts and identifiers as integers/text."""
    view = frame.copy()
    for column in columns:
        if column in view.columns:
            view[column] = view[column].map(
                lambda value: round(float(value), decimals) if value is not None and str(value).strip() not in {"", "-"} else value
            )
    return view


def _short_local_time(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d.%m.%Y %H:%M")
    except Exception:
        return raw[:16].replace("T", " ")


def autonomous_position_rows(portfolio: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pos in (portfolio.get("positions") or {}).values():
        avg = _f(pos.get("average_price"))
        last = _f(pos.get("last_price", pos.get("average_price")))
        qty = _f(pos.get("quantity"))
        value = qty * last
        pnl = qty * (last - avg)
        rows.append({
            "Ticker": str(pos.get("ticker") or "-"), "Selskap": str(pos.get("company") or pos.get("name") or ""),
            "Sektor": str(pos.get("sector") or "Ukjent"), "Antall": qty, "Snittkurs": avg, "Siste kurs": last,
            "Markedsverdi": value, "Avkastning kr": pnl, "Avkastning %": ((last / avg) - 1.0) * 100 if avg else 0.0,
            "Risiko": str(pos.get("risk_status") or pos.get("strategy") or "-"), "Åpnet": _short_local_time(pos.get("opened_at")),
        })
    return sorted(rows, key=lambda row: float(row.get("Markedsverdi") or 0), reverse=True)


def autonomous_trade_display_rows(trades: Sequence[Mapping[str, Any]], limit: int = 250) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for trade in list(trades or [])[:limit]:
        price = _f(trade.get("price")); qty = _f(trade.get("quantity", trade.get("shares")))
        out.append({"Tid": _short_local_time(trade.get("timestamp")), "Ticker": str(trade.get("ticker") or "-"),
            "Kjøp/salg": str(trade.get("side") or trade.get("action") or trade.get("trade_type") or "-").upper(),
            "Antall": qty, "Kurs": price, "Beløp": _f(trade.get("notional", trade.get("amount"))) or qty * price,
            "Begrunnelse": str(trade.get("reason") or "-"), "Status": str(trade.get("status") or "Utført"),
            "Teknisk ID": str(trade.get("trade_id") or "")})
    return out


def autonomous_decision_ledger_rows(decisions: Sequence[Mapping[str, Any]], limit: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for decision in list(decisions or [])[:limit]:
        action = str(decision.get("action") or "-").upper(); reason = str(decision.get("stop_reason") or decision.get("reason") or "-")
        sent = bool(decision.get("sent_to_autonomy", True)); order_intent = bool(decision.get("order_intent_created", action in {"BUY", "SELL"})); executed = bool(decision.get("order_executed", action in {"BUY", "SELL"}))
        stage = "Ordre utført" if executed else ("Ordreintensjon opprettet" if order_intent else ("Stoppet i porteføljekontroll" if sent else "Ikke overlevert til Autonomi"))
        rows.append({"Tid": _short_local_time(decision.get("timestamp")), "Ticker": str(decision.get("ticker") or "-"), "Score": decision.get("score"),
            "Beslutning": action, "Siste steg": str(decision.get("execution_stage") or stage), "Handlet": "Ja" if executed else "Nei",
            "Stoppårsak / begrunnelse": reason, "Kjørings-ID": str(decision.get("run_id") or "-")})
    return rows



def autonomous_trade_block_summary(decisions: Sequence[Mapping[str, Any]], portfolio: Mapping[str, Any], params: AutonomousParameters) -> dict[str, Any]:
    rows = list(decisions or [])
    latest_run = str(rows[0].get("run_id") or "") if rows else ""
    current = [dict(row) for row in rows if not latest_run or str(row.get("run_id") or "") == latest_run]
    buy_sell = [row for row in current if str(row.get("action") or "").upper() in {"BUY", "SELL"}]
    blocked = [row for row in current if str(row.get("action") or "").upper() in {"SKIP", "HOLD", "OBSERVE"}]
    counts: dict[str, int] = {}
    for row in blocked:
        reason = str(row.get("stop_reason") or row.get("reason") or "Ukjent årsak")
        counts[reason] = counts.get(reason, 0) + 1
    reasons = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    status = str(portfolio.get("status") or "PAUSED").upper()
    if buy_sell:
        headline = f"{len(buy_sell)} handel/handler registrert i siste beslutningssyklus"
    elif status != "ACTIVE":
        headline = f"Ingen nye handler: autonom portefølje er {status}"
    elif len(portfolio.get("positions") or {}) >= int(params.maximum_open_positions):
        headline = f"Ingen nye handler: maks {params.maximum_open_positions} åpne posisjoner er nådd"
    elif reasons:
        headline = f"Ingen nye handler: vanligste stoppårsak er {reasons[0][0]}"
    else:
        headline = "Ingen nye handler: ingen beslutningsdata er registrert for siste syklus"
    return {"run_id": latest_run, "headline": headline, "trade_count": len(buy_sell), "blocked_count": len(blocked), "reasons": reasons[:8], "portfolio_status": status}

def _render_position_cards_mobile(rows: Sequence[Mapping[str, Any]], st: Any) -> None:
    import html as _html
    cards = []
    for row in rows:
        pnl_pct = float(row.get("Avkastning %") or 0); pnl_class = "positive" if pnl_pct >= 0 else "negative"
        cards.append(f'''<article class="autonomous-position-card-v1940"><header><div><b>{_html.escape(str(row.get("Ticker") or "-"))}</b><small>{_html.escape(str(row.get("Selskap") or row.get("Sektor") or ""))}</small></div><strong class="{pnl_class}">{pnl_pct:+.2f}%</strong></header><div class="grid"><span><em>Verdi</em>{_html.escape(_fmt_nb_money(row.get("Markedsverdi")))}</span><span><em>Avkastning</em>{_html.escape(_fmt_nb_money(row.get("Avkastning kr")))}</span><span><em>Antall</em>{_html.escape(_fmt_nb_number(row.get("Antall"), 2))}</span><span><em>Snitt / siste</em>{_html.escape(_fmt_nb_number(row.get("Snittkurs"), 2))} / {_html.escape(_fmt_nb_number(row.get("Siste kurs"), 2))}</span></div><footer>{_html.escape(str(row.get("Sektor") or "Ukjent"))} · {_html.escape(str(row.get("Risiko") or "-"))}</footer></article>''')
    st.markdown('''<style>.autonomous-position-cards-v1940{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:.7rem;margin:.4rem 0 1rem}.autonomous-position-card-v1940{background:linear-gradient(160deg,#071426,#0b1f35);border:1px solid rgba(56,189,248,.3);border-radius:16px;padding:.8rem;color:#f8fafc}.autonomous-position-card-v1940 header{display:flex;justify-content:space-between;gap:.7rem}.autonomous-position-card-v1940 small{display:block;color:#94a3b8}.autonomous-position-card-v1940 .positive{color:#34d399}.autonomous-position-card-v1940 .negative{color:#fb7185}.autonomous-position-card-v1940 .grid{display:grid;grid-template-columns:1fr 1fr;gap:.55rem;margin:.75rem 0}.autonomous-position-card-v1940 span{font-weight:800}.autonomous-position-card-v1940 em{display:block;font-size:.68rem;font-style:normal;color:#94a3b8;text-transform:uppercase}.autonomous-position-card-v1940 footer{font-size:.72rem;color:#cbd5e1;border-top:1px solid rgba(148,163,184,.18);padding-top:.45rem}@media (min-width:761px){.autonomous-position-cards-v1940{display:none!important}}</style><div class="autonomous-position-cards-v1940">''' + ''.join(cards) + '</div>', unsafe_allow_html=True)


def _render_trade_cards_mobile(rows: Sequence[Mapping[str, Any]], st: Any) -> None:
    import html as _html
    cards = []
    for row in rows:
        cards.append(
            f'<article class="autonomous-log-card-v1940"><header><b>{_html.escape(str(row.get("Ticker") or "-"))}</b>'
            f'<strong>{_html.escape(str(row.get("Kjøp/salg") or "-"))}</strong></header>'
            f'<div><span>Tid</span>{_html.escape(str(row.get("Tid") or "-"))}</div>'
            f'<div><span>Antall / kurs</span>{_html.escape(_fmt_nb_number(row.get("Antall"), 2))} / {_html.escape(_fmt_nb_number(row.get("Kurs"), 2))}</div>'
            f'<div><span>Beløp</span>{_html.escape(_fmt_nb_money(row.get("Beløp")))}</div>'
            f'<footer>{_html.escape(str(row.get("Begrunnelse") or "-"))} · {_html.escape(str(row.get("Status") or "-"))}</footer></article>'
        )
    st.markdown('<div class="autonomous-mobile-log-cards-v1940">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


def _render_decision_cards_mobile(rows: Sequence[Mapping[str, Any]], st: Any) -> None:
    import html as _html
    cards = []
    for row in rows:
        cards.append(
            f'<article class="autonomous-log-card-v1940"><header><b>{_html.escape(str(row.get("Ticker") or "-"))}</b>'
            f'<strong>{_html.escape(str(row.get("Beslutning") or "-"))}</strong></header>'
            f'<div><span>Siste steg</span>{_html.escape(str(row.get("Siste steg") or "-"))}</div>'
            f'<div><span>Handlet</span>{_html.escape(str(row.get("Handlet") or "Nei"))}</div>'
            f'<div><span>Score</span>{_html.escape(str(row.get("Score") if row.get("Score") is not None else "-"))}</div>'
            f'<footer>{_html.escape(str(row.get("Stoppårsak / begrunnelse") or "-"))}</footer></article>'
        )
    st.markdown('<div class="autonomous-mobile-log-cards-v1940">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


def _render_responsive_portfolio_css(st: Any) -> None:
    st.markdown('''<style>
    .autonomous-mobile-log-cards-v1940{display:none}
    .autonomous-log-card-v1940{background:#071426;border:1px solid rgba(56,189,248,.28);border-radius:14px;padding:.75rem;margin:.55rem 0;color:#f8fafc}
    .autonomous-log-card-v1940 header{display:flex;justify-content:space-between;gap:.6rem;margin-bottom:.55rem}
    .autonomous-log-card-v1940 strong{color:#7dd3fc}.autonomous-log-card-v1940 div{display:flex;justify-content:space-between;gap:.8rem;padding:.2rem 0}
    .autonomous-log-card-v1940 span{color:#94a3b8;font-size:.76rem}.autonomous-log-card-v1940 footer{border-top:1px solid rgba(148,163,184,.18);margin-top:.45rem;padding-top:.45rem;color:#cbd5e1}
    @media(max-width:760px){
      .autonomous-mobile-log-cards-v1940{display:block!important}
      [class*="st-key-autonomous-desktop-positions-v1940"],
      [class*="st-key-autonomous-desktop-trades-v1940"],
      [class*="st-key-autonomous-desktop-decisions-v1940"]{display:none!important}
    }
    </style>''', unsafe_allow_html=True)

def _render_activation_analysis_v1980(st: Any, pd: Any) -> None:
    st.markdown("##### 🧪 Aktiveringsanalyse og strategikontoer")
    st.caption("Resultatene vises direkte her. Hovedstrategien endres ikke automatisk; læringskontoen bruker små, separate paper-posisjoner og samme harde data- og risikogrenser.")
    try:
        analysis = build_activation_analysis(persist=False)
        funnel = dict(analysis.get("funnel") or {})
        a1, a2, a3, a4, a5, a6 = st.columns(6)
        a1.metric("Kandidater", funnel.get("candidates_received", 0))
        a2.metric("Data bestått", funnel.get("passed_data_quality", 0))
        a3.metric("Risiko bestått", funnel.get("passed_risk", 0))
        a4.metric("Score bestått", funnel.get("passed_score", 0))
        a5.metric("Ordreintensjoner", funnel.get("order_intents_created", 0))
        a6.metric("Utførte ordre", funnel.get("orders_executed", 0))
        st.info(str(analysis.get("recommendation") or "Ingen anbefaling tilgjengelig."))
        st.caption("Slik leses kjeden: Kandidat → datakontroll → risikokontroll → score → ordreintensjon → simulert ordre. Et lavere tall viser nøyaktig hvilket trinn som stopper kandidatene.")
        if int(funnel.get("passed_score") or 0) > 0 and int(funnel.get("order_intents_created") or 0) == 0:
            st.warning(
                f"Nåkonklusjon: {int(funnel.get('passed_score') or 0)} kandidater bestod scorekravet, "
                "men ingen ordreintensjon ble opprettet. Scoregrensen er derfor ikke hovedblokkeringen. "
                "Se kandidatbeslutningene for den konkrete ordre- eller porteføljeregelen."
            )

        technical_service = get_autonomy_technical_contribution_service()
        technical_policy = technical_service.policy()
        technical_rows = [dict(row) for row in (analysis.get("candidate_decisions") or []) if row.get("technical_contribution_applied") or row.get("technical_strategy_version_id")]
        st.markdown("**Kontrollert teknisk bidrag til Autonomi**")
        t1, t2, t3, t4, t5 = st.columns(5)
        t1.metric("Status", "AKTIV" if technical_policy.get("enabled") else "AV")
        t2.metric("Maks vekt", f"{float(technical_policy.get('weight_pct') or 0):.0f} %")
        t3.metric("Teknisk VENT", sum(1 for row in technical_rows if row.get("technical_entry_wait") or row.get("execution_stage") == "TECHNICAL_TIMING_WAIT"))
        t4.metric("Positive bidrag", sum(1 for row in technical_rows if _f(row.get("technical_contribution_points")) > 0))
        t5.metric("Negative bidrag", sum(1 for row in technical_rows if _f(row.get("technical_contribution_points")) < 0))
        st.caption(f"Kun teknisk produksjonsbenchmark fra samme snapshot brukes. Autonomi er eksplisitt bundet til {technical_policy.get('bound_technical_strategy_version_id') or '-'}. Bidraget gjelder nye innganger, kan ikke autorisere ordre og kan aldri omgå datakvalitet, risiko, kapital, sektor- eller posisjonsgrenser.")
        if technical_rows:
            technical_view = pd.DataFrame(technical_rows).rename(columns={
                "ticker": "Ticker", "base_score": "Base score", "score": "Justert score",
                "technical_contribution_points": "Teknisk bidrag", "technical_score_100": "Teknisk score",
                "technical_signal_action": "Teknisk signal", "technical_signal_confidence": "Teknisk confidence",
                "technical_timing": "Timing", "technical_strategy_version_id": "Teknisk versjon", "reason": "Beslutningsårsak",
            })
            keep = [col for col in ["Ticker", "Base score", "Justert score", "Teknisk bidrag", "Teknisk score", "Teknisk signal", "Teknisk confidence", "Timing", "Teknisk versjon", "Beslutningsårsak"] if col in technical_view.columns]
            st.dataframe(technical_view[keep], width="stretch", hide_index=True)
        else:
            st.caption("Ingen kandidater med teknisk bidrag er lagret i siste aktiveringsanalyse ennå.")

        with st.expander("Kontrollert teknisk bidragsprofil", expanded=False):
            st.warning("Endringer påvirker bare paper-Autonomi og krever eksplisitt godkjenning. Harde porter kan ikke endres her.")
            tc1, tc2, tc3 = st.columns(3)
            technical_enabled = tc1.checkbox("Aktiver teknisk bidrag", bool(technical_policy.get("enabled", True)), key="v1990_technical_enabled")
            technical_weight = tc2.slider("Maks teknisk vekt %", 0.0, 20.0, float(technical_policy.get("weight_pct") or 15.0), 1.0, key="v1990_technical_weight")
            technical_floor = tc3.slider("Minimum base score for positivt løft", 70.0, 78.0, float(technical_policy.get("minimum_base_score_floor") or 74.0), 1.0, key="v1990_technical_floor")
            tc4, tc5, tc6 = st.columns(3)
            technical_positive = tc4.slider("Maks positivt bidrag", 0.0, 5.0, float(technical_policy.get("maximum_positive_points") or 4.0), 0.5, key="v1990_technical_positive")
            technical_negative = tc5.slider("Maks negativt bidrag", 0.0, 8.0, float(technical_policy.get("maximum_negative_points") or 6.0), 0.5, key="v1990_technical_negative")
            technical_wait = tc6.slider("VENT under teknisk score", 20.0, 45.0, float(technical_policy.get("wait_below_technical_score") or 35.0), 1.0, key="v1990_technical_wait")
            technical_approval = st.text_input("Skriv GODKJENN for å lagre teknisk bidragsprofil", key="v1990_technical_approval")
            technical_reason = st.text_input("Begrunnelse for endringen", key="v1990_technical_reason")
            if st.button("Lagre godkjent teknisk bidragsprofil", width="stretch", key="v1990_save_technical_policy"):
                if technical_approval.strip().upper() != "GODKJENN":
                    st.error("Skriv GODKJENN før profilen lagres.")
                elif not technical_reason.strip():
                    st.error("Skriv en begrunnelse for endringen.")
                else:
                    technical_service.update_policy({
                        "enabled": technical_enabled, "weight_pct": technical_weight,
                        "minimum_base_score_floor": technical_floor,
                        "maximum_positive_points": technical_positive,
                        "maximum_negative_points": technical_negative,
                        "wait_below_technical_score": technical_wait,
                    }, approved_by="streamlit_user", reason=technical_reason)
                    st.success("Teknisk bidragsprofil er lagret med rollback. Harde Autonomi-porter er uendret.")
                    st.rerun()

        left, right = st.columns(2)
        blockers = list(analysis.get("top_blockers") or [])
        with left:
            st.markdown("**Vanligste blokkeringer**")
            st.caption("Viser første registrerte stoppårsak. Koden er sporbar diagnose; Årsak er forklaringen som skal brukes i vurderingen.")
            if blockers:
                st.dataframe(pd.DataFrame(blockers).rename(columns={"label":"Årsak","count":"Antall","share_pct":"Andel %","code":"Kode"}), width="stretch", hide_index=True)
            else:
                st.caption("Ingen blokkeringer registrert.")
        with right:
            st.markdown("**Simulerte scoregrenser**")
            st.caption("En følsomhetsanalyse av scorekravet – ikke et kjøpssignal. Data-, risiko-, kapital-, sektor-, timing- og ordrekrav gjelder fortsatt.")
            simulations = list(analysis.get("threshold_simulations") or [])
            if simulations:
                st.dataframe(pd.DataFrame(simulations)[["minimum_score","eligible_candidates","tickers"]].rename(columns={"minimum_score":"Minimum score","eligible_candidates":"Mulige kandidater","tickers":"Toppkandidater"}), width="stretch", hide_index=True)
            else:
                st.caption("Ingen kandidater å simulere.")

        accounts = get_strategy_account_service()
        accounts.ensure_defaults()
        comparison = accounts.comparison()
        st.markdown("**Separate strategikontoer**")
        st.caption("Produksjon er den ordinære Autonomi-kontoen. Læring bruker små teoretiske posisjoner. Benchmark er kun sammenligningsgrunnlag.")
        if comparison:
            view = pd.DataFrame(comparison).rename(columns={
                "display_name":"Konto", "role":"Rolle", "status":"Status", "equity":"Porteføljeverdi",
                "return_pct":"Avkastning %", "drawdown_pct":"Drawdown %", "open_positions":"Posisjoner",
                "cash":"Kontanter", "last_run_id":"Siste kjøring",
            })
            keep = [c for c in ["Konto","Rolle","Status","Porteføljeverdi","Avkastning %","Drawdown %","Posisjoner","Kontanter","Siste kjøring"] if c in view.columns]
            view = _round_financial_columns(view, ["Porteføljeverdi", "Avkastning %", "Drawdown %", "Kontanter"])
            st.dataframe(view[keep], width="stretch", hide_index=True)
        st.caption("Teknisk benchmark, autonomy_main og autonomy_learning har separate kontanter, posisjoner og handler. Ingen konto kan bruke en annen kontos kapital.")

        with st.expander("Kontrollert parameterprofil for autonomy_learning", expanded=False):
            learning_service = get_autonomy_learning_account_service()
            policy = learning_service.policy()
            st.caption("Endringer gjelder bare den simulerte læringskontoen. Produksjonskontoens score-, evidens- og risikokrav påvirkes ikke.")
            p1, p2, p3, p4 = st.columns(4)
            learning_score = p1.slider("Minimum score – læringskonto", 60.0, 65.0, float(policy["minimum_score"]), 1.0, key="v1980_learning_score")
            learning_risk = p2.slider("Maks risiko – læringskonto", 0.0, 75.0, float(policy["maximum_risk_score"]), 1.0, key="v1980_learning_risk_rc1626")
            learning_notional = p3.number_input("Beløp per læringskjøp", 100.0, 15000.0, float(policy["notional_value"]), 100.0, key="v1980_learning_notional_rc1626")
            learning_buys = p4.number_input("Maks kjøp per syklus", 0, 5, int(policy["maximum_buys_per_cycle"]), 1, key="v1980_learning_buys")
            p4, p5, p6, p7 = st.columns(4)
            learning_reserve = p4.slider("Kontantreserve %", 10.0, 50.0, float(policy["reserve_cash_pct"]), 1.0, key="v1980_learning_reserve")
            learning_stop = p5.slider("Stop-loss %", 2.0, 12.0, float(policy["stop_loss_pct"]), 0.5, key="v1980_learning_stop")
            learning_trailing = p6.slider("Trailing stop %", 2.0, 20.0, float(policy["trailing_stop_pct"]), 0.5, key="v1980_learning_trailing_rc1626")
            learning_target = p7.slider("Gevinstmål %", 5.0, 30.0, float(policy["take_profit_pct"]), 0.5, key="v1980_learning_target")
            approval = st.text_input("Skriv GODKJENN for å lagre læringsprofilen", key="v1980_learning_approval")
            reason = st.text_input("Begrunnelse for endringen", key="v1980_learning_reason")
            if st.button("Lagre godkjent læringsprofil", width="stretch", key="v1980_save_learning_policy"):
                if approval.strip().upper() != "GODKJENN":
                    st.error("Skriv GODKJENN før parameterprofilen lagres.")
                else:
                    learning_service.update_policy({
                        "minimum_score": learning_score, "maximum_risk_score": learning_risk,
                        "notional_value": learning_notional,
                        "maximum_buys_per_cycle": int(learning_buys), "reserve_cash_pct": learning_reserve,
                        "stop_loss_pct": learning_stop, "trailing_stop_pct": learning_trailing,
                        "take_profit_pct": learning_target,
                    }, approved_by="streamlit_user", reason=reason or "Eksplisitt godkjent i v19.8.0")
                    st.success("Læringsprofilen er lagret. autonomy_main er uendret.")
                    st.rerun()

        zip_payload = build_evaluation_bundle()
        st.download_button(
            "📦 Eksporter testresultater (ZIP)", zip_payload,
            file_name=f"autonomy_test_results_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            mime="application/zip", width="stretch", key="alp_test_export_v1980",
            help="Inneholder sammendrag, aktiveringsfunnel, strategisammenligning, kandidatbeslutninger, ordre, handler, porteføljemålinger, parametre og rensede feil. Hemmeligheter filtreres bort.",
        )
    except Exception as exc:
        st.error(f"Aktiveringsanalysen kunne ikke bygges: {type(exc).__name__}: {exc}")


def render_autonomous_portfolio(view: str = "autonomous") -> None:
    import pandas as pd
    import streamlit as st
    _render_responsive_portfolio_css(st)

    if str(view).lower() == "learning":
        render_learning_portfolio()
        return

    st.markdown("#### 📈 Autonom portefølje")
    st.caption("Den ordinære, teoretiske porteføljen som styres av Autonomi. Bare kandidater som består ordinære kjøpsporter påvirker beholdning, kontanter, risiko og porteføljeavkastning. Læringsobservasjoner føres separat.")
    nav1, nav2 = st.columns(2)
    if nav1.button("🧪 Vis læringsportefølje", width="stretch", key="autonomous_to_learning_v19018b"):
        _navigate_autonomy_workspace("learning_portfolio")
    if nav2.button("🧭 Til Autonomi Oversikt", width="stretch", key="autonomous_to_overview_v19018b"):
        _navigate_autonomy_workspace("overview")
    storage_info = persistence_status()
    if storage_info.get("persistent"):
        st.success("🔒 Parameterlås aktiv: lagrede innstillinger hentes fra persistent database og beholdes ved refresh, omstart og ny versjon.")
    else:
        st.warning("⚠ Parameterne lagres bare lokalt. Sett DATABASE_URL på Render for å beholde dem ved ny deploy.")
    params = load_parameters()
    portfolio = load_portfolio()
    perf = calculate_performance(portfolio)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status", portfolio.get("status", "PAUSED"))
    c2.metric("Porteføljeverdi", _fmt_nb_money(perf["equity"]))
    c3.metric("Avkastning", f"{perf['total_return_pct']:+.2f}%")
    c4.metric("Åpne posisjoner", perf["open_positions"])
    c5.metric("Drawdown", f"{perf['drawdown_pct']:.2f}%")

    try:
        from autonomous_orchestrator import load_latest_chain
        latest_chain = load_latest_chain()
    except Exception:
        latest_chain = {}
    status_panel = portfolio_status_summary(latest_chain)
    st.markdown("##### Autonomi status")
    sp1, sp2, sp3, sp4 = st.columns(4)
    sp1.metric("Autonomi-runner", status_panel.get("Autonomi-runner"))
    sp2.metric("Planlegger", status_panel.get("Planlegger"))
    sp3.metric("Paper trading", status_panel.get("Paper trading"))
    sp4.metric("Ekte handel", status_panel.get("Ekte handel"))
    sp5, sp6, sp7, sp8 = st.columns(4)
    sp5.metric("Kandidater mottatt", status_panel.get("Kandidater mottatt"))
    sp6.metric("Ordinære porteføljekjøp", status_panel.get("Ordinære porteføljekjøp"))
    sp7.metric("Separate læringsposisjoner", status_panel.get("Læringsposisjoner opprettet"))
    sp8.metric("Læringsgrense", status_panel.get("Minimum læringsscore"))

    _recent_decisions_v1940 = _read(DECISIONS_PATH, [])
    _block_summary_v1940 = autonomous_trade_block_summary(_recent_decisions_v1940 if isinstance(_recent_decisions_v1940, list) else [], portfolio, params)
    st.markdown("##### Hvorfor ble det ikke handlet?")
    if _block_summary_v1940["trade_count"]:
        st.success(_block_summary_v1940["headline"])
    else:
        st.warning(_block_summary_v1940["headline"])
    if _block_summary_v1940["reasons"]:
        st.caption(" · ".join(f"{reason} ({count})" for reason, count in _block_summary_v1940["reasons"]))
    st.caption(f"Kjørings-ID: {_block_summary_v1940['run_id'] or '-'} · Status: {_block_summary_v1940['portfolio_status']} · Åpne posisjoner: {len(portfolio.get('positions') or {})}/{params.maximum_open_positions}")
    reason_text = status_panel.get("Årsak til ingen kjøp")
    if status_panel.get("Teoretiske kjøp", 0):
        st.success(f"Status: {reason_text}")
    else:
        st.warning(f"Årsak til ingen kjøp: {reason_text}")
    st.caption("Ekte handel er deaktivert. Læringsposisjoner ligger i en separat læringsportefølje og påvirker ikke tallene på denne siden.")

    a, b, c = st.columns(3)
    if portfolio.get("status") == "ACTIVE":
        if a.button("Pause autonom portefølje", width="stretch", key="alp_pause_v18688"):
            set_status(False, "Pauset av bruker"); st.rerun()
    else:
        if a.button("Aktiver autonom simulering", type="primary", width="stretch", key="alp_activate_v18688"):
            set_status(True, "Aktivert av bruker"); st.rerun()
    if b.button("Kjør én teoretisk beslutningssyklus", width="stretch", key="alp_cycle_v18690", help="Bruker siste lagrede kandidatliste. Starter ikke en ny markedsskanning."):
        pipeline = _read(LATEST_PIPELINE_PATH, {})
        candidates = pipeline.get("candidates") or pipeline.get("proposals") or []
        if portfolio.get("status") != "ACTIVE":
            st.warning("Den autonome porteføljen er pauset. Aktiver simuleringen før syklusen kjøres.")
        elif not candidates:
            st.error("Ingen kandidater funnet. Bruk 'Kjør hele autonome kjeden' for å skanne markedet først.")
        else:
            with st.spinner("Evaluerer kandidater og simulerer beslutninger..."):
                result = run_autonomous_cycle(candidates, str(pipeline.get("run_id") or "MANUAL"))
            st.success(f"Syklus fullført: {len(result['trades'])} teoretiske handler og {len(result['decisions'])} beslutninger.")
            st.rerun()

    st.markdown("##### 🚦 Autonom samordning")
    st.caption("Kjør hele kjeden: markedsskanning → Investment Pipeline → teoretiske handler → kontrollert læring.")
    try:
        from market_intelligence import load_jobs, run_job
        jobs = load_jobs()
        active_jobs = [j for j in jobs if j.enabled]
        if active_jobs:
            labels = {f"{j.name} ({', '.join(j.markets)})": j for j in active_jobs}
            chosen = st.selectbox("Jobbprofil for full kjøring", list(labels), key="alp_orchestrator_job_v18690")
            if st.button("▶ Kjør hele autonome kjeden nå", type="primary", width="stretch", key="alp_run_full_chain_v18690"):
                with st.spinner("Skanner markeder og kjører den autonome kjeden..."):
                    full = run_job(labels[chosen], trigger="MANUAL_FULL_CHAIN")
                chain = full.get("autonomous_chain") or {}
                if chain.get("status") == "OK":
                    st.success(f"Hele kjeden er fullført. Kjede-ID: {chain.get('chain_id')}")
                else:
                    st.warning(f"Kjeden ble fullført med status {chain.get('status')}. Se diagnostikk nedenfor.")
                st.session_state["alp_last_full_chain_v18690"] = full
        else:
            st.info("Opprett og aktiver en jobbprofil under Scheduled Market Intelligence for å kjøre hele kjeden.")
    except Exception as exc:
        st.error(f"Autonom orkestrering kunne ikke lastes: {exc}")

    try:
        from autonomous_orchestrator import load_latest_chain
        chain = st.session_state.get("alp_last_full_chain_v18690", {}).get("autonomous_chain") or load_latest_chain()
        if chain:
            with st.expander("Siste kjøring – diagnostikk", expanded=False):
                st.write({"Kjede-ID": chain.get("chain_id"), "Status": chain.get("status"), "Start": chain.get("created_at"), "Kilde": chain.get("source_run_id")})
                st.dataframe(pd.DataFrame(chain.get("stages") or []), width="stretch", hide_index=True)
                if chain.get("errors"):
                    st.error(" | ".join(chain.get("errors") or []))
    except Exception:
        pass

    _render_activation_analysis_v1980(st, pd)

    with st.expander("Faste parametere", expanded=False):
        portfolio_initial_cash = _f(portfolio.get("initial_cash"), params.initial_cash)
        st.info(
            "Disse grensene styrer nye teoretiske beslutninger. Startkapital er bare reset-verdi for en ny konto; "
            "den endrer aldri avkastningsgrunnlaget til en eksisterende portefølje."
        )
        st.caption(
            f"Faktisk avkastningsgrunnlag for aktiv konto: {_fmt_nb_money(portfolio_initial_cash)} · "
            f"valgt reset-verdi: {_fmt_nb_money(params.initial_cash)}."
        )
        if abs(float(params.initial_cash) - portfolio_initial_cash) > 0.01:
            st.warning("Reset-verdien avviker fra aktiv kontos startkapital. Dette er tillatt, men får først virkning etter en uttrykkelig RESET.")
        p1, p2, p3, p4 = st.columns(4)
        initial_cash = p1.number_input("Startkapital ved neste RESET", 1000.0, 100000000.0, float(params.initial_cash), 10000.0, key="alp_initial_v18688")
        min_score = p2.slider("Minimum investeringsscore", 0.0, 100.0, float(params.minimum_investment_score), 1.0, key="alp_minscore_v18688")
        min_quality = p3.slider("Minimum datakvalitet", 0.0, 100.0, float(params.minimum_data_quality), 1.0, key="alp_quality_v18688")
        max_risk = p4.slider("Maks risikoscore", 0.0, 100.0, float(params.maximum_risk_score), 1.0, key="alp_risk_v18688")
        q1, q2, q3, q4 = st.columns(4)
        max_pos = q1.slider("Maks posisjon %", 0.5, 25.0, float(params.maximum_position_pct), 0.5, key="alp_pos_v18688")
        max_sector = q2.slider("Maks sektor %", 1.0, 100.0, float(params.maximum_sector_pct), 1.0, key="alp_sector_v18688")
        max_open = q3.number_input("Maks åpne posisjoner", 1, 100, int(params.maximum_open_positions), 1, key="alp_open_v18688")
        reserve = q4.slider("Kontantreserve %", 0.0, 95.0, float(params.reserve_cash_pct), 1.0, key="alp_reserve_v18688")
        r1, r2, r3, r4 = st.columns(4)
        stop = r1.slider("Stop loss %", 0.5, 50.0, float(params.stop_loss_pct), 0.5, key="alp_stop_v18688")
        trail = r2.slider("Trailing stop %", 0.5, 50.0, float(params.trailing_stop_pct), 0.5, key="alp_trail_v18688")
        target = r3.slider("Take profit %", 0.5, 300.0, float(params.take_profit_pct), 0.5, key="alp_target_v18688")
        score_exit = r4.slider("Score-exit under", 0.0, 100.0, float(params.score_exit_threshold), 1.0, key="alp_scoreexit_v18688")
        s1, s2, s3, s4 = st.columns(4)
        max_dd = s1.slider("Maks drawdown %", 0.5, 80.0, float(params.maximum_drawdown_pct), 0.5, key="alp_dd_v18688")
        learning_enabled = s2.checkbox("Aktiver læringskjøp", params.enable_learning_probe_buys, key="alp_learning_probe_enabled_v19018")
        learning_min_score = s3.slider("Minimum læringsscore", 60.0, 65.0, float(params.learning_probe_minimum_score), 1.0, key="alp_learning_probe_min_v19018")
        learning_max_buys = s4.number_input("Maks læringskjøp", 0, 10, int(params.learning_probe_max_buys), 1, key="alp_learning_probe_max_v19018")
        u1, u2 = st.columns(2)
        learning_notional = u1.number_input("Notional per læringsposisjon", 100.0, 100000.0, float(params.learning_probe_notional_value), 100.0, key="alp_learning_notional_v19018b")
        learning_horizon = u2.number_input("Læringshorisont (dager)", 1, 365, int(params.learning_probe_horizon_days), 1, key="alp_learning_horizon_v19018b")
        learning_max_risk = st.slider("Maksimal risiko for kun læringskjøp", 0.0, 75.0, float(params.learning_probe_maximum_risk_score), 1.0, key="alp_learning_risk_v19220_rc1626")
        notify = st.checkbox("Varsle ved teoretiske handler", params.notify_trades, key="alp_notify_v18688")
        if st.button("Lagre parametere", key="alp_save_params_v18688"):
            save_parameters(AutonomousParameters(initial_cash=initial_cash, minimum_investment_score=min_score, minimum_data_quality=min_quality, maximum_risk_score=max_risk, maximum_position_pct=max_pos, maximum_sector_pct=max_sector, maximum_open_positions=int(max_open), reserve_cash_pct=reserve, stop_loss_pct=stop, trailing_stop_pct=trail, take_profit_pct=target, score_exit_threshold=score_exit, maximum_drawdown_pct=max_dd, daily_loss_limit_pct=params.daily_loss_limit_pct, allow_additions=params.allow_additions, enable_learning_probe_buys=learning_enabled, learning_probe_minimum_score=learning_min_score, learning_probe_maximum_risk_score=learning_max_risk, learning_probe_max_buys=int(learning_max_buys), learning_probe_notional_value=learning_notional, learning_probe_horizon_days=int(learning_horizon), notify_trades=notify, notify_risk_events=True))
            st.success("Parameterne er permanent lagret. De beholdes ved refresh, omstart og ny programversjon."); st.rerun()

        st.markdown("**Kontrollert anbefalt produksjonsprofil**")
        st.caption("Profilen endrer ikke startkapital, læringskonto, historikk eller eksisterende posisjoner. Den må godkjennes eksplisitt.")
        recommended = recommended_production_profile(params)
        profile_rows = [
            {"Parameter": "Minimum investeringsscore", "Nå": params.minimum_investment_score, "Anbefalt": recommended.minimum_investment_score},
            {"Parameter": "Minimum datakvalitet", "Nå": params.minimum_data_quality, "Anbefalt": recommended.minimum_data_quality},
            {"Parameter": "Maks risikoscore", "Nå": params.maximum_risk_score, "Anbefalt": recommended.maximum_risk_score},
            {"Parameter": "Maks posisjon %", "Nå": params.maximum_position_pct, "Anbefalt": recommended.maximum_position_pct},
            {"Parameter": "Maks sektor %", "Nå": params.maximum_sector_pct, "Anbefalt": recommended.maximum_sector_pct},
            {"Parameter": "Maks åpne posisjoner", "Nå": params.maximum_open_positions, "Anbefalt": recommended.maximum_open_positions},
            {"Parameter": "Kontantreserve %", "Nå": params.reserve_cash_pct, "Anbefalt": recommended.reserve_cash_pct},
            {"Parameter": "Stop-loss %", "Nå": params.stop_loss_pct, "Anbefalt": recommended.stop_loss_pct},
            {"Parameter": "Trailing stop %", "Nå": params.trailing_stop_pct, "Anbefalt": recommended.trailing_stop_pct},
            {"Parameter": "Take profit %", "Nå": params.take_profit_pct, "Anbefalt": recommended.take_profit_pct},
            {"Parameter": "Score-exit under", "Nå": params.score_exit_threshold, "Anbefalt": recommended.score_exit_threshold},
            {"Parameter": "Maks drawdown %", "Nå": params.maximum_drawdown_pct, "Anbefalt": recommended.maximum_drawdown_pct},
        ]
        profile_view = pd.DataFrame(profile_rows)
        profile_view[["Nå", "Anbefalt"]] = profile_view[["Nå", "Anbefalt"]].astype(float).round(2)
        st.dataframe(profile_view, width="stretch", hide_index=True)
        production_approval = st.text_input("Skriv GODKJENN for å bruke anbefalt produksjonsprofil", key="alp_recommended_profile_approval_v1931h")
        if st.button("Bruk anbefalt produksjonsprofil", key="alp_apply_recommended_profile_v1931h"):
            if production_approval.strip().upper() != "GODKJENN":
                st.error("Skriv GODKJENN før produksjonsprofilen endres.")
            else:
                save_parameters(recommended)
                st.success("Anbefalt produksjonsprofil er lagret og auditført. Aktiv portefølje og historikk er ikke nullstilt.")
                st.rerun()

    with st.expander("🔐 Konfigurasjonsrammeverk", expanded=False):
        cfg = configuration_status()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Lagringskilde", "PostgreSQL" if cfg.get("persistent") else "Lokal fallback")
        k2.metric("Konfigurasjonsrevisjon", cfg.get("revision", 0))
        k3.metric("Kontrollsum", cfg.get("checksum", "–"))
        k4.metric("Sist lagret", str(cfg.get("updated_at") or "–")[:19])
        st.caption("Én sentral, versjonert konfigurasjonskilde. Programoppdateringer overskriver ikke lagrede brukerinnstillinger.")
        left, right = st.columns(2)
        left.download_button(
            "Eksporter all konfigurasjon som JSON",
            export_bundle(),
            file_name=f"ai_aksje_analyzer_config_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            width="stretch",
            key="cfg_export_v18691",
        )
        uploaded = right.file_uploader("Importer konfigurasjon", type=["json"], key="cfg_import_file_v18691")
        if uploaded is not None:
            st.warning("Import erstatter gjeldende konfigurasjon. Automatisk sikkerhetskopi opprettes først.")
            if st.button("Bekreft import", type="primary", key="cfg_import_confirm_v18691"):
                try:
                    imported = import_bundle(uploaded.getvalue(), create_backup=True)
                    st.success(f"Konfigurasjonen er importert. Revisjon {imported.get('revision', 0)}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Import mislyktes: {exc}")

    history = load_equity_history(200)
    invested = sum(_f(p.get("quantity")) * _f(p.get("last_price", p.get("average_price"))) for p in (portfolio.get("positions") or {}).values())
    cash = _f(portfolio.get("cash"))
    portfolio_initial_cash = _f(portfolio.get("initial_cash")) or perf["equity"]
    total_return_value = perf["equity"] - portfolio_initial_cash
    st.markdown("##### Porteføljeoversikt")
    st.caption(
        f"Avkastning beregnes mot aktiv kontos faktiske startverdi {_fmt_nb_money(portfolio_initial_cash)}. "
        "En endret reset-verdi påvirker ikke denne historikken."
    )
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Porteføljeverdi", _fmt_nb_money(perf["equity"]), f"{perf['total_return_pct']:+.2f}%")
    k2.metric("Total avkastning", _fmt_nb_money(total_return_value))
    k3.metric("Investert", _fmt_nb_money(invested))
    k4.metric("Kontanter", _fmt_nb_money(cash))
    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Åpne posisjoner", perf["open_positions"])
    k6.metric("Eksponering", f"{(invested / perf['equity'] * 100) if perf['equity'] else 0:.1f}%")
    k7.metric("Drawdown", f"{perf['drawdown_pct']:.2f}%")
    k8.metric("Siste beslutningssyklus", str(portfolio.get("last_run_id") or "-")[:22])

    st.markdown("##### Porteføljeutvikling")
    if history and len(history) >= 3:
        hist_df = pd.DataFrame(history).sort_values("timestamp")
        hist_df["Tidspunkt"] = pd.to_datetime(hist_df["timestamp"], utc=True, errors="coerce").dt.tz_convert(None)
        hist_df["Porteføljeverdi"] = pd.to_numeric(hist_df["equity"], errors="coerce")
        hist_df["Kontanter"] = (
            pd.to_numeric(hist_df["cash"], errors="coerce")
            if "cash" in hist_df.columns
            else float(portfolio.get("cash") or 0.0)
        )
        hist_df["Investert"] = hist_df["Porteføljeverdi"] - hist_df["Kontanter"]
        hist_df["Utvikling %"] = (hist_df["Porteføljeverdi"] / max(portfolio_initial_cash, 1.0) - 1.0) * 100.0
        valid_history = hist_df.dropna(subset=["Tidspunkt", "Porteføljeverdi"])
        st.caption("Prosentkurven er normalisert mot kontoens faktiske startverdi, slik at små endringer ikke skjules i en flat millionakse.")
        st.line_chart(valid_history.set_index("Tidspunkt")[["Utvikling %"]], width="stretch", height=280)
        with st.expander("Vis kapitalfordeling", expanded=False):
            st.caption("Porteføljeverdi = kontanter + markedsverdi av åpne posisjoner.")
            st.line_chart(valid_history.set_index("Tidspunkt")[["Porteføljeverdi", "Kontanter", "Investert"]], width="stretch", height=280)
        with st.expander("Vis historikkdetaljer", expanded=False):
            view = hist_df.sort_values("timestamp", ascending=False).head(25).copy()
            view["Dato"] = view["timestamp"].map(_short_local_time)
            view["Kjørings-ID"] = view.get("run_id", "-")
            view["Avkastning %"] = (
                pd.to_numeric(view["total_return_pct"], errors="coerce")
                if "total_return_pct" in view.columns
                else view["Utvikling %"]
            )
            view["Posisjoner"] = view.get("open_positions", 0)
            view["Handler"] = view.get("trades", 0)
            view["Beslutninger"] = view.get("decisions", 0)
            view = _round_financial_columns(view, ["Porteføljeverdi", "Avkastning %"])
            st.dataframe(view[["Dato", "Kjørings-ID", "Porteføljeverdi", "Avkastning %", "Posisjoner", "Handler", "Beslutninger"]], width="stretch", hide_index=True)
    elif history:
        st.info("For få historikkpunkter til en meningsfull graf. Neste autonome kjøringer bygger utviklingskurven.")
        hist_df = pd.DataFrame(history).sort_values("timestamp", ascending=False)
        hist_df["Dato"] = hist_df["timestamp"].map(_short_local_time)
        compact = hist_df[["Dato", "run_id", "equity", "total_return_pct"]].rename(
            columns={"run_id":"Kjørings-ID", "equity":"Porteføljeverdi", "total_return_pct":"Avkastning %"}
        )
        compact = _round_financial_columns(compact, ["Porteføljeverdi", "Avkastning %"])
        st.dataframe(compact, width="stretch", hide_index=True)
    else:
        st.info("Ingen porteføljehistorikk ennå. Historikk opprettes etter neste autonome beslutningssyklus.")

    position_rows = autonomous_position_rows(portfolio)
    st.markdown("##### Åpne posisjoner")
    if position_rows:
        _render_position_cards_mobile(position_rows, st)
        desktop_rows = [{k:v for k,v in row.items() if k not in {"Selskap"}} for row in position_rows]
        with st.container(key="autonomous-desktop-positions-v1940"):
            st.dataframe(pd.DataFrame(desktop_rows), width="stretch", hide_index=True, column_config={"Antall": st.column_config.NumberColumn(format="%.2f"), "Snittkurs": st.column_config.NumberColumn(format="%.2f"), "Siste kurs": st.column_config.NumberColumn(format="%.2f"), "Markedsverdi": st.column_config.NumberColumn(format="%.2f kr"), "Avkastning kr": st.column_config.NumberColumn(format="%+.2f kr"), "Avkastning %": st.column_config.NumberColumn(format="%+.2f%%")})
    else:
        st.info("Ingen åpne teoretiske posisjoner.")

    recovered_count = recover_missing_position_history(portfolio)
    if recovered_count:
        st.warning(f"{recovered_count} eldre handler er merket som rekonstruert fra åpne posisjoner. Originale lokale logger kunne ikke gjenopprettes eksakt.")
    trades = _read(TRADES_PATH, [])
    decisions = _read(DECISIONS_PATH, [])
    notifications = _read(NOTIFICATIONS_PATH, [])
    t1, t2, t3, t4 = st.tabs(["Handler", "Beslutninger og ordreledger", "Kontrollert læring", "Audit og sporbarhet"])
    with t1:
        if trades:
            trade_rows = autonomous_trade_display_rows(trades, limit=500)
            _render_trade_cards_mobile(trade_rows, st)
            with st.container(key="autonomous-desktop-trades-v1940"):
                st.dataframe(pd.DataFrame([{k:v for k,v in row.items() if k != "Teknisk ID"} for row in trade_rows]), width="stretch", hide_index=True, column_config={"Antall": st.column_config.NumberColumn(format="%.2f"), "Kurs": st.column_config.NumberColumn(format="%.2f"), "Beløp": st.column_config.NumberColumn(format="%.2f kr")})
            with st.expander("Tekniske handelsdetaljer", expanded=False):
                st.dataframe(pd.DataFrame(trade_rows), width="stretch", hide_index=True)
            st.download_button("Eksporter handler JSON", json.dumps(trades, ensure_ascii=False, indent=2), "autonomous_trades.json", "application/json", key="alp_trades_json_v18688")
        else:
            st.caption("Ingen handler registrert.")
    with t2:
        if decisions:
            st.caption("Viser hvor hver kandidat stoppet: overlevering, porteføljekontroll, ordreintensjon eller utført ordre.")
            ledger_rows = autonomous_decision_ledger_rows(decisions)
            _render_decision_cards_mobile(ledger_rows, st)
            with st.container(key="autonomous-desktop-decisions-v1940"):
                st.dataframe(pd.DataFrame(ledger_rows), width="stretch", hide_index=True)
        else:
            st.caption("Ingen beslutninger registrert.")
    with t3:
        from controlled_parameter_learning import render_controlled_learning
        render_controlled_learning(namespace="autonomous_portfolio")
    with t4:
        audit_rows = load_audit(1000)
        try:
            from autonomous_orchestrator import load_audit as load_orchestrator_audit
            orchestrator_audit = load_orchestrator_audit(1000)
        except Exception:
            orchestrator_audit = []
        try:
            from controlled_parameter_learning import load_audit as load_learning_audit
            learning_audit = load_learning_audit(1000)
        except Exception:
            learning_audit = []
        try:
            from notifier import pushover_audit
            push_audit = pushover_audit(1000)
        except Exception:
            push_audit = []
        st.markdown("##### Permanente hendelseslogger")
        l1,l2,l3,l4,l5 = st.columns(5)
        l1.metric("Porteføljeaudit", len(audit_rows)); l2.metric("Orchestratoraudit", len(orchestrator_audit)); l3.metric("Læringsaudit", len(learning_audit)); l4.metric("Varsler", len(notifications) if isinstance(notifications, list) else 0); l5.metric("Pushover", len(push_audit))
        log_name = st.selectbox("Vis logg", ["Porteføljeaudit", "Orchestratoraudit", "Læringsaudit", "Varsler", "Pushover"], key="alp_audit_source_v1877")
        selected_log = {"Porteføljeaudit": audit_rows, "Orchestratoraudit": orchestrator_audit, "Læringsaudit": learning_audit, "Varsler": notifications if isinstance(notifications, list) else [], "Pushover": push_audit}[log_name]
        if selected_log: st.dataframe(pd.DataFrame(selected_log[-500:][::-1]), width="stretch", hide_index=True)
        else: st.caption("Ingen hendelser er registrert i valgt logg ennå.")
        st.info("For evaluering: last ned evalueringspakken og last den opp i ChatGPT. Den inneholder parametere, portefølje, handler, beslutninger, ytelse, varslingslogg, audit og siste pipeline-kjøring.")
        st.warning("Kontroller pakken før deling. Ikke legg API-nøkler, Pushover-token eller andre hemmeligheter i runtime-filene.")
        confirm = st.text_input("Skriv RESET for å nullstille kontoen", key="alp_reset_text_v18688")
        if st.button("Nullstill autonom konto", key="alp_reset_v18688"):
            try:
                reset_portfolio(confirm); st.success("Kontoen er nullstilt."); st.rerun()
            except ValueError as exc:
                st.error(str(exc))
