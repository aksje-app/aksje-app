from pathlib import Path

import app_version
from safety_audit import get_feature_registry, run_static_regression_checks, add_audit_event


def test_app_version_v18587():
    assert app_version.get_app_version() == "v18.5.89"
    assert "UI/Data Trust" in app_version.get_app_build_label()


def test_static_ui_regression_anchors_present():
    result = run_static_regression_checks(Path(__file__).resolve().parent)
    assert result["ok"], result


def test_feature_registry_contains_core_controls():
    keys = {item["key"] for item in get_feature_registry()}
    assert {"global_update", "paper_capital", "auto_buy_safety_mode", "pushover_verify", "regression_smoke"}.issubset(keys)


def test_audit_event_never_raises():
    record = add_audit_event("regression_test", {"ok": True})
    assert record["event"] == "regression_test"
    assert record["level"] == "INFO"
