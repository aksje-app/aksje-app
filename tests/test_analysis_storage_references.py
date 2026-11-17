import copy
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

import durable_runtime
import investment_pipeline as pipeline
import market_intelligence as market
import repositories.application as repositories


REPORT_ARCHIVE = "market_intelligence/report_archive.json"
REPORT_REPOSITORY = "repositories/reports.json"
MARKET_LATEST = "market_intelligence/latest_run.json"
PIPELINE_LATEST = "investment_pipeline/latest_run.json"


class StorageDouble:
    """In-memory model of the storage boundary, including alias snapshot semantics."""

    allow_local_fallback = False

    def __init__(self):
        self.documents = {}
        self.aliases = {}

    def using_postgres(self):
        return True

    def read_json(self, name, default=None):
        if name in self.aliases:
            target, field = self.aliases[name]
            value = self.documents[target]
            return copy.deepcopy(value if field is None else value[field])
        return copy.deepcopy(self.documents[name]) if name in self.documents else default

    def write_json(self, name, value):
        self.aliases.pop(name, None)
        self.documents[name] = json.loads(json.dumps(value, default=str))
        return True

    def write_json_aliases(self, name, value, *, aliases, preserve_aliases=()):
        for alias in preserve_aliases:
            if alias not in aliases and self.aliases.get(alias, (None, None))[0] == name:
                self.write_json(alias, self.read_json(alias))
        self.write_json(name, value)
        for alias, field in aliases.items():
            self.documents.pop(alias, None)
            self.aliases[alias] = (name, field)
        return True

    def write_json_immutable(self, name, value):
        if name not in self.documents and name not in self.aliases:
            self.write_json(name, value)
        return self.read_json(name)


@pytest.fixture
def configure_runtime(tmp_path, monkeypatch):
    def use_storage(storage):
        monkeypatch.setattr(durable_runtime, "get_storage_service", lambda: storage)
        monkeypatch.setattr(
            repositories, "get_repository_registry",
            lambda: SimpleNamespace(reports=repositories.ReportRepository(storage)),
        )

    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    monkeypatch.setattr(market, "RUNS_DIR", tmp_path / "market" / "runs")
    monkeypatch.setattr(market, "SUMMARIES_DIR", tmp_path / "market" / "summaries")
    monkeypatch.setattr(market, "LATEST_PATH", tmp_path / "market" / "latest_run.json")
    monkeypatch.setattr(market, "REPORT_ARCHIVE_PATH", tmp_path / "market" / "report_archive.json")
    monkeypatch.setattr(market, "_audit", lambda *args: None)
    monkeypatch.setattr(pipeline, "RUNS_DIR", tmp_path / "pipeline" / "runs")
    monkeypatch.setattr(pipeline, "PROPOSALS_DIR", tmp_path / "pipeline" / "proposals")
    monkeypatch.setattr(pipeline, "LATEST_RUN_PATH", tmp_path / "pipeline" / "latest_run.json")
    return use_storage


@pytest.fixture
def storage(configure_runtime):
    storage = StorageDouble()
    configure_runtime(storage)
    return storage


def test_promoted_market_run_publishes_latest_without_another_full_row(storage, monkeypatch):
    monkeypatch.setattr(market, "build_main_pdf", lambda run: b"%PDF-sample")
    monkeypatch.setattr(market, "publish_pdf", lambda run, pdf: None)
    monkeypatch.setattr(market, "report_public_url", lambda run: "")
    job = market.JobProfile(job_id="MI-AUTONOMY-REPORT-TEST-REF", name="Test")

    run = market._persist_promoted_run({}, job, "MANUAL_FULL_CHAIN", {})
    target = f"market_intelligence/runs/{run['run_id']}.json"
    assert storage.aliases.get(MARKET_LATEST) == (target, None)
    assert market.load_run(run["run_id"]) == storage.read_json(MARKET_LATEST)
    assert json.loads(market.LATEST_PATH.read_text()) == storage.read_json(MARKET_LATEST)


