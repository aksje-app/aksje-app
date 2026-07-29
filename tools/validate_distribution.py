#!/usr/bin/env python3
"""Validate AI Aksje Analyzer release directories and ZIP archives.

The validator is intentionally dependency-free so it can run before deploy.
It rejects mutable runtime state, generated reports, local secrets, databases,
unsafe archive paths and common credential formats.
"""
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

EXPECTED_VERSION = "v19.14.3"

FORBIDDEN_ROOT_DIRS = {
    ".git",
    ".app_runtime",
    ".pytest_cache",
    ".render",
    "build",
    "cache",
    "data",
    "dist",
    "htmlcov",
    "logs",
    "local_runtime",
    "old_work_d",
    "runtime",
    "runtime_data",
    "storage",
}

FORBIDDEN_EXACT_PATHS = {
    ".env",
    ".streamlit/secrets.toml",
    "paper_portfolio.json",
    "app_users.json",
    "remember_tokens.json",
    "app_settings.json",
    "alert_state.json",
    "trading_rules.json",
    "strategy_test_logs.json",
    "strategy_profiles.json",
    "runtime_audit_log.jsonl",
    "runtime_manifest.json",
}

FORBIDDEN_SUFFIXES = {
    ".db",
    ".dump",
    ".log",
    ".pyo",
    ".pyc",
    ".sqlite",
    ".sqlite3",
    ".tmp",
    ".zip",
    ".tar",
    ".gz",
}

GENERATED_REPORT_PREFIX = "static/reports/"
ALLOWED_GENERATED_REPORT_PLACEHOLDERS = {
    "static/reports/.gitkeep",
    "static/reports/README.md",
}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "DATABASE_PASSWORD",
        re.compile(r"\bpostgres(?:ql)?://[^\s:/]+:[^\s@/]+@[^\s]+", re.IGNORECASE),
    ),
)

TEXT_SUFFIXES = {
    ".bat", ".cfg", ".css", ".csv", ".env", ".example", ".html",
    ".ini", ".js", ".json", ".md", ".py", ".sh", ".toml", ".txt",
    ".yaml", ".yml",
}

