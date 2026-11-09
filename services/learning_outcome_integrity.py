"""Narrow, reversible removal of proven inconsistent observation outcomes.

Negative results, small samples and absent cost evidence are never deletion criteria.
Only an explicit, versioned manifest may change production data. Full original
rows are compressed, read back and verified in the SAME transaction before the
active outcome fields are removed. Trading and research keys are out of scope.
"""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import base64
import gzip
import hashlib
import json
import math

SOURCE = 'controlled_learning/observation_cohorts.json'
PREFIX = 'controlled_learning/quarantine/outcomes/'
STATUS = 'QUARANTINED'
MAX_BYTES = 4 * 1024**2
MAX_BATCH = 30


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def issues(row):
    """Check mathematical invariants; no judgement of investment performance."""
    measurements = row.get('horizon_measurements') or {}
    if not isinstance(measurements, dict):
        return ['INVALID_MEASUREMENT_CONTAINER']
    found = set()
    windows = []
    for key, reading in measurements.items():
        if not isinstance(reading, dict):
            found.add('INVALID_MEASUREMENT'); continue
        try:
            horizon = int(key)
            if horizon not in (1, 5, 20, 60):
                continue
            fields = ('return_pct', 'maximum_gain_pct', 'maximum_drawdown_pct')
            if not all(k in reading for k in fields):
                continue  # Legacy partial fixtures are not evidence of corruption.
            ret, maximum, minimum = (float(reading[k]) for k in fields)
            if not all(math.isfinite(v) for v in (ret, maximum, minimum)):
                raise ValueError('nonfinite')
            if ret > maximum + .0002 or ret < minimum - .0002:
                found.add('RETURN_OUTSIDE_WINDOW')
            if row.get('entry_price') and reading.get('price'):
                calculated = (float(reading['price']) / float(row['entry_price']) - 1) * 100
                if not math.isfinite(calculated) or abs(calculated-ret) > .0002:
                    found.add('RETURN_ARITHMETIC_MISMATCH')
            if row.get('benchmark_entry_price') and reading.get('benchmark_price') and reading.get('benchmark_return_pct') is not None:
                calculated = (float(reading['benchmark_price']) / float(row['benchmark_entry_price']) - 1) * 100
                if not math.isfinite(calculated) or abs(calculated-float(reading['benchmark_return_pct'])) > .0002:
                    found.add('BENCHMARK_ARITHMETIC_MISMATCH')
            if reading.get('benchmark_return_pct') is not None and reading.get('excess_return_pct') is not None:
                if abs(ret-float(reading['benchmark_return_pct'])-float(reading['excess_return_pct'])) > .0002:
                    found.add('EXCESS_ARITHMETIC_MISMATCH')
            for mark in row.get('daily_marks') or []:
                if mark.get('market_date') == reading.get('market_date') and mark.get('return_pct') is not None:
                    if abs(float(mark['return_pct'])-ret) > .0002:
                        found.add('DAILY_HORIZON_ENDPOINT_MISMATCH')
            windows.append((horizon, maximum, minimum))
        except (ValueError, TypeError, OverflowError, ZeroDivisionError):
            found.add('INVALID_NUMERIC_MEASUREMENT')
    windows.sort()
    for i, (_, maximum, minimum) in enumerate(windows):
        for _, earlier_maximum, earlier_minimum in windows[:i]:
            if maximum + .0002 < earlier_maximum:
                found.add('MAXIMUM_GAIN_DECREASES')
            if minimum - .0002 > earlier_minimum:
                found.add('MINIMUM_RETURN_INCREASES')
    return sorted(found)


def usable(row):
    return row.get('status') != STATUS and not issues(row)