def test_unpaired_market_run_update_preserves_last_published_revision_after_flag_rollback(storage, monkeypatch):
    key = "market_intelligence/runs/MI-1.json"
    storage.write_json_aliases(key, {"run_id": "MI-1", "status": "published"}, aliases={MARKET_LATEST: None})
    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED")

    market._write(market.RUNS_DIR / "MI-1.json", {"run_id": "MI-1", "status": "updated independently"})

    assert market.load_run("MI-1")["status"] == "updated independently"
    assert market._read(market.LATEST_PATH, {})["status"] == "published"


def test_report_persistence_reports_run_written_before_a_legacy_latest_failure(storage, monkeypatch):
    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED")
    run_path = market.RUNS_DIR / "MI-1.json"
    steps = []

    def write(path, value):
        if path == market.LATEST_PATH:
            raise OSError("disk failure")
        steps.append("run written")

    monkeypatch.setattr(market, "_write", write)
    with pytest.raises(OSError, match="disk failure"):
        market._publish_run(
            run_path, {"run_id": "MI-1"}, publish_latest=True,
            on_run_written=lambda: steps.append("checkpoint reached"),
        )
    assert steps == ["run written", "checkpoint reached"]


def test_pipeline_run_shares_latest_and_proposals_and_keeps_ui_enrichment(storage, monkeypatch):
    import learning_runtime

    monkeypatch.setattr(learning_runtime, "archive", lambda payload: {"status": "RECORDED"})
    payload = pipeline.run_pipeline([])
    target = f"investment_pipeline/runs/{payload['run_id']}.json"
    proposals = f"investment_pipeline/proposals/{payload['run_id']}_proposals.json"

    assert storage.aliases.get(PIPELINE_LATEST) == (target, None)
    assert storage.aliases.get(proposals) == (target, "proposals")
    assert storage.read_json(PIPELINE_LATEST) == storage.read_json(target)
    assert pipeline._read_json(pipeline.PROPOSALS_DIR / f"{payload['run_id']}_proposals.json", {}) == []
    assert json.loads(pipeline.LATEST_RUN_PATH.read_text()) == storage.read_json(target)

    pipeline._write_json(pipeline.LATEST_RUN_PATH, {**payload, "candidate_source": "Scanner"})
    latest = pipeline._read_json(pipeline.LATEST_RUN_PATH, {})
    assert latest["candidate_source"] == "Scanner"
    assert latest["experiment_archive"] == {"status": "RECORDED"}
    assert "candidate_source" not in storage.read_json(target)
    assert storage.read_json(proposals) == []


def test_archive_keeps_legacy_reads_and_stops_writing_the_configuration_copy(storage, monkeypatch):
    legacy = [{"run_id": "MI-LEGACY", "favorite": False}]
    legacy_reads = []
    legacy_writes = []
    monkeypatch.setattr(market, "read_persistent_json", lambda key, default: legacy_reads.append(key) or legacy)
    monkeypatch.setattr(market, "write_persistent_json", lambda key, value: legacy_writes.append(value))

    assert market._load_report_archive() == legacy
    assert storage.read_json(REPORT_REPOSITORY) == legacy
    market.set_report_favorite("MI-LEGACY", True)
    assert storage.aliases.get(REPORT_ARCHIVE) == (REPORT_REPOSITORY, None)
    assert storage.read_json(REPORT_ARCHIVE) == [{"run_id": "MI-LEGACY", "favorite": True}]
    market._save_report_archive([])
    assert market._load_report_archive() == []
    assert legacy_reads == [REPORT_ARCHIVE]
    assert legacy_writes == []


def test_archive_can_promote_old_raw_mirror(storage, monkeypatch):
    legacy = [{"run_id": "MI-RAW"}]
    storage.write_json(REPORT_ARCHIVE, legacy)
    monkeypatch.setattr(market, "read_persistent_json", lambda *args, **kwargs: pytest.fail("found raw archive in storage"))

    assert market._load_report_archive() == legacy
    assert storage.documents[REPORT_ARCHIVE] == legacy
    assert storage.read_json(REPORT_REPOSITORY) == legacy


