"""Atomic identity migration and financial operations against isolated PG only."""
import json
import pytest
from test_revision_trade_postgres import pg
from test_restart_trading import active, storage, sealed, certificate, sources, dump_program, prepare, execute, at, paper_signal
from services import restart_payload_archive as archive, simulation_restart as restart
from services import restart_payload_archive_migration as migration
from test_restart_payload_codec import raw_get


def seed(pg,active,monkeypatch):
    monkeypatch.setenv('RESTART_BUNDLE_COMPRESSION_ENABLED','1')
    storage,bundle,_=active
    key=restart._key(bundle['period_id'])
    root=storage.read_json(key)
    pg.write_json(key,root)
    return key,root


def test_migration_preserves_every_logical_byte_and_exact_backup(pg,active,monkeypatch):
    key,before=seed(pg,active,monkeypatch);raw=raw_get(pg,key)
    result=migration.migrate(pg,key)
    assert result['status']=='VERIFIED'
    assert result['semantic_sha256_before']==result['semantic_sha256_after']==archive.semantic_sha256(before)
    assert raw_get(pg,result['backup_key'])==raw
    after=pg.read_json(key);restart.verify_bundle(after)
    assert after==before and archive.is_archived(after)
    assert json.loads(raw_get(pg,key))['__restart_storage__']==archive.MARKER
    assert archive.status(pg)['status']=='VERIFIED'
    versions=pg.json_row_versions([key,result['backup_key'],archive.KEY])
    assert migration.migrate(pg,key)['status']=='VERIFIED'
    assert versions==pg.json_row_versions([key,result['backup_key'],archive.KEY])
    # Genuine ordinary strategy operation and duplicate retry after migration.
    scoped=restart.AccountStorage(before['period_id'],pg)
    context=(pg,before,scoped);stamp=at(context)
    response=execute(context,'paper','archive-paper',stamp,[paper_signal(stamp)])
    assert execute(context,'paper','archive-paper',stamp,[paper_signal(stamp)])==response
    restart.verify_bundle(pg.read_json(key))
    assert raw_get(pg,result['backup_key'])==raw
    assert json.loads(raw_get(pg,key))['__restart_storage__']==archive.MARKER


def test_failed_final_verification_rolls_back_blobs_backup_root_receipt(pg,active,monkeypatch):
    key,_=seed(pg,active,monkeypatch);raw=raw_get(pg,key)
    original=restart.verify_bundle;calls=[]
    def fail_second(value):
        calls.append(1)
        if len(calls)==2:raise ValueError('injected final replay failure')
        return original(value)
    monkeypatch.setattr(restart,'verify_bundle',fail_second)
    with pytest.raises(ValueError,match='injected'):migration.migrate(pg,key)
    assert raw_get(pg,key)==raw
    conn=pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM app_kv_store WHERE name LIKE %s",(key.removesuffix('bundle.json')+'%',))
            assert cur.fetchall()==[(key,)]
    finally:conn.close()
    assert pg.read_json(archive.KEY,None) is None


def test_corrupt_blob_aborts_financial_replay_without_changing_root(pg,active,monkeypatch):
    key,_=seed(pg,active,monkeypatch);migration.migrate(pg,key);raw=raw_get(pg,key)
    root=pg.read_json(key);reference=root['accounts']['paper']['events'][0]['payload'].reference
    conn=pg._conn()
    try:
        with conn.cursor() as cur:cur.execute('UPDATE app_kv_store SET payload=%s WHERE name=%s',('{}',reference['key']))
        conn.commit()
    finally:conn.close()
    called=[]
    def transform(value):
        restart.verify_bundle(value)
        called.append(True)
        return value
    with pytest.raises(ValueError):pg.mutate_json(key,transform)
    assert not called and raw_get(pg,key)==raw


