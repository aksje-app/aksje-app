from contextlib import closing
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from repositories.application import RepositoryRegistry
from services import autonomy_nok_companion
from services.market_snapshot_service import MarketSnapshotService
from services.parallel_strategy_service import ParallelStrategyService
from services.storage_references import FIELDS, reference_info, version_key
from services.strategy_registry_service import StrategyRegistryService
from test_revision_trade_postgres import pg
from test_v1970_parallel_strategy_interface import _snapshot


def _evaluation(storage):
    repositories = RepositoryRegistry(storage)
    registry = StrategyRegistryService(repositories)
    registry.ensure_defaults()
    snapshots = MarketSnapshotService(repositories)
    snapshot = _snapshot(snapshots)
    snapshots.save(snapshot)
    return repositories, ParallelStrategyService(repositories, registry), snapshot


def _raw_document(storage, key):
    with closing(storage._conn()) as connection, connection.cursor() as cur:
        cur.execute("SELECT payload FROM app_kv_store WHERE name=%s", (key,))
        return json.loads(cur.fetchone()[0])


def test_evaluation_stores_ordered_versions_and_updates_decision_index_once(pg, monkeypatch):
    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    repositories, parallel, snapshot = _evaluation(pg)
    with closing(pg._conn()) as connection, connection, connection.cursor() as cur:
        cur.execute("""CREATE TABLE decision_index_writes (name text);
            CREATE FUNCTION count_decision_index_writes() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.name = 'repositories/strategy_decisions_index.json' THEN
                INSERT INTO decision_index_writes VALUES (NEW.name);
              END IF;
              RETURN NEW;
            END $$;
            CREATE TRIGGER count_decision_index_writes AFTER INSERT OR UPDATE ON app_kv_store
            FOR EACH ROW EXECUTE FUNCTION count_decision_index_writes();""")

    run = parallel.evaluate_snapshot(snapshot, families=["technical"])
    decisions = run["decisions"]
    assert len(decisions) == 2
    with closing(pg._conn()) as connection, connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM decision_index_writes")
        assert cur.fetchone()[0] == 1
    assert repositories.strategy_decisions.list() == decisions[::-1]
    assert repositories.strategy_runs.list() == [run]

    run_key = repositories.strategy_runs._item_key(run["strategy_run_id"])
    assert reference_info(_raw_document(pg, run_key))[0] == version_key(run)
    stored_run = _raw_document(pg, version_key(run))
    assert [reference_info(ref)[0] for ref in stored_run[FIELDS]["fields"]["decisions"]] == [
        version_key(decision) for decision in decisions
    ]
    first = decisions[0]
    decision_key = repositories.strategy_decisions._item_key(first["decision_id"])
    assert reference_info(_raw_document(pg, decision_key))[0] == version_key(first)

    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED")
    changed = {**first, "score": 1.0}
    assert repositories.strategy_decisions.upsert(changed)
    assert repositories.strategy_decisions.get(first["decision_id"]) == changed
    assert repositories.strategy_runs.get(run["strategy_run_id"]) == run


def test_failed_run_publication_leaves_no_decisions_or_index(pg, monkeypatch):
    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    repositories, parallel, snapshot = _evaluation(pg)
    with closing(pg._conn()) as connection, connection, connection.cursor() as cur:
        cur.execute("""CREATE FUNCTION reject_strategy_run() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.name LIKE 'repositories/strategy_runs/items/%' THEN
                RAISE EXCEPTION 'injected strategy run publication failure';
              END IF;
              RETURN NEW;
            END $$;
            CREATE TRIGGER reject_strategy_run BEFORE INSERT OR UPDATE ON app_kv_store
            FOR EACH ROW EXECUTE FUNCTION reject_strategy_run();""")

    with pytest.raises(Exception) as failure:
        parallel.evaluate_snapshot(snapshot, families=["technical"])
    assert "injected strategy run publication failure" in str(failure.value.__cause__ or failure.value)
    assert repositories.strategy_decisions.list() == []
    assert repositories.strategy_runs.list() == []
    with closing(pg._conn()) as connection, connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM app_kv_store WHERE name LIKE 'repositories/strategy_decisions/items/%'")
        assert cur.fetchone()[0] == 0


