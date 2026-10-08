from dataclasses import asdict
from datetime import datetime, timezone

import super_portfolio as sp


NOW = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)


def candidate(ticker, score=90):
    return {
        'ticker': ticker, 'investment_score': score, 'risk_score': 25,
        'data_quality_score': 95, 'price': 105, 'market': 'USA',
        'sector': 'Technology', 'raw': {'last_price': 105,
            'volatility_pct': 20, 'return_5d': 1, 'return_20d': 3, 'return_60d': 6},
    }


def setup(monkeypatch):
    cfg = sp.SuperPortfolioConfig(target_positions=1, candidate_persistence_runs=2,
        production_market_scopes=('USA',), replacement_rank_buffer=0,
        replacement_score_margin=0)
    state = sp.default_state(cfg)
    state['config'] = asdict(cfg)
    state['pending_risk_refill_slots'] = 1
    state['risk_reentry_confirmation'] = {'OLD': {
        'exit_price': 110, 'last_price': 110, 'exit_score': 95,
        'last_score': 95, 'last_run_id': 'EXIT', 'streak': 0}}
    state['candidate_persistence'] = {'NEW': {'streak': 1, 'last_run_id': 'PREV'}}
    monkeypatch.setattr(sp, 'load_state', lambda: state)
    monkeypatch.setattr(sp, 'market_activation_level', lambda _: 'PRODUCTION')
    return state


def evaluate(rows, run='NEXT', created_at=None):
    return sp.evaluate(pipeline={'run_id': run,
        'created_at': created_at or NOW.isoformat(), 'candidates': rows},
        persist=False, now=NOW, rebalance_policy='ANALYZE_ONLY')


def test_vacant_portfolio_searches_beyond_blocked_top_candidate(monkeypatch):
    setup(monkeypatch)
    result = evaluate([candidate('OLD', 95), candidate('NEW', 90)])
    assert result['entry_gate']['OLD']['allowed'] is False
    assert result['entry_gate']['NEW']['allowed'] is True
    assert result['rebalance_gate']['allowed'] is True
    assert set(result['state']['positions']) == {'NEW'}
    assert result['state']['pending_risk_refill_slots'] == 0


def test_fallback_does_not_bypass_persistence(monkeypatch):
    state = setup(monkeypatch)
    state['candidate_persistence'] = {}
    result = evaluate([candidate('OLD', 95), candidate('NEW', 90)])
    assert not result['state']['positions']
    assert result['candidate_persistence']['NEW']['streak'] == 1


def test_fallback_does_not_bypass_stale_pipeline(monkeypatch):
    setup(monkeypatch)
    result = evaluate([candidate('OLD', 95), candidate('NEW', 90)],
        created_at='2026-10-07T14:00:00+00:00')
    assert not result['state']['positions']
    assert 'FRESHNESS_GATE_BLOCKED' in result['rebalance_gate']['reason_codes']


def test_repeated_pipeline_cannot_manufacture_fallback_persistence(monkeypatch):
    state = setup(monkeypatch)
    state['candidate_persistence'] = {'NEW': {'streak': 1, 'last_run_id': 'NEXT'}}
    result = evaluate([candidate('OLD', 95), candidate('NEW', 90)])
    assert result['candidate_persistence']['NEW']['streak'] == 1
    assert not result['state']['positions']


def test_fallback_can_fill_regular_rebalance_without_pending_risk_exit(monkeypatch):
    state = setup(monkeypatch)
    state['pending_risk_refill_slots'] = 0
    result = sp.evaluate(pipeline={'run_id': 'NEXT', 'created_at': NOW.isoformat(),
        'candidates': [candidate('OLD', 95), candidate('NEW', 90)]},
        persist=False, now=NOW, rebalance_policy='FORCE')
    assert set(result['state']['positions']) == {'NEW'}


def test_fallback_with_missing_coverage_is_not_bought(monkeypatch):
    setup(monkeypatch)
    incomplete = candidate('NEW', 90)
    incomplete['raw'] = {'last_price': 105}
    incomplete.pop('sector')
    result = evaluate([candidate('OLD', 95), incomplete])
    assert not result['state']['positions']
    assert 'DATA_COVERAGE_BLOCKED' in result['entry_gate']['NEW']['reason_codes']
