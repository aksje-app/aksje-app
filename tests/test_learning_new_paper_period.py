"""Learning Pushover must never mix legacy 300k Paper rules with new NOK period."""
import sys
import types

import controlled_parameter_learning as learning


def test_new_paper_notification_uses_verified_period_only(monkeypatch):
    chosen = types.ModuleType("services.production_restart")
    chosen.selected = lambda family, require_running=False: {
        "pointer": {"period_id": "nok-20261025T012118Z"}}
    reporter = types.ModuleType("services.restart_reporting")
    reporter.snapshot = lambda period, family: {"account": {"new_period": {
        "opening_nav_nok": 100000, "period_net_pnl_nok": 0,
        "verification": {"verified_nav": 100000, "verified_net_return_pct": 0}}}}
    monkeypatch.setitem(sys.modules, "services.production_restart", chosen)
    monkeypatch.setitem(sys.modules, "services.restart_reporting", reporter)
    line = learning._verified_new_paper_result_line()
    assert "100,000 NOK" in line
    assert "0 NOK" in line
    assert "+0.00%" in line
    assert "300,000" not in line
    assert "-66.67%" not in line


def test_unverified_period_never_falls_back_to_legacy_loss(monkeypatch):
    chosen = types.ModuleType("services.production_restart")
    chosen.selected = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "services.production_restart", chosen)
    line = learning._verified_new_paper_result_line()
    assert "Verifisert saldo er ikke tilgjengelig" in line
    assert "-66.67%" not in line
