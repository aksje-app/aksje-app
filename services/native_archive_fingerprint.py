"""Bounded native UTF-8 reads with the existing archive checksum format.

Promotes the adapter validated during the Windows restore into the shared
archive/activation path. No whole-row JSON, writes, or checksum migration.
Unsupported variable-width types fail closed instead of omitting source data.
"""
import codecs
from decimal import Decimal
import hashlib
import json
import uuid

TEXT_OID = 25
CHUNK_BYTES = 16384
NATIVE_ROW_LIMIT = 160 * 1024**2


class Utf8Text:
    def __init__(self, raw):
        self.raw = raw


def canonical_chunks(value):
    """Exactly json.dumps(sort_keys=True, separators=(',', ':'), default=str)."""
    if isinstance(value, Utf8Text):
        yield b'"'
        decoder = codecs.getincrementaldecoder('utf-8')('strict')
        for start in range(0, len(value.raw), CHUNK_BYTES):
            part = decoder.decode(value.raw[start:start + CHUNK_BYTES], final=False)
            yield json.dumps(part, ensure_ascii=True)[1:-1].encode('ascii')
        part = decoder.decode(b'', final=True)
        if part:
            yield json.dumps(part, ensure_ascii=True)[1:-1].encode('ascii')
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
        yield json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode('ascii')


def row_hash(value):
    result = hashlib.sha256()
    for block in canonical_chunks(value):
        result.update(block)
    return result.digest()


def _decoded_row(columns, values):
    return {name: (Utf8Text(raw) if oid == TEXT_OID and isinstance(raw, bytes) else
                   raw if oid == TEXT_OID or raw is None else json.loads(raw, parse_float=Decimal))
            for (name, oid, _), raw in zip(columns, values, strict=True)}


def _exclude(value, table, period):
    if table != 'app_kv_store' or not period:
        return False
    key = value.get('name', '')
    if isinstance(key, Utf8Text):
        key = key.raw.decode('utf-8')
    if key == 'simulation_restarts/' + period + '/bundle.json':
        return True
    if key.startswith('simulation_restarts/routes/'):
        payload = value.get('payload')
        if isinstance(payload, Utf8Text):
            payload = payload.raw
        if isinstance(payload, (bytes, str)):
            if len(payload) > 65536:
                raise ValueError('Oversized route; cannot safely verify period exclusion')
            payload = json.loads(payload)
        return payload.get('period_id') == period
    return False


def database_fingerprint(connection, *, ignore_period=None):
    from psycopg2 import extensions, sql
    if connection.encoding != 'UTF8':
        raise ValueError('Native archive verification requires UTF8 client encoding')
    result = {}
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL TIME ZONE 'UTC'")
        cursor.execute('SHOW transaction_read_only')
        if cursor.fetchone()[0] != 'on':
            raise ValueError('READ ONLY transaction required for archive fingerprint')
        cursor.execute('SHOW server_encoding')
        if cursor.fetchone()[0] != 'UTF8':
            raise ValueError('Native archive verification requires UTF8 source encoding')
        cursor.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
        tables = cursor.fetchall()
    for schema, table in tables:
        relation = sql.Identifier(schema, table)
        with connection.cursor() as cursor:
            cursor.execute('''SELECT a.attname,a.atttypid,a.attlen FROM pg_attribute a
                JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum''', (schema, table))
            columns = cursor.fetchall()
            if not columns:
                raise ValueError('No visible source columns; refuse omission')
            text = [name for name, oid, _ in columns if oid == TEXT_OID]
            upper = sum(max(64, length * 8) for _, oid, length in columns if oid != TEXT_OID and length > 0)
            if text:
                expressions = [sql.SQL('max(octet_length({}))').format(sql.Identifier(name)) for name in text]
                cursor.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(expressions), relation))
                upper += sum(length or 0 for length in cursor.fetchone())
            variable = [name for name, oid, length in columns if oid != TEXT_OID and length < 0]
            if variable:
                expressions = [sql.SQL('max(pg_column_size({}))').format(sql.Identifier(name)) for name in variable]
                cursor.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(expressions), relation))
                if any(size is not None for size in cursor.fetchone()):
                    raise ValueError('Unsupported variable-width source column; native scan refused')
            if upper > NATIVE_ROW_LIMIT:
                raise ValueError('Native row exceeds verified memory envelope; no value fetched')
        expressions = [sql.SQL('t.{}').format(sql.Identifier(name)) if oid == TEXT_OID else
                       sql.SQL('to_json(t.{})::text').format(sql.Identifier(name)) for name, oid, _ in columns]
        query = sql.SQL('SELECT {} FROM {} t').format(sql.SQL(',').join(expressions), relation)
        count = total = 0
        with connection.cursor(name='native_archive_' + uuid.uuid4().hex) as rows:
            extensions.register_type(extensions.BYTES, rows)
            rows.itersize = rows.arraysize = 1
            rows.execute(query)
            while True:
                raw = rows.fetchone()
                if raw is None:
                    break
                value = _decoded_row(columns, raw)
                if not _exclude(value, table, ignore_period):
                    total = (total + int.from_bytes(row_hash(value), 'big')) % (1 << 256)
                    count += 1
                del value, raw
        result[schema + '.' + table] = dict(rows=count, multiset_sha256_sum=f'{total:064x}')
    return result
