from portfolio_history_optimizer import STOPS,HOLDS,optimize
def test_budget_and_no_fake_data():
    assert len(STOPS)*len(HOLDS)==200
    assert optimize([],"AUTONOMY")["status"]=="INSUFFICIENT_HISTORY"
    assert optimize([],"SUPER_PORTFOLIO")["status"]=="INSUFFICIENT_HISTORY"
def test_no_invalid_portfolio():
    import pytest
    with pytest.raises(ValueError):optimize([],"SUPERFUND")
