from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from tools.prepare_safe_upgrade import create_backup
from tools.restore_safe_upgrade_backup import restore
from tools.validate_distribution import FileEntry, validate_entries, validate_path


def test_release_identity_is_safe_distribution_patch():
    assert APP_VERSION.startswith("v19.22.0-rc")
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc5"


def test_validator_rejects_runtime_secret_and_generated_report():
    entries = [
        FileEntry("app.py", 1, b"x"),
        FileEntry("app_version.py", 30, b'APP_VERSION = "v19.7.0"'),
        FileEntry("report_contracts.py", 1, b"x"),
        FileEntry("decision_report.py", 1, b"x"),
        FileEntry("requirements.txt", 0, b""),
        FileEntry(".env.example", 0, b""),
        FileEntry("RELEASE_NOTES_v19.7.0.md", 0, b""),
        FileEntry("DEPLOY_v19.7.0.md", 0, b""),
        FileEntry("tools/validate_distribution.py", 0, b""),
        FileEntry("tools/prepare_safe_upgrade.py", 0, b""),
        FileEntry("DISTRIBUTION_MANIFEST.json", 2, b"{}"),
        FileEntry(".app_runtime/data/portfolio.json", 2, b"{}"),
        FileEntry(".env", 35, b"OPENAI_API_KEY=" + b"sk-" + b"abcdefghijklmnopqrstuvwxyz"),
        FileEntry("static/reports/report_test.pdf", 4, None),
    ]
    result = validate_entries(entries, profile="full")
    assert result["ok"] is False
    codes = {item["code"] for item in result["issues"]}
    assert "MUTABLE_RUNTIME" in codes
    assert "FORBIDDEN_FILE" in codes
    assert "SECRET_OPENAI_KEY" in codes
    assert "GENERATED_REPORT" in codes


def test_validator_rejects_zip_slip(tmp_path: Path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../outside.txt", "unsafe")
    result = validate_path(archive, profile="migration")
    assert result["ok"] is False
    assert any(item["code"] == "UNSAFE_ARCHIVE_PATH" for item in result["issues"])


def test_backup_is_non_destructive_and_restore_is_checksum_verified(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app_version.py").write_text('APP_VERSION = "v19.0.19"\n', encoding="utf-8")
    runtime_file = project / ".app_runtime" / "data" / "portfolio.json"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text('{"cash": 100000}', encoding="utf-8")
    env_file = project / ".env"
    env_file.write_text("DATABASE_URL=postgresql://local\n", encoding="utf-8")

    backup_path = tmp_path / "backup.zip"
    archive, manifest = create_backup(project, backup_path)
    assert archive == backup_path
    assert runtime_file.exists()
    assert env_file.exists()
    assert len(manifest["files"]) == 2

    restore_root = tmp_path / "restored"
    result = restore(backup_path, restore_root)
    assert result["ok"] is True
    assert (restore_root / ".app_runtime" / "data" / "portfolio.json").read_text(encoding="utf-8") == '{"cash": 100000}'
    assert (restore_root / ".env").exists()

    manifest_from_zip = json.loads(zipfile.ZipFile(backup_path).read("backup_manifest.json"))
    assert all(item["sha256"] for item in manifest_from_zip["files"])


def test_mutable_test_runtime_is_excluded_from_distribution():
    # The full regression suite intentionally creates local runtime files. The
    # release invariant is therefore that every such file is excluded by the
    # packager, not that the working tree stays empty while tests are running.
    from tools.build_safe_distribution import excluded

    root = Path(__file__).resolve().parents[1]
    mutable_roots = [".app_runtime", "data", "cache", "logs", "runtime", "storage"]
    for root_name in mutable_roots:
        folder = root / root_name
        for path in folder.rglob("*") if folder.exists() else []:
            assert excluded(path.relative_to(root)) is True
    for sensitive in (root / ".env", root / ".streamlit" / "secrets.toml"):
        assert not sensitive.exists()
    report_dir = root / "static" / "reports"
    for path in report_dir.glob("*") if report_dir.exists() else []:
        if path.name != ".gitkeep":
            assert excluded(path.relative_to(root)) is True


def test_delta_never_requests_deletion_of_mutable_runtime(tmp_path: Path):
    from tools.build_safe_distribution import build

    baseline = tmp_path / "baseline"
    source = tmp_path / "source"
    output = tmp_path / "output"
    baseline.mkdir()
    source.mkdir()
    (baseline / "app.py").write_text("old\n", encoding="utf-8")
    (source / "app.py").write_text("new\n", encoding="utf-8")
    audit_file = source / "tools" / "audit_full_system_v19150.py"
    audit_file.parent.mkdir(parents=True)
    audit_file.write_text("def audit(): return {'ok': True}\n", encoding="utf-8")
    runtime_file = baseline / ".app_runtime" / "data" / "portfolio.json"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text('{"cash": 100000}', encoding="utf-8")
    cache_file = baseline / "__pycache__" / "app.cpython-313.pyc"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"compiled")

    result = build(source, baseline, output)
    with zipfile.ZipFile(result["delta_zip"], "r") as archive:
        delete_text = archive.read("DELETE_FILES.txt").decode("utf-8")
        inventory = json.loads(archive.read(f"CHANGE_INVENTORY_{APP_VERSION.replace('-rc', '_RC')}.json"))
        delta_names = set(archive.namelist())

    assert ".app_runtime" not in delete_text
    assert "__pycache__" not in delete_text
    assert inventory["delete_file_count"] == 0
    assert inventory["deleted"] == []
    assert "COPY_TO_REPOSITORY/tools/audit_full_system_v19150.py" in delta_names
    assert "tools/audit_full_system_v19150.py" in inventory["support_files"]