def test_archive_legacy_promotion_keeps_concurrently_saved_repository(storage, monkeypatch):
    stale = [{"run_id": "MI-STALE"}]
    current = [{"run_id": "MI-CURRENT"}]

    def read_legacy(key, default):
        market._save_report_archive(current)
        return stale

    monkeypatch.setattr(market, "read_persistent_json", read_legacy)
    assert market._load_report_archive() == current
    assert storage.read_json(REPORT_REPOSITORY) == current


@pytest.mark.parametrize("legacy_source", ["raw_mirror", "configuration"])
def test_existing_empty_repository_can_use_historical_fallback(storage, monkeypatch, legacy_source):
    legacy = [{"run_id": "MI-HISTORICAL"}]
    storage.write_json(REPORT_REPOSITORY, [])
    if legacy_source == "raw_mirror":
        storage.write_json(REPORT_ARCHIVE, legacy)
    else:
        monkeypatch.setattr(market, "read_persistent_json", lambda key, default: legacy)

    assert market._load_report_archive() == legacy
    assert storage.read_json(REPORT_REPOSITORY) == []


def test_local_mirror_recovery_does_not_overwrite_new_latest_published_during_read(storage, monkeypatch):
    key = "market_intelligence/runs/MI-NEW.json"
    stale = {"run_id": "MI-LOCAL"}
    current = {"run_id": "MI-NEW"}
    path = market.LATEST_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(stale))
    original_read = storage.read_json

    def initial_read(name, default=None):
        storage.write_json_aliases(key, current, aliases={MARKET_LATEST: None})
        monkeypatch.setattr(storage, "read_json", original_read)
        return default

    monkeypatch.setattr(storage, "read_json", initial_read)
    assert market._read(path, {}) == current
    assert storage.read_json(MARKET_LATEST) == current


@pytest.fixture
def postgres_storage(configure_runtime, tmp_path):
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set TEST_POSTGRES_URL to an isolated test database.")
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import make_dsn
    from services.storage_service import StorageService

    schema = f"test_analysis_{uuid4().hex}"
    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        scoped_url = make_dsn(database_url, options=f"-c search_path={schema}")
        storage = StorageService(base_dir=tmp_path / "db", database_url=scoped_url, mode="postgres")
        configure_runtime(storage)
        yield storage
    finally:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_postgres_report_and_pipeline_references_remain_readable_after_writer_rollback(postgres_storage, monkeypatch):
    from services.storage_references import REFERENCE

    storage = postgres_storage
    path = market.RUNS_DIR / "MI-1.json"
    market._publish_run(path, {"run_id": "MI-1", "stage": "published"}, publish_latest=True)
    pipeline._publish_run("IP-1", {"run_id": "IP-1", "proposals": [{"ticker": "EQNR.OL"}]})
    market._save_report_archive([{"run_id": "MI-1"}])
    revalidation_path = market.RUNS_DIR / "MI-REVALIDATED.json"
    market._publish_run(revalidation_path, {"run_id": "MI-REVALIDATED"}, publish_latest=False)
    assert market._read(market.LATEST_PATH, {})["run_id"] == "MI-1"
    assert market.load_run("MI-REVALIDATED") == {"run_id": "MI-REVALIDATED"}

    with storage._conn() as conn:
        with conn.cursor() as cursor:
            for key in (MARKET_LATEST, PIPELINE_LATEST, "investment_pipeline/proposals/IP-1_proposals.json", REPORT_ARCHIVE):
                cursor.execute("SELECT payload FROM app_kv_store WHERE name=%s", (key,))
                assert REFERENCE in json.loads(cursor.fetchone()[0])

    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED")
    market._write(path, {"run_id": "MI-1", "stage": "archived"})
    pipeline._write_json(pipeline.RUNS_DIR / "IP-1.json", {"run_id": "IP-1", "proposals": []})

    assert market._read(market.LATEST_PATH, {}) == {"run_id": "MI-1", "stage": "published"}
    assert market.load_run("MI-1")["stage"] == "archived"
    assert pipeline._read_json(pipeline.LATEST_RUN_PATH, {})["proposals"] == [{"ticker": "EQNR.OL"}]
    assert storage.read_json("investment_pipeline/proposals/IP-1_proposals.json") == [{"ticker": "EQNR.OL"}]
    assert market._load_report_archive() == [{"run_id": "MI-1"}]
