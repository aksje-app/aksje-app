"""Atomic storage-only migration: exact backup, full replay, logical identity."""
from datetime import datetime, timezone
import gc
import json

from services import restart_payload_archive as archive
from services.restart_payload_codec import RestartPayloadError, decode_document, MAX_STORED_BYTES


def migrate(storage, root_key):
    from services.simulation_restart import verify_bundle
    from services.large_json_write import BinaryTextRow
    period = archive.period_for_key(root_key)
    if not storage.using_postgres() or storage.allow_local_fallback:
        raise ValueError('Archive migration requires authoritative PostgreSQL')
    storage.init_db()
    conn = storage._conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (root_key,))
            cur.execute('SELECT left(payload,%s),octet_length(payload) FROM app_kv_store WHERE name=%s FOR UPDATE', (len(archive.PREFIX), root_key))
            row = cur.fetchone()
            if not row:
                raise RestartPayloadError('Selected journal missing during archive migration')
            prefix, stored_before = row
            if prefix == archive.PREFIX:
                return archive.status(storage)
            if stored_before > MAX_STORED_BYTES:
                raise RestartPayloadError('Migration source exceeds existing bounded stored size')
            cur.execute("SELECT encode(sha256(convert_to(payload,'UTF8')),'hex') FROM app_kv_store WHERE name=%s", (root_key,))
            stored_sha = cur.fetchone()[0]
            cur.execute('SELECT payload FROM app_kv_store WHERE name=%s', (root_key,))
            raw = cur.fetchone()[0]
        source = decode_document(json.loads(raw))
        del raw
        verify_bundle(source)
        before = archive.semantic_sha256(source)
        payload_count = sum(len(doc['events']) for doc in source['accounts'].values())
        backup_key = 'simulation_restarts/' + period + '/archive_backups/' + stored_sha + '.json'
        with conn.cursor() as cur:
            # Copy original bytes server-side; no large SQL literal or second
            # client representation, and the backup is in this same transaction.
            cur.execute('INSERT INTO app_kv_store(name,payload,updated_at) SELECT %s,payload,NOW()::text FROM app_kv_store WHERE name=%s ON CONFLICT(name) DO NOTHING', (backup_key, root_key))
            cur.execute('SELECT encode(sha256(convert_to(payload,\'UTF8\')),\'hex\') FROM app_kv_store WHERE name=%s FOR SHARE', (backup_key,))
            if cur.fetchone()[0] != stored_sha:
                raise RestartPayloadError('Exact pre-migration backup conflict')
            encoded, header_bytes = archive.encode_document(cur, root_key, source)
        del source
        gc.collect()
        replacement = decode_document(json.loads(encoded), payload_loader=archive.make_loader(storage, conn))
        verify_bundle(replacement)
        after = archive.semantic_sha256(replacement)
        if before != after:
            raise RestartPayloadError('Archive migration changed logical financial journal')
        del replacement
        receipt = dict(status='VERIFIED', schema=1, period_id=period, root_key=root_key,
            migration_completed_at=datetime.now(timezone.utc).isoformat(),
            semantic_sha256_before=before, semantic_sha256_after=after,
            root_stored_bytes_before=stored_before, root_stored_bytes_after=len(encoded),
            root_header_decoded_bytes_after=header_bytes, backup_key=backup_key,
            backup_stored_sha256=stored_sha, payload_count=payload_count,
            financial_state_changed=False, history_deleted=False)
        with conn.cursor() as cur:
            cur.execute('CREATE TEMP TABLE app_archived_root (payload TEXT NOT NULL) ON COMMIT DROP')
            cur.copy_expert('COPY app_archived_root(payload) FROM STDIN WITH(FORMAT binary)', BinaryTextRow(encoded))
            cur.execute('UPDATE app_kv_store SET payload=(SELECT payload FROM app_archived_root),updated_at=NOW()::text WHERE name=%s', (root_key,))
            cur.execute('INSERT INTO app_kv_store(name,payload,updated_at) VALUES(%s,%s,NOW()::text) ON CONFLICT(name) DO UPDATE SET payload=EXCLUDED.payload,updated_at=EXCLUDED.updated_at', (archive.KEY, json.dumps(receipt, separators=(',', ':'))))
        conn.commit()
        return receipt
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run(storage=None):
    """One selected journal per ordinary aligned scheduler; no financial callback."""
    if not archive.enabled():
        return {'status': 'NOT_ENABLED', 'financial_state_changed': False}
    if storage is None:
        from services.storage_service import get_storage_service
        storage = get_storage_service()
    periods = set()
    for family in ('paper', 'autonomy', 'super_portfolio'):
        route = storage.read_json('simulation_restarts/routes/' + family + '.json', None)
        if route is None:
            continue
        period = route.get('period_id')
        if route.get('family') != family:
            raise RestartPayloadError('Invalid explicit route for archive migration')
        archive.period_for_key('simulation_restarts/' + str(period) + '/bundle.json')
        periods.add(period)
    if len(periods) != 1:
        raise RestartPayloadError('Archive migration requires one aligned explicit period')
    return migrate(storage, 'simulation_restarts/' + next(iter(periods)) + '/bundle.json')
