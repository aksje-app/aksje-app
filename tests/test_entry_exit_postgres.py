"""Real PostgreSQL round trips in the release gate's isolated test database."""
import os
from copy import deepcopy
from datetime import datetime, timezone

import pytest

URL = os.getenv("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL runs in release CI")


def test_postgres_keeps_entry_and_exit_evidence_across_load_and_save(monkeypatch, tmp_path):
    import psycopg2
    import paper_store as ps
    from services.storage_service import StorageService

    connection = psycopg2.connect(URL)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        assert cursor.fetchone()[0] == "entry_exit_test"
    connection.close()
    mirror = StorageService(tmp_path, database_url="", mode="local")
    monkeypatch.setattr(ps, "using_postgres", lambda: True)
    monkeypatch.setattr(ps, "get_conn", lambda: psycopg2.connect(URL))
    monkeypatch.setattr(ps, "_storage", lambda: mirror)
    monkeypatch.setattr(ps, "require_paper_trade", lambda *a, **kw: None)
    evidence = {"current_score": 8.2, "market_data_at": datetime.now(timezone.utc).isoformat(),
                "execution_quote": {"price": 100, "adjustment": "raw"},
                "entry_confirmation": {"samples": [{"run_id": "R1"}, {"run_id": "R2"}]},
                "decision_snapshot": {"score": 8.2, "signal": "BUY"}}
    position = {"ticker": "FIXTURE", "shares": 10, "entry_price": 100, "last_price": 100,
                "entry_score": 8.2, "opened_at": datetime.now(timezone.utc).isoformat(), **evidence}
    portfolio = {"cash": 9000, "positions": {"FIXTURE": position}, "trades": []}
    ps.save_portfolio(portfolio)
    ps.add_trade(portfolio, {"trade_id": "PG-ENTRY", "type": "BUY", "ticker": "FIXTURE",
                            "price": 100, "shares": 10, "amount": 1000, "confidence": 80,
                            "entry_score": 8.2, **evidence})
    loaded = ps.load_portfolio()
    assert loaded["positions"]["FIXTURE"]["decision_snapshot"] == evidence["decision_snapshot"]
    assert loaded["positions"]["FIXTURE"]["entry_confirmation"] == evidence["entry_confirmation"]
    assert loaded["trades"][0]["execution_quote"] == evidence["execution_quote"]
    # A read must not rewrite the mirror or strip evidence from it.
    before = deepcopy(mirror.read_json(ps.STORAGE_KEY))
    ps.load_portfolio()
    assert mirror.read_json(ps.STORAGE_KEY) == before
    ps.save_portfolio(loaded)
    loaded["positions"] = {}
    loaded["cash"] = 9940
    ps.add_trade(loaded, {"trade_id": "PG-EXIT", "type": "SELL", "ticker": "FIXTURE",
                         "price": 94, "shares": 10, "amount": 940, "entry_score": 8.2,
                         "exit_score": None, "stop_trigger_price": 97,
                         "execution_gap_pct": -3.09, "holding_minutes": 58})
    exited = ps.load_portfolio()
    assert not exited["positions"]
    assert exited["trades"][0]["holding_minutes"] == 58
    assert exited["trades"][0]["stop_trigger_price"] == 97
    assert exited["trades"][0]["exit_score"] is None


def test_identical_document_write_does_not_rewrite_database_row():
    import psycopg2
    from services.storage_service import StorageService
    storage = StorageService(database_url=URL, mode="postgres")
    key = "test/unchanged_write.json"
    storage.write_json(key, {"evidence": "same"})
    with psycopg2.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT updated_at, xmin::text FROM app_kv_store WHERE name=%s", (key,))
            before = cur.fetchone()
    storage.write_json(key, {"evidence": "same"})
    with psycopg2.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT updated_at, xmin::text FROM app_kv_store WHERE name=%s", (key,))
            assert cur.fetchone() == before


def test_postgres_experiment_archive_concurrent_captures_and_resume(monkeypatch, tmp_path):
    import psycopg2
    from concurrent.futures import ThreadPoolExecutor
    import learning_runtime as lr
    from services.storage_service import StorageService
    conn = psycopg2.connect(URL)
    with conn.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        assert cursor.fetchone()[0] == 'entry_exit_test'
        cursor.execute("DELETE FROM app_kv_store WHERE name LIKE 'controlled_learning/%'")
    conn.commit(); conn.close()
    service = StorageService(tmp_path, database_url=URL, mode='postgres', allow_local_fallback=False)
    service.init_db()
    monkeypatch.setattr(lr, 'storage', lambda: service)
    def capture(i):
        return lr.archive({'engine': 'AUTONOMY', 'run_id': f'PG-{i}',
            'at': f'2025-01-{6+i:02d}T12:00:00+00:00', 'config': {'initial_cash': 10000}, 'candidates': []})
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(capture, range(6)))
    index = service.read_json(lr.INDEX)
    assert len(index['records']) == 6
    assert all(r['status'] == 'READY' for r in index['records'])
    assert index['bytes'] == sum(r['bytes'] for r in index['records'])
    assert capture(0) == results[0]
    # A fresh adapter reproduces the persisted, checksummed archive.
    reloaded = StorageService(tmp_path / 'restart', database_url=URL, mode='postgres', allow_local_fallback=False)
    monkeypatch.setattr(lr, 'storage', lambda: reloaded)
    assert lr.load_frame(index['records'][0])['candidates'] == []
    conn = psycopg2.connect(URL)
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM app_kv_store WHERE name LIKE 'controlled_learning/%'")
    conn.commit(); conn.close()
