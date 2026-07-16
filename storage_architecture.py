"""Central runtime storage layout for v18.6.77.

Git-tracked project files stay in the repository. Mutable runtime data is rooted
at APP_RUNTIME_ROOT (default: .app_runtime) and split into data, cache, logs,
backups and tmp. The module also provides safe backup/restore helpers.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent


def _root_from_env() -> Path:
    raw = os.getenv("APP_RUNTIME_ROOT", ".app_runtime").strip() or ".app_runtime"
    path = Path(raw).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    data: Path
    services: Path
    cache: Path
    logs: Path
    backups: Path
    tmp: Path
    config: Path

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def get_runtime_paths(create: bool = True) -> RuntimePaths:
    root = _root_from_env()
    paths = RuntimePaths(
        root=root,
        data=root / "data",
        services=root / "data" / "services",
        cache=root / "cache",
        logs=root / "logs",
        backups=root / "backups",
        tmp=root / "tmp",
        config=PROJECT_ROOT / "config",
    )
    if create:
        for path in (paths.root, paths.data, paths.services, paths.cache, paths.logs, paths.backups, paths.tmp):
            path.mkdir(parents=True, exist_ok=True)
    return paths


def runtime_data_path(*parts: str) -> Path:
    return get_runtime_paths().data.joinpath(*parts)


def runtime_cache_path(*parts: str) -> Path:
    return get_runtime_paths().cache.joinpath(*parts)


def runtime_log_path(*parts: str) -> Path:
    return get_runtime_paths().logs.joinpath(*parts)


def runtime_backup_path(*parts: str) -> Path:
    return get_runtime_paths().backups.joinpath(*parts)


def storage_manifest() -> dict:
    paths = get_runtime_paths()
    return {
        "version": "v18.6.77",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_paths": paths.to_dict(),
        "policy": {
            "github": ["source code", "config templates", "documentation", "folder placeholders"],
            "runtime": ["paper portfolio", "learning data", "alerts", "performance metrics", "cache", "logs"],
            "secrets": "environment variables or Streamlit secrets only",
        },
    }


def write_manifest() -> Path:
    target = get_runtime_paths().root / "runtime_manifest.json"
    target.write_text(json.dumps(storage_manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def create_runtime_backup(destination: str | Path | None = None) -> Path:
    paths = get_runtime_paths()
    write_manifest()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = Path(destination) if destination else paths.backups / f"runtime_backup_{stamp}.zip"
    target = target.expanduser()
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths.root.rglob("*"):
            if not path.is_file() or target == path:
                continue
            if paths.backups in path.parents:
                continue
            archive.write(path, path.relative_to(paths.root))
    return target


def restore_runtime_backup(backup_file: str | Path, *, overwrite: bool = False) -> Path:
    paths = get_runtime_paths()
    source = Path(backup_file).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="aa_restore_", dir=str(paths.tmp)) as tmp_dir:
        tmp = Path(tmp_dir)
        with zipfile.ZipFile(source, "r") as archive:
            for member in archive.infolist():
                resolved = (tmp / member.filename).resolve()
                if tmp.resolve() not in resolved.parents and resolved != tmp.resolve():
                    raise ValueError(f"Unsafe backup member: {member.filename}")
            archive.extractall(tmp)
        for item in tmp.rglob("*"):
            if not item.is_file():
                continue
            relative = item.relative_to(tmp)
            destination = paths.root / relative
            if destination.exists() and not overwrite:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
    return paths.root


def migrate_legacy_runtime(dry_run: bool = True) -> list[dict[str, str]]:
    """Copy known legacy runtime folders into .app_runtime without deleting originals."""
    paths = get_runtime_paths()
    mappings: Iterable[tuple[Path, Path]] = (
        (PROJECT_ROOT / "data", paths.data),
        (PROJECT_ROOT / "cache", paths.cache),
        (PROJECT_ROOT / "logs", paths.logs),
        (PROJECT_ROOT / "storage", paths.data / "legacy_storage"),
        (PROJECT_ROOT / "runtime", paths.data / "legacy_runtime"),
    )
    actions: list[dict[str, str]] = []
    for source, destination in mappings:
        if not source.exists() or source.resolve() == paths.root.resolve():
            continue
        for item in source.rglob("*"):
            if not item.is_file() or item.name == ".gitkeep":
                continue
            relative = item.relative_to(source)
            target = destination / relative
            actions.append({"source": str(item), "destination": str(target), "status": "planned" if dry_run else "copied"})
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(item, target)
    return actions
