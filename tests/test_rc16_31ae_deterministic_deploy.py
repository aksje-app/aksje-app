from pathlib import Path

import pytest

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from tools.verify_dependency_lock import read_pins, verify


ROOT = Path(__file__).resolve().parents[1]


def test_release_identity_advances_only_deploy_stabilization():
    assert APP_VERSION == "v19.22.0-rc16.31ae"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.31ad"


def test_production_roots_and_complete_lock_are_exact_and_installed():
    direct = read_pins(ROOT / "requirements.txt")
    locked = read_pins(ROOT / "requirements.lock")
    assert len(direct) == 19
    assert len(locked) == 70
    assert set(direct) <= set(locked)
    assert verify()["ok"] is True


def test_unpinned_requirement_is_rejected(tmp_path: Path):
    unsafe = tmp_path / "requirements.lock"
    unsafe.write_text("pandas\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ikke en eksakt"):
        read_pins(unsafe)


def test_all_three_render_services_use_identical_cache_free_lock_build():
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    command = (
        "buildCommand: python -m pip install --disable-pip-version-check "
        "--no-cache-dir -r requirements.lock && python tools/verify_dependency_lock.py "
        "&& python tools/check_runtime_dependencies.py"
    )
    assert render.count(command) == 3
    assert render.count("autoDeployTrigger: commit") == 3
    assert render.count("value: 3.12.13") == 3
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12.13"


def test_scanner_service_keeps_unambiguous_blueprint_name():
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "name: aksje-app-report-scheduler" in render
    assert "name: aksje-app-paper-scanner" in render
    assert "startCommand: python scheduled_runner.py" in render
    assert "startCommand: python scanner_worker.py" in render


def test_legacy_naive_scanner_timestamp_remains_safe():
    import cron_control

    parsed = cron_control._parse_iso("2026-08-24T08:30:00")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0
