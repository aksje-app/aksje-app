#!/usr/bin/env python3
"""Build clean, validated v19.0.19a release archives."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.validate_distribution import (  # noqa: E402
    ALLOWED_GENERATED_REPORT_PLACEHOLDERS,
    FORBIDDEN_EXACT_PATHS,
    FORBIDDEN_ROOT_DIRS,
    FORBIDDEN_SUFFIXES,
    validate_path,
)

VERSION = "v19.0.19a"
VERSION_FILE = "19_0_19a"

UPDATE_FILES = {
    "app_version.py",
    "safety_audit.py",
    "news_intelligence.py",
    "news_source_registry.py",
    "RELEASE_NOTES_v19.0.19a.md",
    "DEPLOY_v19.0.19a.md",
    "DISTRIBUTION_SECURITY_POLICY_v19.0.19a.md",
    "MIGRATION_v19.0.19a.md",
    "TEST_REPORT_v19.0.19a.md",
    "tools/__init__.py",
    "tools/build_safe_distribution.py",
    "tools/validate_distribution.py",
    "tools/prepare_safe_upgrade.py",
    "tools/restore_safe_upgrade_backup.py",
    "tests/test_v1919a_safe_distribution.py",
    "tests/test_v1911_evidence_integrity.py",
    "tests/test_v1915_mobile_navigation.py",
    "tests/test_v1918b_separate_portfolios.py",
}

MIGRATION_FILES = {
    "MIGRATION_v19.0.19a.md",
    "DEPLOY_v19.0.19a.md",
    "DISTRIBUTION_SECURITY_POLICY_v19.0.19a.md",
    "tools/__init__.py",
    "tools/validate_distribution.py",
    "tools/prepare_safe_upgrade.py",
    "tools/restore_safe_upgrade_backup.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def excluded(relative: Path) -> bool:
    posix = relative.as_posix()
    parts = relative.parts
    if not parts:
        return False
    if parts[0] in FORBIDDEN_ROOT_DIRS:
        return True
    if posix in FORBIDDEN_EXACT_PATHS:
        return True
    if relative.suffix.lower() in FORBIDDEN_SUFFIXES:
        return True
    if "__pycache__" in parts:
        return True
    if posix.startswith("static/reports/") and posix not in ALLOWED_GENERATED_REPORT_PLACEHOLDERS:
        return True
    if relative.name in {".coverage", "coverage.xml"}:
        return True
    return False


def copy_full_source(source: Path, stage: Path) -> None:
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if excluded(relative) or item.is_symlink():
            continue
        destination = stage / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def copy_selected(source: Path, stage: Path, selected: set[str]) -> None:
    for relative_name in sorted(selected):
        source_file = source / relative_name
        if not source_file.is_file():
            raise FileNotFoundError(f"Påkrevd releasefil mangler: {relative_name}")
        destination = stage / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)


def write_manifest(stage: Path, profile: str) -> Path:
    files = []
    for path in sorted(stage.rglob("*")):
        if not path.is_file() or path.name == "DISTRIBUTION_MANIFEST.json":
            continue
        files.append(
            {
                "path": path.relative_to(stage).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    manifest = {
        "format": "ai-aksje-analyzer-distribution-manifest-v1",
        "version": VERSION,
        "profile": profile,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mutable_runtime_included": False,
        "files": files,
    }
    target = stage / "DISTRIBUTION_MANIFEST.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def create_zip(stage: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage).as_posix())


def require_valid(path: Path, profile: str) -> dict:
    result = validate_path(path, profile=profile)
    if not result["ok"]:
        formatted = "\n".join(f"{item['code']}: {item['path']} – {item['message']}" for item in result["issues"])
        raise RuntimeError(f"Distribusjonskontroll feilet for {path}:\n{formatted}")
    return result


def build(source: Path, output: Path) -> list[Path]:
    source = source.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    specs = (
        ("full", f"AI_Aksje_Analyzer_v{VERSION_FILE}_Safe_Distribution_FULL.zip", None),
        ("update", f"AI_Aksje_Analyzer_v{VERSION_FILE}_ONLY_CHANGED_FILES.zip", UPDATE_FILES),
        ("migration", f"AI_Aksje_Analyzer_v{VERSION_FILE}_MIGRATION_TOOLS.zip", MIGRATION_FILES),
    )
    built: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="aa_dist_build_") as temp_dir:
        temp_root = Path(temp_dir)
        for profile, filename, selected in specs:
            stage = temp_root / profile
            stage.mkdir(parents=True)
            if selected is None:
                copy_full_source(source, stage)
            else:
                copy_selected(source, stage, selected)
            write_manifest(stage, profile)
            require_valid(stage, profile)
            archive = output / filename
            create_zip(stage, archive)
            require_valid(archive, profile)
            built.append(archive)

    checksum_file = output / f"SHA256SUMS_v{VERSION_FILE}.txt"
    checksum_file.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in built),
        encoding="utf-8",
    )
    built.append(checksum_file)
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description="Bygg trygge v19.0.19a-distribusjonspakker.")
    parser.add_argument("--source", default=str(PROJECT_ROOT))
    parser.add_argument("--output", default=str(PROJECT_ROOT / "dist"))
    args = parser.parse_args()
    built = build(Path(args.source), Path(args.output))
    for path in built:
        print(f"{path.name}: {path.stat().st_size} byte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
