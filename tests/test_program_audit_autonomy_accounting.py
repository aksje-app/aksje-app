from copy import deepcopy
from dataclasses import replace

import autonomous_portfolio as ap


def run(monkeypatch, *, position_value=1000, max_positions=30, omit=None):
    params = replace(ap.AutonomousParameters(), initial_cash=100000,
        allow_additions=True, maximum_open_positions=max_positions,
        enable_learning_probe_buys=False, notify_trades=False, notify_risk_events=False)
    position = {'ticker': 'AAA', 'quantity': position_value / 100,
        'average_price': 100, 'last_price': 100, 'highest_price': 100,
        'sector': 'Technology', 'entry_score': 90,
        'opened_at': '2026-10-08T10:00:00+00:00', 'marker': 'preserve'}
    portfolio = {'cash': 100000 - position_value, 'positions': {'AAA': position},
        'status': 'ACTIVE', 'high_watermark': 100000, 'initial_cash': 100000}
    monkeypatch.setattr(ap, 'load_parameters', lambda: params)
    monkeypatch.setattr(ap, 'load_portfolio', lambda: deepcopy(portfolio))
    monkeypatch.setattr(ap, 'load_learning_portfolio', lambda: {'positions': {}, 'cash': 0})
    monkeypatch.setattr(ap, '_read', lambda path, default: deepcopy(default))
    for name in ('_write', '_append_audit', '_record_trade', '_record_decisions',
                 '_record_learning_decisions', '_append_equity_history',
                 '_append_learning_equity_history'):
        monkeypatch.setattr(ap, name, lambda *a, **kw: None)
    monkeypatch.setattr(ap, '_update_learning_positions', lambda *a: ([], []))
    # External snapshot/parallel analysis is outside this accounting scenario.
    monkeypatch.setattr(ap, 'get_market_snapshot_service', lambda: (_ for _ in ()).throw(RuntimeError('offline fixture')))
    row = {'ticker': 'AAA', 'investment_score': 90, 'risk_score': 10,
        'data_quality_score': 100, 'price': 100, 'sector': 'Technology',
        'portfolio_action': 'BUY', 'autonomy_outcome_code': 'KJØPSKANDIDAT',
        'valid_for_decision': True, 'evidence_valid_for_decision': True,
        'final_decision_ready': True}
    if omit:
        row.pop(omit)
    return ap.run_autonomous_cycle([row], 'ACCOUNTING-AUDIT')


def test_addition_preserves_shares_and_total_equity(monkeypatch):
    result = run(monkeypatch)
    portfolio = result['portfolio']
    assert ap.portfolio_equity(portfolio) == 100000
    assert portfolio['positions']['AAA']['quantity'] == 30
    assert portfolio['positions']['AAA']['marker'] == 'preserve'


def test_addition_cannot_exceed_total_position_cap(monkeypatch):
    result = run(monkeypatch, position_value=3000)
    assert not result['portfolio_trades']
    assert result['portfolio']['positions']['AAA']['quantity'] == 30
    assert ap.portfolio_equity(result['portfolio']) == 100000


def test_existing_position_addition_does_not_consume_new_slot(monkeypatch):
    result = run(monkeypatch, max_positions=1)
    assert result['portfolio_trades']
    assert result['portfolio']['positions']['AAA']['quantity'] == 30


def test_integrity_detects_lost_shares_even_without_new_trades():
    start = {'cash': 9000, 'positions': {'AAA': {'quantity': 10}}}
    corrupted = {'cash': 9000, 'positions': {'AAA': {'quantity': 5}}}
    result = ap._validate_execution_integrity([], {}, corrupted, starting_portfolio=start)
    assert result['ok'] is False
    assert 'beholdningen' in result['errors'][0]


def test_integrity_detects_cash_change_without_a_trade():
    start = {'cash': 9000, 'positions': {}}
    result = ap._validate_execution_integrity([], {}, {'cash': 8500, 'positions': {}}, starting_portfolio=start)
    assert result['ok'] is False


def test_missing_quality_cannot_be_assumed_perfect(monkeypatch):
    result = run(monkeypatch, omit='data_quality_score')
    assert not result['portfolio_trades']


def test_missing_risk_cannot_be_assumed_safe(monkeypatch):
    result = run(monkeypatch, omit='risk_score')
    assert not result['portfolio_trades']
