"""Bound the two report run stores without enabling general history retention."""

import os
from pathlib import PurePosixPath

from services import storage_references
from services.storage_service import _load_json_document, get_storage_service

RUN_PREFIXES = ("market_intelligence/runs/", "investment_pipeline/runs/")
LATEST_KEYS = ("market_intelligence/latest_run.json", "investment_pipeline/latest_run.json")
ARCHIVE_KEYS = ("market_intelligence/report_archive.json", "repositories/reports.json")
KEEP = 3
BATCH_LIMIT = 20
LOCK_ID = 19343503


def enabled():
    return os.getenv("REPORT_RUN_RETENTION_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _protected(archives, retained_ids):
    known = set()
    protected = set()
    for rows in archives.values():
        if not isinstance(rows, list):
            raise ValueError("Report archive must be a list")
        for row in rows:
            run_id = row.get("run_id")
            if not run_id:
                continue
            known.add(run_id)
            pending = row.get("revalidation_required") or row.get("report_state") == "PROVISIONAL"
            if pending or row.get("favorite"):
                protected.add(run_id)
            if pending or run_id in retained_ids:
                parent = row.get("supersedes_run_id")
                if parent:
                    protected.add(parent)
    return known, protected


def prune(*, storage=None):
    if not enabled():
        return {"state": "DISABLED", "removed": {}}
    storage = storage or get_storage_service()
    if not storage_references.authoritative_postgres(storage):
        return {"state": "DISABLED_NO_AUTHORITATIVE_DATABASE", "removed": {}}
    removed = {}
    conn = storage._conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (LOCK_ID,))
            if not cur.fetchone()[0]:
                return {"state": "DEFERRED_BUSY", "removed": {}}
            cur.execute("SET LOCAL lock_timeout = '2s'")
            cur.execute("SET LOCAL statement_timeout = '20s'")
            cur.execute(
                """SELECT name, updated_at FROM app_kv_store
                   WHERE name LIKE ANY(%s)
                   ORDER BY updated_at::timestamptz DESC, name DESC""",
                ([prefix + "%" for prefix in RUN_PREFIXES],),
            )
            rows = cur.fetchall()
            groups = [[(key, at) for key, at in rows if key.startswith(prefix)] for prefix in RUN_PREFIXES]
            candidates = [row for group in groups for row in group[KEEP:]]
            if not candidates:
                return {"state": "COMPLETED", "keep_per_group": KEEP, "removed": removed}

            lock_keys = set(ARCHIVE_KEYS + LATEST_KEYS)
            for key, _ in candidates:
                lock_keys.add(key)
                lock_keys.update(storage_references.dependent_aliases(key))
            storage._lock_shared_keys(cur, lock_keys)
            cur.execute(
                "SELECT name, payload FROM app_kv_store WHERE name=ANY(%s) ORDER BY name FOR UPDATE",
                (list(ARCHIVE_KEYS),),
            )
            archives = {
                key: _load_json_document(key, raw, storage=storage, connection=conn)
                for key, raw in cur.fetchall()
            }
            cur.execute(
                """SELECT name, payload::jsonb->>'run_id',
                          payload::jsonb->%s->>'key'
                   FROM app_kv_store WHERE name=ANY(%s) ORDER BY name FOR UPDATE""",
                (storage_references.REFERENCE, list(LATEST_KEYS)),
            )
            active = {
                reference or f"{key.split('/')[0]}/runs/{run_id}.json"
                for key, run_id, reference in cur.fetchall()
                if reference or run_id
            }
            retained_ids = {PurePosixPath(key).stem for key, _ in groups[0][:KEEP]}
            retained_ids.update(PurePosixPath(key).stem for key in active if key.startswith(RUN_PREFIXES[0]))
            known, protected = _protected(archives, retained_ids)
            deleted_reports = set()
            for key, at in candidates:
                if sum(removed.values()) >= BATCH_LIMIT:
                    break
                report = key.startswith(RUN_PREFIXES[0])
                run_id = PurePosixPath(key).stem
                if key in active or (report and (run_id in protected or run_id not in known)):
                    continue
                cur.execute("SELECT 1 FROM app_kv_store WHERE name=%s AND updated_at=%s FOR UPDATE", (key, at))
                if cur.fetchone() is None:
                    continue
                aliases = storage_references.dependent_aliases(key)
                materialized = {
                    alias: _load_json_document(alias, raw, storage=storage, connection=conn)
                    for alias, raw, _ in storage._locked_aliases(cur, key, aliases)
                }
                storage._write_shared_rows(cur, materialized)
                cur.execute("DELETE FROM app_kv_store WHERE name=%s", (key,))
                group = key.split("/")[0]
                removed[group] = removed.get(group, 0) + cur.rowcount
                if report:
                    deleted_reports.add(run_id)
            if deleted_reports:
                storage._write_shared_rows(cur, {
                    key: [row for row in archive if row.get("run_id") not in deleted_reports]
                    for key, archive in archives.items()
                })
    finally:
        conn.close()
    return {"state": "COMPLETED", "keep_per_group": KEEP, "removed": removed}
