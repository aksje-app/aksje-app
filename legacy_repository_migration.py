"""Bounded, opt-in migration of legacy repository JSON arrays.

Never delete a legacy document until every row has a matching, equal item.
Run migrate_one() repeatedly from a maintenance worker, NOT a web request.
The audit cursor is restart-safe. No trading state is changed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from services.storage_service import get_storage_service

FAMILIES = {
    "market_snapshots": "snapshot_id",
    "strategy_decisions": "decision_id",
    "strategy_runs": "strategy_run_id",
    "strategy_orders": "order_id",
    "strategy_fills": "fill_id",
    "strategy_account_snapshots": "account_snapshot_id",
    "activation_analyses": "analysis_id",
}
STATE_PREFIX = "maintenance/legacy_migration/"
BATCH_MAX = 50


def migrate_one(family: str, *, limit: int = 20, delete_verified: bool = False) -> dict[str, Any]:
    """Compare and migrate a bounded slice. Deletion needs explicit opt-in.

    Verification is exact JSON equality, not merely matching IDs. A concurrent
    writer invalidates deletion by changing the row count or legacy digest.
    """
    if family not in FAMILIES:
        raise ValueError("Unsupported legacy family")
    storage = get_storage_service()
    if not storage.using_postgres():
        raise RuntimeError("PostgreSQL required for migration")
    id_field = FAMILIES[family]
    legacy_key = f"repositories/{family}.json"
    state_key = f"{STATE_PREFIX}{family}.json"
    state = dict(storage.read_json(state_key, {}) or {})
    cursor = max(0, int(state.get("cursor", 0)))
    size = max(1, min(BATCH_MAX, int(limit)))
    conn = storage._conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT md5(payload), jsonb_array_length(payload::jsonb) FROM app_kv_store WHERE name=%s", (legacy_key,))
        header = cur.fetchone()
        if header is None:
            return {"family": family, "status": "ABSENT"}
        fingerprint, count = str(header[0]), int(header[1])
        if state.get("fingerprint") != fingerprint or state.get("total") != count:
            state = {"fingerprint": fingerprint, "total": count, "cursor": 0, "verified": 0, "migrated": 0}
            cursor = 0
        cur.execute(
            """SELECT n, (payload::jsonb -> n)::text
               FROM app_kv_store CROSS JOIN generate_series(%s, %s) AS n
               WHERE name=%s ORDER BY n""",
            (cursor, min(count, cursor + size) - 1, legacy_key),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    migrated = 0
    verified = 0
    for ordinal, serialized in rows:
        value = json.loads(serialized)
        if not isinstance(value, dict) or not str(value.get(id_field) or ""):
            state.update({"status": "BLOCKED_INVALID_ROW", "blocked_index": ordinal})
            storage.write_json(state_key, state)
            return {"family": family, **state}
        record_id = str(value[id_field])
        item_key = f"repositories/{family}/items/{hashlib.sha256(record_id.encode()).hexdigest()}.json"
        current = storage.read_json(item_key, None)
        if current is None:
            storage.write_json(item_key, value)
            migrated += 1
            current = storage.read_json(item_key, None)
        if current != value:
            state.update({"status": "BLOCKED_MISMATCH", "blocked_index": ordinal, "blocked_id": record_id})
            storage.write_json(state_key, state)
            return {"family": family, **state}
        verified += 1
    state["cursor"] = cursor + verified
    state["verified"] = int(state.get("verified", 0)) + verified
    state["migrated"] = int(state.get("migrated", 0)) + migrated
    state["status"] = "VERIFYING" if state["cursor"] < count else "VERIFIED"
    storage.write_json(state_key, state)
    # Never delete in the same pass that imported data. Deletion is a separate
    # operational decision; callers must re-check runtime read compatibility.
    if delete_verified:
        raise RuntimeError("Legacy deletion is not enabled until compatibility readers are retired")
    return {"family": family, **state}
