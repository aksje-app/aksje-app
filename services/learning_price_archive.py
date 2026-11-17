"""Explicit cold-price references; archived input is never missing-price evidence."""
from __future__ import annotations

import hashlib
import json
import re

MARKER = '__learning_price_archive__'
FORMAT = 'VERIFIED_PC_BACKUP_V1'
MAX_PRICE_BYTES = 1024 * 1024
_KEY = re.compile(r'strategy_history/prices/[0-9a-f]{64}\.json\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')


class ArchivedPriceRequired(ValueError):
    def __init__(self, detail):
        self.detail = detail
        super().__init__('Arkivert prisgrunnlag må gjenopprettes før ny beregning.')


def validate_key(key):
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError('Only exact historical price keys are supported')


def reference_detail(value, key):
    """Return a sanitized recovery request for every reserved marker, even invalid."""
    if not isinstance(value, dict) or MARKER not in value:
        return None
    valid = (value.get(MARKER) == FORMAT and value.get('source_key') == key
             and all(isinstance(value.get(k), str) and _HASH.fullmatch(value[k])
                     for k in ('source_sha256', 'backup_sha256', 'manifest_sha256'))
             and isinstance(value.get('source_bytes'), int)
             and 0 < value['source_bytes'] <= MAX_PRICE_BYTES
             and isinstance(value.get('backup_file'), str)
             and re.fullmatch(r'[A-Za-z0-9_.-]+\.dir\.tar\.gz', value['backup_file']))
    return {'state': 'RESTORE_REQUIRED' if valid else 'INVALID_ARCHIVE_REFERENCE',
            'key': key, 'backup_file': value.get('backup_file') if valid else None,
            'backup_sha256': value.get('backup_sha256') if valid else None,
            'source_sha256': value.get('source_sha256') if valid else None}


def read_price(storage, key):
    validate_key(key)
    value = storage.read_json(key, {}) or {}
    detail = reference_detail(value, key)
    if detail:
        raise ArchivedPriceRequired(detail)
    return value


def write_price(storage, key, value):
    """Use the storage row/file lock so a concurrent archive cannot be overwritten."""
    validate_key(key)

    def replace(current):
        detail = reference_detail(current, key)
        if detail:
            raise ArchivedPriceRequired(detail)
        return value

    return storage.mutate_json(key, replace, {})


def _restore_value(key, current, raw):
    detail = reference_detail(current, key)
    value = json.loads(raw)
    if (not isinstance(value, dict) or not isinstance(value.get('ticker'), str)
            or hashlib.sha256(value['ticker'].encode()).hexdigest() + '.json' != key.rsplit('/', 1)[1]
            or not isinstance(value.get('bars'), list) or MARKER in value):
        raise ValueError('Restored bytes are not the original price input')
    if not detail:
        if current == value:
            return value
        raise ValueError('Refusing to replace an unarchived or changed input')
    if (detail['state'] != 'RESTORE_REQUIRED'
            or hashlib.sha256(raw).hexdigest() != current['source_sha256']
            or len(raw) != current['source_bytes']):
        raise ValueError('Restoration does not match the original source bytes')
    return value


def restore_price(storage, key, raw, *, apply=True):
    """Restore only verified original bytes; production preserves their exact encoding."""
    validate_key(key)
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_PRICE_BYTES:
        raise ValueError('Restoration exceeds the price input budget')
    if not storage.using_postgres():
        if not apply:
            _restore_value(key, storage.read_json(key), raw)
            return {'state': 'RESTORE_ELIGIBLE', 'key': key}
        return storage.mutate_json(key, lambda current: _restore_value(key, current, raw))
    if storage.allow_local_fallback:
        raise ValueError('Restoration requires authoritative PostgreSQL')
    conn = storage._conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='2s'")
                cur.execute("SET LOCAL statement_timeout='30s'")
                cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (key,))
                cur.execute('SELECT payload FROM app_kv_store WHERE name=%s AND octet_length(payload)<=%s FOR UPDATE',
                            (key, MAX_PRICE_BYTES))
                row = cur.fetchone()
                if row is None:
                    raise ValueError('Source reference missing or oversized')
                current = json.loads(row[0])
                _restore_value(key, current, raw)
                if reference_detail(current, key) is None:
                    if row[0].encode('utf-8') != raw:
                        raise ValueError('Existing source has different raw bytes')
                    return {'state': 'ALREADY_PRESENT', 'key': key}
                if not apply:
                    return {'state': 'RESTORE_ELIGIBLE', 'key': key}
                cur.execute('UPDATE app_kv_store SET payload=%s,updated_at=NOW()::text WHERE name=%s',
                            (raw.decode('utf-8'), key))
                return {'state': 'RESTORED', 'key': key}
    finally:
        conn.close()
