"""Real cross-session coordination and atomic Superfond decisions in CI DB."""
import os
from concurrent.futures import ThreadPoolExecutor
import pytest

URL=os.getenv('TEST_POSTGRES_URL','')
pytestmark=pytest.mark.skipif(not URL,reason='Isolated PostgreSQL runs in release CI')


@pytest.fixture
def postgres(monkeypatch):
    import psycopg2
    import superfund_runtime as runtime
    from services.storage_service import StorageService
    service=StorageService(database_url=URL,mode='postgres',allow_local_fallback=False)
    service.init_db()
    with psycopg2.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT current_database()')
            assert cur.fetchone()[0]=='entry_exit_test'
            cur.execute("DELETE FROM app_kv_store WHERE name LIKE 'superfund/%'")
    monkeypatch.setenv('DATABASE_URL',URL)
    monkeypatch.setattr(runtime,'storage',lambda:service)
    yield service
    with psycopg2.connect(URL) as conn:
        with conn.cursor() as cur:cur.execute("DELETE FROM app_kv_store WHERE name LIKE 'superfund/%'")


def test_common_lane_across_sessions_and_disconnect_release(postgres):
    from resource_coordinator import execution_lane,verify_lane
    def compete():
        with execution_lane('other') as acquired:return acquired
    with execution_lane('owner') as acquired:
        assert acquired;verify_lane()
        with ThreadPoolExecutor(max_workers=1) as pool:assert pool.submit(compete).result() is False
        with execution_lane('nested') as nested:assert nested
    with execution_lane('next') as acquired:assert acquired


def test_lost_postgres_lock_blocks_fund_publication(postgres):
    import superfund_runtime as runtime
    from resource_coordinator import execution_lane,_connection
    with execution_lane('owner') as acquired:
        assert acquired
        _connection.get().close()
        with pytest.raises(Exception):runtime.write('snapshot.json',{'incorrect':'publish'})
    assert not postgres.read_json('superfund/snapshot.json',{})


def test_concurrent_approval_and_click_queue_are_idempotent(postgres):
    import superfund_runtime as runtime
    from superfund_learning import decide_proposal
    runtime.write('snapshot.json',{'learning':{'proposal':{'id':'p1','state':'WAITING_APPROVAL',
        'parameter':'min_week_pct','current':1.0,'proposed':0.5}}})
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts=list(pool.map(lambda _:decide_proposal('p1',True),range(8)))
        requests=list(pool.map(lambda _:runtime.request_scan(),range(8)))
    assert all(r['state']=='IMPLEMENTED' for r in receipts)
    assert len(runtime.read('parameter_audit.json')['history'])==1
    assert all(r==requests[0] for r in requests)
    assert runtime.config()['min_week_pct']==0.5
