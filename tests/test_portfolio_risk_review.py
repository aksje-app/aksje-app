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


def test_real_engine_state_adapters_are_read_only():
    from portfolio_risk_review import (
        review_super_portfolio_state, review_autonomi_state, review_superfond_state)
    from copy import deepcopy
    sp={"positions":{"ABC":{"entry_price":100,"last_price":98,
        "peak_price":103,"target_weight_pct":12}},"config":{"max_position_pct":15}}
    au={"positions":{"ABC":{"average_price":100,"last_price":99,"highest_price":101}}}
    sf={"cash":1000,"positions":{"FUND":{"entry_nok":100,"last_nok":99,"quantity":20}}}
    originals=deepcopy([sp,au,sf])
    assert review_super_portfolio_state(sp)[0]["action"]=="OVERVAAK"
    assert review_autonomi_state(au)[0]["action"]=="OVERVAAK"
    result=review_superfond_state(sf,position_cap_pct=12.5,
        evidence_by_id={"FUND":{"data_fresh":True}})
    assert result[0]["action"]=="REDUSER"
    assert [sp,au,sf]==originals
    assert not any(x["execution_authorized"] for x in result)


def test_each_engine_exposes_read_only_risk_preview():
    from super_portfolio import preview_existing_super_portfolio_risk
    from superfund_engine import preview_existing_superfund_risk
    from autonomous_portfolio import preview_existing_autonomi_risk
    sp={"config":{"max_position_pct":15},"positions":{"ABC":{
        "entry_price":100,"last_price":99,"target_weight_pct":5}}}
    sf={"cash":0,"positions":{"FUND":{
        "entry_nok":100,"last_nok":99,"quantity":10}}}
    au={"positions":{"XYZ":{"average_price":100,"last_price":99}}}
    assert preview_existing_super_portfolio_risk(sp)[0]["execution_authorized"] is False
    assert preview_existing_superfund_risk(sf)[0]["execution_authorized"] is False
    assert preview_existing_autonomi_risk(au)[0]["execution_authorized"] is False
