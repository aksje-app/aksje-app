"""Regression: signed restart selection is reused within a routing operation."""
from unittest.mock import patch
from services import production_routing as routing


def test_context_reuses_verified_selection_without_another_bundle_read():
    chosen = {
        "pointer": {"family": "super_portfolio", "period_id": "period1"},
        "approval": {"period_id": "period1", "settings": {}, "cost_policy": {}},
        "bundle": {"accounts": {"super_portfolio": {"account": {"positions": {}}, "events": []}}},
    }
    with patch.object(routing.control, "selected", side_effect=AssertionError("duplicate signed bundle read")):
        with patch("services.restart_trading.account_reference", return_value="ref"):
            result = routing.context("super_portfolio", "run1", [], chosen=chosen)
    assert result["account_ref"] == "ref"
    assert result["evidence"] == {}


def test_context_rejects_wrong_family_without_lookup():
    chosen = {"pointer": {"family": "paper"}}
    with patch.object(routing.control, "selected", side_effect=AssertionError("unexpected read")):
        try:
            routing.context("super_portfolio", "run1", [], chosen=chosen)
        except ValueError as exc:
            assert "family mismatch" in str(exc)
        else:
            raise AssertionError("wrong family accepted")
