#!/usr/bin/env python3
"""Mirror legacy Paper Trading and Autonomy state into v19.8.0 accounts.

The tool is intentionally self-contained inside the migration archive. It reads
legacy state through the central document repository, local runtime mirrors, or
legacy PostgreSQL paper tables without importing the full Streamlit app.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.strategy_account_service import get_strategy_account_service
from services.simulated_execution_service import get_simulated_execution_service
from storage_architecture import runtime_data_path


def _json_file(path: Path) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except Exception:
        return None


def _query_rows(conn: Any, sql: str) -> list[dict[str, Any]]:
    try:
        cur = conn.cursor()
        cur.execute(sql)
        columns = [str(item[0]) for item in (cur.description or [])]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def _legacy_paper_postgres() -> dict[str, Any] | None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return None
    try:
        import psycopg2  # type: ignore
    except Exception:
        return None
    try:
        conn = psycopg2.connect(database_url)
    except Exception:
        return None
    try:
        state = _query_rows(conn, "SELECT * FROM paper_state WHERE id=1")
        positions_rows = _query_rows(conn, "SELECT * FROM paper_positions ORDER BY ticker")
        trades = _query_rows(conn, "SELECT * FROM paper_trades ORDER BY id")
        if not state and not positions_rows and not trades:
            return None
        cash = float((state[0] if state else {}).get("cash") or 100000.0)
        positions: dict[str, dict[str, Any]] = {}
        for row in positions_rows:
            ticker = str(row.get("ticker") or "").upper().strip()
            if not ticker:
                continue
            positions[ticker] = dict(row)
        return {"cash": cash, "positions": positions, "trades": trades}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _load_paper_legacy(documents: Any) -> tuple[dict[str, Any] | None, str]:
    value = documents.read("paper_trading/portfolio.json", default=None)
    if isinstance(value, Mapping):
        return dict(value), "document:paper_trading/portfolio.json"
    for path in (
        PROJECT_ROOT / "paper_portfolio.json",
        runtime_data_path("paper_portfolio.json"),
    ):
        value = _json_file(path)
        if isinstance(value, Mapping):
            return dict(value), f"file:{path}"
    value = _legacy_paper_postgres()
    if isinstance(value, Mapping):
        return dict(value), "postgres:legacy_paper_tables"
    return None, "missing"


def _load_autonomy_legacy(documents: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    portfolio = documents.read("autonomous_portfolio/portfolio.json", default=None)
    trades = documents.read("autonomous_portfolio/trades.json", default=[])
    source = "document:autonomous_portfolio"
    if not isinstance(portfolio, Mapping):
        path = runtime_data_path("autonomous_portfolio", "portfolio.json")
        portfolio = _json_file(path)
        source = f"file:{path}"
    if not isinstance(trades, list):
        trades = []
    if not trades:
        local_trades = _json_file(runtime_data_path("autonomous_portfolio", "trades.json"))
        if isinstance(local_trades, list):
            trades = local_trades
    return (dict(portfolio) if isinstance(portfolio, Mapping) else None), [dict(x) for x in trades if isinstance(x, Mapping)], source if isinstance(portfolio, Mapping) else "missing"


def migrate(*, dry_run: bool = False) -> dict[str, Any]:
    accounts = get_strategy_account_service()
    execution = get_simulated_execution_service()
    defaults = accounts.ensure_defaults()
    documents = accounts.repositories.documents
    paper, paper_source = _load_paper_legacy(documents)
    autonomy, autonomy_trades, autonomy_source = _load_autonomy_legacy(documents)
    result: dict[str, Any] = {
        "dry_run": dry_run,
        "defaults": [row["account_id"] for row in defaults],
        "sources": {"paper": paper_source, "autonomy": autonomy_source},
        "synced": [],
        "mirrored_trades": 0,
        "missing_sources": [],
        "errors": [],
    }
    if paper is None:
        result["missing_sources"].append("paper")
    if autonomy is None:
        result["missing_sources"].append("autonomy")
    if dry_run:
        result["would_sync"] = [name for name, value in (("technical_benchmark_main", paper), ("autonomy_main", autonomy)) if value is not None]
        return result

    if paper is not None:
        try:
            row = accounts.sync_legacy_account(
                "technical_benchmark_main", paper,
                strategy_family="technical", strategy_id="technical_benchmark",
                strategy_version_id="technical_benchmark@legacy-1.0.0", display_name="Teknisk benchmark",
                role="BENCHMARK", status="ACTIVE", run_id="MIGRATION-V1980",
                metadata={"migration": "v19.8.0", "legacy_source": paper_source},
            )
            result["synced"].append(row["account_id"])
            for trade in paper.get("trades") or []:
                if isinstance(trade, Mapping):
                    mirrored = execution.mirror_legacy_trade(account_id="technical_benchmark_main", trade=trade, run_id="MIGRATION-V1980")
                    result["mirrored_trades"] += int(bool(mirrored.get("mirrored")))
        except Exception as exc:
            result["errors"].append(f"paper: {type(exc).__name__}: {exc}")

    if autonomy is not None:
        try:
            row = accounts.sync_legacy_account(
                "autonomy_main", autonomy,
                strategy_family="autonomy", strategy_id="autonomy_main",
                strategy_version_id="autonomy_main@1.0.0", display_name="Autonomi hovedstrategi",
                role="PRODUCTION", status=str(autonomy.get("status") or "PAUSED"), run_id="MIGRATION-V1980",
                metadata={"migration": "v19.8.0", "legacy_source": autonomy_source},
            )
            result["synced"].append(row["account_id"])
            for trade in autonomy_trades:
                mirrored = execution.mirror_legacy_trade(account_id="autonomy_main", trade=trade, run_id="MIGRATION-V1980")
                result["mirrored_trades"] += int(bool(mirrored.get("mirrored")))
        except Exception as exc:
            result["errors"].append(f"autonomy: {type(exc).__name__}: {exc}")

    result["accounts"] = accounts.comparison()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrer eksisterende paper/autonomi-state til v19.8.0 strategikontoer.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = migrate(dry_run=args.dry_run)
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
