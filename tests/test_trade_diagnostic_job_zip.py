"""Regression coverage for complete Super Portfolio job diagnostic archives."""
import io
import json
import zipfile

import super_portfolio_jobs as jobs


def test_job_diagnostic_zip_contains_errors_shadow_and_manifest(monkeypatch):
    monkeypatch.setattr(jobs, "get_job", lambda job_id="": {"job_id": "SP-TEST", "state": "FAILED", "error": "test failure"})
    monkeypatch.setattr(jobs, "read_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(jobs, "job_events", lambda *args, **kwargs: [{"event": "FAILED"}])
    monkeypatch.setattr(jobs, "read_events", lambda key, path, limit=500: (
        [{"at": "2026-10-17", "event": "SOURCE-FETCH-FAILED", "error_code": "RATE_LIMIT"}]
        if key == "operations/errors.jsonl" else [{"event": "EVALUATE", "changes": []}]
    ))
    archive_bytes = jobs.diagnostic_zip("SP-TEST")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
        assert z.testzip() is None
        names = set(z.namelist())
        assert {"recent_errors.json", "recent_shadow_decisions.json", "manifest.json", "job_status.json"} <= names
        errors = json.loads(z.read("recent_errors.json"))
        assert errors[0]["error_code"] == "RATE_LIMIT"
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["strategy_validated"] is False
        assert any(item["path"] == "recent_errors.json" for item in manifest["files"])


def test_error_unavailable_must_be_explicit_in_zip(monkeypatch):
    monkeypatch.setattr(jobs, "get_job", lambda job_id="": {"job_id": "SP-TEST", "state": "FAILED"})
    monkeypatch.setattr(jobs, "read_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(jobs, "job_events", lambda *args, **kwargs: [])
    def broken(*args, **kwargs):
        raise RuntimeError("storage offline")
    monkeypatch.setattr(jobs, "read_events", broken)
    with zipfile.ZipFile(io.BytesIO(jobs.diagnostic_zip("SP-TEST"))) as z:
        assert "recent_errors_unavailable.json" in z.namelist()
        assert "recent_shadow_unavailable.json" in z.namelist()
        assert z.testzip() is None
