"""Atomic Super Portfolio state, transaction journal and idempotency receipts.

Postgres commits all three in one transaction. The explicit local fallback keeps
the journal/receipts inside the atomically replaced document, never in a second
file that could disagree after a crash. Historical missing trades are not made up.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from services.storage_service import get_storage_service

STATE_KEY = "super_portfolio/state.json"
TRADES_KEY = "super_portfolio/transactions.jsonl"


class PortfolioConflict(RuntimeError):
    """A concurrent writer won; reload before making another decision."""


def _receipt_key(operation_id):
    return "super_portfolio/commits/" + hashlib.sha256(operation_id.encode()).hexdigest() + ".json"


def receipt(operation_id, storage=None):
    storage = storage or get_storage_service()
    if storage.using_postgres():
        return storage.read_json(_receipt_key(operation_id), None)
    return (storage.read_json(STATE_KEY, {}) or {}).get("_commit_receipts", {}).get(operation_id)


def committed_job(job_id, storage=None):
    """Recognize both new receipts and the audited pre-fix post-commit failure.

Legacy recovery requires the job's verified pipeline AND its exact persisted
evaluation snapshot. It creates a receipt only, not invented historical fills.
"""
    storage = storage or get_storage_service()
    operation = "job:" + job_id
    saved = receipt(operation, storage)
    if saved:
        return saved
    pipeline = storage.read_json("super_portfolio/market_pipeline.json", {}) or {}
    state = storage.read_json(STATE_KEY, {}) or {}
    run_id = pipeline.get("run_id")
    if pipeline.get("job_id") != job_id or not run_id or state.get("source_run_id") != run_id:
        return None
    if not (pipeline.get("verification") or {}).get("ok"):
        return None
    snapshot = next((s for s in reversed(state.get("history") or []) if s.get("source_run_id") == run_id), None)
    if snapshot is None or not isinstance(snapshot.get("changes"), list):
        return None
    commit(state, operation_id=operation, trades=[], result={"changes": snapshot["changes"],
           "run_id": run_id, "verification": pipeline["verification"], "outcome": pipeline.get("outcome", "COMPLETED"),
           "legacy_commit_verified": True}, storage=storage)
    return receipt(operation, storage)


def commit(state, *, operation_id="", trades=(), result=None, storage=None):
    storage = storage or get_storage_service()
    proposed = deepcopy(state)
    expected = int(proposed.get("_revision", 0))
    proposed.pop("_pending_commit", None)
    record = {"operation_id": operation_id, "changes": list(trades), **dict(result or {})}

    def check(current):
        if int((current or {}).get("_revision", 0)) != expected:
            raise PortfolioConflict("Super Portfolio ble oppdatert samtidig; last inn tilstanden på nytt")
        proposed["_revision"] = expected + 1

    if storage.using_postgres():
        storage.init_db()
        conn = storage._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (STATE_KEY,))
                cur.execute("SELECT payload FROM app_kv_store WHERE name=%s FOR UPDATE", (STATE_KEY,))
                row = cur.fetchone()
                current = json.loads(row[0]) if row else {}
                if operation_id:
                    cur.execute("SELECT payload FROM app_kv_store WHERE name=%s", (_receipt_key(operation_id),))
                    if cur.fetchone():
                        conn.rollback()
                        return current
                check(current)
                for trade in trades:
                    cur.execute("INSERT INTO app_jsonl_store (name,payload,created_at) VALUES (%s,%s,NOW()::TEXT)",
                                (TRADES_KEY, json.dumps(trade, ensure_ascii=False, default=str)))
                cur.execute("INSERT INTO app_kv_store (name,payload,updated_at) VALUES (%s,%s,NOW()::TEXT) "
                            "ON CONFLICT (name) DO UPDATE SET payload=EXCLUDED.payload,updated_at=EXCLUDED.updated_at",
                            (STATE_KEY, json.dumps(proposed, ensure_ascii=False, default=str)))
                if operation_id:
                    cur.execute("INSERT INTO app_kv_store (name,payload,updated_at) VALUES (%s,%s,NOW()::TEXT)",
                                (_receipt_key(operation_id), json.dumps(record, ensure_ascii=False, default=str)))
            conn.commit()
            return proposed
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update(current):
        current = current or {}
        receipts = dict(current.get("_commit_receipts") or {})
        if operation_id and operation_id in receipts:
            return current
        check(current)
        proposed["_trade_ledger"] = list(current.get("_trade_ledger") or []) + list(trades)
        if operation_id:
            receipts[operation_id] = record
        proposed["_commit_receipts"] = receipts
        return proposed

    return storage.mutate_json(STATE_KEY, update, {})


def transactions(storage=None, limit=None):
    """Complete retained journal, with no diagnostic row cap."""
    storage = storage or get_storage_service()
    if not storage.using_postgres():
        rows = list((storage.read_json(STATE_KEY, {}) or {}).get("_trade_ledger") or [])
        return rows[-limit:] if limit else rows
    storage.init_db()
    conn = storage._conn()
    try:
        with conn.cursor() as cur:
            if limit:
                cur.execute("SELECT payload FROM app_jsonl_store WHERE name=%s ORDER BY id DESC LIMIT %s", (TRADES_KEY, limit))
                return list(reversed([json.loads(row[0]) for row in cur.fetchall()]))
            cur.execute("SELECT payload FROM app_jsonl_store WHERE name=%s ORDER BY id", (TRADES_KEY,))
            return [json.loads(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()


def audit_snapshot(storage=None):
    """State and trades from the same committed revision, including local fallback."""
    storage = storage or get_storage_service()
    if not storage.using_postgres():
        state = storage.read_json(STATE_KEY, {}) or {}
        return state, list(state.get("_trade_ledger") or [])
    storage.init_db()
    conn = storage._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cur.execute("SELECT payload FROM app_kv_store WHERE name=%s", (STATE_KEY,))
            row = cur.fetchone()
            state = json.loads(row[0]) if row else {}
            cur.execute("SELECT payload FROM app_jsonl_store WHERE name=%s ORDER BY id", (TRADES_KEY,))
            return state, [json.loads(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()


def export_files(storage=None):
    import csv
    import io
    state, rows = audit_snapshot(storage)
    fields = ["trade_id", "position_id", "ticker", "action", "entry_at", "decision_at", "price_observed_at",
              "simulated_execution_at", "execution_price", "quantity", "gross_amount", "transaction_cost",
              "cash_after", "portfolio_value_after", "stop_price", "reason_code", "reason", "operation_id",
              "quote_currency", "portfolio_currency", "quantity_unit"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    coverage = {"schema": 1, "state_revision": state.get("_revision"), "records": len(rows),
                "first_decision_at": rows[0].get("decision_at") if rows else None,
                "last_decision_at": rows[-1].get("decision_at") if rows else None,
                "historical_coverage": "UNKNOWN_BEFORE_ACCOUNTING_OPENING_BALANCE",
                "historical_return_fully_verified": False,
                "valuation_basis": "LOCAL_PRICE_RETURN_IN_PORTFOLIO_MODEL_UNITS",
                "fx_revaluation": False,
                "opening_balance": state.get("accounting_opening_balance"),
                "cash": state.get("cash"), "portfolio_value": state.get("portfolio_value"),
                "positions": state.get("positions") or {}, "actual_broker_trades": False}
    from services.portfolio_accounting import report as nok_report
    return {"nok_accounting.json": json.dumps(nok_report("super_portfolio", storage=storage), ensure_ascii=False, indent=2),
            "transactions.json": json.dumps(rows, ensure_ascii=False, indent=2, default=str),
            "transactions.csv": output.getvalue(),
            "transaction_coverage.json": json.dumps(coverage, ensure_ascii=False, indent=2, default=str)}


def record_documented_nok_fill(fill, *, storage=None):
    """Explicit actual-share adapter; never infer a fill from legacy model units.

    Requires a separately approved NOK period. Existing historical execution and
    selection rules remain unchanged until a controlled handover is authorised.
    """
    from services.portfolio_accounting import settle
    return settle('super_portfolio', fill, storage=storage)
