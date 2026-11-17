"""Native atomic archive/restore against a disposable PostgreSQL schema."""
import hashlib
import json

import pytest

from test_revision_trade_postgres import pg
from portfolio_history_optimizer import METHOD_VERSION


def raw(storage, key):
    conn = storage._conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT payload FROM app_kv_store WHERE name=%s', (key,))
            return cur.fetchone()[0]
    finally:
        conn.close()


def seed(storage, count=2):
    entries = []
    tickers = ['ARCHIVE'+str(i)+'.OL' for i in range(count)]
    for ticker in tickers:
        leaf = hashlib.sha256(ticker.encode()).hexdigest()+'.json'
        key = 'strategy_history/prices/'+leaf
        storage.write_json(key, {'ticker': ticker, 'bars': [{'date': '2026-01-01', 'close': 100}], 'original': 'å'})
        price_raw = raw(storage, key)
        result_hashes = {}
        for engine in ('AUTONOMY', 'SUPER_PORTFOLIO'):
            result_key = 'strategy_history/optimized/'+engine+'/'+leaf
            storage.write_json(result_key, {'ticker': ticker, 'status': 'COMPLETE_RESEARCH', 'method_version': METHOD_VERSION})
            result_hashes[engine] = hashlib.sha256(raw(storage, result_key).encode()).hexdigest()
        entries.append({'key': key, 'sha256': hashlib.sha256(price_raw.encode()).hexdigest(),
                        'bytes': len(price_raw.encode()), 'result_sha256': result_hashes})
    storage.write_json('strategy_history/progress.json', {'completed_tickers': tickers})
    storage.write_json('strategy_history/optimization_progress.json',
                       {'method_version': METHOD_VERSION, 'completed_tickers': tickers, 'aggregated_tickers': tickers})
    storage.write_json('controlled_learning/observation_cohorts.json', [{'status': 'ACTIVE', 'do_not_change': True}])
    storage.write_json('simulation_restarts/current/bundle.json', {'keep': True})
    return {'schema': 1, 'authorization': 'USER_APPROVED_VERIFIED_PC_BACKUP', 'method_version': METHOD_VERSION,
            'backup': {'file': '2026-11-17T16_06Z.dir.tar.gz', 'bytes': 888151608, 'sha256': 'a'*64,
                       'pc_copy_sha256': 'a'*64, 'restore_verification_sha256': 'd'*64, 'restore_verified': True},
            'entries': sorted(entries, key=lambda x: x['key'])}


def test_exact_archive_references_keep_results_and_active_learning(pg):
    from services.learning_price_archive_batch import archive_batch
    from services.learning_price_archive import read_price, ArchivedPriceRequired
    m = seed(pg)
    result_key = m['entries'][0]['key'].replace('/prices/', '/optimized/AUTONOMY/')
    before = raw(pg, result_key)
    result = archive_batch(pg, m, apply=True)
    assert result['state'] == 'COMPLETED' and result['archived_total'] == 2
    with pytest.raises(ArchivedPriceRequired):
        read_price(pg, m['entries'][0]['key'])
    assert raw(pg, result_key) == before
    assert pg.read_json('controlled_learning/observation_cohorts.json') == [{'status': 'ACTIVE', 'do_not_change': True}]
    assert pg.read_json('simulation_restarts/current/bundle.json') == {'keep': True}


@pytest.mark.parametrize('change', ['price', 'result', 'method', 'collection_ledger', 'optimization_ledger'])
def test_changed_evidence_never_archives_a_price(pg, change):
    from services.learning_price_archive_batch import archive_batch
    m = seed(pg, 1); key = m['entries'][0]['key']
    if change == 'price':
        pg.write_json(key, {'new_source': True})
    elif change == 'result':
        pg.write_json(key.replace('/prices/', '/optimized/SUPER_PORTFOLIO/'), {'status': 'RUNNING'})
    elif change == 'method':
        pg.write_json('strategy_history/optimization_progress.json', {'method_version': 'new-method'})
    else:
        control = 'progress.json' if change == 'collection_ledger' else 'optimization_progress.json'
        pg.write_json('strategy_history/'+control, {'method_version': METHOD_VERSION, 'completed_tickers': []})
    before = raw(pg, key)
    result = archive_batch(pg, m, apply=True)
    assert result['archived_total'] == 0
    assert raw(pg, key) == before


