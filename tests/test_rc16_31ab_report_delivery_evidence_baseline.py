from __future__ import annotations

from pathlib import Path

import insider_intelligence as insider
import market_intelligence as mi
import cron_control
import runtime_identity


def test_durable_json_download_materialises_stable_static_file(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, "PUBLIC_REPORT_DIR", tmp_path)
    run = {
        "run_id": "MI-JSON-STABLE",
        "created_at": "2026-08-18T08:58:30+00:00",
        "timezone_name": "Europe/Oslo",
        "job_name": "Utkast",
        "trigger": "MANUAL_DRAFT_TEST",
        "public_report_token": "A" * 43,
        "candidates": [{"ticker": "TEST", "score": 75.0}],
    }
    first = mi.durable_json_download(run)
    second = mi.durable_json_download(run)
    target = tmp_path / Path(first["url"]).name
    assert first["url"] == second["url"]
    assert target.is_file()
    assert target.read_bytes() == first["data"]
    assert first["filename"].endswith(".json")


def test_primary_only_insider_skips_secondary_provider_and_discovery(monkeypatch):
    monkeypatch.setattr(insider, "_load_cache", lambda: {})
    monkeypatch.setattr(insider, "_store_cached_result", lambda *args: None)
    monkeypatch.setattr(insider, "fetch_official_insider_sources", lambda *args, **kwargs: {
        "status": "SUCCESS_NO_RESULTS",
        "attempts": [{
            "source": "Primærregister", "source_type": "OFFICIAL_PRIMARY",
            "attempted": True, "status": "SUCCESS_NO_RESULTS", "results": 0,
            "direct_primary_source_checked": True,
        }],
        "transactions": [],
    })
    monkeypatch.setattr(insider, "discover_with_newsapi", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("discovery")))
    result = insider.fetch_insider_intelligence(
        "TEST.OL", force_refresh=True, market="Norge", company="Test ASA", primary_only=True,
    )
    assert result["coverage"] == "CHECKED_NO_EVENTS"
    assert result["source_budget"]["attempted"] == 1
    assert all(row.get("source_type") != "SECONDARY_STRUCTURED" for row in result["search_log"])


def test_technical_report_contains_all_tasks_and_clear_coverage_language():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert 'Paragraph(f"Komplett oppgavespor ({len(decision_tasks)})"' in source
    assert "for task in decision_tasks:" in source
    assert "Kontrollandel måler kontrolluniversets andel" in source
    assert "Grunnkontroll innsider" in Path("investment_pipeline.py").read_text(encoding="utf-8")
    assert "Grunnkontroll short" in Path("investment_pipeline.py").read_text(encoding="utf-8")


def test_legacy_naive_cron_timestamp_is_normalized_to_utc():
    parsed = cron_control._parse_iso("2026-08-24T08:30:00")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_runtime_identity_detects_expected_version_mismatch(monkeypatch):
    monkeypatch.setenv("EXPECTED_APP_VERSION", "v0-wrong")
    ok, reason = runtime_identity.validate_expected_runtime()
    assert ok is False
    assert runtime_identity.APP_VERSION in reason


def test_headless_and_diagnostic_runtime_contracts_are_present():
    scheduler = Path("scheduled_runner.py").read_text(encoding="utf-8")
    scanner = Path("scanner_worker.py").read_text(encoding="utf-8")
    diagnostics = Path("manual_job_background.py").read_text(encoding="utf-8")
    assert "publish_runtime_identity" in scheduler
    assert 'logging.getLogger("yfinance").setLevel(logging.CRITICAL)' in scanner
    assert "runtime/RUNTIME_IDENTITIES.json" in diagnostics
