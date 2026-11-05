from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest
from services import restart_read_reuse as reuse, production_restart as control
from services import restart_io_metrics as io


class Versioned:
    def __init__(self):
        self.revision = 1
        self.pointer = {'family': 'paper', 'period_id': 'p', 'deployment_id': 'test'}
    def using_postgres(self): return True
    def json_row_versions(self, names): return {n: (str(self.revision), '(0,1)') for n in names}
    def read_json(self, name, default=None): return deepcopy(self.pointer)


@pytest.fixture
def example(monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT', 'test')
    monkeypatch.setenv('NOK_DEPLOYMENT_ID', 'test')
    monkeypatch.setattr(control, '_certificate', lambda: None)
    calls = []
    backend = Versioned()
    @reuse.account_read
    def view(family, *, storage=None, chosen=None):
        calls.append(storage.revision)
        return {'cash': storage.revision, 'base_currency': 'NOK', 'positions': {},
                'economic_verification': {'status': 'BESTÅTT'}}
    return backend, calls, view


def test_many_candidates_reuse_detached_account_only_and_external_revision_invalidates(example):
    backend, calls, view = example
    with reuse.scope():
        for _ in range(100):
            result = view('paper', storage=backend)
            result['cash'] = -1
            result['positions']['POISON'] = {}
        assert calls == [1]
        backend.revision = 2  # Includes financial writes, pause and route changes.
        assert view('paper', storage=backend)['cash'] == 2
        assert calls == [1, 2]
    assert view('paper', storage=backend)['cash'] == 2
    assert calls == [1, 2, 2]


def test_explicit_verified_selection_is_never_cached(example):
    backend, calls, view = example
    with reuse.scope():
        for _ in range(3): view('paper', storage=backend, chosen={'fresh': True})
    assert calls == [1, 1, 1]


def test_storage_failure_cannot_return_cached_balance(example, monkeypatch):
    backend, calls, view = example
    with reuse.scope():
        view('paper', storage=backend)
        def failed(*a): raise ConnectionError('database offline')
        monkeypatch.setattr(backend, 'json_row_versions', failed)
        with pytest.raises(ConnectionError): view('paper', storage=backend)
    assert calls == [1]


def test_replaced_certificate_cannot_return_cached_balance(example, monkeypatch):
    backend, calls, view = example
    with reuse.scope():
        view('paper', storage=backend)
        def failed(): raise ValueError('Operator certificate fingerprint mismatch')
        monkeypatch.setattr(control, '_certificate', failed)
        with pytest.raises(ValueError, match='fingerprint'): view('paper', storage=backend)


def test_concurrent_read_is_discarded(example, monkeypatch):
    backend, calls, view = example
    original = backend.json_row_versions
    def versions(names):
        if calls: backend.revision += 1
        return original(names)
    monkeypatch.setattr(backend, 'json_row_versions', versions)
    with reuse.scope(), pytest.raises(ValueError, match='Concurrent'):
        view('paper', storage=backend)


def test_cache_never_crosses_existing_valuation_deadline(example, monkeypatch):
    backend, calls, _ = example
    now = datetime.now(timezone.utc)
    value = {'base_currency': 'NOK', 'economic_verification': {'status': 'BESTÅTT'},
             'positions': {'TEST': {'currency': 'NOK', 'price_observed_at': (now-timedelta(days=5)+timedelta(seconds=1)).isoformat()}}}
    @reuse.account_read
    def view(family, *, storage=None, chosen=None):
        calls.append(1)
        return deepcopy(value)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return now + timedelta(seconds=2)
    with reuse.scope():
        view('paper', storage=backend)
        monkeypatch.setattr(reuse, 'datetime', Clock)
        view('paper', storage=backend)
    assert calls == [1, 1]


def test_unknown_nav_and_oversize_views_are_not_reused(example, monkeypatch):
    backend, calls, view = example
    monkeypatch.setattr(reuse, 'MAX_BYTES', 1)
    with reuse.scope():
        for _ in range(2): view('paper', storage=backend)
    assert calls == [1, 1]
    assert reuse._valuation_deadline({'economic_verification': {'status': 'IKKE VERIFISERT'}}) is None


def test_full_decode_counter_includes_aborted_locked_transform(tmp_path):
    from services.storage_service import StorageService
    backend = StorageService(tmp_path, mode='local')
    key = 'simulation_restarts/p/bundle.json'
    backend.write_json(key, {'historical': 'ø'*100000})
    io.reset()
    backend.read_json(key)
    def abort(doc): raise ValueError('rollback')
    with pytest.raises(ValueError): backend.mutate_json(key, abort)
    counts = io.snapshot()
    assert counts['total_full_loads'] == 2
    assert {row['kind'] for row in counts['documents']} == {'read', 'locked_mutation'}
    assert all(row['bytes'] == (tmp_path/key).stat().st_size for row in counts['documents'])
    assert backend.read_json(key) == {'historical': 'ø'*100000}


@pytest.mark.parametrize('pointer', [{}, {'status': 'PAUSED'}, {'deployment_id': 'FOREIGN'}, {'grant_sha256': 'INVALID'}])
def test_legacy_write_prohibition_needs_only_route_and_fails_closed(pointer, monkeypatch):
    from services import production_routing
    monkeypatch.setenv('APP_ENVIRONMENT', 'test')
    class Storage:
        def read_json(self, key, default=None):
            assert key == control.route_key('paper'), 'legacy guard must not load full bundle'
            return deepcopy(pointer)
    monkeypatch.setattr(control, 'get_storage_service', lambda: Storage())
    with pytest.raises(ValueError, match='legacy balance writes are forbidden'):
        production_routing.guard_legacy_write('paper')


def test_legacy_write_prohibition_does_not_authorize_missing_or_unreadable_route(monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT', 'test')
    class Storage:
        def read_json(self, key, default=None): return None
    assert control.has_selection('paper', storage=Storage()) is False
    class Failed:
        def read_json(self, *args): raise ConnectionError('database offline')
    with pytest.raises(ConnectionError): control.has_selection('paper', storage=Failed())
