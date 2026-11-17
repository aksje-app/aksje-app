import os
from contextlib import closing
from uuid import uuid4

import pytest

from services.storage_references import StorageReferenceError, reference
from services.storage_service import StorageService


@pytest.fixture
def postgres(tmp_path):
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set TEST_POSTGRES_URL to an isolated test database.")
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import make_dsn

    schema = f"test_array_reference_{uuid4().hex}"
    with closing(psycopg2.connect(database_url)) as conn, conn, conn.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        dsn = make_dsn(database_url, options=f"-c search_path={schema}")
        yield StorageService(tmp_path, database_url=dsn, mode="postgres", allow_local_fallback=False)
    finally:
        with closing(psycopg2.connect(database_url)) as conn, conn, conn.cursor() as cursor:
            cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.mark.parametrize("field", [None, "proposals"])
def test_bounded_postgres_array_readers_match_legacy_answers_with_references(postgres, field):
    if field is None:
        target = "repositories/reports.json"
        alias = "market_intelligence/report_archive.json"
    else:
        target = "investment_pipeline/runs/IP-1.json"
        alias = "investment_pipeline/proposals/IP-1_proposals.json"
    old = {"id": "old", "created_at": "2026-11-15"}
    first = {"id": "first", "created_at": "2026-11-17"}
    second = {"id": "second", "created_at": "2026-11-17"}
    rows = [old, "scalar", first, second, {"id": "excluded", "created_at": "2026-11-18"}]

    def check_bounded_reads():
        assert postgres.read_json_array_slice(alias, limit=3) == [old, first]
        assert postgres.read_json_array_item(alias, "id", "second") == second
        assert postgres.read_json_array_item(alias, "id", "absent", "missing") == "missing"
        assert postgres.read_json_array_page(alias, id_field="id", exclude_ids=["excluded"]) == [first, second, old]
        assert postgres.read_json_array_page(alias, limit=1, offset=1, id_field="id", exclude_ids=["excluded"]) == [second]

    postgres.write_json(alias, rows)
    check_bounded_reads()
    postgres.write_json_aliases(target, rows if field is None else {field: rows}, aliases={alias: field})
    check_bounded_reads()


@pytest.mark.parametrize("read", [
    lambda storage, key: storage.read_json_array_slice(key),
    lambda storage, key: storage.read_json_array_item(key, "run_id", "MI-1"),
    lambda storage, key: storage.read_json_array_page(key),
])
def test_bounded_postgres_readers_fail_closed_on_corrupt_reference(postgres, read):
    alias = "market_intelligence/report_archive.json"
    target = "repositories/reports.json"
    postgres.write_json(target, [{"run_id": "MI-OTHER"}])
    postgres.write_json(alias, reference(target, [{"run_id": "MI-1"}]))

    with pytest.raises(StorageReferenceError, match="checksum"):
        read(postgres, alias)


def test_bounded_postgres_reader_resolves_in_the_snapshot_where_it_found_the_alias(postgres, monkeypatch):
    from services import storage_service

    alias = "investment_pipeline/proposals/IP-2_proposals.json"
    target = "investment_pipeline/runs/IP-2.json"
    old = [{"id": "original"}]
    new = [{"id": "replacement"}]
    postgres.write_json_aliases(target, {"proposals": old}, aliases={alias: "proposals"})
    load = storage_service._load_json_document

    def publish_during_resolution(name, raw, **kwargs):
        if name == alias:
            postgres.write_json_aliases(target, {"proposals": new}, aliases={alias: "proposals"})
        return load(name, raw, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(storage_service, "_load_json_document", publish_during_resolution)
        assert postgres.read_json_array_slice(alias) == old
    assert postgres.read_json_array_slice(alias) == new
