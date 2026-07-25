#!/usr/bin/env python3
"""Verify and import a v19.2.0 persistent-storage export."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.storage_service import StorageService
from tools.export_persistent_storage_v1920 import FORMAT


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and "" not in path.parts


def import_storage(storage: StorageService, source: Path, *, apply: bool = False, overwrite: bool = False) -> dict:
    with zipfile.ZipFile(source) as archive:
        if any(not _safe_member(name) for name in archive.namelist()):
            raise ValueError("Arkivet inneholder en utrygg sti")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != FORMAT:
            raise ValueError("Ukjent eksportformat")
        seen: set[tuple[str, str]] = set()
        actions: list[dict] = []
        for entry in manifest.get("entries") or []:
            kind = str(entry.get("kind") or "")
            key = str(entry.get("key") or "")
            archive_path = str(entry.get("path") or "")
            identity = (kind, key)
            if identity in seen:
                raise ValueError(f"Duplikat i manifest: {kind}:{key}")
            seen.add(identity)
            raw = archive.read(archive_path)
            if _sha(raw) != str(entry.get("sha256") or ""):
                raise ValueError(f"Kontrollsum stemmer ikke: {archive_path}")
            if kind == "document":
                value = json.loads(raw.decode("utf-8"))
                exists = key in set(storage.list_json_names())
                action = "skip_existing" if exists and not overwrite else "write"
                if apply and action == "write":
                    storage.write_json(key, value)
            elif kind == "events":
                rows = []
                for line in raw.decode("utf-8").splitlines():
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError(f"Hendelsesrad er ikke et objekt: {archive_path}")
                    rows.append(value)
                exists = key in set(storage.list_jsonl_names())
                action = "skip_existing" if exists and not overwrite else "replace"
                if apply and action == "replace":
                    storage.replace_jsonl(key, rows)
            else:
                raise ValueError(f"Ukjent posttype: {kind}")
            actions.append({"kind": kind, "key": key, "action": action})
    return {"ok": True, "dry_run": not apply, "overwrite": overwrite, "actions": actions}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifiser/importer permanent v19.2.0-lagring.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    result = import_storage(
        StorageService(base_dir=args.base_dir, database_url=args.database_url),
        args.source, apply=args.apply, overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
