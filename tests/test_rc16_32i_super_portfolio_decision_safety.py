from datetime import datetime, timedelta, timezone

import super_portfolio as sp


def candidate(ticker, score, *, risk=30, quality=90, price=100, sector='Tech', market='USA'):
    return {
        'ticker': ticker,
        'investment_score': score,
        'risk_score': risk,
        'data_quality_score': quality,
        'price': price,
        'sector': sector,
        'market': market,
        'raw': {'last_price': price, 'volatility_pct': 20},
    }


def fresh_pipeline(now, rows, run_id='FRESH', regime_fit=70):
    return {
        'run_id': run_id,
        'created_at': now.isoformat(timespec='seconds'),
        'regime_fit_score': regime_fit,
        'candidates': rows,
    }


def existing_position(ticker, weight=50, score=80, *, price=100, peak=100, rank=1, sector='Tech'):
    return {
        'ticker': ticker,
        'market': 'USA',
        'sector': sector,
        'target_weight_pct': weight,
        'entry_price': price,
        'last_price': price,
        'peak_price': peak,
        'risk_score': 30,
        'quality_score': 90,
        'portfolio_score': score,
        'portfolio_score_adjusted': score,
        'rank': rank,
        'max_portfolio_correlation': 0.2,
        'correlation_source': 'MULTI_HORIZON_RETURN_PROFILE',
    }


def test_stale_feed_blocks_ordinary_auto_rebalance_but_keeps_advisory(monkeypatch):
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)  # Friday
    cfg = sp.SuperPortfolioConfig(target_positions=2, rebalance_weekday=4, max_rebalance_data_age_minutes=60)
    state = sp.default_state(cfg)
    state['positions'] = {
        'AAA': existing_position('AAA', 50, 80, rank=1),
        'BBB': existing_position('BBB', 50, 79, rank=2, sector='Health'),
    }
    monkeypatch.setattr(sp, 'load_state', lambda: state)
    pipeline = fresh_pipeline(now - timedelta(hours=3), [candidate('CCC', 99), candidate('DDD', 98)], run_id='STALE')

    result = sp.evaluate(pipeline=pipeline, persist=False, now=now, rebalance_policy='AUTO')

    assert result['rebalance_due'] is True
    assert result['rebalance_gate']['allowed'] is False
    assert 'FRESHNESS_GATE_BLOCKED' in result['rebalance_gate']['reason_codes']
    assert set(result['state']['positions']) == {'AAA', 'BBB'}
    assert any(row['action'] == 'BUY' for row in result['ai_would_do_today'])
    assert result['changes'] == []


def test_low_confidence_blocks_ordinary_rebalance(monkeypatch):
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(target_positions=2, rebalance_weekday=4, min_rebalance_confidence=65)
    state = sp.default_state(cfg)
    state['positions'] = {'AAA': existing_position('AAA', 100, 80)}
    monkeypatch.setattr(sp, 'load_state', lambda: state)
    pipeline = fresh_pipeline(now, [
        candidate('CCC', 99, quality=0),
        candidate('DDD', 98, quality=0),
    ], run_id='LOWCONF', regime_fit=0)

    result = sp.evaluate(pipeline=pipeline, persist=False, now=now, rebalance_policy='AUTO')

    assert result['rebalance_due'] is True
    assert result['rebalance_gate']['allowed'] is False
    assert 'CONFIDENCE_GATE_BLOCKED' in result['rebalance_gate']['reason_codes']
    assert set(result['state']['positions']) == {'AAA'}


def test_hard_stop_executes_even_when_ordinary_gate_is_blocked(monkeypatch):
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(target_positions=1, rebalance_weekday=4, max_rebalance_data_age_minutes=60)
    state = sp.default_state(cfg)
    state['positions'] = {
        'AAA': existing_position('AAA', 100, 80, price=80, peak=120),
    }
    monkeypatch.setattr(sp, 'load_state', lambda: state)
    stale = fresh_pipeline(now - timedelta(hours=4), [candidate('AAA', 90, price=80)], run_id='STALESTOP')

    result = sp.evaluate(pipeline=stale, persist=False, now=now, rebalance_policy='AUTO')

    assert result['rebalance_gate']['allowed'] is False
    assert 'AAA' not in result['state']['positions']
    assert any(c['ticker'] == 'AAA' and c['reason_code'] == 'HARD_STOP' for c in result['changes'])


def test_hysteresis_retains_incumbent_when_challenger_margin_is_too_small():
    cfg = sp.SuperPortfolioConfig(target_positions=2, replacement_rank_buffer=2, replacement_score_margin=2.0)
    ranked = [
        {'ticker': 'AAA', 'rank': 1, 'portfolio_score_adjusted': 90.0},
        {'ticker': 'CCC', 'rank': 2, 'portfolio_score_adjusted': 80.8},
        {'ticker': 'BBB', 'rank': 3, 'portfolio_score_adjusted': 80.0},
    ]
    previous = {'AAA': existing_position('AAA', score=90), 'BBB': existing_position('BBB', score=80, rank=2)}

    selected, metadata = sp.select_target_rows_with_hysteresis(ranked, previous, cfg)

    assert [row['ticker'] for row in selected] == ['AAA', 'BBB']
    assert metadata['BBB']['reason_code'] == 'HYSTERESIS_HOLD'
    assert metadata['CCC']['reason_code'] == 'HYSTERESIS_BLOCKED_CHALLENGER'


