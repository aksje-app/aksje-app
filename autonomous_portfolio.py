"""Autonomous Learning Portfolio Foundation v18.6.88.

A fully isolated, theoretical portfolio that can execute simulated BUY, HOLD,
REDUCE and SELL decisions from the latest Investment Pipeline output. It uses a
fixed, user-controlled parameter set. Self-modifying parameters are explicitly
out of scope for this version.
"""
from __future__ import annotations

import io
import json
import math
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from storage_architecture import runtime_data_path
from persistent_config_store import read_persistent_json, write_persistent_json, persistence_status
from configuration_framework import export_bundle, import_bundle, status as configuration_status
from durable_runtime import append_event, read_events, read_json as durable_read_json, write_json as durable_write_json

VERSION = "v19.0.18b"
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


@dataclass
class AutonomousParameters:
    initial_cash: float = 500000.0
    minimum_investment_score: float = 78.0
    minimum_data_quality: float = 55.0
    maximum_risk_score: float = 65.0
    maximum_position_pct: float = 5.0
    maximum_sector_pct: float = 20.0
    maximum_open_positions: int = 12
    reserve_cash_pct: float = 10.0
    stop_loss_pct: float = 8.0
    trailing_stop_pct: float = 10.0
    take_profit_pct: float = 22.0
    score_exit_threshold: float = 55.0
    maximum_drawdown_pct: float = 12.0
    daily_loss_limit_pct: float = 4.0
    allow_additions: bool = False
    enable_learning_probe_buys: bool = True
    learning_probe_minimum_score: float = 70.0
    learning_probe_max_buys: int = 3
    learning_probe_notional_value: float = 2500.0
    learning_probe_horizon_days: int = 30
    notify_trades: bool = True
    notify_risk_events: bool = True

    def normalized(self) -> "AutonomousParameters":
        return AutonomousParameters(
            initial_cash=max(1000.0, _f(self.initial_cash, 500000.0)),
            minimum_investment_score=max(0.0, min(100.0, _f(self.minimum_investment_score, 78.0))),
            minimum_data_quality=max(0.0, min(100.0, _f(self.minimum_data_quality, 55.0))),
            maximum_risk_score=max(0.0, min(100.0, _f(self.maximum_risk_score, 65.0))),
            maximum_position_pct=max(0.1, min(25.0, _f(self.maximum_position_pct, 5.0))),
            maximum_sector_pct=max(1.0, min(100.0, _f(self.maximum_sector_pct, 20.0))),
            maximum_open_positions=max(1, min(100, int(self.maximum_open_positions))),
            reserve_cash_pct=max(0.0, min(95.0, _f(self.reserve_cash_pct, 10.0))),
            stop_loss_pct=max(0.1, min(50.0, _f(self.stop_loss_pct, 8.0))),
            trailing_stop_pct=max(0.1, min(50.0, _f(self.trailing_stop_pct, 10.0))),
            take_profit_pct=max(0.1, min(300.0, _f(self.take_profit_pct, 22.0))),
            score_exit_threshold=max(0.0, min(100.0, _f(self.score_exit_threshold, 55.0))),
            maximum_drawdown_pct=max(0.5, min(80.0, _f(self.maximum_drawdown_pct, 12.0))),
            daily_loss_limit_pct=max(0.1, min(50.0, _f(self.daily_loss_limit_pct, 4.0))),
            allow_additions=bool(self.allow_additions),
            enable_learning_probe_buys=bool(self.enable_learning_probe_buys),
            learning_probe_minimum_score=max(0.0, min(100.0, _f(self.learning_probe_minimum_score, 70.0))),
            learning_probe_max_buys=max(0, min(10, int(self.learning_probe_max_buys))),
            learning_probe_notional_value=max(100.0, min(100000.0, _f(self.learning_probe_notional_value, 2500.0))),
            learning_probe_horizon_days=max(1, min(365, int(self.learning_probe_horizon_days))),
            notify_trades=bool(self.notify_trades),
            notify_risk_events=bool(self.notify_risk_events),
        )


def load_parameters() -> AutonomousParameters:
    raw = _read(PARAMETERS_PATH, {})
    try:
        return AutonomousParameters(**{k: raw[k] for k in AutonomousParameters.__dataclass_fields__ if k in raw}).normalized()
    except Exception:
        return AutonomousParameters()


