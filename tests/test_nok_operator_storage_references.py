import pytest

from services import storage_references
from services.storage_references import reference, referenced_fields
from test_revision_trade_postgres import pg
from tools.nok_operator.operator_common import ReadOnlyStorage


LATEST_RUN = "market_intelligence/latest_run.json"


def test_operator_reads_latest_run_reference_with_writes_disabled(pg, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg.database_url)
    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED", raising=False)
    run = {"run_id": "MI-operator", "candidates": [{"ticker": "EQNR.OL"}]}
    key = "market_intelligence/runs/MI-operator.json"
    pg.write_json(key, run)
    pg.write_json(LATEST_RUN, reference(key, run))

    assert ReadOnlyStorage().read_json(LATEST_RUN) == run


def test_operator_loads_alias_and_target_from_same_read_snapshot(pg, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg.database_url)
    key = "market_intelligence/runs/replace-during-read.json"
    first = {"run_id": "old", "candidates": []}
    next_run = {"run_id": "next", "candidates": []}
    pg.write_json(key, first)
    pg.write_json(LATEST_RUN, reference(key, first))
    resolve = storage_references.resolve_references

    def replace_target_then_resolve(value, load_targets, **kwargs):
        # Updating a target now preserves its current alias through the same
        # resolver. Only the original operator read should inject a writer.
        monkeypatch.setattr(storage_references, "resolve_references", resolve)
        pg.write_json(key, next_run)
        return resolve(value, load_targets, **kwargs)

    monkeypatch.setattr(storage_references, "resolve_references", replace_target_then_resolve)
    assert ReadOnlyStorage().read_json(LATEST_RUN) == first
    assert pg.read_json(key) == next_run


def test_operator_rejects_cumulative_raw_reference_targets_over_limit(pg, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg.database_url)
    fields = {}
    for name in ("first", "second"):
        key = f"market_intelligence/runs/{name}.json"
        target = {"text": name[0] * (16 * 1024**2)}
        pg.write_json(key, target)
        fields[name] = reference(key, target)
    pg.write_json(LATEST_RUN, referenced_fields(dict.fromkeys(fields), fields))

    with pytest.raises(ValueError, match="Stored shared documents exceed bounded read limit"):
        ReadOnlyStorage().read_json(LATEST_RUN)


def test_operator_rejects_repeated_fields_over_materialized_limit(pg, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg.database_url)
    target = {"text": "x" * (11 * 1024**2)}
    key = "market_intelligence/runs/repeated.json"
    pg.write_json(key, target)
    pointer = reference(key, target)
    pg.write_json(LATEST_RUN, referenced_fields({"items": []}, {"items": [pointer] * 3}))

    with pytest.raises(ValueError, match="Resolved document exceeds bounded read limit"):
        ReadOnlyStorage().read_json(LATEST_RUN)
