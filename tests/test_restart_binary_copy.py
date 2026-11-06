"""Large-document transport retains real transactional semantics."""
import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import pytest
from test_revision_trade_postgres import pg
from services.large_json_write import BinaryTextRow


@pytest.mark.parametrize('chunk', [1, 7, 8192, 65536])
def test_binary_copy_stream_is_exact_and_bounded(chunk):
    import struct
    payload = json.dumps({'history': ['\\\t\n–📈'] * 10000}, ensure_ascii=True)
    stream = BinaryTextRow(payload)
    pieces = []
    while piece := stream.read(chunk):
        assert len(piece) <= chunk
        pieces.append(piece)
    assert b''.join(pieces) == b'PGCOPY\n\xff\r\n\x00' + struct.pack('!iihi', 0, 0, 1, len(payload)) + payload.encode() + b'\xff\xff'


def test_large_pg_write_rollback_and_concurrency(pg, monkeypatch):
    monkeypatch.setenv('SCHEDULER_LARGE_JSON_WARN_MB','0.0001')
    # The production threshold has a 1 MiB lower bound.
    key='simulation_restarts/isolated/bundle.json'
    value={'history':['NOK \\ \" – 📈' * 1000] * 120, 'counter':0}
    pg.write_json(key,value)
    assert pg.read_json(key)==value
    revision=pg.json_row_versions([key])
    pg.write_json(key,value)
    assert pg.json_row_versions([key])==revision
    def fail(doc):
        doc['counter']=999
        raise ValueError('abort transaction')
    with pytest.raises(ValueError,match='abort transaction'):
        pg.mutate_json(key,fail)
    assert pg.read_json(key)==value
    def increment(_):
        def update(doc):
            doc['counter']+=1
            return doc
        return pg.mutate_json(key,update)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(increment,range(3)))
    assert pg.read_json(key)=={**value,'counter':3}
    connection=pg._conn()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('pg_temp.app_restart_payload')")
            assert cursor.fetchone()[0] is None
    finally:connection.close()


def test_copy_failure_after_staging_rolls_back_old_document(pg,monkeypatch):
    import services.large_json_write as transport
    # Raising a logging threshold must not switch off bounded transport.
    monkeypatch.setenv('SCHEDULER_LARGE_JSON_WARN_MB','500')
    key='simulation_restarts/rollback/bundle.json';value={'text':'x'*1100000,'counter':0}
    pg.write_json(key,value)
    original=transport.write_restart_payload
    def failing(cursor,*args,**kwargs):
        original(cursor,*args,**kwargs)
        raise RuntimeError('after staged upsert, before commit')
    monkeypatch.setattr(transport,'write_restart_payload',failing)
    with pytest.raises(RuntimeError,match='before commit'):
        pg.mutate_json(key,lambda doc:{**doc,'counter':1})
    assert pg.read_json(key)==value