def save_parameters(params: AutonomousParameters) -> AutonomousParameters:
    params = params.normalized()
    previous = _read(PARAMETERS_PATH, {})
    _write(PARAMETERS_PATH, asdict(params))
    if previous and previous != asdict(params):
        _append_audit("PARAMETERS_CHANGED_BY_USER", {"before": previous, "after": asdict(params)})
    return params


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
    return value


def load_learning_portfolio() -> dict[str, Any]:
    ensure_portfolio_separation()
    params = load_parameters()
    value = _read(LEARNING_PORTFOLIO_PATH, None)
    if not isinstance(value, dict):
        value = default_learning_portfolio(params)
        _write(LEARNING_PORTFOLIO_PATH, value)
    value.setdefault("positions", {})
    value.setdefault("closed_positions", [])
    return value


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
    for key in ("investment_score", "score", "combined_score", "decision_score"):
        value = _f(candidate.get(key), float("nan"))
        if math.isfinite(value):
            return value
    return default


def _candidate_quality(candidate: Mapping[str, Any], default: float = 100.0) -> float:
    raw = candidate.get("combined_data_quality") if isinstance(candidate.get("combined_data_quality"), Mapping) else {}
    evidence = candidate.get("evidence_coverage") if isinstance(candidate.get("evidence_coverage"), Mapping) else {}
    for value in (
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
    _write(LEARNING_DECISIONS_PATH, list(rows) + current[:5000])


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
        avg = _f(pos.get("average_price"), price)
        score = _candidate_score(candidate, _f(pos.get("entry_score"), 100.0))
        age = _days_opened(pos.get("opened_at"))
        reason = None
        if price <= avg * (1 - params.stop_loss_pct / 100):
            reason = "Læringsobservasjon: stop loss"
        elif price >= avg * (1 + params.take_profit_pct / 100):
            reason = "Læringsobservasjon: gevinstmål"
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
        "Læringskjøp aktivert": bool(params.enable_learning_probe_buys),
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


def _notification(kind: str, title: str, message: str, payload: Mapping[str, Any]) -> None:
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
        from notification_service import send_pushover_notification
        item["attempted_at"] = _now(); ok = send_pushover_notification(title, message)
        item["status"] = "SENT" if ok is not False else "FAILED"; item["delivery"] = "PUSHOVER_SENT" if ok is not False else "PUSHOVER_FAILED"
        if ok is not False: item["sent_at"] = _now()
        else: item["error"] = "Pushover-sender returnerte False"
    except Exception as exc:
        item["attempted_at"] = _now(); item["status"] = "FAILED"; item["delivery"] = "PUSHOVER_FAILED"; item["error"] = str(exc)[:500]
    _write(NOTIFICATIONS_PATH, rows[:1000])


def _record_trade(trade: dict[str, Any]) -> None:
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
        row = dict(raw)
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


def _sell(portfolio: dict[str, Any], ticker: str, price: float, reason: str, run_id: str, params: AutonomousParameters) -> dict[str, Any] | None:
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
    }
    _record_trade(trade)
    if params.notify_trades:
        _notification("TRADE", f"AUTONOMOUS SELL {ticker}", f"{reason}. Teoretisk resultat {trade['pnl_pct']:+.2f}% ({pnl:+.2f}).", trade)
    return trade


