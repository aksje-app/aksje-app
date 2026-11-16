"""Lossless, content-addressed event payloads with bounded lazy materialization.

Only the locked root writer creates references. Full accounting chain/replay is
unchanged: callers see immutable dicts containing the original logical values.
"""
from collections import OrderedDict
import hashlib
import json
import os
import re

from services.restart_payload_codec import RestartPayloadError

MARKER = 'ARCHIVED_EVENT_PAYLOADS_V2'
PREFIX = '{"__restart_storage__":"' + MARKER + '"'
FLAG = 'RESTART_JOURNAL_PAYLOAD_ARCHIVE_ENABLED'
KEY = 'scheduler/restart_payload_archive.json'
MAX_PAYLOAD_RAW_BYTES = 64 * 1024**2
MAX_PAYLOAD_STORED_BYTES = 8 * 1024**2
ENCODED_CACHE_BYTES = 64 * 1024**2
REF_MARKER = 'SHA256_JSON_V1'
PERIOD = r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}'


def enabled():
    return os.getenv(FLAG, '').lower().strip() in {'1', 'true', 'yes', 'on'}


def period_for_key(key):
    match = re.fullmatch(r'simulation_restarts/(' + PERIOD + r')/bundle\.json', key)
    if not match:
        raise RestartPayloadError('Explicit safe restart root required')
    return match[1]


def canonical_chunks(value):
    for part in json.JSONEncoder(sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                                 allow_nan=False).iterencode(value):
        yield part.encode('ascii')


def semantic_sha256(value):
    checksum = hashlib.sha256()
    for part in canonical_chunks(value):
        checksum.update(part)
    return checksum.hexdigest()


def validate_reference(ref, period=None):
    if not isinstance(ref, dict) or set(ref) != {'__restart_payload__', 'key', 'sha256', 'uncompressed_bytes'}:
        raise RestartPayloadError('Invalid historical payload reference')
    sha, key, size = ref['sha256'], ref['key'], ref['uncompressed_bytes']
    if ref['__restart_payload__'] != REF_MARKER or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
        raise RestartPayloadError('Invalid historical payload digest')
    match = re.fullmatch(r'simulation_restarts/(' + PERIOD + r')/payloads/' + sha + r'\.json', str(key))
    if not match or (period is not None and match[1] != period):
        raise RestartPayloadError('Historical payload outside its restart period')
    if type(size) is not int or not 0 < size <= MAX_PAYLOAD_RAW_BYTES:
        raise RestartPayloadError('Historical payload exceeds decoded bound')
    return ref


def _events(root):
    if not isinstance(root, dict) or not isinstance(root.get('accounts'), dict):
        raise RestartPayloadError('Archived root requires economic accounts')
    for doc in root['accounts'].values():
        if not isinstance(doc, dict) or not isinstance(doc.get('events'), list):
            raise RestartPayloadError('Archived root requires event lists')
        yield from doc['events']


def is_archived(document):
    from services.restart_payload_archive_values import LazyPayload
    if not isinstance(document, dict) or not isinstance(document.get('accounts'), dict):
        return False
    return any(isinstance(e.get('payload'), LazyPayload) for doc in document['accounts'].values()
               if isinstance(doc, dict) for e in doc.get('events', []) if isinstance(e, dict))


def externalize(document, root_key, put):
    from services.restart_payload_archive_values import LazyPayload
    from services.restart_payload_codec import _encode_chunks
    period = period_for_key(root_key)
    if document.get('period_id') != period:
        raise RestartPayloadError('Root period does not match its storage key')
    root = dict(document)
    root['accounts'] = {}
    for family, doc in document['accounts'].items():
        copied = {**doc, 'events': []}
        root['accounts'][family] = copied
        for event in doc['events']:
            payload = event['payload']
            if isinstance(payload, LazyPayload):
                reference = dict(validate_reference(dict(payload.reference), period))
            else:
                if not isinstance(payload, dict) or '__restart_payload__' in payload:
                    raise RestartPayloadError('Native event payload must be a plain logical object')
                encoded, size = _encode_chunks(canonical_chunks(payload), max_raw_bytes=MAX_PAYLOAD_RAW_BYTES, max_stored_bytes=MAX_PAYLOAD_STORED_BYTES)
                if size > MAX_PAYLOAD_RAW_BYTES or len(encoded) > MAX_PAYLOAD_STORED_BYTES:
                    raise RestartPayloadError('Historical event payload exceeds bounded blob limits')
                record = json.loads(encoded)
                sha = record['sha256']
                key = 'simulation_restarts/' + period + '/payloads/' + sha + '.json'
                reference = dict(__restart_payload__=REF_MARKER, key=key, sha256=sha, uncompressed_bytes=size)
                put(key, encoded)
            copied['events'].append({**event, 'payload': reference})
    return root


def encode_root(compact):
    from services.restart_payload_codec import encode_document as encode
    encoded, size = encode(compact)
    # Replace only the first marker in the small envelope header.
    return encoded.replace('"__restart_storage__":"ZLIB_BASE64_JSON_V1"',
                           '"__restart_storage__":"' + MARKER + '"', 1), size


