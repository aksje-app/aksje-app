"""Real transactions, rollback and concurrent retry against isolated local PG."""
from concurrent.futures import ThreadPoolExecutor
import os
from urllib.parse import urlsplit, urlunsplit, urlencode, parse_qsl
import uuid

import pytest

from services import super_portfolio_store as journal
from services.storage_service import StorageService


@pytest.fixture
def pg(tmp_path):
    url = os.getenv("TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("Requires the release gate's isolated PostgreSQL")
    assert urlsplit(url).hostname in {"localhost", "127.0.0.1"}, "Never run this fixture against production"
    import psycopg2
    from psycopg2 import sql
    schema = "audit_" + uuid.uuid4().hex
    admin = psycopg2.connect(url)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["options"] = "-csearch_path=" + schema
    scoped = urlunsplit(parts._replace(query=urlencode(query)))
    storage = StorageService(tmp_path, database_url=scoped, mode="postgres", allow_local_fallback=False)
    storage.init_db()
    try:
        yield storage
    finally:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def test_pg_retry_survives_new_process_and_duplicate_operations(pg):
    state = {"portfolio_value": 1000, "cash": 1000, "positions": {}}
    row = {"trade_id": "DNO-SELL", "ticker": "DNO.OL", "action": "SELL"}
    operation = "job:SPJ-20261021-131559-9C8E27"
    journal.commit(state, operation_id=operation, trades=[row], storage=pg)
    restarted = StorageService(pg.base_dir, database_url=pg.database_url, mode="postgres", allow_local_fallback=False)
    journal.commit(state, operation_id=operation, trades=[row], storage=restarted)
    assert journal.transactions(restarted) == [row]
    assert journal.receipt(operation, restarted)["changes"] == [row]
    assert journal.audit_snapshot(restarted)[0]["_revision"] == 1


def test_pg_failure_after_state_write_rolls_back_state_and_ledger(pg):
    before = journal.commit({"cash": 1000, "positions": {}}, storage=pg)
    conn = pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE FUNCTION reject_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                  IF NEW.name LIKE 'super_portfolio/commits/%' THEN
                    RAISE EXCEPTION 'injected receipt failure after state and trades';
                  END IF;
                  RETURN NEW;
                END $$""")
            cur.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON app_kv_store FOR EACH ROW EXECUTE FUNCTION reject_receipt()")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(Exception, match="injected receipt failure"):
        journal.commit({**before, "cash": 500}, operation_id="failure", trades=[{"trade_id": "must-not-exist"}], storage=pg)
    assert pg.read_json(journal.STATE_KEY) == before
    assert journal.transactions(pg) == []
    assert journal.receipt("failure", pg) is None


def test_pg_concurrent_same_job_can_only_commit_one_trade(pg):
    state = {"cash": 1000, "positions": {}}
    def attempt(_):
        return journal.commit(state, operation_id="same-job", trades=[{"trade_id": "one"}], storage=pg)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert all(r["_revision"] == 1 for r in results)
    assert journal.transactions(pg) == [{"trade_id": "one"}]


def test_pg_concurrent_different_decisions_do_not_overwrite_each_other(pg):
    state = {"cash": 1000, "positions": {}}
    def attempt(index):
        try:
            journal.commit(state, operation_id=str(index), trades=[{"trade_id": str(index)}], storage=pg)
            return "committed"
        except journal.PortfolioConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results) == ["committed", "conflict"]
    assert len(journal.transactions(pg)) == 1