def run_autonomous_cycle(candidates: Sequence[Mapping[str, Any]], run_id: str | None = None) -> dict[str, Any]:
    params = load_parameters().normalized()
    portfolio = load_portfolio()
    learning_portfolio = load_learning_portfolio()
    run_id = run_id or f"ALP-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    decisions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    learning_decisions: list[dict[str, Any]] = []
    learning_trades: list[dict[str, Any]] = []
    exited_this_cycle: set[str] = set()
    candidate_map = {str(c.get("ticker") or "").upper(): c for c in candidates if str(c.get("ticker") or "").strip()}

    # Learning observations have their own ledger and never affect ordinary
    # portfolio cash, position limits, sector exposure or performance.
    observed_decisions, observed_trades = _update_learning_positions(learning_portfolio, candidate_map, run_id, params)
    learning_decisions.extend(observed_decisions)
    learning_trades.extend(observed_trades)

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
            trade = _sell(portfolio, ticker, price, reason, run_id, params)
            if trade:
                trades.append(trade)
                exited_this_cycle.add(ticker)
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SELL", "reason": reason, "price": price, "score": score})
        else:
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "HOLD", "reason": "Ingen exitregel utløst", "price": price, "score": score})

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
        for candidate in sorted(candidates, key=lambda c: _candidate_score(c), reverse=True):
            ticker = str(candidate.get("ticker") or "").upper()
            if not ticker or ticker in held:
                continue
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP",
                              "reason": pause_reason, "score": _candidate_score(candidate),
                              "sent_to_autonomy": True, "portfolio_check_completed": True,
                              "order_intent_created": False, "order_executed": False,
                              "execution_stage": "PORTFOLIO_PAUSED"})
    if portfolio.get("status") == "ACTIVE":
        ranked = sorted(candidates, key=lambda c: _candidate_score(c), reverse=True)
        for candidate in ranked:
            ticker = str(candidate.get("ticker") or "").upper()
            if not ticker:
                continue
            if ticker in exited_this_cycle:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": "Ingen gjeninntreden i samme beslutningssyklus"})
                continue
            score = _candidate_score(candidate)
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
            if score < params.minimum_investment_score:
                rejection = f"Score {score:.1f} under terskel"
            elif quality < params.minimum_data_quality:
                rejection = f"Datakvalitet {quality:.1f} under terskel"
            elif risk > params.maximum_risk_score:
                rejection = f"Risiko {risk:.1f} over grense"
            elif price <= 0:
                rejection = "Mangler gyldig markedspris"
            elif len(portfolio["positions"]) >= params.maximum_open_positions:
                rejection = "Maks antall åpne posisjoner"
            if rejection:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": rejection, "score": score})
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
                "entry_score": score, "entry_risk_score": risk, "entry_data_quality": quality,
                "source_run_id": run_id,
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
                "value": round(value, 2), "pnl": 0.0, "reason": f"Score {score:.1f}, risiko {risk:.1f}, datakvalitet {quality:.1f}",
                "strategy": _candidate_strategy(candidate), "mode": "THEORETICAL_ONLY",
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
            _record_trade(trade)
            trades.append(trade)
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "BUY", "reason": trade["reason"], "price": price, "score": score})
            if params.notify_trades:
                _notification("TRADE", f"AUTONOMOUS BUY {ticker}", f"Teoretisk kjøp {quantity:g} @ {price:.2f}. {trade['reason']}", trade)

        # v19.0.18: Learning guarantee. If an active theoretical portfolio
        # received candidates but the ordinary production gates created no BUY,
        # create a small number of explicitly marked learning-probe positions.
        # This does not alter real trading, production thresholds or risk limits;
        # it prevents a week of Autonomi runs from producing zero learning data.
        normal_buys_this_cycle = [t for t in trades if t.get("action") == "BUY" and not t.get("learning_probe")]
        if params.enable_learning_probe_buys and not normal_buys_this_cycle and candidates:
            learning_ranked = sorted(candidates, key=lambda c: _candidate_score(c), reverse=True)
            learning_count = 0
            for candidate in learning_ranked:
                if learning_count >= params.learning_probe_max_buys:
                    break
                ticker = str(candidate.get("ticker") or "").upper()
                if not ticker or ticker in portfolio["positions"] or ticker in learning_portfolio["positions"] or ticker in exited_this_cycle:
                    continue
                score = _candidate_score(candidate)
                if score < params.learning_probe_minimum_score:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": f"Under læringsgrense {score:.1f} < {params.learning_probe_minimum_score:.1f}", "score": score})
                    continue
                price = _candidate_price(candidate)
                if price <= 0:
                    learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "OBSERVE", "reason": "Mangler gyldig pris for læringskjøp", "score": score})
                    continue
                risk = _candidate_risk(candidate)
                quality = _candidate_quality(candidate)
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
                    "entry_score": score, "entry_risk_score": risk, "entry_data_quality": quality,
                    "source_run_id": run_id, "learning_probe": True, "origin": "AUTONOMY_LEARNING_PROBE", "portfolio_type": "LEARNING",
                    "observation_horizon_days": params.learning_probe_horizon_days,
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
                    "trade_id": f"LT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", "timestamp": _now(), "run_id": run_id,
                    "action": "BUY", "ticker": ticker, "price": round(price, 4), "quantity": quantity,
                    "value": round(value, 2), "pnl": 0.0,
                    "reason": f"Læringskjøp: ingen ordinære kjøp ble utløst. Score {score:.1f}, risiko {risk:.1f}, datakvalitet {quality:.1f}",
                    "strategy": _candidate_strategy(candidate), "mode": "LEARNING_ONLY", "learning_probe": True, "portfolio_type": "LEARNING",
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
                _record_learning_trade(trade)
                learning_trades.append(trade)
                learning_decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "ADD_OBSERVATION", "reason": trade["reason"], "price": price, "score": score, "learning_probe": True})
                learning_portfolio["total_entry_notional"] = _f(learning_portfolio.get("total_entry_notional")) + value
                learning_count += 1
                if params.notify_trades:
                    _notification("TRADE", f"AUTONOMY LEARNING BUY {ticker}", f"Teoretisk læringskjøp {quantity:g} @ {price:.2f}. {trade['reason']}", trade)

    equity = portfolio_equity(portfolio)
    portfolio["updated_at"] = _now()
    portfolio["last_run_id"] = run_id
    portfolio["last_equity"] = equity
    portfolio["high_watermark"] = max(_f(portfolio.get("high_watermark"), equity), equity)
    learning_portfolio["updated_at"] = _now()
    learning_portfolio["last_run_id"] = run_id
    _write(PORTFOLIO_PATH, portfolio)
    _write(LEARNING_PORTFOLIO_PATH, learning_portfolio)
    _record_decisions(decisions)
    _record_learning_decisions(learning_decisions)
    _append_equity_history(portfolio, run_id, trades=len(trades), decisions=len(decisions))
    _append_learning_equity_history(learning_portfolio, run_id, trades=len(learning_trades), decisions=len(learning_decisions))
    perf = calculate_performance(portfolio)
    learning_perf = learning_portfolio_performance(learning_portfolio)
    _write(PERFORMANCE_PATH, perf)
    _write(LEARNING_PERFORMANCE_PATH, learning_perf)
    _append_audit("AUTONOMOUS_CYCLE_COMPLETED", {"run_id": run_id, "decisions": len(decisions), "ordinary_trades": len(trades), "learning_decisions": len(learning_decisions), "learning_trades": len(learning_trades), "equity": equity, "status": portfolio.get("status")})
    learning_result = None
    try:
        from controlled_parameter_learning import run_automatic_learning_if_due
        learning_result = run_automatic_learning_if_due(trigger="AUTONOMOUS_CYCLE", force=False)
    except Exception as exc:
        _append_audit("AUTOMATIC_LEARNING_HOOK_FAILED", {"run_id": run_id, "error": str(exc)})
    return {"run_id": run_id, "portfolio": portfolio, "learning_portfolio": learning_portfolio, "decisions": decisions + learning_decisions, "portfolio_decisions": decisions, "learning_decisions": learning_decisions, "trades": trades + learning_trades, "portfolio_trades": trades, "learning_trades": learning_trades, "performance": perf, "learning_performance": learning_perf, "learning": learning_result}


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