def hydrate(root, loader):
    if loader is None:
        raise RestartPayloadError('Archived restart requires a historical payload reader')
    from services.restart_payload_archive_values import LazyPayload, PayloadCache
    period = period_for_key('simulation_restarts/' + str(root.get('period_id')) + '/bundle.json')
    cache = PayloadCache(loader)
    for event in _events(root):
        ref = validate_reference(event.get('payload'), period)
        event['payload'] = LazyPayload(ref, cache)
    return root


def validating_loader(fetch):
    """Per-root compressed LRU; every miss verifies envelope and original bytes."""
    from services.restart_payload_codec import MARKER as V1, decode_document
    cache = OrderedDict()
    total = 0
    def load(reference):
        nonlocal total
        ref = validate_reference(dict(reference))
        key = ref['key']
        encoded = cache.get(key)
        if encoded is None:
            encoded = fetch(key)
        if not isinstance(encoded, str) or len(encoded) > MAX_PAYLOAD_STORED_BYTES:
            raise RestartPayloadError('Invalid or oversized historical payload blob')
        try:
            envelope = json.loads(encoded)
        except (ValueError, UnicodeError) as exc:
            raise RestartPayloadError('Invalid historical payload envelope') from exc
        if not isinstance(envelope, dict) or envelope.get('__restart_storage__') != V1 or envelope.get('sha256') != ref['sha256'] or envelope.get('uncompressed_bytes') != ref['uncompressed_bytes']:
            raise RestartPayloadError('Historical payload envelope does not match its reference')
        value = decode_document(envelope)
        if not isinstance(value, dict):
            raise RestartPayloadError('Historical payload must decode to an object')
        if key not in cache and len(encoded) <= ENCODED_CACHE_BYTES:
            while cache and total + len(encoded) > ENCODED_CACHE_BYTES:
                _, previous = cache.popitem(last=False)
                total -= len(previous)
            cache[key] = encoded
            total += len(encoded)
        if key in cache:
            cache.move_to_end(key)
        return value
    return load


def make_loader(storage, connection=None):
    def fetch(key):
        own = connection is None or connection.closed
        conn = storage._conn() if own else connection
        try:
            with conn.cursor() as cur:
                # Own readers also support strictly READ ONLY operator sessions.
                lock = '' if own else ' FOR SHARE'
                cur.execute('SELECT CASE WHEN octet_length(payload)<=%s THEN payload END FROM app_kv_store WHERE name=%s' + lock, (MAX_PAYLOAD_STORED_BYTES, key))
                row = cur.fetchone()
                if not row or row[0] is None:
                    raise RestartPayloadError('Missing or oversized historical payload blob')
                return row[0]
        finally:
            if own:
                conn.close()
    return validating_loader(fetch)


def encode_document(cur, root_key, document):
    def put(key, encoded):
        # Eight MiB per blob bounds psycopg2 SQL-literal parser expansion. Never
        # overwrite existing history, including an unexpectedly corrupt blob.
        cur.execute('INSERT INTO app_kv_store(name,payload,updated_at) VALUES(%s,%s,NOW()::text) ON CONFLICT(name) DO NOTHING', (key, encoded))
        if cur.rowcount == 0:
            cur.execute('SELECT octet_length(payload) FROM app_kv_store WHERE name=%s FOR SHARE', (key,))
            size = cur.fetchone()
            if not size or size[0] != len(encoded):
                raise RestartPayloadError('Immutable historical payload conflict')
            cur.execute('SELECT payload FROM app_kv_store WHERE name=%s FOR SHARE', (key,))
            if cur.fetchone()[0] != encoded:
                raise RestartPayloadError('Immutable historical payload conflict')
    return encode_root(externalize(document, root_key, put))


def status(storage=None):
    if storage is None:
        from services.storage_service import get_storage_service
        storage = get_storage_service()
    receipt = storage.read_json(KEY, {})
    if not isinstance(receipt, dict) or receipt.get('status') != 'VERIFIED' or not receipt.get('semantic_sha256_before') or receipt.get('semantic_sha256_before') != receipt.get('semantic_sha256_after'):
        return {'status': 'NOT_VERIFIED'}
    key = receipt.get('root_key', '')
    if period_for_key(key) != receipt.get('period_id'):
        return {'status': 'NOT_VERIFIED'}
    conn = storage._conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT left(payload,%s),octet_length(payload),pg_database_size(current_database()) FROM app_kv_store WHERE name=%s', (len(PREFIX), key))
            row = cur.fetchone()
        if not row or row[0] != PREFIX:
            return {'status': 'NOT_VERIFIED'}
        return {**receipt, 'current_root_stored_bytes': row[1], 'database_bytes': row[2],
                'root_growth_since_migration_bytes': row[1] - receipt['root_stored_bytes_after'],
                'root_budget_bytes': 64 * 1024**2, 'root_budget_warning': row[1] >= 16 * 1024**2}
    finally:
        conn.close()
