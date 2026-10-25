"""Check the explicit, uninstalled model proposals against the existing engine."""
import json
from pathlib import Path
import pytest
from services.trading_costs import calculate, validate_family

PROPOSALS = json.loads((Path(__file__).resolve().parents[1]/'docs/nok-produksjonsstart-20261025/cost-policy-proposals.json').read_text())


@pytest.mark.parametrize('family,gross,fee,base,fx,price', [
    ('paper',10010,30.03,5.005,25.025,100.1),
    ('autonomy',10000,45,20,25,100),
    ('super_portfolio',10000,35,10,25,100),
])
def test_documented_foreign_proposal_has_one_base_charge_and_one_fx_charge(family,gross,fee,base,fx,price):
    proposal = PROPOSALS['policies'][family]
    assert proposal['status'] == 'PROPOSED_NOT_APPROVED_OR_INSTALLED'
    policy = proposal['policy']
    validate_family(policy,family,{'transaction_cost_bps':10})
    result = calculate(policy,quantity=10,reference_price=100,side='BUY',currency='USD',nok_rate=10)
    assert result['gross_nok'] == pytest.approx(gross)
    assert result['fee_nok'] == pytest.approx(fee)
    assert result['price'] == pytest.approx(price)
    assert result['cost_components'] == pytest.approx({'model_transaction_cost_nok':base,'fx_cost_nok':fx})


@pytest.mark.parametrize('family,base', [('paper',5),('autonomy',20),('super_portfolio',10)])
def test_no_conversion_for_nok_and_slippage_is_only_in_price(family,base):
    policy = PROPOSALS['policies'][family]['policy']
    buy = calculate(policy,quantity=10,reference_price=100,side='BUY',currency='NOK',nok_rate=1)
    sell = calculate(policy,quantity=10,reference_price=100,side='SELL',currency='NOK',nok_rate=1)
    assert buy['cost_calculation']['fx_treatment'] == sell['cost_calculation']['fx_treatment'] == 'NO_CURRENCY_CONVERSION'
    for result in (buy,sell):
        assert result['cost_components']['fx_cost_nok'] == 0
        assert result['fee_nok'] == pytest.approx(result['gross_nok']*base/10000)
    assert buy['price'] == pytest.approx(100.1 if family=='paper' else 100)
    assert sell['price'] == pytest.approx(99.9 if family=='paper' else 100)
