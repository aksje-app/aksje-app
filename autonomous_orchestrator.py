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
from typing import Any, Mapping, Sequence

from storage_architecture import runtime_data_path
from durable_runtime import append_event, read_events, read_json as durable_read_json, write_json as durable_write_json
from local_time import as_local, local_display

VERSION = "v19.0.17"
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

    observed_candidates: Sequence[Mapping[str, Any]] = market_run.get("observed_candidates") or []
    candidates: Sequence[Mapping[str, Any]] = market_run.get("candidates") or market_run.get("proposals") or []
    handoff_input = market_run.get("autonomy_handoff_input") if isinstance(market_run.get("autonomy_handoff_input"), Mapping) else {}
    scan_status = "WARNING" if observed_candidates and not candidates else "OK"
    stage("MARKET_SCAN", scan_status, {
        "candidates": len(candidates), "observed_candidates": len(observed_candidates),
        "markets": market_run.get("markets", []), "handoff_input": dict(handoff_input),
        "warning": "Rapportkandidater finnes, men ingen ble videresendt til Autonomi" if observed_candidates and not candidates else "",
    })

    if run_autonomous:
        try:
            from autonomous_portfolio import load_portfolio, run_autonomous_cycle
            portfolio = load_portfolio()
            if require_active_portfolio and portfolio.get("status") != "ACTIVE":
                stage("AUTONOMOUS_PORTFOLIO", "SKIPPED", {"reason": "Porteføljen er pauset"})
            elif not candidates:
                stage("AUTONOMOUS_PORTFOLIO", "SKIPPED", {"reason": "Ingen kandidater fra skanningen"})
            else:
                cycle = run_autonomous_cycle(candidates, str(market_run.get("run_id") or chain_id))
                cycle_trades = cycle.get("trades") or []
                cycle_decisions = cycle.get("decisions") or []
                buys = [x for x in cycle_trades if x.get("action") == "BUY"]
                sells = [x for x in cycle_trades if x.get("action") == "SELL"]
                skips = [x for x in cycle_decisions if x.get("action") == "SKIP"]
                stage("AUTONOMOUS_PORTFOLIO", "OK", {
                    "trades": len(cycle_trades), "buys": len(buys), "sells": len(sells),
                    "skips": len(skips), "decisions": len(cycle_decisions),
                    "open_positions": len((cycle.get("portfolio") or {}).get("positions") or {}),
                    "status": cycle.get("portfolio", {}).get("status"),
                    "buy_tickers": [x.get("ticker") for x in buys],
                    "sell_tickers": [x.get("ticker") for x in sells],
                })
        except Exception as exc:
            result["errors"].append(f"Autonomous Portfolio: {exc}")
            stage("AUTONOMOUS_PORTFOLIO", "ERROR", {"error": str(exc)})
    else:
        stage("AUTONOMOUS_PORTFOLIO", "DISABLED")

    if run_learning:
        try:
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