def test_hysteresis_allows_strong_challenger_to_replace_incumbent():
    cfg = sp.SuperPortfolioConfig(target_positions=2, replacement_rank_buffer=2, replacement_score_margin=2.0)
    ranked = [
        {'ticker': 'AAA', 'rank': 1, 'portfolio_score_adjusted': 90.0},
        {'ticker': 'CCC', 'rank': 2, 'portfolio_score_adjusted': 84.0},
        {'ticker': 'BBB', 'rank': 3, 'portfolio_score_adjusted': 80.0},
    ]
    previous = {'AAA': existing_position('AAA', score=90), 'BBB': existing_position('BBB', score=80, rank=2)}

    selected, metadata = sp.select_target_rows_with_hysteresis(ranked, previous, cfg)

    assert [row['ticker'] for row in selected] == ['AAA', 'CCC']
    assert metadata['CCC']['reason_code'] == 'CHALLENGER_WIN'


def test_advisory_actions_have_explicit_reason_codes_and_rebalance_impact(monkeypatch):
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(target_positions=2)
    state = sp.default_state(cfg)
    state['positions'] = {
        'AAA': existing_position('AAA', 60, 82, rank=1),
        'BBB': existing_position('BBB', 40, 75, rank=2, sector='Health'),
    }
    monkeypatch.setattr(sp, 'load_state', lambda: state)
    pipeline = fresh_pipeline(now, [candidate('AAA', 90), candidate('CCC', 88, sector='Energy'), candidate('BBB', 70, sector='Health')], run_id='IMPACT')

    result = sp.evaluate(pipeline=pipeline, persist=False, now=now, rebalance_policy='ANALYZE_ONLY')

    assert result['ai_would_do_today']
    assert all(row.get('reason_code') and row.get('reason') for row in result['ai_would_do_today'])
    impact = result['rebalance_impact']
    assert 'health_before' in impact and 'health_after' in impact
    assert 'health_delta' in impact
    assert 'turnover_pct' in impact
    assert impact['decision_run_id'] == 'IMPACT'


def test_scheduled_rebalance_due_forces_fresh_market_pipeline(monkeypatch):
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(target_positions=1, rebalance_weekday=0)
    state = sp.default_state(cfg)
    state['config'] = sp.asdict(cfg)
    state['positions'] = {'AAA': existing_position('AAA', 100, 80)}
    calls = []
    cached = fresh_pipeline(now - timedelta(hours=3), [candidate('AAA', 80)], run_id='OLD')
    fresh = fresh_pipeline(now, [candidate('CCC', 90)], run_id='NEW')

    monkeypatch.setattr(sp, '_now_dt', lambda: now)
    monkeypatch.setattr(sp, 'load_state', lambda: state)
    monkeypatch.setattr(sp, 'get_or_build_super_portfolio_market_pipeline', lambda **kwargs: calls.append(dict(kwargs)) or (fresh if kwargs.get('force_refresh') else cached))
    monkeypatch.setattr(sp, 'evaluate', lambda **kwargs: {'state': {**state, 'source_run_id': kwargs['pipeline']['run_id']}, 'changes': [], 'stop_alerts': [], 'rebalance_due': True})
    monkeypatch.setattr(sp, 'refresh_index_benchmark', lambda *_: {})
    monkeypatch.setattr(sp, 'resource_health', lambda: {})
    monkeypatch.setattr(sp, 'save_state', lambda value: value)
    monkeypatch.setattr(sp, 'append_event', lambda *a, **k: None)

    result = sp.run_scheduled_shadow_cycle()

    assert result['state'] == 'COMPLETED'
    assert any(call.get('force_refresh') is True for call in calls)
    assert result['source_run_id'] == 'NEW'


def test_rc16_32i_release_gate_tracks_new_safety_features():
    keys = {row['key'] for row in sp.master_checklist()}
    assert {
        'fresh_rebalance_gate', 'rebalance_confidence_gate', 'replacement_hysteresis',
        'explicit_action_reasons', 'rebalance_before_after_impact'
    }.issubset(keys)


def test_version_contract_is_rc16_32i():
    import app_version
    assert app_version.APP_VERSION == "v19.22.0-rc16.32i"
    assert app_version.PREVIOUS_APP_VERSION == "v19.22.0-rc16.32h"
    assert sp.VERSION == "v19.22.0-rc16.32i"


def test_ui_surfaces_rebalance_gate_impact_and_action_reasons():
    source = open('pages/super_portfolio.py', encoding='utf-8').read()
    assert '🛡️ Rebalance Gate' in source
    assert '📊 Før / etter rebalansering' in source
    assert 'reason_code' in source
    assert 'execution_status' in source
