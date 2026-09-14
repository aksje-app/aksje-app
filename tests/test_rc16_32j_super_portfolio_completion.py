from datetime import datetime, timezone

import super_portfolio as sp


def candidate(ticker, score=90, *, quality=90, risk=30, price=100, market='USA', sector='Tech', volatility=20):
    return {
        'ticker': ticker, 'investment_score': score, 'risk_score': risk,
        'data_quality_score': quality, 'price': price, 'market': market, 'sector': sector,
        'raw': {'last_price': price, 'volatility_pct': volatility, 'return_20d': 2.0, 'return_60d': 5.0},
    }


def position(ticker, *, weight=50, score=80, rank=1, market='USA', sector='Tech'):
    return {
        'ticker': ticker, 'market': market, 'sector': sector, 'target_weight_pct': weight,
        'entry_price': 100, 'last_price': 100, 'peak_price': 100, 'risk_score': 30,
        'quality_score': 90, 'portfolio_score': score, 'portfolio_score_adjusted': score,
        'rank': rank, 'max_portfolio_correlation': 0.2, 'correlation_source': 'MULTI_HORIZON_RETURN_PROFILE',
    }


def pipeline(now, rows, run_id='RUN1', **extra):
    return {'run_id': run_id, 'created_at': now.isoformat(timespec='seconds'), 'candidates': rows, **extra}


def test_broad_us_universe_combines_large_mid_small_and_nasdaq_without_duplicates(monkeypatch):
    import stocks
    monkeypatch.setattr(stocks, '_get_sp500_tickers_cached', lambda limit=500: tuple(['A', 'B', 'C']))
    monkeypatch.setattr(stocks, '_get_sp400_tickers_cached', lambda limit=400: tuple(['C', 'D']))
    monkeypatch.setattr(stocks, '_get_sp600_tickers_cached', lambda limit=600: tuple(['E', 'F']))
    monkeypatch.setattr(stocks, '_get_nasdaq100_tickers_cached', lambda limit=100: tuple(['A', 'G']))
    assert stocks.get_us_broad_tickers(limit=20) == ['A', 'B', 'C', 'D', 'E', 'F', 'G']


def test_sp_default_us_universe_capacity_is_broader_than_500():
    cfg = sp.SuperPortfolioConfig()
    assert cfg.us_broad_universe_enabled is True
    assert cfg.us_universe_limit >= 1400
    assert cfg.market_universe_limit_per_market >= 500



def test_broad_coarse_market_snapshot_chunks_large_us_batches(monkeypatch):
    import learning_observation_engine as loe
    calls=[]
    def fake_loader(tickers, start):
        calls.append(list(tickers))
        rows=[{"close": 100+i*0.1} for i in range(30)]
        return {ticker: rows for ticker in tickers}
    monkeypatch.setattr(loe, 'yfinance_series_loader', fake_loader)
    tickers=[f"T{i}" for i in range(601)]
    out=sp._coarse_market_snapshot(tickers, 'USA')
    assert len(out) == 601
    assert len(calls) >= 3
    assert max(len(batch) for batch in calls) <= 250

def test_candidate_data_coverage_blocks_new_low_coverage_entry_but_not_incumbent(monkeypatch):
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(target_positions=1, rebalance_weekday=4, min_entry_data_coverage=75, candidate_persistence_runs=1)
    state = sp.default_state(cfg)
    state['positions'] = {'AAA': position('AAA', weight=100, score=70)}
    monkeypatch.setattr(sp, 'load_state', lambda: state)
    low = candidate('NEW', 99, quality=90)
    low['sector'] = 'Ukjent'
    low['raw'] = {'last_price': 100}  # deliberately missing volatility/returns
    result = sp.evaluate(pipeline=pipeline(now, [low, candidate('AAA', 70)], run_id='COV1'), persist=False, now=now, rebalance_policy='FORCE')
    assert set(result['state']['positions']) == {'AAA'}
    assert result['entry_gate']['NEW']['allowed'] is False
    assert 'DATA_COVERAGE_BLOCKED' in result['entry_gate']['NEW']['reason_codes']


