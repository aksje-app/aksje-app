from fund_type_adapter import (
    canonicalize_fund_type,
    get_fund_type_profile,
    build_fund_type_adapter,
    adapt_rows_for_fund_type,
    build_fund_type_aware_analysis,
)


def test_canonicalize_common_fund_types():
    assert canonicalize_fund_type('ETF') == 'indeksfond'
    assert canonicalize_fund_type('Rente-/obligasjonsfond') == 'rentefond'
    assert canonicalize_fund_type('Money market') == 'pengemarkedsfond'
    assert canonicalize_fund_type('Hedge Fund') == 'alternativt fond'


def test_profile_contains_relevant_risk_language():
    p = get_fund_type_profile('High yield')
    assert p['canonical_type'] == 'high yield-fond'
    assert 'credit_spread' in p['primary_factors']
    assert 'credit_spread_widening' in p['stress_scenarios']
    assert p['optimizer_constraints']['max_factor_budget_pct'] <= 24.0


def test_adapter_combines_mixed_portfolio():
    rows = [
        {'symbol': 'EUNL', 'fund_type': 'Indeksfond', 'score': 80},
        {'symbol': 'TLT', 'fund_type': 'Rentefond', 'score': 70},
        {'symbol': 'HYG', 'fund_type': 'High yield', 'score': 72},
    ]
    adapter = build_fund_type_adapter(rows)
    assert adapter['fund_type_buckets']['indeksfond']['count'] == 1
    assert adapter['fund_type_buckets']['rentefond']['count'] == 1
    assert 'duration' in adapter['combined_primary_factors']
    assert 'credit_spread_widening' in adapter['combined_stress_scenarios']


def test_adapt_rows_adds_metadata_without_losing_input():
    rows = [{'symbol': 'BIL', 'fund_type': 'Pengemarkedsfond', 'metadata': {'x': 1}}]
    out = adapt_rows_for_fund_type(rows)
    assert out[0]['metadata']['x'] == 1
    assert out[0]['metadata']['fund_type_adapter']['canonical_type'] == 'pengemarkedsfond'
    assert rows[0]['fund_type'] == 'Pengemarkedsfond'


def test_fund_type_aware_analysis_runs_end_to_end():
    rows = [
        {'symbol': 'QQQ', 'fund_type': 'Sektorfond', 'score': 86, 'weight_pct': 50},
        {'symbol': 'AGG', 'fund_type': 'Rentefond', 'score': 68, 'weight_pct': 30},
        {'symbol': 'SGOV', 'fund_type': 'Pengemarkedsfond', 'score': 62, 'weight_pct': 20},
    ]
    result = build_fund_type_aware_analysis(rows, regime='risk_off')
    assert result['adapter']['schema_version'] == 1
    assert result['core_risk']['schema_version'] >= 1
    assert result['portfolio_intelligence']['schema_version'] >= 1
    assert result['validation']['schema_version'] >= 1
    assert any(s['scenario'] == 'liquidity_squeeze' for s in result['fund_type_stress']['scenarios'])
