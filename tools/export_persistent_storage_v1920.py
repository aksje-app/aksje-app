#!/usr/bin/env python3
"""Export all StorageService documents and event streams to a checksummed ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.storage_service import StorageService

FORMAT = "ai-aksje-analyzer-persistent-export-v1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_archive_name(kind: str, key: str) -> str:
    parts = [part for part in str(key).replace("\\", "/").split("/") if part and part not in {".", ".."}]
    return f"{kind}/" + "/".join(parts)


def export_storage(storage: StorageService, destination: Path) -> dict:
    entries: list[dict] = []
    payloads: dict[str, bytes] = {}
    for key in storage.list_json_names():
        value = storage.read_json(key, None)
        raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8")
        archive_path = _safe_archive_name("documents", key)
        payloads[archive_path] = raw
        entries.append({"kind": "document", "key": key, "path": archive_path, "sha256": _sha(raw), "size_bytes": len(raw)})
    for key in storage.list_jsonl_names():
        rows = storage.read_jsonl(key, limit=10_000_000)
        raw = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n" for row in rows).encode("utf-8")
        archive_path = _safe_archive_name("events", key)
        payloads[archive_path] = raw
        entries.append({"kind": "events", "key": key, "path": archive_path, "sha256": _sha(raw), "size_bytes": len(raw), "rows": len(rows)})
    manifest = {
        "format": FORMAT,
        "schema_version": "2.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "backend": storage.backend(),
        "entries": sorted(entries, key=lambda row: (row["kind"], row["key"])),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, raw in sorted(payloads.items()):
            archive.writestr(path, raw)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Eksporter permanent v19.2.0-lagring med kontrollsummer.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    storage = StorageService(base_dir=args.base_dir, database_url=args.database_url)
    manifest = export_storage(storage, args.output)
    print(json.dumps({"output": str(args.output), "entries": len(manifest["entries"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