@pytest.mark.parametrize('family',['autonomy','super_portfolio'])
def test_archived_history_supports_real_buy_stop_and_retry(pg,active,monkeypatch,family):
    from test_restart_trading import candidate,evidence
    key,before=seed(pg,active,monkeypatch);migration.migrate(pg,key)
    context=(pg,before,restart.AccountStorage(before['period_id'],pg))
    first,second,third=at(context),at(context,3),at(context,4)
    execute(context,family,'archive-search',first,[candidate(first)])
    execute(context,family,'archive-buy',second,[candidate(second)])
    bought=pg.read_json(key)['accounts'][family]['account']
    assert len(bought['trades'])==1 and bought['positions']
    result=execute(context,family,'archive-stop',third,[candidate(third,price=80)],evidence(third,price=80))
    assert execute(context,family,'archive-stop',third,[candidate(third,price=80)],evidence(third,price=80))==result
    root=pg.read_json(key);restart.verify_bundle(root)
    assert root['accounts'][family]['account']['positions']=={}
    assert len(root['accounts'][family]['account']['trades'])==2


def test_archive_preserves_fingerprint_of_all_sources_outside_current_period(pg,active,monkeypatch):
    from services.native_archive_fingerprint import database_fingerprint
    key,before=seed(pg,active,monkeypatch)
    pg.write_json('learning/protected.json',{'observations':[1,2,3]})
    def fingerprint():
        conn=pg._conn();conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
        try:return database_fingerprint(conn,ignore_period=before['period_id'])
        finally:conn.close()
    protected=fingerprint();migration.migrate(pg,key)
    assert fingerprint()==protected
    assert pg.read_json('learning/protected.json')=={'observations':[1,2,3]}


def test_readonly_operator_can_verify_archived_root_without_writes(pg,active,monkeypatch):
    from tools.nok_operator.operator_common import ReadOnlyStorage
    key,before=seed(pg,active,monkeypatch);migration.migrate(pg,key)
    versions=pg.json_row_versions([key,archive.KEY])
    monkeypatch.setenv('DATABASE_URL',pg.database_url)
    read_only=ReadOnlyStorage();root=read_only.read_json(key)
    restart.verify_bundle(root)
    assert archive.semantic_sha256(root)==archive.semantic_sha256(before)
    assert pg.json_row_versions([key,archive.KEY])==versions


def test_locked_blob_cache_blocks_concurrent_changes_until_root_commit(pg,active,monkeypatch):
    """Cached verification cannot outlive a blob's lock inside a root mutation."""
    from concurrent.futures import ThreadPoolExecutor
    import psycopg2
    key,_=seed(pg,active,monkeypatch)
    migration.migrate(pg,key)
    original_root=raw_get(pg,key)
    observed=[]

    def update_blob(blob_key, *, corrupt=False):
        conn=pg._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='150ms'")
                if corrupt:
                    cur.execute('UPDATE app_kv_store SET payload=%s WHERE name=%s',('{}',blob_key))
                else:
                    cur.execute('UPDATE app_kv_store SET payload=payload WHERE name=%s',(blob_key,))
                changed=cur.rowcount
            conn.commit()
            return ('UPDATED',changed)
        except psycopg2.Error as exc:
            conn.rollback()
            return ('BLOCKED',exc.pgcode)
        finally:
            conn.close()

    def checked_mutation(root):
        restart.verify_bundle(root)
        ref=root['accounts']['paper']['events'][0]['payload'].reference
        observed.append(ref['key'])
        # A separate connection must wait on the FOR SHARE row lock, including
        # while repeated verification is served by this root's encoded cache.
        with ThreadPoolExecutor(max_workers=1) as pool:
            result=pool.submit(update_blob,ref['key']).result(timeout=10)
        assert result==('BLOCKED','55P03')
        restart.verify_bundle(root)
        return root

    pg.mutate_json(key,checked_mutation)
    assert raw_get(pg,key)==original_root
    # Committing the root releases its payload row locks. A new hydrated root
    # must fetch and reject corruption rather than reuse another root's cache.
    assert update_blob(observed[0],corrupt=True)==('UPDATED',1)
    with pytest.raises(ValueError):
        restart.verify_bundle(pg.read_json(key))
    assert raw_get(pg,key)==original_root
