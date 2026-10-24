"""Native-column canonical fingerprint implementation for isolated operator jobs.

Same canonical JSON/multiset SHA256 as simulation_archive.database_fingerprint;
large TEXT values are escaped incrementally by the client, never row_to_json on
those complete production-style rows. No archive, restart or activation action.
"""
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import codecs
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

TEXT_OID = 25
CHUNK_CHARACTERS = 16384
MODULUS = 1 << 256


class Utf8Text:
    """Native libpq bytes: avoid a complete UCS4 allocation for large TEXT."""
    def __init__(self, raw):
        self.raw = raw


def canonical_chunks(value):
    if isinstance(value, Utf8Text):
        yield b'"'
        decoder = codecs.getincrementaldecoder('utf-8')('strict')
        for start in range(0, len(value.raw), CHUNK_CHARACTERS):
            part = decoder.decode(value.raw[start:start + CHUNK_CHARACTERS], final=False)
            yield json.dumps(part, ensure_ascii=True)[1:-1].encode('ascii')
        part = decoder.decode(b'', final=True)
        if part:
            yield json.dumps(part, ensure_ascii=True)[1:-1].encode('ascii')
        yield b'"'
    elif isinstance(value, str):
        yield b'"'
        for start in range(0, len(value), CHUNK_CHARACTERS):
            yield json.dumps(value[start:start + CHUNK_CHARACTERS], ensure_ascii=True)[1:-1].encode('ascii')
        yield b'"'
    elif isinstance(value, dict):
        yield b'{'
        for index, key in enumerate(sorted(value)):
            if index:
                yield b','
            yield json.dumps(key, ensure_ascii=True).encode('ascii')
            yield b':'
            yield from canonical_chunks(value[key])
        yield b'}'
    elif isinstance(value, list):
        yield b'['
        for index, item in enumerate(value):
            if index:
                yield b','
            yield from canonical_chunks(item)
        yield b']'
    else:
        yield json.dumps(value, sort_keys=True, separators=(',', ':'), default=str, ensure_ascii=True).encode('ascii')


def row_hash(value):
    digest = hashlib.sha256()
    for block in canonical_chunks(value):
        digest.update(block)
    return digest.digest()


def decoded_row(columns, values):
    return {name: (Utf8Text(raw) if type_oid == TEXT_OID and isinstance(raw, bytes) else
                   raw if type_oid == TEXT_OID or raw is None else json.loads(raw, parse_float=Decimal))
            for (name, type_oid, _), raw in zip(columns, values, strict=True)}


def emit(value):
    print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)


def available_memory():
    if os.name != 'nt':
        return None
    import ctypes
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                    ('total_phys', ctypes.c_ulonglong), ('avail_phys', ctypes.c_ulonglong),
                    ('total_page', ctypes.c_ulonglong), ('avail_page', ctypes.c_ulonglong),
                    ('total_virtual', ctypes.c_ulonglong), ('avail_virtual', ctypes.c_ulonglong),
                    ('avail_extended', ctypes.c_ulonglong)]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise RuntimeError('Cannot verify local available memory; no large-value scan')
    return status.avail_phys


