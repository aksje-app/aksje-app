#!/usr/bin/env python3
"""Create a non-destructive, checksummed backup before an application update."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PRESERVE_PATHS = (
    ".app_runtime",
    "data",
    "storage",
    "runtime",
    "cache",
    "logs",
    ".env",
    ".streamlit/secrets.toml",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collect_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for relative in PRESERVE_PATHS:
        target = project_root / relative
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(path for path in target.rglob("*") if path.is_file())
    return sorted(set(files))


def create_backup(project_root: Path, destination: Path | None = None) -> tuple[Path, dict]:
    project_root = project_root.resolve()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = (destination or project_root.parent / f"ai_aksje_analyzer_preupgrade_{stamp}.zip").resolve()
    if project_root == destination or project_root in destination.parents:
        raise ValueError("Backupfilen må ligge utenfor applikasjonsmappen.")
    destination.parent.mkdir(parents=True, exist_ok=True)

    files = collect_files(project_root)
    manifest = {
        "format": "ai-aksje-analyzer-safe-upgrade-backup-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "source_version": _read_version(project_root),
        "files": [],
    }

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(project_root).as_posix()
            record = {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            manifest["files"].append(record)
            archive.write(path, relative)
        archive.writestr("backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    manifest["archive_sha256"] = _sha256(destination)
    return destination, manifest


def _read_version(project_root: Path) -> str:
    version_file = project_root / "app_version.py"
    if not version_file.exists():
        return "UNKNOWN"
    for line in version_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("APP_VERSION") and "=" in line:
            return line.split("=", 1)[1].strip().strip('"\'')
    return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(description="Ta trygg backup av produksjonsdata før oppgradering.")
    parser.add_argument("--project-root", default=".", help="Eksisterende applikasjonsmappe.")
    parser.add_argument("--destination", help="Valgfri ZIP-fil utenfor applikasjonsmappen.")
    parser.add_argument("--inventory-only", action="store_true", help="Vis hva som ville blitt tatt med uten å lage backup.")
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Applikasjonsmappen finnes ikke: {root}")

    files = collect_files(root)
    if args.inventory_only:
        print(json.dumps({"project_root": str(root), "files": [p.relative_to(root).as_posix() for p in files]}, ensure_ascii=False, indent=2))
        return 0

    destination = Path(args.destination).expanduser() if args.destination else None
    archive, manifest = create_backup(root, destination)
    print(f"Backup opprettet: {archive}")
    print(f"Filer: {len(manifest['files'])}")
    print(f"SHA-256: {manifest['archive_sha256']}")
    print("Ingen kildefiler ble flyttet eller slettet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
