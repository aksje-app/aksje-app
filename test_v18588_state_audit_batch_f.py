import app_version
from safety_audit import get_feature_registry
from state_audit import build_paper_state_snapshot, validate_buy_order


def test_app_version_v18588_state_audit():
    assert app_version.get_app_version() == "v18.5.89"
    assert "UI/Data Trust" in app_version.get_app_build_label()


def test_state_snapshot_cash_and_positions_value():
    portfolio = {
        "cash": 1000,
        "positions": {"ABC": {"shares": 2, "entry_price": 100, "last_price": 125}},
        "trades": [],
    }
    snap = build_paper_state_snapshot(portfolio)
    assert snap["cash"] == 1000
    assert snap["buying_power"] == 1000
    assert snap["positions_value"] == 250
    assert snap["total_value"] == 1250


def test_validate_buy_order_blocks_overspend_and_duplicates():
    portfolio = {"cash": 500, "positions": {"ABC": {"shares": 1}}, "trades": []}
    ok, msg = validate_buy_order(portfolio, ticker="XYZ", price=10, amount=600, safety_mode=True)
    assert not ok
    assert "Ikke nok cash" in msg
    ok, msg = validate_buy_order(portfolio, ticker="ABC", price=10, amount=100, allow_existing=False)
    assert not ok
    assert "eies allerede" in msg


def test_feature_registry_contains_state_and_failsafe():
    keys = {item["key"] for item in get_feature_registry()}
    assert {"state_audit", "trading_fail_safe"}.issubset(keys)
