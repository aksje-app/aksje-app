"""A dead connection must not hide the database error or retry a financial mutation."""
import pytest
from test_revision_trade_postgres import pg


def test_backend_disconnect_preserves_original_error_and_old_document(pg,monkeypatch):
    import psycopg2
    from services import large_json_write as transport
    key='simulation_restarts/disconnect/bundle.json'
    value={'text':'x'*1100000,'counter':0}
    pg.write_json(key,value)
    original=transport.write_restart_payload
    transforms=[]
    def disconnect(cursor,*args,**kwargs):
        killer=pg._conn()
        try:
            killer.autocommit=True
            with killer.cursor() as cur:
                cur.execute('SELECT pg_terminate_backend(%s)',(cursor.connection.get_backend_pid(),))
                assert cur.fetchone()[0] is True
        finally:killer.close()
        return original(cursor,*args,**kwargs)
    def mutate(doc):
        transforms.append('called')
        return {**doc,'counter':1}
    monkeypatch.setattr(transport,'write_restart_payload',disconnect)
    with pytest.raises(psycopg2.OperationalError):
        pg.mutate_json(key,mutate)
    assert transforms==['called']
    assert pg.read_json(key)==value
