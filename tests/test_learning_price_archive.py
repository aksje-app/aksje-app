"""Archived input must never become a failed/insufficient learning result."""
import hashlib
import json

import pytest

from services.storage_service import StorageService


TICKER = 'ARCHIVE.OL'
LEAF = hashlib.sha256(TICKER.encode()).hexdigest() + '.json'
KEY = 'strategy_history/prices/' + LEAF
RAW = json.dumps({'ticker': TICKER, 'bars': [{'date': '2026-01-01', 'close': 100}], 'source': 'original'})


def reference():
    return {'__learning_price_archive__': 'VERIFIED_PC_BACKUP_V1',
            'backup_file': '2026-11-17T16_06Z.dir.tar.gz', 'backup_sha256': 'a' * 64,
            'source_key': KEY, 'source_sha256': hashlib.sha256(RAW.encode()).hexdigest(),
            'source_bytes': len(RAW.encode()), 'manifest_sha256': 'b' * 64,
            'method_version': '2-entry-day-stop-nonoverlapping-capital'}


@pytest.fixture
def store(tmp_path):
    return StorageService(tmp_path, mode='local', allow_local_fallback=True)


def test_archived_input_is_an_explicit_recovery_request(store):
    from services.learning_price_archive import read_price, ArchivedPriceRequired
    store.write_json(KEY, reference())
    with pytest.raises(ArchivedPriceRequired) as error:
        read_price(store, KEY)
    assert error.value.detail['backup_file'] == '2026-11-17T16_06Z.dir.tar.gz'
    assert store.read_json(KEY) == reference()


def test_unknown_or_malformed_reference_does_not_become_empty_prices(store):
    from services.learning_price_archive import read_price, ArchivedPriceRequired
    store.write_json(KEY, {**reference(), 'backup_sha256': 'not-a-hash'})
    with pytest.raises(ArchivedPriceRequired):
        read_price(store, KEY)


def test_collection_cannot_overwrite_an_archive_reference(store):
    from services.learning_price_archive import write_price, ArchivedPriceRequired
    store.write_json(KEY, reference())
    with pytest.raises(ArchivedPriceRequired):
        write_price(store, KEY, {'ticker': TICKER, 'bars': [{'close': 999}]})
    assert store.read_json(KEY) == reference()


def test_exact_restore_rejects_changed_bytes_and_restores_the_original(store):
    from services.learning_price_archive import restore_price, read_price
    store.write_json(KEY, reference())
    with pytest.raises(ValueError):
        restore_price(store, KEY, RAW.replace('100', '999'))
    assert store.read_json(KEY) == reference()
    restore_price(store, KEY, RAW)
    assert read_price(store, KEY) == json.loads(RAW)
    restore_price(store, KEY, RAW)  # exact replay is harmless
    assert read_price(store, KEY) == json.loads(RAW)


def test_optimizer_waits_without_rejecting_or_overwriting_results(store, monkeypatch):
    import portfolio_history_optimizer as optimizer
    store.write_json('strategy_history/progress.json', {'completed_tickers': [TICKER]})
    store.write_json('strategy_history/optimization_progress.json',
                     {'method_version': 'previous-method', 'completed_tickers': [TICKER]})
    store.write_json(KEY, reference())
    result_key = 'strategy_history/optimized/AUTONOMY/' + LEAF
    original_result = {'status': 'COMPLETE_RESEARCH', 'method_version': 'previous-method', 'evidence': 'keep'}
    store.write_json(result_key, original_result)
    monkeypatch.setattr(optimizer, 'get_storage_service', lambda: store)
    monkeypatch.setattr(optimizer, 'optimize', lambda *a, **k: pytest.fail('Archived data must not be optimized'))
    result = optimizer.run_once()
    assert result['status'] == 'WAITING_ARCHIVE'
    assert result['processed'] == result['failed'] == 0
    assert store.read_json('strategy_history/optimization_progress.json')['rejected_tickers'] == []
    assert store.read_json(result_key) == original_result
    assert store.read_json(KEY) == reference()


def test_collection_waits_before_fetching_replacement_history(store, monkeypatch):
    import strategy_history_worker as worker
    store.write_json('strategy_history/universe.json', {'symbols': [TICKER]})
    store.write_json(KEY, reference())
    monkeypatch.setattr(worker, 'get_storage_service', lambda: store)
    monkeypatch.setattr(store, 'storage_usage_report', lambda: {'database_bytes': 1, 'capacity_bytes': 100})
    monkeypatch.setattr(worker, 'load_price_series_bounded', lambda *a, **k: pytest.fail('Do not refetch archived history'))
    result = worker.run_once()
    assert result['status'] == 'WAITING_ARCHIVE'
    assert TICKER not in result.get('rejected_tickers', [])
    assert store.read_json(KEY) == reference()


def test_disabled_scheduler_does_not_open_storage(monkeypatch):
    from services import learning_price_archive_batch as batch
    monkeypatch.delenv(batch.ENABLED_FLAG, raising=False)
    monkeypatch.setattr(batch, 'get_storage_service', lambda: pytest.fail('Disabled archive must not access storage'))
    assert batch.run_scheduled_archive()['state'] == 'DISABLED'


def test_collection_recovery_request_is_visible_in_progress(store):
    from strategy_history_progress_view import snapshot
    store.write_json('strategy_history/progress.json',
                     {'status': 'WAITING_ARCHIVE', 'archive_required': {'backup_file': 'original.dir.tar.gz'}})
    assert snapshot(store)['archive_required']['backup_file'] == 'original.dir.tar.gz'


def test_production_authorization_is_checksum_pinned(monkeypatch):
    from services import learning_price_archive_batch as batch
    manifest = batch.load_authorized_manifest()
    assert len(manifest['entries']) == 1344
    assert manifest['backup']['sha256'] == 'bcde2be937aa8317a9f26234de01df872acd2bfe3e42567a95de41ed6d495309'
    monkeypatch.setattr(batch, 'MANIFEST_FILE_SHA256', '0' * 64)
    with pytest.raises(ValueError, match='checksum'):
        batch.load_authorized_manifest()