def test_dry_run_has_no_price_or_receipt_writes(pg):
    from services.learning_price_archive_batch import archive_batch, RECEIPT_KEY
    m = seed(pg, 1); key = m['entries'][0]['key']; before = raw(pg, key)
    result = archive_batch(pg, m)
    assert result['state'] == 'DRY_RUN' and result['eligible_this_batch'] == 1
    assert raw(pg, key) == before and pg.read_json(RECEIPT_KEY) is None


def test_small_batches_resume_and_a_completed_pass_does_not_rearchive_restored_input(pg):
    from services.learning_price_archive_batch import archive_batch
    from services.learning_price_archive import restore_price
    m = seed(pg); key = m['entries'][0]['key']; original = raw(pg, key)
    first = archive_batch(pg, m, max_items=1, apply=True)
    assert first['state'] == 'PARTIAL' and first['archived_total'] == 1
    final = archive_batch(pg, m, max_items=1, apply=True)
    assert final['state'] == 'COMPLETED' and final['archived_total'] == 2
    assert restore_price(pg, key, original)['state'] == 'RESTORED'
    assert raw(pg, key) == original
    assert restore_price(pg, key, original)['state'] == 'ALREADY_PRESENT'
    archive_batch(pg, m, apply=True)
    assert raw(pg, key) == original


def test_restore_rejects_changed_original_bytes_without_changing_reference(pg):
    from services.learning_price_archive_batch import archive_batch
    from services.learning_price_archive import restore_price
    m = seed(pg, 1); key = m['entries'][0]['key']; original = raw(pg, key)
    archive_batch(pg, m, apply=True); ref = raw(pg, key)
    with pytest.raises(ValueError):
        restore_price(pg, key, original.replace('100', '999'))
    assert raw(pg, key) == ref