def test_disabled_writer_publishes_inline_evaluation_as_one_transaction(pg, monkeypatch):
    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED", raising=False)
    repositories, parallel, snapshot = _evaluation(pg)
    with pg._conn() as connection, connection.cursor() as cur:
        cur.execute("""CREATE FUNCTION reject_inline_run() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.name LIKE 'repositories/strategy_runs/items/%' THEN
                RAISE EXCEPTION 'reject incomplete inline run';
              END IF;
              RETURN NEW;
            END $$;
            CREATE TRIGGER reject_inline_run BEFORE INSERT ON app_kv_store
            FOR EACH ROW EXECUTE FUNCTION reject_inline_run();""")

    with pytest.raises(Exception) as failure:
        parallel.evaluate_snapshot(snapshot, families=["technical"])
    assert "reject incomplete inline run" in str(failure.value.__cause__ or failure.value)
    assert repositories.strategy_decisions.list() == []
    assert repositories.strategy_runs.list() == []


def test_concurrent_plain_and_shared_writers_keep_both_index_entries(pg, monkeypatch):
    from services import storage_references
    from services.storage_service import StorageService

    other = StorageService(pg.base_dir, database_url=pg.database_url, mode="postgres", allow_local_fallback=False)
    other.init_db()
    monkeypatch.setattr(storage_references, "references_enabled", lambda storage: storage is pg)

    def publish(storage, run_id):
        repositories = RepositoryRegistry(storage)
        row = {"strategy_run_id": run_id, "run_id": run_id, "decisions": [{"decision_id": f"decision-{run_id}"}]}
        return repositories.strategy_runs.publish_evaluation(row, repositories.strategy_decisions)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(publish, pg, "shared")
        second = pool.submit(publish, other, "plain")
        assert first.result() and second.result()
    repositories = RepositoryRegistry(pg)
    assert {row["strategy_run_id"] for row in repositories.strategy_runs.list()} == {"shared", "plain"}
    assert {row["decision_id"] for row in repositories.strategy_decisions.list()} == {"decision-shared", "decision-plain"}


def test_nok_preparation_reuses_exact_persisted_versions_across_retry(pg, monkeypatch):
    import autonomous_portfolio as ap

    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    repositories, parallel, snapshot = _evaluation(pg)
    run = parallel.evaluate_snapshot(snapshot, families=["technical"])
    snapshot_row = snapshot.to_dict()
    candidates = [{"ticker": "EQNR.OL"}]
    portfolio = {"cash": 1000, "positions": {}}
    chosen = {"pointer": {"period_id": "test-period"}, "approval": {"settings": {}}}
    monkeypatch.setattr(ap, "prepare_cycle_candidates", lambda *_: (candidates, snapshot_row, run, {}))

    prepared = autonomy_nok_companion.prepare(chosen, "test-run", candidates, storage=pg, portfolio=portfolio)
    assert prepared["market_snapshot"] == snapshot_row
    assert prepared["parallel_strategy_run"] == run
    key = autonomy_nok_companion.preparation_key(chosen, "test-run")
    stored = _raw_document(pg, key)
    fields = stored[FIELDS]["fields"]
    assert reference_info(fields["market_snapshot"])[0] == repositories.market_snapshots._item_key(snapshot.snapshot_id)
    assert reference_info(fields["parallel_strategy_run"])[0] == version_key(run)
    assert len(json.dumps(stored)) < len(json.dumps(prepared))

    changed_run = {**run, "error_count": 1}
    assert repositories.strategy_runs.upsert(changed_run)
    assert repositories.strategy_runs.get(run["strategy_run_id"]) == changed_run
    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED")
    assert autonomy_nok_companion.prepare(chosen, "test-run", candidates, storage=pg) == prepared
    assert _raw_document(pg, key) == stored
    with pytest.raises(ValueError, match="different input"):
        autonomy_nok_companion.prepare(chosen, "test-run", [], storage=pg)


def test_nok_preparation_retains_inline_fields_without_exact_targets(pg, monkeypatch):
    import autonomous_portfolio as ap

    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    repositories, parallel, snapshot = _evaluation(pg)
    run = parallel.evaluate_snapshot(snapshot, families=["technical"])
    changed_run = {**run, "error_count": 1}
    changed_snapshot = {**snapshot.to_dict(), "run_id": "different-run"}
    assert repositories.market_snapshots.get(snapshot.snapshot_id)["run_id"] != changed_snapshot["run_id"]
    chosen = {"pointer": {"period_id": "test-period"}, "approval": {"settings": {}}}
    monkeypatch.setattr(ap, "prepare_cycle_candidates", lambda *_: ([], changed_snapshot, changed_run, {}))

    prepared = autonomy_nok_companion.prepare(chosen, "test-run", [], storage=pg, portfolio={})
    assert prepared["market_snapshot"] == changed_snapshot
    assert prepared["parallel_strategy_run"] == changed_run
    assert _raw_document(pg, autonomy_nok_companion.preparation_key(chosen, "test-run")) == prepared