def build_evaluation_bundle() -> bytes:
    """Create a compact ZIP that can be uploaded to ChatGPT for evaluation."""
    # Rehydrate durable event streams before building the backwards-compatible
    # file bundle after a deploy/restart.
    load_audit(5000)
    try:
        from autonomous_orchestrator import load_audit as load_orchestrator_audit, load_latest_chain
        load_orchestrator_audit(5000); load_latest_chain()
        from controlled_parameter_learning import load_audit as load_learning_audit
        load_learning_audit(5000)
    except Exception:
        pass
    manifest = {
        "version": VERSION, "created_at": _now(), "purpose": "Module evaluation",
        "contains": ["autonomous_portfolio", "learning_portfolio", "parameters", "ordinary_trades", "learning_trades", "ordinary_decisions", "learning_decisions", "performance", "equity_history", "learning_equity_history", "notifications", "audit", "latest_pipeline", "controlled_learning"],
        "privacy_note": "Review before sharing. The bundle is intended to contain trading simulation data, not credentials.",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, path in (
            ("portfolio.json", PORTFOLIO_PATH), ("learning_portfolio.json", LEARNING_PORTFOLIO_PATH), ("parameters.json", PARAMETERS_PATH), ("trades.json", TRADES_PATH), ("learning_trades.json", LEARNING_TRADES_PATH),
            ("decisions.json", DECISIONS_PATH), ("learning_decisions.json", LEARNING_DECISIONS_PATH), ("performance.json", PERFORMANCE_PATH), ("learning_performance.json", LEARNING_PERFORMANCE_PATH), ("equity_history.json", EQUITY_HISTORY_PATH), ("learning_equity_history.json", LEARNING_EQUITY_HISTORY_PATH), ("notifications.json", NOTIFICATIONS_PATH),
            ("audit.jsonl", AUDIT_PATH), ("equity_history_pre_separation.json", LEGACY_MIXED_EQUITY_HISTORY_PATH), ("latest_pipeline.json", LATEST_PIPELINE_PATH),
        ):
            if path.exists():
                zf.writestr(name, path.read_bytes())
        try:
            from autonomous_orchestrator import LATEST_PATH as ORCHESTRATOR_LATEST_PATH, AUDIT_PATH as ORCHESTRATOR_AUDIT_PATH
            for name, path in (("autonomous_orchestrator/latest_run.json", ORCHESTRATOR_LATEST_PATH), ("autonomous_orchestrator/audit.jsonl", ORCHESTRATOR_AUDIT_PATH)):
                if path.exists(): zf.writestr(name, path.read_bytes())
        except Exception:
            pass
        try:
            from controlled_parameter_learning import STATE_PATH, HYPOTHESES_PATH, EXPERIMENTS_PATH, VERSIONS_PATH, AUDIT_PATH as LEARNING_AUDIT_PATH, REPORTS_PATH
            for name, path in (("controlled_learning/state.json", STATE_PATH), ("controlled_learning/hypotheses.json", HYPOTHESES_PATH), ("controlled_learning/experiments.json", EXPERIMENTS_PATH), ("controlled_learning/parameter_versions.json", VERSIONS_PATH), ("controlled_learning/audit.jsonl", LEARNING_AUDIT_PATH), ("controlled_learning/management_reports.json", REPORTS_PATH)):
                if path.exists(): zf.writestr(name, path.read_bytes())
        except Exception:
            pass
    return buffer.getvalue()


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
    if b1.button("📈 Åpne autonom portefølje", use_container_width=True, key="learning_to_autonomous_v19018b"):
        _navigate_autonomy_workspace("autonomous_portfolio")
    if b2.button("🧭 Til Autonomi Oversikt", use_container_width=True, key="learning_to_overview_v19018b"):
        _navigate_autonomy_workspace("overview")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Åpne læringsposisjoner", perf["open_positions"])
    c2.metric("Inngangsnotional", f"{perf['entry_notional']:,.0f}")
    c3.metric("Nåverdi", f"{perf['current_value']:,.0f}")
    c4.metric("Samlet P/L", f"{perf['total_pnl']:+,.0f}")
    c5.metric("Læringsavkastning", f"{perf['return_pct']:+.2f}%")
    st.info(f"Fast notional per ny læringsposisjon: {params.learning_probe_notional_value:,.0f}. Normal observasjonshorisont: {params.learning_probe_horizon_days} dager.")

    history = load_learning_equity_history(200)
    st.markdown("##### Utvikling i læringsporteføljen")
    if history:
        hist_df = pd.DataFrame(history).sort_values("timestamp")
        chart_cols = [c for c in ("total_pnl", "return_pct") if c in hist_df.columns]
        if chart_cols:
            st.line_chart(hist_df.set_index("timestamp")[chart_cols], use_container_width=True)
        st.dataframe(hist_df.sort_values("timestamp", ascending=False).head(25), use_container_width=True, hide_index=True)
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
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Ingen åpne læringsposisjoner.")

    learning_trades = _read(LEARNING_TRADES_PATH, [])
    learning_decisions = _read(LEARNING_DECISIONS_PATH, [])
    closed = portfolio.get("closed_positions") or []
    t1, t2, t3 = st.tabs(["Læringshandler", "Observasjonsbeslutninger", "Lukkede observasjoner"])
    with t1:
        st.dataframe(pd.DataFrame(learning_trades[:500]), use_container_width=True, hide_index=True) if learning_trades else st.caption("Ingen læringshandler registrert.")
    with t2:
        st.dataframe(pd.DataFrame(learning_decisions[:1000]), use_container_width=True, hide_index=True) if learning_decisions else st.caption("Ingen observasjonsbeslutninger registrert.")
    with t3:
        st.dataframe(pd.DataFrame(closed[:500]), use_container_width=True, hide_index=True) if closed else st.caption("Ingen lukkede læringsobservasjoner.")



def _fmt_nb_money(value: Any) -> str:
    try:
        return f"{float(value):,.0f} kr".replace(",", " ")
    except Exception:
        return "-"


def _fmt_nb_number(value: Any, decimals: int = 2) -> str:
    try:
        return f"{float(value):,.{decimals}f}".replace(",", " ")
    except Exception:
        return "-"


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
    if nav1.button("🧪 Vis læringsportefølje", use_container_width=True, key="autonomous_to_learning_v19018b"):
        _navigate_autonomy_workspace("learning_portfolio")
    if nav2.button("🧭 Til Autonomi Oversikt", use_container_width=True, key="autonomous_to_overview_v19018b"):
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
    c2.metric("Porteføljeverdi", f"{perf['equity']:,.0f}")
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
        if a.button("Pause autonom portefølje", use_container_width=True, key="alp_pause_v18688"):
            set_status(False, "Pauset av bruker"); st.rerun()
    else:
        if a.button("Aktiver autonom simulering", type="primary", use_container_width=True, key="alp_activate_v18688"):
            set_status(True, "Aktivert av bruker"); st.rerun()
    if b.button("Kjør én teoretisk beslutningssyklus", use_container_width=True, key="alp_cycle_v18690", help="Bruker siste lagrede kandidatliste. Starter ikke en ny markedsskanning."):
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
            if st.button("▶ Kjør hele autonome kjeden nå", type="primary", use_container_width=True, key="alp_run_full_chain_v18690"):
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
                st.dataframe(pd.DataFrame(chain.get("stages") or []), use_container_width=True, hide_index=True)
                if chain.get("errors"):
                    st.error(" | ".join(chain.get("errors") or []))
    except Exception:
        pass

    c.download_button("Last ned evalueringspakke", build_evaluation_bundle(), file_name=f"autonomous_learning_evaluation_{datetime.now().strftime('%Y%m%d_%H%M')}.zip", mime="application/zip", use_container_width=True, key="alp_eval_bundle_v18688")

    with st.expander("Faste parametere", expanded=False):
        p1, p2, p3, p4 = st.columns(4)
        initial_cash = p1.number_input("Startkapital", 1000.0, 100000000.0, float(params.initial_cash), 10000.0, key="alp_initial_v18688")
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
        learning_min_score = s3.slider("Minimum læringsscore", 0.0, 100.0, float(params.learning_probe_minimum_score), 1.0, key="alp_learning_probe_min_v19018")
        learning_max_buys = s4.number_input("Maks læringskjøp", 0, 10, int(params.learning_probe_max_buys), 1, key="alp_learning_probe_max_v19018")
        u1, u2 = st.columns(2)
        learning_notional = u1.number_input("Notional per læringsposisjon", 100.0, 100000.0, float(params.learning_probe_notional_value), 100.0, key="alp_learning_notional_v19018b")
        learning_horizon = u2.number_input("Læringshorisont (dager)", 1, 365, int(params.learning_probe_horizon_days), 1, key="alp_learning_horizon_v19018b")
        notify = st.checkbox("Varsle ved teoretiske handler", params.notify_trades, key="alp_notify_v18688")
        if st.button("Lagre parametere", key="alp_save_params_v18688"):
            save_parameters(AutonomousParameters(initial_cash=initial_cash, minimum_investment_score=min_score, minimum_data_quality=min_quality, maximum_risk_score=max_risk, maximum_position_pct=max_pos, maximum_sector_pct=max_sector, maximum_open_positions=int(max_open), reserve_cash_pct=reserve, stop_loss_pct=stop, trailing_stop_pct=trail, take_profit_pct=target, score_exit_threshold=score_exit, maximum_drawdown_pct=max_dd, enable_learning_probe_buys=learning_enabled, learning_probe_minimum_score=learning_min_score, learning_probe_max_buys=int(learning_max_buys), learning_probe_notional_value=learning_notional, learning_probe_horizon_days=int(learning_horizon), notify_trades=notify, notify_risk_events=True))
            st.success("Parameterne er permanent lagret. De beholdes ved refresh, omstart og ny programversjon."); st.rerun()

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
            use_container_width=True,
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
    start_value = _f(params.initial_cash) or perf["equity"]
    total_return_value = perf["equity"] - start_value
    st.markdown("##### Porteføljeoversikt")
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
        hist_df["Dato"] = hist_df["timestamp"].map(_short_local_time)
        st.line_chart(hist_df.set_index("Dato")[["equity"]], use_container_width=True, height=280)
        with st.expander("Vis historikkdetaljer", expanded=False):
            view = hist_df.sort_values("timestamp", ascending=False).head(25).copy()
            view = view.rename(columns={"equity":"Porteføljeverdi", "total_return_pct":"Avkastning %", "open_positions":"Posisjoner", "trades":"Handler", "decisions":"Beslutninger", "run_id":"Kjørings-ID"})
            st.dataframe(view[["Dato", "Kjørings-ID", "Porteføljeverdi", "Avkastning %", "Posisjoner", "Handler", "Beslutninger"]], use_container_width=True, hide_index=True)
    elif history:
        st.info("For få historikkpunkter til en meningsfull graf. Neste autonome kjøringer bygger utviklingskurven.")
        hist_df = pd.DataFrame(history).sort_values("timestamp", ascending=False)
        hist_df["Dato"] = hist_df["timestamp"].map(_short_local_time)
        st.dataframe(hist_df[["Dato", "run_id", "equity", "total_return_pct"]].rename(columns={"run_id":"Kjørings-ID", "equity":"Porteføljeverdi", "total_return_pct":"Avkastning %"}), use_container_width=True, hide_index=True)
    else:
        st.info("Ingen porteføljehistorikk ennå. Historikk opprettes etter neste autonome beslutningssyklus.")

    position_rows = autonomous_position_rows(portfolio)
    st.markdown("##### Åpne posisjoner")
    if position_rows:
        _render_position_cards_mobile(position_rows, st)
        desktop_rows = [{k:v for k,v in row.items() if k not in {"Selskap"}} for row in position_rows]
        with st.container(key="autonomous-desktop-positions-v1940"):
            st.dataframe(pd.DataFrame(desktop_rows), use_container_width=True, hide_index=True, column_config={"Antall": st.column_config.NumberColumn(format="%.2f"), "Snittkurs": st.column_config.NumberColumn(format="%.2f"), "Siste kurs": st.column_config.NumberColumn(format="%.2f"), "Markedsverdi": st.column_config.NumberColumn(format="%.0f kr"), "Avkastning kr": st.column_config.NumberColumn(format="%+.0f kr"), "Avkastning %": st.column_config.NumberColumn(format="%+.2f%%")})
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
                st.dataframe(pd.DataFrame([{k:v for k,v in row.items() if k != "Teknisk ID"} for row in trade_rows]), use_container_width=True, hide_index=True, column_config={"Antall": st.column_config.NumberColumn(format="%.2f"), "Kurs": st.column_config.NumberColumn(format="%.2f"), "Beløp": st.column_config.NumberColumn(format="%.0f kr")})
            with st.expander("Tekniske handelsdetaljer", expanded=False):
                st.dataframe(pd.DataFrame(trade_rows), use_container_width=True, hide_index=True)
            st.download_button("Eksporter handler JSON", json.dumps(trades, ensure_ascii=False, indent=2), "autonomous_trades.json", "application/json", key="alp_trades_json_v18688")
        else:
            st.caption("Ingen handler registrert.")
    with t2:
        if decisions:
            st.caption("Viser hvor hver kandidat stoppet: overlevering, porteføljekontroll, ordreintensjon eller utført ordre.")
            ledger_rows = autonomous_decision_ledger_rows(decisions)
            _render_decision_cards_mobile(ledger_rows, st)
            with st.container(key="autonomous-desktop-decisions-v1940"):
                st.dataframe(pd.DataFrame(ledger_rows), use_container_width=True, hide_index=True)
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
        if selected_log: st.dataframe(pd.DataFrame(selected_log[-500:][::-1]), use_container_width=True, hide_index=True)
        else: st.caption("Ingen hendelser er registrert i valgt logg ennå.")
        st.info("For evaluering: last ned evalueringspakken og last den opp i ChatGPT. Den inneholder parametere, portefølje, handler, beslutninger, ytelse, varslingslogg, audit og siste pipeline-kjøring.")
        st.warning("Kontroller pakken før deling. Ikke legg API-nøkler, Pushover-token eller andre hemmeligheter i runtime-filene.")
        confirm = st.text_input("Skriv RESET for å nullstille kontoen", key="alp_reset_text_v18688")
        if st.button("Nullstill autonom konto", key="alp_reset_v18688"):
            try:
                reset_portfolio(confirm); st.success("Kontoen er nullstilt."); st.rerun()
            except ValueError as exc:
                st.error(str(exc))