def scan_database(connection, *, ignore_period=None, progress=emit, bounded_oracle=True, native_limit_bytes=None):
    from psycopg2 import sql, extensions
    started = time.monotonic()
    result = {}
    sizes = {}
    samples = 0
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL TIME ZONE 'UTC'")
        cursor.execute("SHOW transaction_read_only")
        if cursor.fetchone()[0] != 'on':
            raise ValueError('READ ONLY transaction required')
        cursor.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
        tables = cursor.fetchall()
    for table_index, (schema, table) in enumerate(tables, 1):
        relation = sql.Identifier(schema, table)
        label = schema + '.' + table
        progress(dict(kind='TABLE_START', table_index=table_index, table=label))
        with connection.cursor() as cursor:
            cursor.execute('''SELECT a.attname,a.atttypid,a.attlen FROM pg_attribute a
                JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum''', (schema, table))
            columns = cursor.fetchall()
            if not columns:
                raise ValueError('No visible columns; refuse silent omission')
            text_columns = [name for name, oid, _ in columns if oid == TEXT_OID]
            if text_columns:
                expressions = [sql.SQL('max(octet_length({}))').format(sql.Identifier(name)) for name in text_columns]
                cursor.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(expressions), relation))
                text_sizes = dict(zip(text_columns, cursor.fetchone(), strict=True))
            else:
                text_sizes = {}
            max_text_row = sum(length or 0 for length in text_sizes.values())
            if native_limit_bytes is not None:
                unsupported = [name for name, oid, length in columns if oid != TEXT_OID and length < 0]
                if unsupported:
                    expressions = [sql.SQL('max(pg_column_size({}))').format(sql.Identifier(name)) for name in unsupported]
                    cursor.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(expressions), relation))
                    if any(value is not None for value in cursor.fetchone()):
                        raise ValueError('Unsupported variable-width source column; native scan refused')
                native_upper = max_text_row + sum(max(64, length * 8) for _, oid, length in columns if oid != TEXT_OID and length > 0)
                if native_upper > native_limit_bytes:
                    raise ValueError('Native row exceeds verified memory envelope; no value fetched')
            sizes[label] = text_sizes
            free = available_memory()
            progress(dict(kind='NATIVE_READ_PLAN', table=label, max_text_column_octets=text_sizes,
                          available_pc_memory_bytes=free, fetch_rows=1))
            if free is not None and max(512 * 1024**2, max_text_row * 8) > free // 2:
                raise MemoryError('Local copy scan exceeds conservative available-memory budget')
            expressions = [sql.SQL('t.{}').format(sql.Identifier(name)) if oid == TEXT_OID else
                           sql.SQL('to_json(t.{})::text').format(sql.Identifier(name)) for name, oid, _ in columns]
            selected = sql.SQL(',').join(expressions)
            # Only bounded small samples use the original row_to_json oracle.
            # This entire program is constrained to the local restored copy.
            limits = [sql.SQL('coalesce(octet_length(t.{}),0)<=8192').format(sql.Identifier(name)) if oid == TEXT_OID else
                      sql.SQL('coalesce(pg_column_size(t.{}),0)<=4096').format(sql.Identifier(name)) for name, oid, _ in columns]
            query = sql.SQL('SELECT {},row_to_json(t)::text FROM {} t WHERE {} LIMIT 3').format(selected, relation, sql.SQL(' AND ').join(limits))
            if bounded_oracle:
                cursor.execute(query)
            for sample in cursor.fetchall() if bounded_oracle else ():
                expected = json.loads(sample[-1], parse_float=Decimal)
                actual = decoded_row(columns, sample[:-1])
                original_hash = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(',', ':'), default=str).encode()).digest()
                if row_hash(actual) != original_hash:
                    raise ValueError('Canonical checksum mismatch in local bounded sample: ' + label)
                samples += 1
        # Native TEXT columns never pass through PostgreSQL JSON serialization.
        query = sql.SQL('SELECT {} FROM {} t').format(selected, relation)
        count = total = 0
        last_progress = time.monotonic()
        with connection.cursor(name='native_' + uuid.uuid4().hex) as rows:
            extensions.register_type(extensions.BYTES, rows)
            rows.itersize = 1
            rows.arraysize = 1
            rows.execute(query)
            while True:
                raw = rows.fetchone()
                if raw is None:
                    break
                value = decoded_row(columns, raw)
                if table == 'app_kv_store' and ignore_period:
                    key = value.get('name', '')
                    if isinstance(key, Utf8Text):
                        key = key.raw.decode('utf-8')
                    if key == 'simulation_restarts/' + ignore_period + '/bundle.json':
                        del value, raw
                        continue
                    if key.startswith('simulation_restarts/routes/'):
                        payload = value.get('payload')
                        payload = json.loads(payload.raw) if isinstance(payload, Utf8Text) else json.loads(payload) if isinstance(payload, str) else payload
                        if payload.get('period_id') == ignore_period:
                            del value, raw, payload
                            continue
                        del payload
                total = (total + int.from_bytes(row_hash(value), 'big')) % MODULUS
                count += 1
                del value, raw
                if time.monotonic() - last_progress >= 5:
                    progress(dict(kind='READ_PROGRESS', table=label, rows=count, elapsed_seconds=round(time.monotonic() - started)))
                    last_progress = time.monotonic()
        result[label] = dict(rows=count, multiset_sha256_sum=f'{total:064x}')
        progress(dict(kind='TABLE_DONE', table=label, rows=count, max_text_column_octets=text_sizes))
    return dict(fingerprints=result, max_text_column_octets=sizes, bounded_oracle_samples=samples,
                elapsed_seconds=round(time.monotonic() - started))