def test_database_failure_rolls_back_every_replacement_and_receipt(pg):
    from services.learning_price_archive_batch import archive_batch, RECEIPT_KEY
    m = seed(pg); originals = {e['key']: raw(pg, e['key']) for e in m['entries']}
    conn = pg._conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""CREATE FUNCTION reject_archive_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN IF NEW.name='maintenance/learning_price_archive_20261117.json' THEN
                    RAISE EXCEPTION 'controlled receipt failure'; END IF; RETURN NEW; END $$""")
                cur.execute('CREATE TRIGGER reject_archive BEFORE INSERT OR UPDATE ON app_kv_store FOR EACH ROW EXECUTE FUNCTION reject_archive_receipt()')
    finally:
        conn.close()
    with pytest.raises(Exception, match='controlled receipt failure'):
        archive_batch(pg, m, apply=True)
    assert {k: raw(pg, k) for k in originals} == originals
    assert pg.read_json(RECEIPT_KEY) is None


def test_another_archive_owner_defers_without_mutation(pg):
    from services.learning_price_archive_batch import archive_batch, LOCK_ID
    m = seed(pg, 1); key = m['entries'][0]['key']; before = raw(pg, key)
    conn = pg._conn(); conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_lock(%s)', (LOCK_ID,))
        assert archive_batch(pg, m, apply=True)['state'] == 'DEFERRED_BUSY'
        assert raw(pg, key) == before
    finally:
        conn.close()


def test_manifest_cannot_target_a_portfolio_or_duplicate_key(pg):
    from services.learning_price_archive_batch import archive_batch
    m = seed(pg, 1)
    m['entries'][0]['key'] = 'autonomous_portfolio/state.json'
    with pytest.raises(ValueError):
        archive_batch(pg, m, apply=True)
    m = seed(pg, 1); m['entries'].append(m['entries'][0])
    with pytest.raises(ValueError):
        archive_batch(pg, m, apply=True)


def test_oversized_existing_receipt_cannot_reset_one_time_scope(pg):
    from services.learning_price_archive_batch import archive_batch, RECEIPT_KEY
    m = seed(pg, 1); key = m['entries'][0]['key']; before = raw(pg, key)
    pg.write_json(RECEIPT_KEY, {'untrusted': 'x' * (1024 * 1024 + 1)})
    with pytest.raises(ValueError, match='budget'):
        archive_batch(pg, m, apply=True)
    assert raw(pg, key) == before


def test_caller_cannot_exceed_the_native_batch_cap(pg):
    from services.learning_price_archive_batch import archive_batch
    m = seed(pg, 129)
    first = archive_batch(pg, m, max_items=10000, apply=True)
    assert first['cursor'] == first['archived_total'] == 128
    assert first['state'] == 'PARTIAL'
    final = archive_batch(pg, m, apply=True)
    assert final['archived_total'] == 129 and final['state'] == 'COMPLETED'


def test_a_locked_live_checkpoint_causes_no_replacements(pg):
    from services.learning_price_archive_batch import archive_batch
    m = seed(pg, 1); key = m['entries'][0]['key']; before = raw(pg, key)
    conn = pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM app_kv_store WHERE name='strategy_history/optimization_progress.json' FOR UPDATE")
        import psycopg2
        with pytest.raises(psycopg2.errors.LockNotAvailable):
            archive_batch(pg, m, apply=True)
        assert raw(pg, key) == before
    finally:
        conn.close()


def test_restore_operator_dry_run_then_apply_uses_a_readonly_original_source(pg):
    from services.learning_price_archive_batch import archive_batch
    from tools.restore_learning_prices import restore_selected
    m = seed(pg, 1); key = m['entries'][0]['key']; original = raw(pg, key)
    source = pg._conn(); source.set_session(readonly=True, isolation_level='REPEATABLE READ')
    try:
        # Freeze the genuine original version as a separate read-only recovery source.
        with source.cursor() as cur:
            cur.execute('SELECT payload FROM app_kv_store WHERE name=%s', (key,))
            assert cur.fetchone()[0] == original
        archive_batch(pg, m, apply=True); ref = raw(pg, key)
        assert restore_selected(source, pg, [key])[0]['state'] == 'RESTORE_ELIGIBLE'
        assert raw(pg, key) == ref
        assert restore_selected(source, pg, [key], apply=True)[0]['state'] == 'RESTORED'
        assert raw(pg, key) == original
    finally:
        source.close()


def test_native_restore_dry_run_validates_without_modifying_the_reference(pg):
    from services.learning_price_archive_batch import archive_batch
    from services.learning_price_archive import restore_price
    m = seed(pg, 1); key = m['entries'][0]['key']; original = raw(pg, key)
    archive_batch(pg, m, apply=True); reference = raw(pg, key)
    assert restore_price(pg, key, original, apply=False)['state'] == 'RESTORE_ELIGIBLE'
    assert raw(pg, key) == reference


def test_inconsistent_receipt_cannot_skip_unprocessed_prices(pg):
    from services.learning_price_archive_batch import archive_batch, RECEIPT_KEY
    m = seed(pg)
    progress = archive_batch(pg, m, max_items=1, apply=True)
    second = m['entries'][1]['key']; before = raw(pg, second)
    progress['cursor'] = 2  # one replacement does not prove two checked entries
    pg.write_json(RECEIPT_KEY, progress)
    with pytest.raises(ValueError, match='receipt'):
        archive_batch(pg, m, apply=True)
    assert raw(pg, second) == before


def test_empty_existing_receipt_cannot_rearchive_restored_inputs(pg):
    from services.learning_price_archive_batch import archive_batch, RECEIPT_KEY
    from services.learning_price_archive import restore_price
    m = seed(pg, 1); key = m['entries'][0]['key']; original = raw(pg, key)
    archive_batch(pg, m, apply=True)
    restore_price(pg, key, original)
    pg.write_json(RECEIPT_KEY, {})
    with pytest.raises(ValueError, match='receipt'):
        archive_batch(pg, m, apply=True)
    assert raw(pg, key) == original
    assert pg.read_json(RECEIPT_KEY) == {}
