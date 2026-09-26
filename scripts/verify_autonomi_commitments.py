"""Fail a release when Autonomi commitments are represented as more complete than their evidence."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "release_manifest.json").read_text(encoding="utf-8"))
contract = (ROOT / "AUTONOMI_COMMITMENTS.md").read_text(encoding="utf-8")
allowed = set(manifest["status_order"])
assert manifest["production_completion_status"] == "DEPLOY_VERIFIED"
assert "Only **DEPLOY_VERIFIED**" in contract
ids = set()
for item in manifest["items"]:
    assert item["id"] not in ids
    ids.add(item["id"])
    assert item["status"] in allowed
    assert isinstance(item.get("evidence"), list)
    if item["status"] in {"IMPLEMENTED", "TESTED", "MERGED", "DEPLOY_VERIFIED"}:
        assert item["evidence"], f"{item['id']} claims {item['status']} without evidence"
    if item["status"] == "DEPLOY_VERIFIED":
        assert any("deploy" in str(e).lower() or "render" in str(e).lower() for e in item["evidence"])
print(f"Autonomi release truth gate OK: {len(ids)} tracked commitments")
