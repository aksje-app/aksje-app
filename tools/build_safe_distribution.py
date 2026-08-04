#!/usr/bin/env python3
"""Build deterministic full and delta archives for the canonical current release."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app_version import APP_VERSION

VERSION = APP_VERSION
DOC_TAG = APP_VERSION.replace("-rc", "_RC")
ARCHIVE_BASE = APP_VERSION.split("-rc", 1)[0].replace(".", "_")
RC_LABEL = "RC" + APP_VERSION.rsplit("-rc", 1)[1] if "-rc" in APP_VERSION else "RELEASE"
MUTABLE_PARTS = {
    ".git", ".app_runtime", ".pytest_cache", ".render", "__pycache__", "build",
    "cache", "data", "dist", "htmlcov", "logs", "local_runtime", "runtime",
    "runtime_data", "storage", ".venv", "venv", "env",
}
FORBIDDEN_NAMES = {".env", "secrets.toml", "paper_portfolio.json", "app_users.json", "remember_tokens.json"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".db", ".sqlite", ".sqlite3", ".zip", ".tar", ".gz"}
DELTA_SUPPORT_FILES = {
    "tools/audit_full_system_v19150.py",
    "tools/validate_distribution.py",
    "tools/build_safe_distribution.py",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def excluded(relative: Path) -> bool:
    parts = relative.parts
    if (parts and parts[0] in MUTABLE_PARTS) or "__pycache__" in parts:
        return True
    if relative.name in FORBIDDEN_NAMES or relative.suffix.lower() in FORBIDDEN_SUFFIXES:
        return True
    if relative.as_posix().startswith("static/reports/") and relative.name not in {".gitkeep", "README.md"}:
        return True
    return False


def safe_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink() and not excluded(path.relative_to(root))
    }


def make_manifest(files: dict[str, Path], *, package: str) -> dict:
    return {
        "version": VERSION,
        "package": package,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_count": len(files),
        "files": [{"path": rel, "size": path.stat().st_size, "sha256": sha256(path)} for rel, path in sorted(files.items())],
    }


def write_deterministic_zip(source_dir: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(2026, 8, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def build(source: Path, baseline: Path, output: Path) -> dict:
    source = source.resolve(); baseline = baseline.resolve(); output = output.resolve()
    stage = output / "stage"
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir(parents=True)

    source_files = safe_files(source)
    baseline_files = safe_files(baseline)

    # Refresh the source manifest before package comparison.
    manifest_path = source / "DISTRIBUTION_MANIFEST.json"
    pre_manifest = make_manifest({k: v for k, v in source_files.items() if k != "DISTRIBUTION_MANIFEST.json"}, package="source")
    manifest_path.write_text(json.dumps(pre_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_files = safe_files(source)

    changed = []
    new = []
    for rel, path in source_files.items():
        old = baseline_files.get(rel)
        if old is None:
            new.append(rel)
        elif sha256(path) != sha256(old):
            changed.append(rel)
    # DELETE_FILES may only contain paths that belong to the safe, distributable
    # source set. Mutable runtime data, caches and local secrets are deliberately
    # excluded from both snapshots and must never be deleted by an upgrade package.
    delete_files = sorted(set(baseline_files) - set(source_files))

    full_stage = stage / "full"
    full_stage.mkdir()
    for rel, path in source_files.items():
        dest = full_stage / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, dest)

    delta_stage = stage / "delta"
    copy_root = delta_stage / "COPY_TO_REPOSITORY"
    copy_root.mkdir(parents=True)
    support_files = sorted(rel for rel in DELTA_SUPPORT_FILES if rel in source_files)
    delta_copy_files = sorted(set(new + changed + support_files))
    for rel in delta_copy_files:
        path = source_files[rel]; dest = copy_root / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, dest)
    inventory = {
        "version": VERSION, "baseline": baseline.name,
        "new": sorted(new), "changed": sorted(changed), "support_files": support_files, "deleted": delete_files,
        "copy_file_count": len(delta_copy_files), "delete_file_count": len(delete_files),
    }
    (delta_stage / f"CHANGE_INVENTORY_{DOC_TAG}.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (delta_stage / "DELETE_FILES.txt").write_text("\n".join(delete_files) + ("\n" if delete_files else ""), encoding="utf-8")
    (delta_stage / "README_APPLY_DELTA.md").write_text(
        f"# Bruk av {VERSION}-delta\n\n"
        f"1. Bruk repositorygrenen som er basert på {source.name} sin autoritative forgjenger.\n"
        "2. Kopier alt under `COPY_TO_REPOSITORY` til repositoryroten og erstatt eksisterende filer.\n"
        "3. Slett hver bane i `DELETE_FILES.txt`. Baner under `.app_runtime` er mutable testdata og skal fjernes fra GitHub, ikke fra Render-disken.\n"
        "4. Kontroller endringene, commit og push. Ikke marker produksjonsklar før Render-akseptansen er bestått.\n",
        encoding="utf-8",
    )

    full_zip = output / f"AI_Aksje_Analyzer_{ARCHIVE_BASE}_INVESTOR_EDITION_{RC_LABEL}_FULL.zip"
    delta_zip = output / f"AI_Aksje_Analyzer_{ARCHIVE_BASE}_INVESTOR_EDITION_{RC_LABEL}_DELTA.zip"
    write_deterministic_zip(full_stage, full_zip)
    write_deterministic_zip(delta_stage, delta_zip)
    result = {
        "version": VERSION, "full_zip": str(full_zip), "delta_zip": str(delta_zip),
        "full_sha256": sha256(full_zip), "delta_sha256": sha256(delta_zip), **inventory,
    }
    (output / f"BUILD_RESULT_{DOC_TAG}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.baseline, args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
