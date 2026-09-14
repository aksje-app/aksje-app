from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import app_version
import report_integrity
import runtime_identity


def test_bx_version():
    assert app_version.APP_VERSION == "v19.22.0-rc16.31bx"


def test_canonical_duplicate_prefers_ready_richer_record_and_merges_missing():
    corrections = []
    rows = [
        {
            "ticker": "DOFG.OL",
            "investment_score": 72.0,
            "confidence_score": 50.0,
            "valid_for_decision": True,
            "evidence_data_ready": False,
            "final_decision_ready": False,
            "sector": "Industri",
            "raw": {"source_a": "yes"},
        },
        {
            "ticker": " dofg.ol ",
            "investment_score": 76.0,
            "confidence_score": 68.0,
            "valid_for_decision": True,
            "evidence_data_ready": True,
            "final_decision_ready": True,
            "raw": {"source_b": "yes"},
        },
    ]
    result = report_integrity._deduplicate_canonical_candidates(rows, corrections)
    assert len(result) == 1
    assert result[0]["investment_score"] == 76.0
    assert result[0]["sector"] == "Industri"
    assert result[0]["raw"]["source_a"] == "yes"
    assert result[0]["raw"]["source_b"] == "yes"
    assert result[0]["canonical_dedup"]["applied"] is True
    assert corrections and corrections[0]["ticker"] == "DOFG.OL"


def test_runtime_identity_ignores_stale_peer_for_banner(monkeypatch):
    now = datetime.now(timezone.utc)
    payload = {
        "web": {"version": app_version.APP_VERSION, "commit": "new", "observed_at": now.isoformat()},
        "scheduler": {"version": "old", "commit": "old", "observed_at": (now - timedelta(hours=3)).isoformat()},
    }
    monkeypatch.setattr(runtime_identity, "read_json", lambda *a, **k: payload)
    snap = runtime_identity.runtime_identity_snapshot(max_age_minutes=90)
    assert snap["version_mismatch"] is False
    assert snap["commit_mismatch"] is False
    assert "scheduler" in snap["stale_identities"]


def test_runtime_identity_still_blocks_fresh_mismatch(monkeypatch):
    now = datetime.now(timezone.utc)
    payload = {
        "web": {"version": app_version.APP_VERSION, "commit": "new", "observed_at": now.isoformat()},
        "scheduler": {"version": "old", "commit": "old", "observed_at": now.isoformat()},
    }
    monkeypatch.setattr(runtime_identity, "read_json", lambda *a, **k: payload)
    snap = runtime_identity.runtime_identity_snapshot(max_age_minutes=90)
    assert snap["version_mismatch"] is True
    assert snap["commit_mismatch"] is True


def test_ui_workflow_closure_is_present_in_sources():
    autonomy = Path("autonomy_overview.py").read_text(encoding="utf-8")
    market = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "autonomy_pending_execution_v1931bx" in autonomy
    assert "st.rerun()" in autonomy
    assert 'run_every="2s"' in autonomy
    assert "Grunnkontrollutvalg:" in autonomy
    assert "render_report_file_center" in autonomy
    assert "📄 Standardrapport PDF" in market
    assert "📊 Teknisk rapport PDF" in market
    assert "🧾 Rapportdata JSON" in market
    assert "🩺 Diagnose ZIP" in market
    assert "⬇ Last ned komplett rapportpakke" in market
    assert "buy-blocker-table" in market
    assert "overflow-wrap:anywhere" in market


def test_bw_norway_universe_parser_is_preserved():
    source = Path("norway_exchange_universe.py").read_text(encoding="utf-8")
    assert "XOSL" in source and "MERK" in source and "XOAS" in source
    assert "OFFICIAL_LIVE" in source
    assert "json_html_cells_flexible" in source
