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

VERSION = "v18.6.92d"
ROOT = runtime_data_path("autonomous_orchestrator")
RUNS_DIR = ROOT / "runs"
LATEST_PATH = ROOT / "latest_run.json"
AUDIT_PATH = ROOT / "audit.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _audit(event: str, payload: Mapping[str, Any]) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": _now(), "version": VERSION, "event": event, **dict(payload)}, ensure_ascii=False, default=str) + "\n")


def run_post_scan_chain(
    market_run: Mapping[str, Any],
    *,
    run_autonomous: bool = True,
    run_learning: bool = True,
    require_active_portfolio: bool = True,
    trigger: str = "SCHEDULED",
) -> dict[str, Any]:
    """Execute the autonomous stages after a completed market scan."""
    chain_id = f"AO-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    result: dict[str, Any] = {
        "version": VERSION,
        "chain_id": chain_id,
        "created_at": _now(),
        "trigger": trigger,
        "source_run_id": market_run.get("run_id"),
        "status": "RUNNING",
        "stages": [],
        "errors": [],
        "execution": "THEORETICAL_ONLY",
    }

    def stage(name: str, status: str, detail: Mapping[str, Any] | None = None) -> None:
        result["stages"].append({"name": name, "status": status, "at": _now(), "detail": dict(detail or {})})

    candidates: Sequence[Mapping[str, Any]] = market_run.get("candidates") or market_run.get("proposals") or []
    stage("MARKET_SCAN", "OK", {"candidates": len(candidates), "markets": market_run.get("markets", [])})

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
    try:
        return json.loads(LATEST_PATH.read_text(encoding="utf-8")) if LATEST_PATH.exists() else {}
    except Exception:
        return {}
