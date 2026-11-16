"""Archive readers/writers keep lazy history inside the root transaction."""
import json
import sys
import pytest
from types import SimpleNamespace

from services import storage_service as storage
from services import large_json_write as transport


V2 = 'ARCHIVED_EVENT_PAYLOADS_V2'
PREFIX = '{"__restart_storage__":"' + V2 + '"'
KEY = 'simulation_restarts/archive-test/bundle.json'


class Cursor:
    def __init__(self, previous=None):
        self.previous = previous
        self.queries = []
        self.copied = b''
    def execute(self, query, args=None):
        self.queries.append((query, args))
    def fetchone(self):
        return (self.previous,) if self.previous is not None else None
    def copy_expert(self, query, stream):
        self.copied = b''.join(iter(lambda: stream.read(97), b''))


def archive_stub(monkeypatch, **overrides):
    values = dict(MARKER=V2, PREFIX=PREFIX, is_archived=lambda value: False)
    values.update(overrides)
    monkeypatch.setitem(sys.modules, 'services.restart_payload_archive', SimpleNamespace(**values))


def test_v2_decode_receives_storage_and_locked_connection(monkeypatch):
    owner, connection, loader = object(), object(), object()
    calls = []
    archive_stub(monkeypatch, make_loader=lambda *a, **kw: calls.append((a, kw)) or loader)
    monkeypatch.setattr(storage, 'decode_document', lambda value, **kw: (value, kw))
    document = {'__restart_storage__': V2, 'data': 'encoded'}
    result = storage._load_json_document(KEY, json.dumps(document), storage=owner, connection=connection)
    assert calls == [((owner,), {'connection': connection})]
    assert result == (document, {'payload_loader': loader})


def test_existing_v2_remains_archived_without_rollout_flags(monkeypatch):
    monkeypatch.delenv('RESTART_BUNDLE_COMPRESSION_ENABLED', raising=False)
    value, calls = {'cash': 1000}, []
    archive_stub(monkeypatch, encode_document=lambda *args: calls.append(args) or ('{"archive":true}', 13))
    cur = Cursor(PREFIX)
    transport.write_restart_payload(cur, KEY, value)
    assert calls == [(cur, KEY, value)]
    assert b'{"archive":true}' in cur.copied


def test_lazy_payload_never_materializes_before_archive_encoder(monkeypatch):
    calls = []
    class LazyDocument(dict):
        def items(self):
            raise AssertionError('Root serialized before archive encoder')
    value = LazyDocument(cash=1000)
    archive_stub(monkeypatch, is_archived=lambda data: data is value,
                 encode_document=lambda *args: calls.append(args) or ('{"archive":true}', 13))
    cur = Cursor()
    transport.write_restart_payload(cur, KEY, value)
    assert calls == [(cur, KEY, value)]


def test_immutable_existing_root_does_not_create_orphan_archives(monkeypatch):
    archive_stub(monkeypatch, encode_document=lambda *args: (_ for _ in ()).throw(AssertionError('must not archive conflicting immutable input')))
    cur = Cursor(PREFIX)
    transport.write_restart_payload(cur, KEY, {'conflict': True}, immutable=True)
    assert cur.copied == b''


@pytest.mark.parametrize('method', ['write_json', 'write_json_immutable', 'mutate_json'])
def test_public_root_writes_do_not_serialize_lazy_history_before_locked_transport(tmp_path, monkeypatch, method):
    value = {'accounts': {}}
    calls = []
    class Connection:
        def cursor(self): return cur
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass
    class RootCursor(Cursor):
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def fetchone(self): return ('{"accounts":{}}',)
    cur = RootCursor()
    owner = storage.StorageService(tmp_path, mode='postgres', allow_local_fallback=False)
    monkeypatch.setattr(owner, 'using_postgres', lambda: True)
    monkeypatch.setattr(owner, 'init_db', lambda: None)
    monkeypatch.setattr(owner, '_conn', Connection)
    monkeypatch.setattr(transport, 'write_restart_payload', lambda cursor, name, data, **kw: calls.append((cursor, name, data, kw)))
    def fail_serialization(*args, **kwargs):
        raise AssertionError('Premature whole-root JSON serialization')
    monkeypatch.setattr(storage, 'json', SimpleNamespace(loads=json.loads, dumps=fail_serialization))
    if method == 'mutate_json':
        owner.mutate_json(KEY, lambda doc: value)
    else:
        getattr(owner, method)(KEY, value)
    assert len(calls) == 1
    assert calls[0][:3] == (cur, KEY, value)
