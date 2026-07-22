"""Canonical Learning & Reporting result store (v18.9.0).

One immutable analysis result is persisted once.  PDF, report archive,
Historical Learning, Accuracy Analytics, Controlled Learning and Pushover all
receive a materialised view of this same record and stable result identity.
Delivery receipts are deliberately separate from the immutable result.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from durable_runtime import read_json, write_json


VERSION = "v18.9.0"
SCHEMA_VERSION = "1.0"
INDEX_KEY = "autonomi_core/learning_reporting/result_index.json"
ROOT = Path(__file__).resolve().parents[2] / ".app_runtime" / "data" / "autonomi_core"
INDEX_PATH = ROOT / "learning_reporting" / "result_index.json"


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def build_canonical_result(run: Mapping[str, Any]) -> dict[str, Any]:
    """Build the immutable domain result before delivery-specific metadata."""
    run_id = str(run.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id mangler; kanonisk resultat kan ikke opprettes")
    payload = deepcopy(dict(run))
    # Delivery state is mutable and therefore never part of the domain result.
    for key in ("pdf_path", "public_pdf_name", "report_url", "notification", "persistence", "historical_learning", "canonical_result"):
        payload.pop(key, None)
    digest = sha256(_stable_json(payload).encode("utf-8")).hexdigest()
    return {
        "layer_version": VERSION, "schema_version": SCHEMA_VERSION,
        "result_id": f"RESULT-{run_id}", "run_id": run_id,
        "content_hash": digest, "stored_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
        "consumers": [
            "HISTORICAL_LEARNING", "ACCURACY_ANALYTICS", "SNAPSHOTS",
            "CONTROLLED_LEARNING", "EXECUTIVE_SUMMARY", "PDF",
            "REPORT_ARCHIVE", "PUSHOVER",
        ],
    }


def save_canonical_result(run: Mapping[str, Any]) -> dict[str, Any]:
    """Persist once; identical retries reuse the record, conflicts fail closed."""
    record = build_canonical_result(run)
    key = f"autonomi_core/learning_reporting/results/{record['result_id']}.json"
    path = ROOT / "learning_reporting" / "results" / f"{record['result_id']}.json"
    existing = read_json(key, path, {})
    if isinstance(existing, Mapping) and existing:
        if str(existing.get("content_hash")) != record["content_hash"]:
            raise RuntimeError(f"Resultatkonflikt for {record['result_id']}; eksisterende resultat er uforanderlig")
        return dict(existing)
    write_json(key, path, record)
    index = read_json(INDEX_KEY, INDEX_PATH, [])
    rows = [dict(x) for x in index if isinstance(x, Mapping)] if isinstance(index, list) else []
    if not any(str(x.get("result_id")) == record["result_id"] for x in rows):
        rows.insert(0, {k: record[k] for k in ("result_id", "run_id", "stored_at", "content_hash", "schema_version")})
        write_json(INDEX_KEY, INDEX_PATH, rows[:2000])
    return record


def load_canonical_result(result_id: str) -> dict[str, Any]:
    rid = str(result_id or "")
    return dict(read_json(
        f"autonomi_core/learning_reporting/results/{rid}.json",
        ROOT / "learning_reporting" / "results" / f"{rid}.json", {},
    ) or {})


def canonical_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Materialise one shared payload and attach only its stable reference."""
    payload = deepcopy(dict(record.get("payload") or {}))
    payload["canonical_result"] = {
        "result_id": record.get("result_id"), "run_id": record.get("run_id"),
        "schema_version": record.get("schema_version"),
        "content_hash": record.get("content_hash"), "stored_once": True,
    }
    return payload
