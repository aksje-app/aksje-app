from unittest.mock import patch
from services import production_routing


def test_portfolio_view_reuses_verified_snapshot():
    family = "super_portfolio"
    account = {"cash": 1000, "initial_cash": 1000, "positions": {}, "trades": [], "realized_pnl": 0}
    doc = {"account": account, "events": []}
    chosen = {"approval": {"period_id": "test-period", "settings": {}},
              "bundle": {"accounts": {family: doc}, "production_controls": {family: {"status": "RUNNING"}}}}
    calls = []

    def report(family_arg, *, storage, at=None):
        calls.append(storage.read_json(__import__("services.portfolio_accounting", fromlist=["key"]).key(family_arg)))
        return {"new_period": {"verification": {"verified_nav": 1000, "converted_position_values": {}, "verified_net_return_pct": 0}}}

    with patch.object(production_routing.control, "selected", return_value=chosen), patch("services.portfolio_accounting.report", side_effect=report):
        result = production_routing.view(family)
    assert calls == [doc]
    assert result["portfolio_value"] == 1000