PROFILE_REQUIRED_FILES = {
    "full": {
        "RELEASE_NOTES_v19.14.3.md", "ACCEPTANCE_v19.14.3.md", "DEPLOY_v19.14.3.md",
        "app.py", "app_version.py", "requirements.txt", ".env.example",
        "services/storage_service.py", "services/persistence_service.py",
        "repositories/base.py", "repositories/application.py", "domain/persistence.py",
        "pages/overview.py", "pages/analysis.py", "pages/ranking.py", "pages/paper_trading.py",
        "pages/top_picks.py", "pages/long_engine.py", "pages/autonomy.py", "pages/trading.py",
        "pages/strategy_versions.py", "pages/strategy_lab.py", "ui/candidate_cards.py", "ui/live_market_banner.py",
        "ui/legacy_context.py", "ui/global_styles.py", "app_core/context.py",
        "domain/strategy_versioning.py", "domain/market_snapshot.py", "domain/strategy_contract.py", "domain/strategy_account.py", "services/strategy_registry_service.py", "services/strategy_binding.py",
        "services/market_snapshot_service.py", "services/technical_signal_service.py", "services/parallel_strategy_service.py",
        "services/strategy_account_service.py", "services/simulated_execution_service.py",
        "services/autonomy_activation_service.py", "services/autonomy_learning_account_service.py", "services/evaluation_export_service.py", "services/autonomy_technical_contribution_service.py",
        "services/strategy_outcome_service.py",
        "domain/strategy_lab.py", "domain/strategy_promotion.py", "services/technical_quality_service.py", "services/strategy_lab_service.py",
        "services/strategy_promotion_service.py", "services/production_strategy_service.py",
        "services/quality_evidence_normalizer.py", "services/paper_quality_enrichment_service.py", "services/strategy_outcome_service.py",
        "strategies/technical_benchmark.py", "strategies/autonomy_strategy.py", "strategies/technical_quality_challenger.py", "signal_engine.py", "scanner_worker.py",
        "migrations/migrate_legacy_storage.py", "tools/export_persistent_storage_v1920.py",
        "tools/import_persistent_storage_v1920.py", "operational_telemetry.py", "report_contracts.py", "report_integrity.py",
        "decision_report.py", "decision_intelligence.py", "controlled_parameter_learning.py", "market_universe.py", "investment_pipeline.py", "autonomous_decision_reduction.py", "norwegian_report_language.py",
        "autonomy_modes.py", "autonomous_orchestrator.py", "autonomous_portfolio.py", "insider_intelligence.py", "official_insider_sources.py",
        "autonomi_core/runtime/orchestrator.py", "autonomi_core/runtime/full_execution.py",
        "autonomi_core/portfolio_decisions/layer.py", "autonomi_core/portfolio_decisions/decision_funnel.py", "autonomi_core/learning_reporting/top_picks.py",
        "autonomy_overview.py", "RELEASE_NOTES_v19.14.2.md", "DEPLOY_v19.14.2.md",
        "DISTRIBUTION_SECURITY_POLICY_v19.14.2.md", "MIGRATION_v19.14.2.md", "ACCEPTANCE_v19.14.2.md",
        "tools/migrate_strategy_accounts_v1980.py", "tools/export_strategy_evaluation_v1980.py", "tools/export_strategy_evaluation_v1990.py",
        "tools/migrate_strategy_lab_v19100.py", "tools/export_strategy_evaluation_v19100.py",
        "tools/migrate_strategy_comparison_v19110.py", "tools/export_strategy_evaluation_v19110.py",
        "tools/migrate_strategy_promotion_v19120.py", "tools/export_strategy_evaluation_v19120.py",
        "services/paper_migration_service.py", "tools/migrate_paper_foundation_v19130.py",
        "runtime_safety.py", "paper_trading_guard.py", "paper_store.py", "trading_engine.py",
        "runtime_background.py", "notifier.py", "auth.py", "render.yaml", "pytest.ini",
        "tests/test_v19142_runtime_safety.py", "tests/test_clean_startup_imports_v19142.py",
        "tools/smoke_start_app_v19142.py", "tools/verify_runtime_v19142.py",
        "TEST_REPORT_v19.14.2.md", "V19_14_2_IMPLEMENTATION_AND_VERIFICATION.md",
        "tools/validate_distribution.py", "tools/prepare_safe_upgrade.py", "DISTRIBUTION_MANIFEST.json",
    },
    "update": {
        "RELEASE_NOTES_v19.14.3.md", "ACCEPTANCE_v19.14.3.md", "DEPLOY_v19.14.3.md",
        "app.py", "app_version.py", "autonomy_overview.py", "controlled_parameter_learning.py",
        "daily_user_experience.py", "decision_intelligence.py", "decision_report.py",
        "market_intelligence.py", "market_universe.py", "investment_pipeline.py", "autonomous_decision_reduction.py", "norwegian_report_language.py", "report_contracts.py", "report_integrity.py", "ui/candidate_cards.py", "ui/live_market_banner.py", "safety_audit.py",
        "autonomy_modes.py", "autonomous_orchestrator.py", "autonomous_portfolio.py", "insider_intelligence.py", "official_insider_sources.py",
        "autonomi_core/runtime/orchestrator.py", "autonomi_core/runtime/full_execution.py",
        "autonomi_core/portfolio_decisions/layer.py", "autonomi_core/portfolio_decisions/decision_funnel.py", "autonomi_core/learning_reporting/top_picks.py",
        "app_core/context.py", "domain/strategy_versioning.py", "domain/market_snapshot.py", "domain/strategy_contract.py", "domain/strategy_account.py", "repositories/application.py",
        "services/service_registry.py", "services/strategy_registry_service.py", "services/strategy_binding.py",
        "services/market_snapshot_service.py", "services/technical_signal_service.py", "services/parallel_strategy_service.py",
        "services/strategy_account_service.py", "services/simulated_execution_service.py",
        "services/autonomy_activation_service.py", "services/autonomy_learning_account_service.py", "services/evaluation_export_service.py", "services/autonomy_technical_contribution_service.py",
        "services/strategy_outcome_service.py",
        "domain/strategy_lab.py", "domain/strategy_promotion.py", "services/technical_quality_service.py", "services/strategy_lab_service.py",
        "services/strategy_promotion_service.py", "services/production_strategy_service.py",
        "services/quality_evidence_normalizer.py", "services/paper_quality_enrichment_service.py", "services/strategy_outcome_service.py",
        "strategies/technical_benchmark.py", "strategies/autonomy_strategy.py", "strategies/technical_quality_challenger.py", "signal_engine.py", "scanner_worker.py",
        "pages/autonomy.py", "pages/strategy_versions.py", "pages/strategy_lab.py", "ui/global_styles.py", "trading_engine.py",
        "autonomous_portfolio.py", "operations_ui.py", "scheduler_background.py", "scheduled_runner.py", ".streamlit/config.toml",
        "RELEASE_NOTES_v19.14.2.md", "DEPLOY_v19.14.2.md",
        "DISTRIBUTION_SECURITY_POLICY_v19.14.2.md", "MIGRATION_v19.14.2.md", "ACCEPTANCE_v19.14.2.md",
        "tools/migrate_strategy_accounts_v1980.py", "tools/export_strategy_evaluation_v1980.py", "tools/export_strategy_evaluation_v1990.py",
        "tools/migrate_strategy_lab_v19100.py", "tools/export_strategy_evaluation_v19100.py",
        "tools/migrate_strategy_comparison_v19110.py", "tools/export_strategy_evaluation_v19110.py",
        "tools/migrate_strategy_promotion_v19120.py", "tools/export_strategy_evaluation_v19120.py",
        "services/paper_migration_service.py", "tools/migrate_paper_foundation_v19130.py",
        "runtime_safety.py", "paper_trading_guard.py", "paper_store.py", "trading_engine.py",
        "runtime_background.py", "notifier.py", "auth.py", "render.yaml", "pytest.ini",
        "tests/test_v19142_runtime_safety.py", "tests/test_clean_startup_imports_v19142.py",
        "tools/smoke_start_app_v19142.py", "tools/verify_runtime_v19142.py",
        "TEST_REPORT_v19.14.2.md", "V19_14_2_IMPLEMENTATION_AND_VERIFICATION.md",
        "tools/validate_distribution.py", "tools/prepare_safe_upgrade.py", "DISTRIBUTION_MANIFEST.json",
    },
    "migration": {
        "app_version.py", "migrations/migrate_legacy_storage.py", "services/__init__.py", "services/storage_service.py",
        "services/persistence_service.py", "services/strategy_registry_service.py", "services/strategy_binding.py", "services/strategy_promotion_service.py",
        "storage_architecture.py", "utils.py", "repositories/base.py", "repositories/application.py",
        "domain/persistence.py", "domain/strategy_versioning.py", "domain/market_snapshot.py", "domain/strategy_account.py", "domain/strategy_lab.py", "domain/strategy_promotion.py",
        "services/strategy_account_service.py", "services/simulated_execution_service.py",
        "services/autonomy_activation_service.py", "services/autonomy_learning_account_service.py", "services/evaluation_export_service.py", "services/autonomy_technical_contribution_service.py",
        "services/strategy_outcome_service.py",
        "tools/export_persistent_storage_v1920.py",
        "tools/import_persistent_storage_v1920.py", "tools/migrate_strategy_accounts_v1980.py", "tools/export_strategy_evaluation_v1980.py", "tools/export_strategy_evaluation_v1990.py",
        "tools/migrate_strategy_lab_v19100.py", "tools/export_strategy_evaluation_v19100.py",
        "tools/migrate_strategy_comparison_v19110.py", "tools/export_strategy_evaluation_v19110.py",
        "tools/migrate_strategy_promotion_v19120.py", "tools/export_strategy_evaluation_v19120.py",
        "services/paper_migration_service.py", "tools/migrate_paper_foundation_v19130.py",
        "MIGRATION_v19.14.2.md", "DEPLOY_v19.14.2.md",
        "DISTRIBUTION_SECURITY_POLICY_v19.14.2.md", "tools/prepare_safe_upgrade.py",
        "tools/restore_safe_upgrade_backup.py", "tools/validate_distribution.py", "DISTRIBUTION_MANIFEST.json",
    },
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


def _iter_directory(root: Path) -> Iterator[FileEntry]:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            yield FileEntry(name=path.relative_to(root).as_posix(), size=-1)
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        content = None
        if path.stat().st_size <= 2_000_000 and _is_text_candidate(relative):
            content = path.read_bytes()
        yield FileEntry(name=relative, size=path.stat().st_size, content=content)


def _iter_zip(archive_path: Path) -> Iterator[FileEntry]:
    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            raw_name = info.filename
            if _unsafe_archive_path(raw_name):
                yield FileEntry(name=f"__UNSAFE__:{raw_name}", size=info.file_size)
                continue
            name = _normalise_name(raw_name)
            content = None
            if info.file_size <= 2_000_000 and _is_text_candidate(name):
                content = archive.read(info)
            yield FileEntry(name=name, size=info.file_size, content=content)


def _is_text_candidate(name: str) -> bool:
    path = Path(name)
    if path.name in {".env", ".env.example", ".gitignore"}:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def _scan_secret_content(name: str, content: bytes | None) -> list[ValidationIssue]:
    if content is None:
        return []
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return []
    issues: list[ValidationIssue] = []
    for code, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            issues.append(
                ValidationIssue(
                    code=f"SECRET_{code}",
                    path=name,
                    message="Filen ser ut til å inneholde en virkelig hemmelighet eller legitimasjon.",
                )
            )
    return issues


def validate_entries(entries: Iterable[FileEntry], profile: str = "full") -> dict:
    issues: list[ValidationIssue] = []
    names: set[str] = set()
    total_size = 0

    for entry in entries:
        name = _normalise_name(entry.name)
        names.add(name)
        total_size += max(0, entry.size)

        if entry.name.startswith("__UNSAFE__:"):
            issues.append(
                ValidationIssue("UNSAFE_ARCHIVE_PATH", entry.name.split(":", 1)[1], "Arkivstien kan skrive utenfor målmappen.")
            )
            continue

        parts = PurePosixPath(name).parts
        root = parts[0] if parts else ""

        if entry.size == -1:
            issues.append(ValidationIssue("SYMLINK", name, "Symbolske lenker er ikke tillatt i distribusjonen."))
        if root in FORBIDDEN_ROOT_DIRS:
            issues.append(ValidationIssue("MUTABLE_RUNTIME", name, f"Rotmappen '{root}' inneholder eller kan inneholde mutable produksjonsdata."))
        if name in FORBIDDEN_EXACT_PATHS:
            issues.append(ValidationIssue("FORBIDDEN_FILE", name, "Filen er lokal, sensitiv eller runtime-generert og skal ikke distribueres."))
        if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES:
            issues.append(ValidationIssue("GENERATED_FILE", name, "Genererte logger, databaser, midlertidige filer eller bytekode er ikke tillatt."))
        if GENERATED_REPORT_PREFIX in name and name not in ALLOWED_GENERATED_REPORT_PLACEHOLDERS:
            issues.append(ValidationIssue("GENERATED_REPORT", name, "Genererte rapporter skal ikke ligge i installasjonspakken."))
        if "__pycache__" in parts:
            issues.append(ValidationIssue("PYTHON_CACHE", name, "Python-cache skal ikke distribueres."))

        issues.extend(_scan_secret_content(name, entry.content))

    required = PROFILE_REQUIRED_FILES.get(profile, set())
    for required_name in sorted(required - names):
        issues.append(ValidationIssue("MISSING_REQUIRED_FILE", required_name, f"Påkrevd fil mangler for profil '{profile}'."))

    version_text = ""
    for entry in entries if isinstance(entries, list) else []:
        if _normalise_name(entry.name) == "app_version.py" and entry.content:
            version_text = entry.content.decode("utf-8", errors="ignore")
            break
    if profile in {"full", "update"} and version_text and f'APP_VERSION = "{EXPECTED_VERSION}"' not in version_text:
        issues.append(ValidationIssue("VERSION_MISMATCH", "app_version.py", f"Forventet {EXPECTED_VERSION}."))

    unique = {(issue.code, issue.path, issue.message): issue for issue in issues}
    ordered = sorted(unique.values(), key=lambda item: (item.code, item.path))
    return {
        "ok": not ordered,
        "profile": profile,
        "expected_version": EXPECTED_VERSION,
        "file_count": len(names),
        "total_size_bytes": total_size,
        "issues": [asdict(issue) for issue in ordered],
    }


def validate_path(path: str | Path, profile: str = "full") -> dict:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {
            "ok": False,
            "profile": profile,
            "expected_version": EXPECTED_VERSION,
            "file_count": 0,
            "total_size_bytes": 0,
            "issues": [asdict(ValidationIssue("NOT_FOUND", str(target), "Distribusjonen finnes ikke."))],
        }
    entries = list(_iter_directory(target) if target.is_dir() else _iter_zip(target))
    return validate_entries(entries, profile=profile)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Valider en trygg AI Aksje Analyzer-distribusjon.")
    parser.add_argument("path", help="Mappe eller ZIP-fil som skal kontrolleres.")
    parser.add_argument("--profile", choices=sorted(PROFILE_REQUIRED_FILES), default="full")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Skriv maskinlesbart JSON-resultat.")
    args = parser.parse_args()

    result = validate_path(args.path, profile=args.profile)
    target = Path(args.path)
    if target.is_file():
        result["sha256"] = sha256_file(target)

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        state = "BESTÅTT" if result["ok"] else "FEILET"
        print(f"Distribusjonskontroll: {state}")
        print(f"Profil: {result['profile']}")
        print(f"Filer: {result['file_count']}")
        print(f"Størrelse: {result['total_size_bytes']} byte")
        if result.get("sha256"):
            print(f"SHA-256: {result['sha256']}")
        for issue in result["issues"]:
            print(f"- {issue['code']}: {issue['path']} – {issue['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
