"""Autonomous Orchestrator v18.6.90.

Binds Scheduled Market Intelligence, the Investment Pipeline, the theoretical
Autonomous Learning Portfolio and Controlled Parameter Learning into one
observable execution chain. No broker or live-trading integration is used.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from storage_architecture import runtime_data_path
from durable_runtime import append_event, read_events, read_json as durable_read_json, write_json as durable_write_json
from local_time import as_local, local_display

from app_version import APP_VERSION

VERSION = APP_VERSION
ROOT = runtime_data_path("autonomous_orchestrator")
RUNS_DIR = ROOT / "runs"
LATEST_PATH = ROOT / "latest_run.json"
AUDIT_PATH = ROOT / "audit.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(path: Path, value: Any) -> None:
    key = "autonomous_orchestrator/latest_run.json" if path == LATEST_PATH else f"autonomous_orchestrator/runs/{path.name}"
    durable_write_json(key, path, value)


def _audit(event: str, payload: Mapping[str, Any]) -> None:
    append_event("autonomous_orchestrator/audit.jsonl", AUDIT_PATH, {"at": _now(), "version": VERSION, "event": event, **dict(payload)})


def run_post_scan_chain(
    market_run: Mapping[str, Any],
    *,
    run_autonomous: bool = True,
    run_learning: bool = True,
    require_active_portfolio: bool = True,
    trigger: str = "SCHEDULED",
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute the autonomous stages after a completed market scan."""
    timezone_name = str(market_run.get("timezone_name") or "Europe/Oslo")
    chain_id = f"AO-{as_local(datetime.now(timezone.utc), timezone_name):%Y%m%d-%H%M%S-%f}"
    result: dict[str, Any] = {
        "version": VERSION,
        "chain_id": chain_id,
        "created_at": _now(),
        "created_at_local": local_display(_now(), timezone_name),
        "timezone_name": timezone_name,
        "trigger": trigger,
        "source_run_id": market_run.get("run_id"),
        "status": "RUNNING",
        "stages": [],
        "errors": [],
        "execution": "THEORETICAL_ONLY",
    }

    def stage(name: str, status: str, detail: Mapping[str, Any] | None = None) -> None:
        result["stages"].append({"name": name, "status": status, "at": _now(), "detail": dict(detail or {})})
        if progress_callback is not None:
            progress_callback({
                "phase": "AUTONOMOUS", "substage": name,
                "message": f"Autonomi: {name.replace('_', ' ').title()} · {status}",
            })

    observed_candidates: Sequence[Mapping[str, Any]] = market_run.get("observed_candidates") or []
    candidates: Sequence[Mapping[str, Any]] = market_run.get("candidates") or market_run.get("proposals") or []
    handoff_input = market_run.get("autonomy_handoff_input") if isinstance(market_run.get("autonomy_handoff_input"), Mapping) else {}
    scan_status = "WARNING" if observed_candidates and not candidates else "OK"
    stage("MARKET_SCAN", scan_status, {
        "candidates": len(candidates), "observed_candidates": len(observed_candidates),
        "markets": market_run.get("markets", []), "handoff_input": dict(handoff_input),
        "learning_probe_mode": bool(market_run.get("autonomy_learning_probe")),
        "warning": "Rapportkandidater finnes, men ingen ble videresendt til Autonomi" if observed_candidates and not candidates else "",
    })

    if run_autonomous:
        try:
            from autonomous_portfolio import load_portfolio, run_autonomous_cycle
            portfolio = load_portfolio()
            if not candidates:
                stage("AUTONOMOUS_PORTFOLIO", "SKIPPED", {"reason": "Ingen kandidater fra skanningen"})
            else:
                # The production portfolio remains fail-closed inside
                # run_autonomous_cycle when paused. The separate learning
                # account must still receive the canonical candidate set;
                # otherwise a paused production account silently disables all
                # learning and recreates the original no-learning deadlock.
                cycle = run_autonomous_cycle(
                    candidates, str(market_run.get("run_id") or chain_id),
                    progress_callback=progress_callback,
                )
                portfolio_trades = list(cycle.get("portfolio_trades") or [])
                learning_trades = list(cycle.get("learning_trades") or [])
                shared_learning = dict(cycle.get("autonomy_learning_account") or {})
                shared_learning_fills = [
                    dict(row) for row in list(shared_learning.get("fills") or [])
                    if isinstance(row, Mapping)
                ]
                shared_learning_buys = [row for row in shared_learning_fills if str(row.get("side") or "").upper() == "BUY"]
                shared_learning_sells = [row for row in shared_learning_fills if str(row.get("side") or "").upper() == "SELL"]
                shared_metrics = dict(shared_learning.get("account_metrics") or {})
                cycle_trades = portfolio_trades + learning_trades
                cycle_decisions = cycle.get("decisions") or []
                ordinary_buys = [x for x in portfolio_trades if str(x.get("action") or "").upper() == "BUY"]
                sells = [x for x in portfolio_trades if str(x.get("action") or "").upper() == "SELL"]
                legacy_learning_buys = [x for x in learning_trades if str(x.get("action") or "").upper() == "BUY"]
                # The shared learning account is the canonical account. Legacy
                # rows remain diagnostic only and must not make the report show
                # zero after persisted shared-account fills were completed.
                learning_buys = shared_learning_buys or legacy_learning_buys
                buys = ordinary_buys + learning_buys
                execution_integrity = dict(cycle.get("execution_integrity") or {})
                full_replay = dict(cycle.get("full_replay") or {})
                skips = [x for x in cycle_decisions if x.get("action") == "SKIP"]
                stage("AUTONOMOUS_PORTFOLIO", "OK" if execution_integrity.get("ok", True) else "BLOCKED", {
                    "trades": len(cycle_trades), "buys": len(buys), "ordinary_buys": len(ordinary_buys), "learning_buys": len(learning_buys), "sells": len(sells),
                    "skips": len(skips), "decisions": len(cycle_decisions),
                    "open_positions": len((cycle.get("portfolio") or {}).get("positions") or {}),
                    "learning_open_positions": int(shared_metrics.get("open_positions") or len((cycle.get("learning_portfolio") or {}).get("positions") or {})),
                    "status": cycle.get("portfolio", {}).get("status"),
                    "buy_tickers": [x.get("ticker") for x in ordinary_buys],
                    "learning_buy_tickers": [x.get("ticker") for x in learning_buys],
                    "learning_sell_tickers": [x.get("ticker") for x in shared_learning_sells],
                    "learning_account_id": "autonomy_learning",
                    "learning_account_updated_at": shared_metrics.get("updated_at"),
                    "learning_account_last_run_id": shared_metrics.get("last_run_id"),
                    "learning_account_metrics": shared_metrics,
                    "learning_decisions": list(shared_learning.get("decisions") or []),
                    "learning_fills": shared_learning_fills,
                    "sell_tickers": [x.get("ticker") for x in sells],
                    "execution_integrity": execution_integrity,
                    "replay_level": cycle.get("replay_level") or "DECISION_REPLAY",
                    "full_replay_audit": full_replay.get("audit") or {},
                    "full_replay_missing": full_replay.get("missing") or [],
                    "reason": ("Handel blokkert av integritetskontrollen" if not execution_integrity.get("ok", True) else ("Separate læringsposisjoner opprettet" if learning_buys and not ordinary_buys else ("Ingen kjøp opprettet" if not ordinary_buys else "Ordinære teoretiske porteføljekjøp opprettet"))),
                })
                result["autonomy_learning_account"] = shared_learning
                result["autonomy_cycle"] = {
                    "run_id": cycle.get("run_id"),
                    "learning_account": shared_learning,
                    "production_trades": portfolio_trades,
                    "legacy_learning_trades": learning_trades,
                }
                # Expose the exact persisted learning artifacts to the
                # acceptance auditor.  They remain theoretical-only and are
                # already stored by run_autonomous_cycle.
                result["learning_portfolio"] = cycle.get("learning_portfolio") or {}
                result["learning_decisions"] = cycle.get("learning_decisions") or []
                result["learning_trades"] = learning_trades
                result["learning_performance"] = cycle.get("learning_performance") or {}
        except Exception as exc:
            result["errors"].append(f"Autonomous Portfolio: {exc}")
            stage("AUTONOMOUS_PORTFOLIO", "ERROR", {
                "error_type": type(exc).__name__, "error": str(exc),
                "traceback": traceback.format_exc()[-12000:],
            })
    else:
        stage("AUTONOMOUS_PORTFOLIO", "DISABLED")

    if run_learning:
        try:
            if progress_callback is not None:
                progress_callback({
                    "phase": "AUTONOMOUS", "substage": "CONTROLLED_LEARNING",
                    "completed": 0, "total": 1,
                    "message": "Kjører kontrollert læring på lagrede resultater",
                })
            from controlled_parameter_learning import run_automatic_learning_if_due
            learning = run_automatic_learning_if_due(trigger=f"ORCHESTRATOR:{trigger}", force=True)
            learning["source_result_id"] = (market_run.get("canonical_result") or {}).get("result_id")
            stage("CONTROLLED_LEARNING", "OK" if learning.get("ran") else "SKIPPED", learning)
        except Exception as exc:
            result["errors"].append(f"Controlled Learning: {exc}")
            stage("CONTROLLED_LEARNING", "ERROR", {"error": str(exc)})
    else:
        stage("CONTROLLED_LEARNING", "DISABLED")

    result["completed_at"] = _now()
    result["status"] = "OK" if not result["errors"] else "COMPLETED_WITH_ERRORS"
    _write(RUNS_DIR / f"{chain_id}.json", result)
    _write(LATEST_PATH, result)
    _audit("CHAIN_COMPLETED", {"chain_id": chain_id, "status": result["status"], "source_run_id": result["source_run_id"], "errors": result["errors"]})
    return result


def load_latest_chain() -> dict[str, Any]:
    value = durable_read_json("autonomous_orchestrator/latest_run.json", LATEST_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def load_audit(limit: int = 1000) -> list[dict[str, Any]]:
    return read_events("autonomous_orchestrator/audit.jsonl", AUDIT_PATH, limit=limit)
