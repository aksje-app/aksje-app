"""The libpq result must not overlap the decoded large JSON object graph."""
import json
from types import SimpleNamespace
from services import storage_service as module


def test_json_result_buffer_is_released_before_decode(tmp_path, monkeypatch):
    raw = json.dumps({'history': ['ø', 1.25, -0.0, {'preserved': True}]})
    events = []
    class Cursor:
        sql = ''
        def __enter__(self): return self
        def __exit__(self, *args): events.append('cursor_closed')
        def execute(self, sql, params): self.sql = sql
        def fetchone(self): return (len(raw.encode()),) if 'octet_length' in self.sql else (raw,)
    class Connection:
        def cursor(self): return Cursor()
        def close(self): events.append('connection_closed')
    backend = module.StorageService(tmp_path, mode='postgres', allow_local_fallback=False)
    monkeypatch.setattr(backend, 'using_postgres', lambda: True)
    monkeypatch.setattr(backend, 'init_db', lambda: None)
    monkeypatch.setattr(backend, '_conn', Connection)
    def decode(value):
        assert events == ['cursor_closed', 'connection_closed']
        events.append('decode')
        return json.loads(value)
    monkeypatch.setattr(module, 'json', SimpleNamespace(loads=decode))
    assert backend.read_json('simulation_restarts/p/bundle.json') == json.loads(raw)
    assert events == ['cursor_closed', 'connection_closed', 'decode']
