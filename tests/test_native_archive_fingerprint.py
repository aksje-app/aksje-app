"""Checksum compatibility and fail-closed source verification on isolated PG."""
from decimal import Decimal
import hashlib
import json

import pytest
from test_revision_trade_postgres import pg
from services import native_archive_fingerprint as native, simulation_archive as archive


@pytest.mark.parametrize('value', [
    '', 'escaped " \\ \n\t', 'æøå😀雪' * 5000, 'x' * 16383 + '😀' + 'y' * 16385,
    '\u2028\u0001',
])
def test_incremental_utf8_is_exact_old_canonical_json(value):
    document = {'雪': [Decimal('1.2300'), None, True], 'payload': value, 'id': 7}
    wrapped = {**document, 'payload': native.Utf8Text(value.encode())}
    assert native.row_hash(wrapped) == hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(',', ':'), default=str).encode()).digest()


def readonly(pg):
    connection = pg._conn()
    connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
    return connection


def old_oracle(connection, ignore_period=None):
    """Old serialization is an oracle only on this bounded synthetic database."""
    from psycopg2 import sql
    result = {}
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL TIME ZONE 'UTC'")
        cursor.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
        tables = cursor.fetchall()
        for schema, table in tables:
            cursor.execute(sql.SQL('SELECT row_to_json(t)::text FROM {} t').format(sql.Identifier(schema, table)))
            count = total = 0
            for (raw,) in cursor:
                value = json.loads(raw, parse_float=Decimal)
                if table == 'app_kv_store' and ignore_period:
                    name = value['name']
                    if name == 'simulation_restarts/' + ignore_period + '/bundle.json':
                        continue
                    if name.startswith('simulation_restarts/routes/') and json.loads(value['payload']).get('period_id') == ignore_period:
                        continue
                total = (total + int.from_bytes(hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).digest(), 'big')) % (1 << 256)
                count += 1
            result[schema+'.'+table] = dict(rows=count, multiset_sha256_sum=f'{total:064x}')
    return result


def traced(connection):
    from psycopg2.extensions import cursor
    queries = []
    class Trace(cursor):
        def execute(self, query, args=None):
            queries.append(query.as_string(self) if hasattr(query, 'as_string') else query)
            return super().execute(query, args)
    connection.cursor_factory = Trace
    return queries


def test_native_matches_full_existing_format_and_preserves_other_periods(pg):
    connection = pg._conn()
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE "unknown source" ("雪" text, at timestamptz, qty double precision, active boolean)')
        # Deliberate duplicate, Unicode, quoting, UTC conversion, NULL and empty table.
        for _ in range(2):
            cursor.execute('INSERT INTO "unknown source" VALUES (%s,%s,%s,%s)',
                           ('😀雪\\"\n' * 10000, '2026-10-25T03:12:15.123456+01:00', 1.23e-12, True))
        cursor.execute('INSERT INTO "unknown source" VALUES (NULL,NULL,NULL,NULL)')
        cursor.execute('CREATE TABLE "empty source" (payload text)')
    connection.commit()
    connection.close()
    for name, payload in {
        'simulation_restarts/new/bundle.json': {'status': 'DRAFT'},
        'simulation_restarts/old/bundle.json': {'original_loss': -25000},
        'simulation_restarts/routes/paper.json': {'period_id': 'new'},
        'simulation_restarts/routes/autonomy.json': {'period_id': 'old'},
        'learning/original.json': {'observations': 81},
        'superfund/original.json': {'cash': 1000000},
    }.items():
        pg.write_json(name, payload)
    connection = readonly(pg)
    try:
        queries = traced(connection)
        actual = archive.database_fingerprint(connection, ignore_period='new')
        assert not any('row_to_json' in query for query in queries)
        assert not any('to_json(t."payload")' in query for query in queries)
        assert actual == old_oracle(connection, ignore_period='new')
        full = archive.database_fingerprint(connection)
        assert full == old_oracle(connection)
        schema = next(name.rsplit('.', 1)[0] for name in actual if name.endswith('.app_kv_store'))
        assert full[schema+'.app_kv_store']['rows'] - actual[schema+'.app_kv_store']['rows'] == 2
        assert actual[schema+'.unknown source']['rows'] == 3
        assert actual[schema+'.empty source']['rows'] == 0
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.parametrize('kind', ['size', 'type', 'write_transaction', 'encoding'])
def test_unverified_sources_fail_before_value_fetch(pg, monkeypatch, kind):
    connection = pg._conn()
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE source (payload text, extra jsonb)')
        cursor.execute('INSERT INTO source VALUES (%s,%s)', ('snow雪' * 100, '{"x":1}' if kind == 'type' else None))
    connection.commit()
    if kind == 'size':
        monkeypatch.setattr(native, 'NATIVE_ROW_LIMIT', 100)
    if kind != 'write_transaction':
        connection.set_session(readonly=True)
    if kind == 'encoding':
        connection.set_client_encoding('LATIN1')
    queries = traced(connection)
    try:
        with pytest.raises(ValueError, match={'size': 'memory envelope', 'type': 'variable-width', 'write_transaction': 'READ ONLY', 'encoding': 'UTF8'}[kind]):
            archive.database_fingerprint(connection)
        assert not any('."source" t' in query for query in queries)
    finally:
        connection.rollback()
        connection.close()


def test_existing_live_source_barrier_still_rejects_history_changes(pg, tmp_path):
    pg.write_json('learning/original.json', {'loss': -25000, 'observations': 81})
    root = tmp_path/'runtime'
    root.mkdir()
    (root/'original').write_text('unchanged history')
    connection = readonly(pg)
    try:
        fingerprint = archive.database_fingerprint(connection)
    finally:
        connection.rollback()
        connection.close()
    reviewed = {'manifest': {'source_roots': {'runtime': str(root)},
        'source_inventory': {'runtime': archive._inventory(root)},
        'database_model_fingerprints': {'original': fingerprint}}}
    connection = pg._conn()
    try:
        archive.verify_live_sources(reviewed, databases={'original': connection})
        pg.write_json('learning/original.json', {'loss': 0, 'observations': 81})
        with pytest.raises(ValueError, match='history changed'):
            archive.verify_live_sources(reviewed, databases={'original': connection})
    finally:
        connection.close()
