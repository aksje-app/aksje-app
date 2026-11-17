"""Bounded, exact-manifest replacement of prices backed up outside PostgreSQL.

Disabled by default. Results and financial history are never changed. The
versioned manifest is an explicit one-time authorization, not an age policy.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone

from services.storage_service import get_storage_service
from services.learning_price_archive import (
    MARKER, FORMAT, MAX_PRICE_BYTES, validate_key, reference_detail,
)

ENABLED_FLAG = 'LEARNING_PRICE_ARCHIVE_20261117_ENABLED'
RECEIPT_KEY = 'maintenance/learning_price_archive_20261117.json'
LOCK_ID = 19343514
MANIFEST_FILE_SHA256 = '25ef8298085d664144e0c2401779795983066c5e136b5443e93414c3de82e458'
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_CONTROLS = ('strategy_history/progress.json', 'strategy_history/optimization_progress.json')


def manifest_identity(manifest):
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_manifest(manifest):
    if (manifest.get('schema') != 1
            or manifest.get('authorization') != 'USER_APPROVED_VERIFIED_PC_BACKUP'
            or not isinstance(manifest.get('method_version'), str)):
        raise ValueError('Explicit versioned archive authorization required')
    backup = manifest.get('backup') or {}
    if (backup.get('restore_verified') is not True
            or not isinstance(backup.get('bytes'), int) or backup['bytes'] <= 0
            or not isinstance(backup.get('file'), str)
            or not re.fullmatch(r'[A-Za-z0-9_.-]+\.dir\.tar\.gz', backup['file'])
            or backup.get('pc_copy_sha256') != backup.get('sha256')
            or not all(isinstance(backup.get(k), str) and _HASH.fullmatch(backup[k])
                       for k in ('sha256', 'pc_copy_sha256', 'restore_verification_sha256'))):
        raise ValueError('Checksum-matched PC backup and restore proof required')
    entries = manifest.get('entries')
    if not isinstance(entries, list) or not 0 < len(entries) <= 2000:
        raise ValueError('Explicit bounded price manifest required')
    seen = set()
    for entry in entries:
        validate_key(entry['key'])
        if (entry['key'] in seen or not isinstance(entry.get('bytes'), int)
                or not 0 < entry['bytes'] <= MAX_PRICE_BYTES
                or not isinstance(entry.get('sha256'), str) or not _HASH.fullmatch(entry['sha256'])
                or not all(isinstance(entry.get('result_sha256', {}).get(engine), str)
                           and _HASH.fullmatch(entry['result_sha256'][engine])
                           for engine in ('AUTONOMY', 'SUPER_PORTFOLIO'))):
            raise ValueError('Duplicate, oversized or incomplete source authorization')
        seen.add(entry['key'])
    return sorted(entries, key=lambda entry: entry['key'])


def load_authorized_manifest():
    path = Path(__file__).with_name('learning_price_archive_20261117.json')
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Archive authorization exceeds its byte budget')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_FILE_SHA256:
        raise ValueError('Archive authorization checksum mismatch')
    manifest = json.loads(raw)
    validate_manifest(manifest)
    return manifest


def _document(cur, key, *, limit=1024 * 1024, lock='SHARE'):
    # Every caller supplies a fixed lock mode, never user SQL.
    if lock not in {'SHARE', 'UPDATE'}:
        raise ValueError('Invalid row lock mode')
    cur.execute(f'SELECT octet_length(payload) FROM app_kv_store WHERE name=%s FOR {lock}', (key,))
    size = cur.fetchone()
    if size is None:
        return None
    if size[0] > limit:
        raise ValueError('Control document exceeds its byte budget')
    cur.execute('SELECT payload FROM app_kv_store WHERE name=%s AND octet_length(payload)<=%s', (key, limit))
    row = cur.fetchone()
    if row is None:
        return None
    value = json.loads(row[0])
    if not isinstance(value, dict):
        raise ValueError('Expected a bounded control document')
    return value


def _save_receipt(cur, value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'))
    if len(raw.encode()) > 1024 * 1024:
        raise ValueError('Archive receipt exceeds its budget')
    cur.execute('INSERT INTO app_kv_store(name,payload,updated_at) VALUES(%s,%s,NOW()::text) '
                'ON CONFLICT(name) DO UPDATE SET payload=EXCLUDED.payload,updated_at=EXCLUDED.updated_at',
                (RECEIPT_KEY, raw))


def archive_batch(storage, manifest, *, max_items=128, apply=False):
    """Compare-and-replace exact prices; receipt and replacements commit together."""
    entries = validate_manifest(manifest)
    if not storage.using_postgres() or storage.allow_local_fallback:
        raise ValueError('Archive replacement requires authoritative PostgreSQL')
    from portfolio_history_optimizer import METHOD_VERSION
    identity = manifest_identity(manifest)
    now = datetime.now(timezone.utc).isoformat()
    base = {'schema': 1, 'manifest_sha256': identity, 'backup_sha256': manifest['backup']['sha256'],
            'backup_file': manifest['backup']['file'], 'total': len(entries), 'cursor': 0,
            'archived_total': 0, 'estimated_saved_value_bytes': 0, 'blocked': [], 'checked_at': now}
    limit = max(1, min(128, int(max_items)))
    conn = storage._conn()
    started = time.monotonic()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='2s'")
                cur.execute("SET LOCAL statement_timeout='30s'")
                cur.execute('SELECT pg_try_advisory_xact_lock(%s)', (LOCK_ID,))
                if not cur.fetchone()[0]:
                    return {**base, 'state': 'DEFERRED_BUSY'}
                previous = _document(cur, RECEIPT_KEY, lock='UPDATE')
                if previous:
                    if previous.get('manifest_sha256') != identity or previous.get('backup_sha256') != base['backup_sha256']:
                        raise ValueError('Existing receipt belongs to another authorization')
                    cursor_value = previous.get('cursor')
                    archived_value = previous.get('archived_total')
                    blocked_value = previous.get('blocked')
                    valid_cursor = type(cursor_value) is int and 0 <= cursor_value <= len(entries)
                    valid_blocked = (isinstance(blocked_value, list)
                                     and all(isinstance(item, dict) and isinstance(item.get('key'), str)
                                             and isinstance(item.get('reason'), str) for item in blocked_value))
                    if (not valid_cursor or type(archived_value) is not int or archived_value < 0
                            or not valid_blocked or archived_value + len(blocked_value) != cursor_value
                            or previous.get('total') != len(entries)
                            or type(previous.get('estimated_saved_value_bytes')) is not int
                            or previous['estimated_saved_value_bytes'] < 0):
                        raise ValueError('Invalid archive progress receipt')
                    blocked_keys = [item['key'] for item in blocked_value]
                    if (len(set(blocked_keys)) != len(blocked_keys)
                            or not set(blocked_keys).issubset({e['key'] for e in entries[:cursor_value]})
                            or previous.get('state') not in {'PARTIAL', 'COMPLETED', 'COMPLETED_WITH_BLOCKS',
                                                             'BLOCKED_METHOD', 'BLOCKED_CHECKPOINT'}
                            or (cursor_value == len(entries)) != previous.get('state', '').startswith('COMPLETED')):
                        raise ValueError('Inconsistent archive progress receipt')
                    base.update(previous, checked_at=now)
                    if base['cursor'] == len(entries):
                        return base  # completed one-time scope never consumes restored inputs
                controls = {key: _document(cur, key) for key in _CONTROLS}
                checkpoint = controls[_CONTROLS[1]] or {}
                if (manifest['method_version'] != METHOD_VERSION
                        or checkpoint.get('method_version') != manifest['method_version']):
                    result = {**base, 'state': 'BLOCKED_METHOD', 'eligible_this_batch': 0}
                    if apply:
                        _save_receipt(cur, result)
                    return result
                if not all(controls.values()):
                    result = {**base, 'state': 'BLOCKED_CHECKPOINT', 'eligible_this_batch': 0}
                    if apply:
                        _save_receipt(cur, result)
                    return result
                completed = []
                for control in controls.values():
                    tickers = control.get('completed_tickers')
                    if not isinstance(tickers, list) or len(tickers) > 5000 or not all(isinstance(t, str) for t in tickers):
                        raise ValueError('Missing bounded completed-ticker ledger')
                    completed.append({hashlib.sha256(t.encode()).hexdigest()+'.json' for t in tickers})
                blocked = list(base['blocked'])
                cursor = base['cursor']
                eligible = 0

                def block(key, reason):
                    blocked.append({'key': key, 'reason': reason})

                for entry in entries[cursor:cursor + limit]:
                    if cursor > base['cursor'] and time.monotonic() - started >= 25:
                        break
                    key = entry['key']; leaf = key.rsplit('/', 1)[1]
                    cursor += 1
                    cur.execute('SELECT octet_length(payload),pg_column_size(payload),'
                                "CASE WHEN octet_length(payload)<=%s THEN encode(sha256(convert_to(payload,'UTF8')),'hex') END,"
                                'CASE WHEN octet_length(payload)<=8192 THEN payload END '
                                'FROM app_kv_store WHERE name=%s FOR UPDATE', (MAX_PRICE_BYTES, key))
                    row = cur.fetchone()
                    if row is None:
                        block(key, 'SOURCE_MISSING'); continue
                    size, stored_bytes, source_sha, small = row
                    value = json.loads(small) if small is not None else None
                    detail = reference_detail(value, key)
                    if detail:
                        if (detail['state'] == 'RESTORE_REQUIRED' and value.get('manifest_sha256') == identity
                                and value.get('backup_sha256') == base['backup_sha256']
                                and value.get('source_sha256') == entry['sha256']
                                and value.get('source_bytes') == entry['bytes']):
                            base['archived_total'] += 1
                        else:
                            block(key, 'REFERENCE_CONFLICT')
                        continue
                    if size != entry['bytes'] or source_sha != entry['sha256']:
                        block(key, 'SOURCE_CHANGED_OR_OVERSIZED'); continue
                    if not all(leaf in done for done in completed):
                        block(key, 'NOT_COMPLETED_IN_BOTH_LEDGERS'); continue
                    valid_results = True
                    for engine in ('AUTONOMY', 'SUPER_PORTFOLIO'):
                        result_key = 'strategy_history/optimized/'+engine+'/'+leaf
                        cur.execute("SELECT payload,encode(sha256(convert_to(payload,'UTF8')),'hex') "
                                    'FROM app_kv_store WHERE name=%s AND octet_length(payload)<=65536 FOR SHARE',
                                    (result_key,))
                        result_row = cur.fetchone()
                        result = json.loads(result_row[0]) if result_row else {}
                        if (not isinstance(result, dict) or result.get('status') != 'COMPLETE_RESEARCH'
                                or result.get('method_version') != manifest['method_version']
                                or result_row[1] != entry['result_sha256'][engine]):
                            valid_results = False
                            break
                    if not valid_results:
                        block(key, 'RESULT_CHANGED_OR_INCOMPLETE'); continue
                    eligible += 1
                    if not apply:
                        continue
                    reference = {MARKER: FORMAT, 'backup_file': base['backup_file'],
                                 'backup_sha256': base['backup_sha256'], 'manifest_sha256': identity,
                                 'source_key': key, 'source_sha256': entry['sha256'], 'source_bytes': entry['bytes'],
                                 'method_version': manifest['method_version'], 'archived_at': now}
                    cur.execute('UPDATE app_kv_store SET payload=%s,updated_at=NOW()::text WHERE name=%s '
                                'RETURNING pg_column_size(payload)',
                                (json.dumps(reference, sort_keys=True, separators=(',', ':')), key))
                    base['estimated_saved_value_bytes'] += max(0, stored_bytes - cur.fetchone()[0])
                    base['archived_total'] += 1
                result = {**base, 'cursor': cursor, 'eligible_this_batch': eligible, 'blocked': blocked,
                          'blocked_total': len(blocked), 'historical_results_changed': False,
                          'state': ('COMPLETED_WITH_BLOCKS' if blocked else 'COMPLETED')
                          if cursor == len(entries) else 'PARTIAL'}
                if apply:
                    if cursor == len(entries):
                        result['completed_at'] = now
                    _save_receipt(cur, result)
                else:
                    result['state'] = 'DRY_RUN'
                return result
    finally:
        conn.close()


def run_scheduled_archive():
    if os.getenv(ENABLED_FLAG, '').strip().lower() not in {'1', 'true', 'yes', 'on'}:
        return {'state': 'DISABLED'}
    return archive_batch(get_storage_service(), load_authorized_manifest(), apply=True)
