#!/usr/bin/env python3
"""Validate clean AI Aksje Analyzer source and delta distributions."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator

from app_version import APP_VERSION

EXPECTED_VERSION = APP_VERSION
DOC_TAG = APP_VERSION.replace("-rc", "_RC")

FORBIDDEN_ROOT_DIRS = {
    ".git", ".app_runtime", ".pytest_cache", ".render", "build", "cache",
    "data", "dist", "htmlcov", "logs", "local_runtime", "old_work_d",
    "runtime", "runtime_data", "storage", "tmp", "__pycache__",
}
FORBIDDEN_EXACT_PATHS = {
    ".env", ".streamlit/secrets.toml", "paper_portfolio.json", "app_users.json",
    "remember_tokens.json", "app_settings.json", "alert_state.json",
    "trading_rules.json", "strategy_test_logs.json", "strategy_profiles.json",
    "runtime_audit_log.jsonl", "runtime_manifest.json",
}
FORBIDDEN_SUFFIXES = {
    ".db", ".dump", ".log", ".pyo", ".pyc", ".sqlite", ".sqlite3",
    ".tmp", ".tar", ".gz",
}
GENERATED_REPORT_PREFIX = "static/reports/"
ALLOWED_GENERATED_REPORT_PLACEHOLDERS = {
    "static/reports/.gitkeep", "static/reports/README.md",
    "COPY_TO_REPOSITORY/static/reports/.gitkeep",
    "COPY_TO_REPOSITORY/static/reports/README.md",
}
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("DATABASE_PASSWORD", re.compile(r"\bpostgres(?:ql)?://[^\s:/]+:[^\s@/]+@[^\s]+", re.I)),
)
TEXT_SUFFIXES = {
    ".bat", ".cfg", ".css", ".csv", ".env", ".example", ".html",
    ".ini", ".js", ".json", ".md", ".py", ".sh", ".toml", ".txt",
    ".yaml", ".yml",
}
PROFILE_REQUIRED_FILES = {
    "full": {
        "app.py", "app_version.py", "requirements.txt", "requirements-dev.txt",
        "render.yaml", ".env.example", "market_intelligence.py", "market_universe.py",
        "report_integrity.py", "decision_report.py", "evidence_contract.py",
        "evidence_search_status.py", "news_intelligence.py", "insider_intelligence.py", "notifier.py",
        f"RELEASE_NOTES_{DOC_TAG}.md", f"ACCEPTANCE_{DOC_TAG}.md", f"DEPLOY_{DOC_TAG}.md",
        "tests/test_v19150_full_system_stabilization.py",
        "tools/audit_full_system_v19150.py", "tools/audit_evidence_search_v19220_rc10.py",
        "tools/validate_distribution.py", "tools/build_safe_distribution.py", "DISTRIBUTION_MANIFEST.json",
        "autonomi_core/runtime/orchestrator.py", "autonomi_core/runtime/full_execution.py",
    },
    "update": {
        "README_APPLY_DELTA.md", f"CHANGE_INVENTORY_{DOC_TAG}.json", "DELETE_FILES.txt",
        "COPY_TO_REPOSITORY/app_version.py",
        f"COPY_TO_REPOSITORY/RELEASE_NOTES_{DOC_TAG}.md",
        "COPY_TO_REPOSITORY/tools/audit_full_system_v19150.py",
    },
    "migration": {"app_version.py", f"DEPLOY_{DOC_TAG}.md"},
}


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class FileEntry:
    name: str
    size: int
    content: bytes | None = None


def _normalise_name(raw: str) -> str:
    value = raw.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def _unsafe_archive_path(raw: str) -> bool:
    if raw.startswith(("/", "\\")) or "\\" in raw:
        return True
    path = PurePosixPath(raw)
    return path.is_absolute() or any(part == ".." for part in path.parts)


def _is_text_candidate(name: str) -> bool:
    path = Path(name)
    return path.name in {".env", ".env.example", ".gitignore"} or path.suffix.lower() in TEXT_SUFFIXES


def _iter_directory(root: Path) -> Iterator[FileEntry]:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            yield FileEntry(path.relative_to(root).as_posix(), -1)
        elif path.is_file():
            rel = path.relative_to(root).as_posix()
            content = path.read_bytes() if path.stat().st_size <= 2_000_000 and _is_text_candidate(rel) else None
            yield FileEntry(rel, path.stat().st_size, content)


def _iter_zip(archive_path: Path) -> Iterator[FileEntry]:
    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            if _unsafe_archive_path(info.filename):
                yield FileEntry(f"__UNSAFE__:{info.filename}", info.file_size)
                continue
            name = _normalise_name(info.filename)
            content = archive.read(info) if info.file_size <= 2_000_000 and _is_text_candidate(name) else None
            yield FileEntry(name, info.file_size, content)


def _scan_secret_content(name: str, content: bytes | None) -> list[ValidationIssue]:
    if content is None:
        return []
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return []
    return [
        ValidationIssue(f"SECRET_{code}", name, "Filen ser ut til å inneholde en virkelig hemmelighet eller legitimasjon.")
        for code, pattern in SECRET_PATTERNS if pattern.search(text)
    ]


def _is_forbidden_runtime_path(name: str) -> bool:
    parts = PurePosixPath(name).parts
    # Delta wrapper itself is safe; inspect everything below it.
    inspected = parts[1:] if parts and parts[0] == "COPY_TO_REPOSITORY" else parts
    return bool(inspected and inspected[0] in FORBIDDEN_ROOT_DIRS) or "__pycache__" in inspected


def validate_entries(entries: Iterable[FileEntry], profile: str = "full") -> dict:
    issues: list[ValidationIssue] = []
    names: set[str] = set()
    text_by_name: dict[str, str] = {}
    total_size = 0

    for entry in entries:
        name = _normalise_name(entry.name)
        names.add(name)
        total_size += max(0, entry.size)
        if name.startswith("__UNSAFE__:"):
            issues.append(ValidationIssue("UNSAFE_ARCHIVE_PATH", name.split(":", 1)[1], "Arkivstien kan skrive utenfor målmappen."))
            continue
        if entry.size == -1:
            issues.append(ValidationIssue("SYMLINK", name, "Symbolske lenker er ikke tillatt."))
        if _is_forbidden_runtime_path(name):
            issues.append(ValidationIssue("MUTABLE_RUNTIME", name, "Mutable runtime-data skal ikke distribueres."))
        inspected = name.removeprefix("COPY_TO_REPOSITORY/")
        if inspected in FORBIDDEN_EXACT_PATHS:
            issues.append(ValidationIssue("FORBIDDEN_FILE", name, "Lokal eller sensitiv fil skal ikke distribueres."))
        if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES:
            issues.append(ValidationIssue("GENERATED_FILE", name, "Generert logg, database, tempfil eller arkiv er ikke tillatt."))
        if GENERATED_REPORT_PREFIX in inspected and name not in ALLOWED_GENERATED_REPORT_PLACEHOLDERS:
            issues.append(ValidationIssue("GENERATED_REPORT", name, "Genererte rapporter skal ikke ligge i installasjonspakken."))
        issues.extend(_scan_secret_content(name, entry.content))
        if entry.content is not None:
            try:
                text_by_name[name] = entry.content.decode("utf-8")
            except UnicodeDecodeError:
                pass

    for required_name in sorted(PROFILE_REQUIRED_FILES.get(profile, set()) - names):
        issues.append(ValidationIssue("MISSING_REQUIRED_FILE", required_name, f"Påkrevd fil mangler for profil '{profile}'."))

    version_name = "COPY_TO_REPOSITORY/app_version.py" if profile == "update" else "app_version.py"
    version_text = text_by_name.get(version_name, "")
    if profile in {"full", "update"} and f'APP_VERSION = "{EXPECTED_VERSION}"' not in version_text:
        issues.append(ValidationIssue("VERSION_MISMATCH", version_name, f"Forventet {EXPECTED_VERSION}."))

    req_name = "COPY_TO_REPOSITORY/requirements.txt" if profile == "update" else "requirements.txt"
    requirements_text = text_by_name.get(req_name, "")
    if requirements_text:
        lines = {line.strip() for line in requirements_text.splitlines() if line.strip() and not line.lstrip().startswith("#")}
        if "pypdf==5.9.0" not in lines:
            issues.append(ValidationIssue("MISSING_PDF_DEPENDENCY", req_name, "pypdf==5.9.0 må være eksplisitt deklarert."))

    unique = {(item.code, item.path, item.message): item for item in issues}
    ordered = sorted(unique.values(), key=lambda item: (item.code, item.path))
    return {
        "ok": not ordered, "profile": profile, "expected_version": EXPECTED_VERSION,
        "file_count": len(names), "total_size_bytes": total_size,
        "issues": [asdict(item) for item in ordered],
    }


def validate_path(path: str | Path, profile: str = "full") -> dict:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"ok": False, "profile": profile, "expected_version": EXPECTED_VERSION,
                "file_count": 0, "total_size_bytes": 0,
                "issues": [asdict(ValidationIssue("NOT_FOUND", str(target), "Distribusjonen finnes ikke."))]}
    entries = list(_iter_directory(target) if target.is_dir() else _iter_zip(target))
    return validate_entries(entries, profile)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--profile", choices=sorted(PROFILE_REQUIRED_FILES), default="full")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = validate_path(args.path, args.profile)
    if Path(args.path).is_file():
        result["sha256"] = sha256_file(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else ("BESTÅTT" if result["ok"] else "FEILET"))
    if not args.as_json:
        for issue in result["issues"]:
            print(f"- {issue['code']}: {issue['path']} - {issue['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
