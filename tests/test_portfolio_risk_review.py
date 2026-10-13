from copy import deepcopy
import pytest

from portfolio_risk_review import review_existing_position, review_portfolio


@pytest.mark.parametrize("engine", ["super_portfolio", "autonomi", "superfond"])
def test_all_portfolios_can_review_existing_positions_without_cash(engine):
    positions={"ABC":{"entry_price":100,"last_price":98.5,"peak_price":103}}
    original=deepcopy(positions)
    result=review_portfolio(engine,positions,{"ABC":{"current_price":98.5,
        "score_change":-5,"relative_return_pct":-2,
        "thesis_valid":True,"data_fresh":True}})
    assert positions==original
    assert len(result)==1 and result[0]["action"]=="OVERVAAK"
    assert result[0]["execution_authorized"] is False


def test_hard_stop_is_advisory_even_when_triggered():
    r=review_existing_position(ticker="ABC",entry_price=100,
        current_price=96,stop_triggered=True,data_fresh=True)
    assert r["action"]=="SELG" and r["execution_authorized"] is False


def test_missing_price_never_authorizes_sale():
    r=review_existing_position(ticker="ABC",entry_price=100,
        current_price=None,stop_triggered=True,data_fresh=False)
    assert r["action"]=="OVERVAAK"


def test_position_cap_and_invalid_thesis_require_review():
    x=review_existing_position(ticker="A",entry_price=100,current_price=99,
        thesis_valid=False,score_change=-2)
    assert x["action"]=="REDUSER"
    y=review_existing_position(ticker="B",entry_price=100,current_price=101,
        position_weight_pct=16,position_cap_pct=15)
    assert y["action"]=="REDUSER"


def test_unknown_evidence_does_not_guess_sell_or_hold():
    r=review_existing_position(ticker="A",entry_price=100,current_price=99)
    assert r["action"]=="OVERVAAK"
    assert "INCOMPLETE_RISK_EVIDENCE" in r["reason_codes"]
