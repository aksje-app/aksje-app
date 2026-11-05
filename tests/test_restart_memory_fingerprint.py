"""Regression for bounded restart preview validation."""
from pathlib import Path


def test_preview_uses_fingerprint_without_second_bundle_read():
    source = (Path(__file__).resolve().parents[1] / "services/restart_trading.py").read_text()
    preview = source[source.index("def preview("):source.index("\ndef paper(", source.index("def preview("))]
    assert preview.count("backend.read_json(key)") == 2  # fallback for injected storage
    assert "backend.json_fingerprint(key)" in preview
    assert "backend.read_json(key) == before" in preview


def test_storage_fingerprint_does_not_deserialize_document():
    source = (Path(__file__).resolve().parents[1] / "services/storage_service.py").read_text()
    method = source[source.index("    def json_fingerprint("):source.index("    def read_json(", source.index("    def json_fingerprint("))]
    assert "SELECT md5(payload)" in method
    assert "json.loads(" not in method


def test_stop_resume_only_copies_mutable_control():
    source = (Path(__file__).resolve().parents[1] / "services/production_restart.py").read_text()
    stop = source[source.index("\ndef stop("):source.index("\ndef economic_event(", source.index("\ndef stop("))]
    assert "result=deepcopy(bundle)" not in stop
    assert "deepcopy(bundle['production_controls'][family])" in stop
