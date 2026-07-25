#!/usr/bin/env python3
"""Restore a safe-upgrade backup with path validation and checksum checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in name


def restore(backup: Path, project_root: Path, overwrite: bool = False, dry_run: bool = False) -> dict:
    backup = backup.resolve()
    project_root = project_root.resolve()
    if not backup.exists():
        raise FileNotFoundError(backup)
    project_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(backup, "r") as archive:
        for info in archive.infolist():
            if not _safe_member(info.filename):
                raise ValueError(f"Utrygg arkivsti: {info.filename}")
        try:
            manifest = json.loads(archive.read("backup_manifest.json").decode("utf-8"))
        except KeyError as exc:
            raise ValueError("Backupen mangler backup_manifest.json") from exc

        records = {item["path"]: item for item in manifest.get("files", [])}
        actions: list[dict] = []
        with tempfile.TemporaryDirectory(prefix="aa_safe_restore_") as temp_dir:
            temp = Path(temp_dir)
            archive.extractall(temp)
            for relative, record in sorted(records.items()):
                source = temp / relative
                if not source.is_file():
                    raise ValueError(f"Backupfil mangler: {relative}")
                actual = _sha256(source)
                if actual != record.get("sha256"):
                    raise ValueError(f"Kontrollsumfeil: {relative}")
                destination = project_root / relative
                if destination.exists() and not overwrite:
                    actions.append({"path": relative, "status": "SKIPPED_EXISTS"})
                    continue
                actions.append({"path": relative, "status": "WOULD_RESTORE" if dry_run else "RESTORED"})
                if not dry_run:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    return {"ok": True, "backup": str(backup), "project_root": str(project_root), "actions": actions}


def main() -> int:
    parser = argparse.ArgumentParser(description="Gjenopprett en sikker oppgraderingsbackup.")
    parser.add_argument("backup")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--overwrite", action="store_true", help="Overskriv eksisterende filer eksplisitt.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = restore(Path(args.backup), Path(args.project_root), overwrite=args.overwrite, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
