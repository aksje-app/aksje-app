from pathlib import Path

import app_version
from governance_registry import get_changelog, get_protected_zones
from safety_audit import get_feature_registry, run_static_regression_checks


def test_app_version_v18587_governance():
    assert app_version.get_app_version() == "v18.5.89"
    assert "UI/Data Trust" in app_version.get_app_build_label()


def test_governance_registry_has_protected_zones_and_changelog():
    zones = {item["key"] for item in get_protected_zones()}
    assert {"global_update_topbar", "paper_capital_controls", "pushover_alert_controls", "safety_mode_guardrail"}.issubset(zones)
    versions = [item["version"] for item in get_changelog()]
    assert versions[0] == "v18.5.89"
    assert "v18.5.86" in versions


def test_feature_registry_contains_governance_controls():
    keys = {item["key"] for item in get_feature_registry()}
    assert {"protected_zones", "in_app_changelog", "feature_governance"}.issubset(keys)


def test_static_regression_includes_governance_anchor():
    result = run_static_regression_checks(Path(__file__).resolve().parent)
    assert result["ok"], result
