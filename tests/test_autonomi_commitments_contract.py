from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_release_manifest_tracks_cross_chat_contract():
    manifest = json.loads((ROOT / "release_manifest.json").read_text(encoding="utf-8"))
    ids = {row["id"] for row in manifest["items"]}
    assert {"QV2-001","QV2-002","QV2-003","QV2-004","QV2-006","QV2-008","QV2-009","QV2-014"}.issubset(ids)
    assert manifest["production_completion_status"] == "DEPLOY_VERIFIED"
    assert manifest["rules"]["planned_is_not_implemented"] is True

def test_contract_forbids_unverified_finished_claims():
    text = (ROOT / "AUTONOMI_COMMITMENTS.md").read_text(encoding="utf-8")
    assert "Only **DEPLOY_VERIFIED** may be described" in text
    assert "Never infer completion from a prior chat" in text
