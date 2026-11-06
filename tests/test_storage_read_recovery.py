"""Availability retries apply to reads, never uncertain financial commits."""
import pytest
import psycopg2
from test_revision_trade_postgres import pg
from services.storage_service import StorageUnavailableError


def test_recovery_waits_and_reads_same_authoritative_parameters(pg,monkeypatch):
    key='autonomous_portfolio/parameters.json';value={'rule':'unchanged – 📈'}
    pg.write_json(key,value)
    connect=pg._conn;attempts=[];delays=[]
    def recovering():
        attempts.append(1)
        if len(attempts)<4:
            raise psycopg2.OperationalError('FATAL: the database system is not yet accepting connections')
        return connect()
    monkeypatch.setattr(pg,'_conn',recovering)
    monkeypatch.setattr('services.storage_service.time.sleep',delays.append)
    assert pg.read_json(key)==value
    assert delays==[1,2,4] and len(attempts)==4
    assert not (pg.base_dir/key).exists()


def test_read_recovery_is_bounded_and_does_not_hide_corruption(pg,monkeypatch):
    delays=[]
    monkeypatch.setattr('services.storage_service.time.sleep',delays.append)
    connect=pg._conn
    def unavailable():raise psycopg2.OperationalError('connection refused')
    monkeypatch.setattr(pg,'_conn',unavailable)
    with pytest.raises(StorageUnavailableError):pg.read_json('parameters.json',{'unsafe':'fallback'})
    assert delays==[1,2,4,8]
    monkeypatch.setattr(pg,'_conn',connect)
    conn=connect()
    try:
        with conn.cursor() as cur:cur.execute("INSERT INTO app_kv_store(name,payload) VALUES ('broken.json','{broken')")
        conn.commit()
    finally:conn.close()
    delays.clear()
    with pytest.raises(StorageUnavailableError):pg.read_json('broken.json')
    assert delays==[]


def test_commit_acknowledgement_loss_never_replays_mutation(pg,monkeypatch):
    key='simulation_restarts/ack/bundle.json';pg.write_json(key,{'counter':0})
    connect=pg._conn;calls=[]
    class LostAcknowledgement:
        def __init__(self):self.conn=connect()
        def __getattr__(self,name):return getattr(self.conn,name)
        def commit(self):
            self.conn.commit()
            raise psycopg2.OperationalError('injected lost commit acknowledgement')
    monkeypatch.setattr(pg,'_conn',LostAcknowledgement)
    def update(doc):calls.append(1);return {'counter':doc['counter']+1}
    with pytest.raises(psycopg2.OperationalError,match='acknowledgement'):
        pg.mutate_json(key,update)
    monkeypatch.setattr(pg,'_conn',connect)
    assert calls==[1] and pg.read_json(key)=={'counter':1}
