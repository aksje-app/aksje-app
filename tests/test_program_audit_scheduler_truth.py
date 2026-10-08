import scheduled_runner as scheduler


def test_super_portfolio_failure_cannot_be_reported_as_clean_success():
    state = {'state': 'RUNNING', 'paper_scanner': {'state': 'MARKET_CLOSED'},
             'super_portfolio': {'state': 'FAILED', 'error': 'source failure'}}
    assert scheduler._derive_overall_state(state) == 'COMPLETED_WITH_WARNINGS'
    assert 'super_portfolio:FAILED' in state['degraded_components']


def test_expected_closed_market_is_not_a_failure():
    state = {'state': 'RUNNING', 'paper_scanner': {'state': 'MARKET_CLOSED'},
             'super_portfolio': {'state': 'NOT_DUE'}}
    assert scheduler._derive_overall_state(state) == 'COMPLETED'