def test_candidate_requires_two_consecutive_fresh_runs_before_replacing_incumbent(monkeypatch):
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(target_positions=1, rebalance_weekday=4, candidate_persistence_runs=2, replacement_rank_buffer=0, replacement_score_margin=0)
    state = sp.default_state(cfg)
    state['positions'] = {'AAA': position('AAA', weight=100, score=70)}
    monkeypatch.setattr(sp, 'load_state', lambda: state)
    first = sp.evaluate(pipeline=pipeline(now, [candidate('NEW', 99), candidate('AAA', 70)], run_id='P1'), persist=False, now=now, rebalance_policy='FORCE')
    assert set(first['state']['positions']) == {'AAA'}
    assert first['candidate_persistence']['NEW']['streak'] == 1
    assert 'PERSISTENCE_GATE_BLOCKED' in first['entry_gate']['NEW']['reason_codes']

    state.update(first['state'])
    second = sp.evaluate(pipeline=pipeline(now, [candidate('NEW', 99), candidate('AAA', 70)], run_id='P2'), persist=False, now=now, rebalance_policy='FORCE')
    assert set(second['state']['positions']) == {'NEW'}
    assert second['candidate_persistence']['NEW']['streak'] == 2


def test_regime_policy_changes_persistence_confidence_and_margin():
    cfg = sp.SuperPortfolioConfig(candidate_persistence_runs=2, min_rebalance_confidence=65, replacement_score_margin=2.0)
    calm = sp.rebalance_regime_policy({'market_regime': 'CALM'}, cfg)
    normal = sp.rebalance_regime_policy({'market_regime': 'NORMAL'}, cfg)
    stressed = sp.rebalance_regime_policy({'market_regime': 'STRESSED'}, cfg)
    assert calm['required_persistence_runs'] > normal['required_persistence_runs'] > stressed['required_persistence_runs']
    assert calm['min_confidence'] > normal['min_confidence'] > stressed['min_confidence']
    assert calm['replacement_score_margin'] > normal['replacement_score_margin'] > stressed['replacement_score_margin']


def test_ai_thinks_and_shadow_executed_are_persisted_separately(monkeypatch):
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(target_positions=1, candidate_persistence_runs=1, replacement_rank_buffer=0, replacement_score_margin=0)
    state = sp.default_state(cfg)
    state['positions'] = {'AAA': position('AAA', weight=100, score=70)}
    monkeypatch.setattr(sp, 'load_state', lambda: state)
    result = sp.evaluate(pipeline=pipeline(now, [candidate('NEW', 99), candidate('AAA', 70)], run_id='SEP1'), persist=False, now=now, rebalance_policy='ANALYZE_ONLY')
    assert result['state']['ai_thinks'] == result['ai_would_do_today']
    assert result['state']['shadow_executed'] == []
    assert result['snapshot']['ai_thinks'] == result['ai_would_do_today']
    assert result['snapshot']['shadow_executed'] == []


def test_ui_labels_ai_thinks_and_shadow_executed():
    source = open('pages/super_portfolio.py', encoding='utf-8').read()
    assert '🧠 AI THINKS' in source
    assert '✅ SHADOW EXECUTED' in source
    assert '🎛️ Regime Policy' in source
    assert '🎯 Candidate Entry Gate' in source


def test_rc16_32j_release_contract_and_master_gate():
    import app_version
    assert app_version.APP_VERSION == 'v19.22.0-rc16.32j'
    assert app_version.PREVIOUS_APP_VERSION == 'v19.22.0-rc16.32i'
    assert sp.VERSION == 'v19.22.0-rc16.32j'
    keys = {row['key'] for row in sp.master_checklist()}
    assert {'candidate_persistence', 'regime_aware_rebalance', 'candidate_data_coverage_gate', 'broad_us_universe', 'ai_vs_shadow_separation'}.issubset(keys)
