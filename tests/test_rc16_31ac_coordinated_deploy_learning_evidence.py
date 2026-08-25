from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import autonomous_portfolio as portfolio
import runtime_identity


def test_render_blueprint_autodeploys_unified_services():
    source = Path("render.yaml").read_text(encoding="utf-8")
    assert source.count("autoDeployTrigger: commit") == 2
    assert source.count("REQUIRE_CLUSTER_ALIGNMENT") == 1


def test_cluster_alignment_uses_render_commit_without_manual_version(monkeypatch):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    monkeypatch.setenv("REQUIRE_CLUSTER_ALIGNMENT", "true")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    monkeypatch.setattr(runtime_identity, "runtime_identity_snapshot", lambda: {
        "identities": {"web": {
            "version": runtime_identity.APP_VERSION, "commit": "abcdef1234567890",
            "commit_short": "abcdef12", "observed_at": now,
        }}
    })
    ok, reason = runtime_identity.validate_cluster_alignment("report_scheduler", ("web",))
    assert ok is True
    assert "abcdef12" in reason


def test_cluster_alignment_blocks_different_commit(monkeypatch):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    monkeypatch.setenv("REQUIRE_CLUSTER_ALIGNMENT", "true")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "newcommit123456")
    monkeypatch.setattr(runtime_identity, "runtime_identity_snapshot", lambda: {
        "identities": {"web": {
            "version": runtime_identity.APP_VERSION, "commit": "oldcommit123456",
            "commit_short": "oldcommi", "observed_at": now,
        }}
    })
    ok, reason = runtime_identity.validate_cluster_alignment("report_scheduler", ("web",))
    assert ok is False
    assert "Distribusjon ikke synkronisert" in reason


def test_learning_compaction_protects_oldest_open_cohort():
    rows = [
        {"observation_id": "new", "ticker": "ABC", "created_at": "2026-08-20", "status": "OPEN"},
        {"observation_id": "old", "ticker": "ABC", "created_at": "2026-08-01", "status": "OPEN"},
        {"observation_id": "xyz", "ticker": "XYZ", "created_at": "2026-08-10", "status": "OPEN"},
    ]
    compacted = portfolio._compact_learning_observations(rows, limit=3)
    by_id = {row["observation_id"]: row for row in compacted}
    assert by_id["old"]["status"] == "OPEN"
    assert by_id["new"]["status"] == "SUPERSEDED"
    assert by_id["new"]["superseded_by"] == "old"
    assert by_id["xyz"]["status"] == "OPEN"


def test_compact_pdf_contract_exposes_short_and_insider():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert '"Short / innsider / kilder"' in source
    assert 'Paragraph("Short- og innsiderdekning"' in source
    assert '"Innsider", "Kapitalstatus"' in source
    assert "UKJENT betyr at eksponering ikke er dokumentert" in source
