"""Storage escapes must preserve Unicode journal values, hashes and rollback."""
from copy import deepcopy
import json
import pytest
from services.storage_service import StorageService
from services.economic_opening import digest
from test_revision_trade_postgres import pg


def journal():
    return {'history':[{'text':'Årsrapport – 💹 e\u0301 é', 'literal':'\\ud83d\\udcc8',
                        'control':'\n\t\x00', 'amount':-0.0, 'unicode_key':{'日本語':'NOK'}}]*10}


def test_restart_unicode_values_and_fingerprints_survive_local_storage(tmp_path):
    backend=StorageService(tmp_path,mode='local')
    key='simulation_restarts/parity/bundle.json'
    value=journal();before=digest(value)
    backend.write_json(key,value)
    backend.mutate_json(key,lambda current: current)
    raw=(tmp_path/key).read_text()
    assert raw.isascii()
    assert backend.read_json(key)==value
    assert digest(backend.read_json(key))==before
    def abort(current):
        current['history'].clear()
        raise ValueError('rollback')
    with pytest.raises(ValueError):backend.mutate_json(key,abort)
    assert backend.read_json(key)==value


def test_restart_unicode_roundtrip_and_transaction_rollback_on_postgres(pg):
    key='simulation_restarts/ascii-proof/bundle.json'
    value=journal();before=digest(value)
    pg.write_json(key,value)
    pg.mutate_json(key,lambda current: current)
    conn=pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT payload FROM app_kv_store WHERE name=%s',(key,))
            assert cur.fetchone()[0].isascii()
    finally:conn.close()
    assert pg.read_json(key)==value
    assert digest(pg.read_json(key))==before
    def abort(current):
        current['history'].clear()
        raise ValueError('rollback')
    with pytest.raises(ValueError):pg.mutate_json(key,abort)
    assert pg.read_json(key)==value


def test_row_and_advisory_locks_survive_cursor_closure_on_postgres(pg):
    import psycopg2
    key='simulation_restarts/locks/bundle.json'
    pg.write_json(key, journal())
    def transform(current):
        other=pg._conn()
        try:
            with other.cursor() as cur:
                cur.execute('SELECT pg_try_advisory_xact_lock(hashtext(%s))', (key,))
                assert cur.fetchone()[0] is False
                with pytest.raises(psycopg2.errors.LockNotAvailable):
                    cur.execute('SELECT payload FROM app_kv_store WHERE name=%s FOR UPDATE NOWAIT', (key,))
        finally:other.rollback();other.close()
        return {**current, 'lock_proof':True}
    assert pg.mutate_json(key, transform)['lock_proof'] is True
