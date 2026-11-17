import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from services import storage_service


def test_resolves_field_and_ordered_nested_refs_without_rewriting_legacy(tmp_path):
    from services.storage_references import reference, referenced_fields, version_key

    storage = storage_service.StorageService(tmp_path, mode="local")
    first = {"decision_id": "a", "values": [None, 2]}
    second = {"decision_id": "b", "values": [3]}
    for row in (first, second):
        assert storage.write_json_immutable(version_key(row), row) == row
    refs = [reference(version_key(row), row) for row in (second, first, second)]
    run = {"run_id": "R1", "decisions": [second, first, second]}
    compact = referenced_fields(run, {"decisions": refs})
    assert storage.write_json_immutable(version_key(run), compact) == run
    run_ref = reference(version_key(run), run)
    key = "repositories/strategy_runs/items/strategy.json"
    storage.write_json(key, run_ref)
    storage.write_json("old.json", run)
    assert storage.read_json(key) == storage.read_json("old.json") == run
    assert storage.read_json(key)["decisions"][0] == second
    assert "decision_id" not in (tmp_path / key).read_text()
    source = "investment_pipeline/runs/R1.json"
    storage.write_json(source, {"proposals": [first]})
    storage.write_json("investment_pipeline/proposals/R1_proposals.json", reference(source, [first], "proposals"))
    assert storage.read_json("investment_pipeline/proposals/R1_proposals.json") == [first]


def test_broken_reference_is_explicit_and_can_be_restored(tmp_path):
    from services.storage_references import StorageReferenceError, reference

    storage = storage_service.StorageService(tmp_path, mode="local")
    target = "market_intelligence/runs/restore.json"
    alias = "market_intelligence/latest_run.json"
    expected = {"run_id": "restore"}
    storage.write_json(alias, reference(target, expected))
    with pytest.raises(StorageReferenceError, match="missing"):
        storage.read_json(alias, {})
    storage.write_json(target, {"run_id": "wrong"})
    with pytest.raises(StorageReferenceError, match="checksum"):
        storage.read_json(alias, {})
    storage.write_json(target, expected)
    assert storage.read_json(alias) == expected


def test_cyclic_references_fail_closed(tmp_path):
    from services.storage_references import StorageReferenceError, reference

    storage = storage_service.StorageService(tmp_path, mode="local")
    first = "market_intelligence/runs/one.json"
    second = "market_intelligence/runs/two.json"
    storage.write_json(first, reference(second, {}))
    storage.write_json(second, reference(first, {}))
    with pytest.raises(StorageReferenceError, match="cycle"):
        storage.read_json(first)


def test_reference_hash_matches_keys_as_written_by_json(tmp_path):
    from services.storage_references import reference

    storage = storage_service.StorageService(tmp_path, mode="local")
    target = "market_intelligence/runs/dict-keys.json"
    alias = "market_intelligence/latest_run.json"
    for data in ({"scores": {2: "two", 10: "ten"}}, {"mixed": {"2": "before", 2: "after"}}):
        storage.write_json(target, data)
        storage.write_json(alias, reference(target, data))
        assert storage.read_json(alias) == storage.read_json(target)


@pytest.fixture
def postgres(tmp_path):
    dsn = os.environ.get("TEST_POSTGRES_URL")
    if not dsn:
        pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL verification")
    storage = storage_service.StorageService(tmp_path, database_url=dsn, mode="postgres", allow_local_fallback=False)
    storage.init_db()
    return storage


def test_atomic_alias_write_preserves_previous_projection_on_unpaired_revision(postgres):
    suffix = uuid.uuid4().hex
    target = f"investment_pipeline/runs/{suffix}.json"
    alias = f"investment_pipeline/proposals/{suffix}_proposals.json"
    initial = {"run_id": suffix, "proposals": [1, 2]}
    later = {"run_id": suffix, "proposals": [3]}
    postgres.write_json_aliases(target, initial, aliases={alias: "proposals"})
    assert postgres.read_json(alias) == [1, 2]
    postgres.write_json_aliases(target, later, aliases={}, preserve_aliases=(alias,))
    assert postgres.read_json(target) == later
    assert postgres.read_json(alias) == [1, 2]
    postgres.write_json_aliases(target, later, aliases={alias: "proposals"})
    assert postgres.read_json(alias) == [3]


def test_concurrent_alias_updates_use_consistent_read_snapshot(postgres):
    suffix = uuid.uuid4().hex
    target = f"market_intelligence/runs/{suffix}.json"
    alias = f"market_intelligence/runs/{suffix}-alias.json"

    def publish(n):
        postgres.write_json_aliases(target, {"n": n}, aliases={alias: None})

    publish(0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        writers = [pool.submit(publish, n) for n in range(1, 12)]
        reads = [pool.submit(postgres.read_json, alias) for _ in range(15)]
        for writer in writers:
            writer.result()
        assert all(0 <= read.result()["n"] <= 11 for read in reads)


def test_existing_retention_delete_keeps_the_live_proposal_projection(postgres):
    suffix = uuid.uuid4().hex
    target = f"investment_pipeline/runs/{suffix}.json"
    alias = f"investment_pipeline/proposals/{suffix}_proposals.json"
    rows = [{"ticker": "test"}]
    postgres.write_json_aliases(target, {"proposals": rows}, aliases={alias: "proposals"})
    assert postgres.delete_json(target)
    assert postgres.read_json(target) is None
    assert postgres.read_json(alias) == rows


def test_group_rollback_preserves_items_versions_and_indexes(postgres):
    from services.storage_references import version_key

    suffix = uuid.uuid4().hex
    item = f"repositories/strategy_decisions/items/{suffix}.json"
    index = f"repositories/{suffix}-test-index.json"
    doc = {"decision_id": suffix}
    target = version_key(doc)

    def fail(_current):
        raise ValueError("fail within transaction")

    with pytest.raises(ValueError, match="fail within transaction"):
        postgres.write_json_documents({item: doc}, immutable={target: doc}, mutate={index: fail})
    assert [postgres.read_json(key) for key in (item, target, index)] == [None, None, None]
    postgres.write_json_documents({item: doc}, immutable={target: doc}, mutate={index: lambda _current: [item]})
    assert postgres.read_json(item) == postgres.read_json(target) == doc
    assert postgres.read_json(index) == [item]


def test_encoded_mutation_returns_full_result_and_keeps_reference_on_retry(tmp_path):
    from services.storage_references import reference, referenced_fields

    storage = storage_service.StorageService(tmp_path, mode="local")
    snapshot = "repositories/market_snapshots/items/s.json"
    receipt = "autonomous_portfolio/nok_preparation/test.json"
    storage.write_json(snapshot, {"snapshot_id": "s"})
    content = {"market_snapshot": {"snapshot_id": "s"}, "at": 1}

    def encode(result):
        return referenced_fields(result, {"market_snapshot": reference(snapshot, result["market_snapshot"])})

    assert storage.mutate_json(receipt, lambda _: content, encode=encode) == content
    before = (tmp_path / receipt).read_bytes()
    assert storage.mutate_json(receipt, lambda current: current, encode=encode) == content
    assert (tmp_path / receipt).read_bytes() == before