@lru_cache(maxsize=16)
def completed_through(market, at):
    """Use the actual exchange close plus the existing 15-minute publication buffer."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from services.learning_position_outcomes import MARKETS, session_closes
    local_day = at.astimezone(ZoneInfo(MARKETS[market][1])).date()
    closes = session_closes(market, (local_day-timedelta(days=14)).isoformat(), local_day.isoformat())
    eligible = [day for day, close in closes if close+timedelta(minutes=15) <= at]
    if not eligible:
        raise ValueError('No completed exchange session')
    return eligible[-1]


def unpack(backup):
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(base64.b64decode(backup['gzip_base64'], validate=True))) as f:
        raw = f.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Backup exceeds limit')
    rows = json.loads(raw)
    if digest(rows) != backup['rows_sha256']:
        raise ValueError('Backup checksum mismatch')
    return rows


def tombstone(original, *, manifest, backup_key, at):
    row = deepcopy(original)
    row.update(status=STATUS, horizon_measurements={}, daily_marks=[],
               source_health={'status': STATUS, 'checked_at': at},
               outcome_quarantine={'manifest_sha256': digest(manifest), 'backup_key': backup_key,
                   'original_sha256': manifest[row['observation_id']],
                   'reasons': issues(original), 'at': at})
    return row


def apply_manifest(*, storage, manifest, apply=False, now=None):
    if not storage.using_postgres() or storage.allow_local_fallback:
        raise ValueError('Authoritative PostgreSQL required')
    if not manifest or len(manifest) > MAX_BATCH:
        raise ValueError('Explicit bounded manifest required')
    identity = digest(manifest)
    backup_key = PREFIX + identity + '.json'
    receipt_key = PREFIX + identity + '-receipt.json'
    at = (now or datetime.now(timezone.utc)).isoformat()
    result = {'state': 'DRY_RUN', 'isolated': 0, 'backup_key': backup_key,
              'manifest_sha256': identity, 'source': SOURCE,
              'permanent_backup_purge': False, 'trading_changed': False}
    conn = storage._conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='2s'")
                cur.execute("SET LOCAL statement_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(%s)', (19343503,))
                cur.execute('SELECT octet_length(payload) FROM app_kv_store WHERE name=%s', (SOURCE,))
                size = cur.fetchone()
                if not size:
                    return {**result, 'state': 'NO_SOURCE'}
                if size[0] > MAX_BYTES:
                    raise ValueError('Source exceeds bounded cleanup limit')
                cur.execute('SELECT payload FROM app_kv_store WHERE name=%s FOR UPDATE', (SOURCE,))
                rows = json.loads(cur.fetchone()[0])
                if not isinstance(rows, list) or len(rows) > 5120:
                    raise ValueError('Invalid observation source')
                by_id = {r['observation_id']:r for r in rows}
                if len(by_id) != len(rows):
                    raise ValueError('Duplicate observation identities')
                selected = [by_id.get(k) for k in manifest]
                if all(r and r.get('status') == STATUS and r.get('outcome_quarantine', {}).get('manifest_sha256') == identity for r in selected):
                    cur.execute('SELECT payload FROM app_kv_store WHERE name=%s', (backup_key,))
                    existing = cur.fetchone()
                    if not existing or len(unpack(json.loads(existing[0]))) != len(manifest):
                        raise ValueError('Quarantine backup missing or invalid')
                    return {**result, 'state': 'ALREADY_APPLIED', 'isolated': len(manifest)}
                if any(r is None or digest(r) != manifest[k] for k,r in zip(manifest, selected)):
                    return {**result, 'state': 'SOURCE_CHANGED'}
                if any(not issues(r) for r in selected):
                    raise ValueError('Manifest contains an observation without proven inconsistency')
                result.update(isolated=len(selected), reasons={r['observation_id']:issues(r) for r in selected})
                if not apply:
                    return result
                backup = {'schema': 1, 'created_at': at, 'source': SOURCE, 'manifest': manifest,
                          'rows_sha256': digest(selected),
                          'gzip_base64': base64.b64encode(gzip.compress(json.dumps(selected,
                              ensure_ascii=False, allow_nan=False).encode(), mtime=0)).decode()}
                cur.execute('INSERT INTO app_kv_store(name,payload) VALUES(%s,%s) ON CONFLICT(name) DO NOTHING',
                            (backup_key, json.dumps(backup)))
                cur.execute('SELECT payload FROM app_kv_store WHERE name=%s', (backup_key,))
                stored_backup = json.loads(cur.fetchone()[0])
                verified = unpack(stored_backup)
                if verified != selected:
                    raise ValueError('Backup read-back does not match original rows')
                cleaned = deepcopy(rows)
                for i, row in enumerate(cleaned):
                    if row['observation_id'] not in manifest:
                        continue
                    cleaned[i] = tombstone(row, manifest=manifest, backup_key=backup_key,
                                           at=stored_backup['created_at'])
                result.update(state='COMPLETED', completed_at=at, source_after_sha256=digest(cleaned))
                cur.execute('UPDATE app_kv_store SET payload=%s,updated_at=NOW()::TEXT WHERE name=%s',
                            (json.dumps(cleaned, ensure_ascii=False, allow_nan=False), SOURCE))
                cur.execute('INSERT INTO app_kv_store(name,payload) VALUES(%s,%s) ON CONFLICT(name) DO UPDATE SET payload=EXCLUDED.payload,updated_at=NOW()::TEXT',
                            (receipt_key, json.dumps(result)))
                return result
    finally:
        conn.close()


def restore(*, storage, backup_key, apply=False):
    """Explicit recovery tool; never called by the scheduler."""
    if not storage.using_postgres() or storage.allow_local_fallback:
        raise ValueError('Authoritative PostgreSQL required')
    if not backup_key.startswith(PREFIX) or backup_key.endswith('-receipt.json'):
        raise ValueError('Invalid quarantine key')
    conn = storage._conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='2s'")
                cur.execute("SET LOCAL statement_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(%s)', (19343503,))
                cur.execute('SELECT payload FROM app_kv_store WHERE name=%s', (backup_key,))
                backup = json.loads(cur.fetchone()[0])
                originals = unpack(backup)
                cur.execute('SELECT payload FROM app_kv_store WHERE name=%s FOR UPDATE', (SOURCE,))
                rows = json.loads(cur.fetchone()[0])
                for original in originals:
                    target = next(r for r in rows if r['observation_id'] == original['observation_id'])
                    expected = tombstone(original, manifest=backup['manifest'], backup_key=backup_key,
                                         at=backup['created_at'])
                    if target != expected:
                        raise ValueError('Restore would overwrite a changed observation')
                    target.clear(); target.update(original)
                if apply:
                    cur.execute('UPDATE app_kv_store SET payload=%s,updated_at=NOW()::TEXT WHERE name=%s',
                                (json.dumps(rows, ensure_ascii=False), SOURCE))
                return {'state': 'RESTORED' if apply else 'DRY_RUN', 'restored': len(originals)}
    finally:
        conn.close()


def run_authorized_cleanup(*, now=None):
    """User-authorized 9 Nov repair, only the 78 audited immutable row versions.

    The manifest can never expand from data or environment flags. Missing local
    production storage is a no-op for development and test harnesses.
    """
    from pathlib import Path
    from services.storage_service import get_storage_service
    storage = get_storage_service()
    if not storage.using_postgres() or storage.allow_local_fallback:
        return {'state': 'NOT_POSTGRES', 'isolated': 0}
    manifest = json.loads(Path(__file__).with_name('learning_quarantine_20261109.json').read_text())
    entries = list(manifest.items())
    if len(entries) != 78:
        raise ValueError('Unexpected authorized cleanup scope')
    results = []
    for offset in range(0, len(entries), MAX_BATCH):
        batch = dict(entries[offset:offset+MAX_BATCH])
        result = apply_manifest(storage=storage, manifest=batch, apply=True, now=now)
        results.append({k:v for k,v in result.items() if k != 'reasons'})
    return {'state': 'COMPLETED' if all(r['state'] in ('COMPLETED','ALREADY_APPLIED') for r in results) else 'DEFERRED',
            'isolated': sum(r['isolated'] for r in results), 'batches': results,
            'permanent_backup_purge': False}
