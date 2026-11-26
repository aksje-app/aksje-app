"""Bound the two report run stores without enabling general history retention."""

import os
from pathlib import PurePosixPath

from services import storage_references
from services.storage_service import _load_json_document, get_storage_service

RUN_PREFIXES = storage_references.REPORT_RUN_PREFIXES
LATEST_KEYS = ("market_intelligence/latest_run.json", "investment_pipeline/latest_run.json")
ARCHIVE_KEYS = ("market_intelligence/report_archive.json", "repositories/reports.json")
KEEP = 3
BATCH_LIMIT = 20
LOCK_ID = 19343503


def enabled():
    return os.getenv("REPORT_RUN_RETENTION_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _protected(archives, retained_ids):
    known = {}
    protected = set()
    parent_by_id = {}
    for rows in archives.values():
        if not isinstance(rows, list):
            raise ValueError("Report archive must be a list")
        seen_series = set()
        for row in rows:
            run_id = row.get("run_id")
            if not run_id:
                continue
            known[run_id] = row
            series = row.get("report_series_id") or run_id
            pending = row.get("revalidation_required") or row.get("report_state") == "PROVISIONAL"
            if (series not in seen_series and pending) or row.get("favorite"):
                protected.add(run_id)
            seen_series.add(series)
            if row.get("supersedes_run_id"):
                parent_by_id[run_id] = row["supersedes_run_id"]
    pending_ids = list(retained_ids | protected)
    while pending_ids:
        parent = parent_by_id.get(pending_ids.pop())
        if parent and parent not in protected:
            protected.add(parent)
            pending_ids.append(parent)
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
                   ORDER BY name DESC""",
                ([prefix + "%" for prefix in RUN_PREFIXES],),
            )
            rows = cur.fetchall()
            groups = [[(key, at) for key, at in rows if key.startswith(prefix)] for prefix in RUN_PREFIXES]
            if all(len(group) <= KEEP for group in groups):
                return {"state": "COMPLETED", "keep_per_group": KEEP, "removed": removed}

            lock_keys = set(ARCHIVE_KEYS + LATEST_KEYS)
            for key, _ in rows:
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
            known, _ = _protected(archives, set())
            complete = []
            for key, at in groups[0]:
                run_id = PurePosixPath(key).stem
                entry = known.get(run_id)
                if entry is None:
                    # Some complete canonical runs have aged out of the compact archive.
                    cur.execute("SELECT payload FROM app_kv_store WHERE name=%s", (key,))
                    row = cur.fetchone()
                    run = _load_json_document(key, row[0], storage=storage, connection=conn) if row else {}
                    if not (run.get("persistence") or {}).get("ok"):
                        continue
                    entry = {"created_at": run.get("created_at"), "report_state": (run.get("report_status") or {}).get("state"),
                             "revalidation_required": (run.get("report_status") or {}).get("revalidation_required"),
                             "analysis_aborted": run.get("analysis_aborted"), "test_run": run.get("test_run")}
                    if entry["revalidation_required"] or entry["report_state"] == "PROVISIONAL":
                        continue
                complete.append((key, at, entry))
            complete.sort(key=lambda row: (row[2].get("created_at") or "", row[0]), reverse=True)
            complete_ids = [
                key for key, _, entry in complete
                if not (entry.get("analysis_aborted") or entry.get("test_run") or "TEST" in (entry.get("trigger") or "").upper()
                        or entry.get("report_state") in {"PROVISIONAL", "FAILED", "ABORTED", "IN_PROGRESS"}
                        or entry.get("revalidation_required"))
            ]
            retained = set(complete_ids[:KEEP])
            retained_ids = {PurePosixPath(key).stem for key in retained}
            retained_ids.update(PurePosixPath(key).stem for key in active if key.startswith(RUN_PREFIXES[0]))
            _, protected = _protected(archives, retained_ids)
            candidates = [(key, at) for key, at, _ in complete if key not in retained] + groups[1][KEEP:]
            deleted_reports = set()
            for key, at in candidates:
                if sum(removed.values()) >= BATCH_LIMIT:
                    break
                report = key.startswith(RUN_PREFIXES[0])
                run_id = PurePosixPath(key).stem
                if key in active or (report and run_id in protected):
                    continue
                cur.execute("SELECT payload FROM app_kv_store WHERE name=%s AND updated_at=%s FOR UPDATE", (key, at))
                current = cur.fetchone()
                if current is None:
                    continue
                aliases = storage_references.dependent_aliases(key)
                materialized = {
                    alias: _load_json_document(alias, raw, storage=storage, connection=conn)
                    for alias, raw, _ in storage._locked_aliases(cur, key, aliases)
                }
                marker = {}
                if report and run_id in known:
                    from learning_observation_engine import _compact_run_for_baseline

                    run = _load_json_document(key, current[0], storage=storage, connection=conn)
                    marker["learning_baseline"] = _compact_run_for_baseline(run, remaining_signals=1500)
                materialized[storage_references.retired_report_run_key(key)] = marker
                storage._write_shared_rows(cur, materialized)
                cur.execute("DELETE FROM app_kv_store WHERE name=%s", (key,))
                group = key.split("/")[0]
                removed[group] = removed.get(group, 0) + cur.rowcount
                if report:
                    deleted_reports.add(run_id)
            if deleted_reports:
                storage._write_shared_rows(cur, {
                    key: [{**entry, "run_details_retired": True}
                          if entry.get("run_id") in deleted_reports else entry for entry in archive]
                    for key, archive in archives.items()
                })
    finally:
        conn.close()
    return {"state": "COMPLETED", "keep_per_group": KEEP, "removed": removed}
