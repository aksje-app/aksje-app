from __future__ import annotations
import json
from pathlib import Path
from services.storage_service import StorageService
from repositories.application import RepositoryRegistry
from services.persistence_service import PersistenceService
from migrations.migrate_legacy_storage import migrate_file
from pages.overview import build_overview_page
from ui.candidate_cards import build_candidate_card


def test_repository_roundtrip_local_fallback(tmp_path):
    storage=StorageService(base_dir=tmp_path, database_url="")
    repos=RepositoryRegistry(storage)
    repos.reports.replace_all([{"run_id":"R-1","status":"final"}])
    assert repos.reports.get("R-1")["status"] == "final"
    repos.reports.upsert({"run_id":"R-1","status":"updated"})
    assert repos.reports.get("R-1")["status"] == "updated"
    repos.reports.delete("R-1")
    assert repos.reports.list() == []


def test_persistence_status_identifies_nonpersistent_fallback(tmp_path):
    service=PersistenceService(StorageService(base_dir=tmp_path, database_url=""))
    status=service.status()
    assert status.backend == "local_json_fallback"
    assert status.persistent is False


def test_legacy_report_archive_migration_is_non_destructive(tmp_path):
    source=tmp_path / "report_archive.json"
    source.write_text(json.dumps([{"run_id":"MI-1","report_type":"MORGENRAPPORT"}]), encoding="utf-8")
    storage=StorageService(base_dir=tmp_path / "target", database_url="")
    dry=migrate_file(source, storage=storage, dry_run=True)
    assert dry.ok and dry.rows_imported == 0
    assert json.loads(source.read_text(encoding="utf-8"))[0]["run_id"] == "MI-1"
    applied=migrate_file(source, storage=storage, dry_run=False)
    assert applied.rows_imported == 1
    assert RepositoryRegistry(storage).reports.get("MI-1") is not None
    assert source.exists()


def test_overview_page_model_is_renderer_independent():
    model=build_overview_page([], pending_approvals=2, scheduler_ok=False)
    assert model["page"] == "overview"
    assert len(model["actions"]) == 5
    assert any(x["code"] == "REPORT_MISSING" for x in model["attention_items"])


def test_candidate_card_model_keeps_all_direct_actions():
    model=build_candidate_card({"ticker":"EQNR.OL","score":82}, {"decision":"BUY"})
    assert model["ticker"] == "EQNR.OL"
    assert "analysis" in model["actions"]
    assert "export" in model["actions"]


def test_registry_exposes_all_permanent_domains(tmp_path):
    registry = RepositoryRegistry(StorageService(base_dir=tmp_path, database_url=""))
    expected = {
        "settings", "reports", "portfolios", "trades", "tasks", "approvals",
        "source_health", "scheduler", "run_traces", "configurations",
        "learning", "model_state", "notifications", "operational_events",
        "audit_events",
    }
    assert expected.issubset(set(registry.domain_names()))


def test_production_policy_rejects_silent_local_write(tmp_path):
    from services.storage_service import StorageUnavailableError
    storage = StorageService(
        base_dir=tmp_path, database_url="", mode="auto", allow_local_fallback=False,
    )
    assert storage.health().ok is False
    try:
        storage.write_json("critical/state.json", {"ok": True})
    except StorageUnavailableError:
        pass
    else:
        raise AssertionError("Production policy accepted a silent local write")


def test_event_stream_replace_remains_structured(tmp_path):
    storage = StorageService(base_dir=tmp_path, database_url="")
    storage.replace_jsonl("events/audit.jsonl", [{"event": "A"}, {"event": "B"}])
    assert storage.read_jsonl("events/audit.jsonl", 10) == [{"event": "A"}, {"event": "B"}]


def test_checksumned_export_import_roundtrip(tmp_path):
    from tools.export_persistent_storage_v1920 import export_storage
    from tools.import_persistent_storage_v1920 import import_storage

    source = StorageService(base_dir=tmp_path / "source", database_url="")
    source.write_json("settings/app_settings.json", {"mode": "simple"})
    source.replace_jsonl("operations/events.jsonl", [{"event": "start"}, {"event": "done"}])
    archive = tmp_path / "backup.zip"
    manifest = export_storage(source, archive)
    assert len(manifest["entries"]) == 2

    target = StorageService(base_dir=tmp_path / "target", database_url="")
    dry = import_storage(target, archive, apply=False)
    assert dry["dry_run"] is True
    assert target.list_json_names() == []
    applied = import_storage(target, archive, apply=True)
    assert applied["ok"] is True
    assert target.read_json("settings/app_settings.json", {})["mode"] == "simple"
    assert target.read_jsonl("operations/events.jsonl", 10)[1]["event"] == "done"


def test_legacy_migration_is_idempotent_and_keeps_source(tmp_path):
    source_dir = tmp_path / "legacy" / "autonomous_portfolio"
    source_dir.mkdir(parents=True)
    source = source_dir / "trades.json"
    source.write_text(json.dumps([{"trade_id": "T-1", "ticker": "EQNR.OL"}]), encoding="utf-8")
    storage = StorageService(base_dir=tmp_path / "target", database_url="")
    first = migrate_file(source, storage=storage, dry_run=False)
    second = migrate_file(source, storage=storage, dry_run=False)
    assert first.ok and first.rows_imported == 1
    assert second.ok and second.rows_imported == 0 and second.message == "Allerede migrert"
    assert source.exists()


def test_large_renderers_are_extracted_from_app_shell():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    assert len(app.splitlines()) < 20500
    expected = [
        root / "pages" / "analysis.py", root / "pages" / "ranking.py",
        root / "pages" / "trading.py", root / "pages" / "paper_trading.py",
        root / "pages" / "top_picks.py", root / "pages" / "long_engine.py",
        root / "pages" / "autonomy.py", root / "ui" / "live_market_banner.py",
    ]
    assert all(path.is_file() for path in expected)
    assert "from pages.analysis import render_analysis as _implementation" in app
