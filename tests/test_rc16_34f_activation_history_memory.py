import json
import tracemalloc
from concurrent.futures import ThreadPoolExecutor

import pytest

from repositories.application import ActivationAnalysisRepository, RepositoryRegistry
from services.autonomy_activation_service import AutonomyActivationService
from services.storage_service import StorageService, StorageUnavailableError


def storage(tmp_path):
    return StorageService(tmp_path, database_url='', mode='local')


def analysis(number, **extra):
    return {'analysis_id': f'A{number}', 'created_at': f'2026-10-08T{number:04d}', **extra}


def test_legacy_history_is_preserved_and_merged_across_pages(tmp_path, monkeypatch):
    st = storage(tmp_path)
    repo = ActivationAnalysisRepository(st)
    st.write_json(repo.key, [analysis(i) for i in range(70)])  # deliberately unsorted
    before = (tmp_path / repo.key).read_bytes()
    original_read = st.read_json
    def guarded_read(key, default=None):
        assert key != repo.key, 'Full legacy collection must never be read'
        return original_read(key, default)
    monkeypatch.setattr(st, 'read_json', guarded_read)
    repo.upsert(analysis(80))
    repo.upsert(analysis(30, recommendation='updated'))  # shadows legacy ID
    repo.upsert(analysis(75))
    service = AutonomyActivationService(RepositoryRegistry(st))
    assert service.latest()['analysis_id'] == 'A80'
    pages = [service.history(limit=17, offset=offset) for offset in range(0, 85, 17)]
    rows = [row for page in pages for row in page]
    assert [row['analysis_id'] for row in rows] == ['A80', 'A75'] + [f'A{i}' for i in range(69, -1, -1)]
    assert repo.get('A30')['recommendation'] == 'updated'
    assert repo.get('A5') == analysis(5)
    assert (tmp_path / repo.key).read_bytes() == before
    assert len(ActivationAnalysisRepository(storage(tmp_path)).list()) == 72
    assert repo.list(limit=0) == []
    assert service.history(limit=-1) == []


def test_concurrent_saves_keep_all_ids_in_index(tmp_path):
    st = storage(tmp_path)
    repo = ActivationAnalysisRepository(st)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(repo.upsert, [analysis(i) for i in range(30)]))
    assert len(repo._index()) == 30
    assert [row['analysis_id'] for row in repo.list(limit=3)] == ['A29', 'A28', 'A27']


def test_index_write_failure_is_reported_and_legacy_is_untouched(tmp_path, monkeypatch):
    st = storage(tmp_path)
    repo = ActivationAnalysisRepository(st)
    st.write_json(repo.key, [analysis(1)])
    before = (tmp_path / repo.key).read_bytes()
    def unavailable(*args, **kwargs):
        raise StorageUnavailableError('database unavailable')
    monkeypatch.setattr(st, 'mutate_json', unavailable)
    with pytest.raises(StorageUnavailableError):
        repo.upsert(analysis(2))
    assert (tmp_path / repo.key).read_bytes() == before


def test_large_legacy_latest_has_bounded_python_memory(tmp_path):
    st = storage(tmp_path)
    repo = ActivationAnalysisRepository(st)
    path = tmp_path / repo.key
    path.parent.mkdir(parents=True, exist_ok=True)
    # 40 MiB history. Track allocations only during the actual read.
    with path.open('w') as handle:
        handle.write('[')
        for i in range(80):
            if i:
                handle.write(',')
            json.dump(analysis(i, details='x' * (512 * 1024)), handle)
        handle.write(']')
    tracemalloc.start()
    try:
        latest = repo.list(limit=1)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert latest[0]['analysis_id'] == 'A79'
    assert peak < 6 * 1024 * 1024, f'Unexpected full-history allocation: {peak}'


def test_local_streaming_handles_chunk_boundaries_unicode_and_lookup(tmp_path):
    st = storage(tmp_path)
    rows = [analysis(1, text='æøå' * 50000), analysis(2, text='small')]
    st.write_json('array.json', rows)
    assert st.read_json_array_page('array.json', limit=1, offset=1) == [rows[0]]
    assert st.read_json_array_item('array.json', 'analysis_id', 'A2') == rows[1]
    assert st.read_json_array_page('array.json', exclude_ids=['A2']) == [rows[0]]


class Cursor:
    def __init__(self):
        self.query = ''
        self.params = None
    def execute(self, query, params):
        self.query, self.params = query, params
    def fetchall(self):
        return [(json.dumps(analysis(2)),)]


class Connection:
    def __init__(self, cursor):
        self.cur = cursor
        self.closed = False
    def cursor(self):
        return self.cur
    def close(self):
        self.closed = True


def test_postgres_page_binds_filters_and_limits_transfer(tmp_path, monkeypatch):
    st = storage(tmp_path)
    cur = Cursor()
    conn = Connection(cur)
    monkeypatch.setattr(st, 'using_postgres', lambda: True)
    monkeypatch.setattr(st, 'init_db', lambda: None)
    monkeypatch.setattr(st, '_conn', lambda: conn)
    assert st.read_json_array_page('array.json', limit=1, offset=8, exclude_ids=['A1']) == [analysis(2)]
    assert 'LIMIT %s OFFSET %s' in cur.query
    assert 'elem::text' in cur.query
    assert cur.params == ('array.json', 'analysis_id', ['A1'], 'created_at', 1, 8)
    assert conn.closed


def test_postgres_failure_never_reads_local_history(tmp_path, monkeypatch):
    st = StorageService(tmp_path, database_url='', mode='postgres', allow_local_fallback=False)
    monkeypatch.setattr(st, 'using_postgres', lambda: True)
    monkeypatch.setattr(st, 'init_db', lambda: None)
    def fail():
        raise RuntimeError('DB down')
    monkeypatch.setattr(st, '_conn', fail)
    with pytest.raises(StorageUnavailableError):
        st.read_json_array_page('array.json')
