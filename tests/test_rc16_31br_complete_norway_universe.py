from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import norway_exchange_universe as neu


def _euronext_row(name: str, isin: str, symbol: str, market: str):
    return [f'<a data-title-hover="{name}">{name}</a>', isin, symbol, market, '10.00', '+1.0%', '08 Sep 2026']


def test_official_parser_preserves_all_three_oslo_markets_and_identity():
    payload = {
        'aaData': [
            _euronext_row('Main ASA', 'NO0010000001', 'MAIN', 'Oslo Børs'),
            _euronext_row('Growth AS', 'NO0010000002', 'GROW', 'Euronext Growth Oslo'),
            _euronext_row('Expand ASA', 'NO0010000003', 'EXPD', 'Euronext Expand Oslo'),
        ]
    }
    rows = neu._parse_rows(payload)
    assert [r['exchange_mic'] for r in rows] == ['XOSL', 'MERK', 'XOAS']
    assert [r['ticker'] for r in rows] == ['MAIN.OL', 'GROW.OL', 'EXPD.OL']
    assert rows[1]['exchange_name'] == 'Euronext Growth Oslo'
    assert rows[2]['isin'] == 'NO0010000003'


def test_source_contract_uses_official_euronext_stock_endpoint_and_mics():
    params, data = neu._request_payload()
    assert neu.EURONEXT_STOCKS_ENDPOINT.endswith('/en/pd/data/stocks')
    assert params['mics'] == 'XOSL,MERK,XOAS'
    assert data['iDisplayLength'] == '2000'
    assert neu.MIC_TO_MARKET['XOSL'] == 'Oslo Børs'
    assert neu.MIC_TO_MARKET['MERK'] == 'Euronext Growth Oslo'
    assert neu.MIC_TO_MARKET['XOAS'] == 'Euronext Expand Oslo'


def test_universe_engine_allows_more_than_250_norway_symbols(monkeypatch):
    import universe_engine
    import stocks
    fake = [f'T{i:03d}.OL' for i in range(320)]
    monkeypatch.setattr(stocks, 'get_norwegian_tickers', lambda limit=None: fake[:limit] if limit else fake)
    out = universe_engine.resolve_universe_tickers(['Norge'], max_count=500)
    assert len(out) == 320
    assert out[-1] == 'T319.OL'


def test_every_stage1_candidate_gets_fresh_preview_before_deep_cut():
    src = Path('investment_pipeline.py').read_text(encoding='utf-8')
    preview_pos = src.index('for row in sanitized_rows:\n            row["early_opportunity_preview"]')
    selection_pos = src.index('select_sector_balanced_rows(sanitized_rows, cfg.deep_analysis_count)')
    assert preview_pos < selection_pos
    assert 'fresh_screening_candidates' in src
    assert 'fresh_trend_reserved' in src


def test_trend_discovery_reads_full_stage1_screening_pool():
    src = Path('trend_intelligence.py').read_text(encoding='utf-8')
    assert 'run.get("fresh_screening_candidates")' in src
    assert '"full_stage1_universe":len(pool)' in src
    assert 'exchange_name' in src


def test_paper_trade_rotation_is_bounded_and_persistent_by_contract():
    src = Path('scanner_worker.py').read_text(encoding='utf-8')
    assert 'def _rotating_norway_batch' in src
    assert 'full_no = _take(get_norwegian_tickers, 500)' in src
    assert '_commit_norway_rotation(final_rotation_meta)' in src
    assert 'NORWAY_ROTATION_KEY = "paper_trading/norway_universe_rotation.json"' in src
    assert 'len(selected) < batch_size' in src

def test_market_report_has_authoritative_exchange_breakdown_fields():
    src = Path('market_intelligence.py').read_text(encoding='utf-8')
    assert '"Børser":' in src
    assert '"børsfordeling": row.get("exchange_counts")' in src
    assert 'Euronexts offisielle Oslo-aksjemaster' in src
    assert '"Børs": receipt.get("exchange_name")' in src


def test_candidate_assessment_carries_exchange_identity():
    src = Path('investment_pipeline.py').read_text(encoding='utf-8')
    for field in ('exchange_name', 'market_segment', 'exchange_mic', 'exchange_symbol', 'isin', 'listing_status'):
        assert f'{field}: str' in src
        assert f'{field}=str(row.get("{field}")' in src


def test_version_is_br():
    import app_version
    assert app_version.APP_VERSION == 'v19.22.0-rc16.31br'


def test_fresh_stage1_payload_is_compact_to_protect_manual_report_memory():
    import investment_pipeline as ip
    row = {
        'ticker': 'TEST.OL', 'market': 'Norge', 'exchange_name': 'Oslo Børs',
        'return_5d': 4.2, 'rsi': 61.0, 'price_trend_60d': [{'date': '2026-09-08', 'close': 10.0}],
        'early_opportunity_preview': {'fresh_signal': {'score': 80}},
        'huge_unused_blob': 'x' * 10000, 'news_intelligence': {'articles': ['x'] * 100},
    }
    compact = ip._compact_fresh_screening_row(row)
    assert compact['ticker'] == 'TEST.OL'
    assert compact['exchange_name'] == 'Oslo Børs'
    assert compact['return_5d'] == 4.2
    assert 'huge_unused_blob' not in compact
    assert 'news_intelligence' not in compact


def test_norway_coverage_contract_reports_authoritative_exchange_counts(monkeypatch):
    import universe_coverage as uc
    import norway_exchange_universe as neu_mod
    master = {
        'source_authoritative_exchange_master': True,
        'source': 'Euronext official stocks endpoint',
        'status': 'OFFICIAL_LIVE',
        'verified_at': '2026-09-08T19:00:00+00:00',
        'by_exchange': {'Oslo Børs': 2, 'Euronext Growth Oslo': 1, 'Euronext Expand Oslo': 1},
        'instruments': [
            {'ticker':'A.OL','exchange_name':'Oslo Børs'},
            {'ticker':'B.OL','exchange_name':'Oslo Børs'},
            {'ticker':'G.OL','exchange_name':'Euronext Growth Oslo'},
            {'ticker':'X.OL','exchange_name':'Euronext Expand Oslo'},
        ],
    }
    monkeypatch.setattr(neu_mod, 'get_norway_exchange_master', lambda *a, **k: master)
    monkeypatch.setattr(uc, 'configured_universe_tickers', lambda market: ['A.OL','B.OL','G.OL','X.OL'])
    rows = [
        {'ticker':'A.OL','market':'Norge','sector':'Energi'},
        {'ticker':'B.OL','market':'Norge','sector':'Finans'},
        {'ticker':'G.OL','market':'Norge','sector':'Teknologi'},
        {'ticker':'X.OL','market':'Norge','sector':'Industri'},
    ]
    contract = uc.build_universe_contract('Norge', rows, advanced_tickers=['A.OL'], evidence_tickers=[])
    assert contract['source_authoritative_exchange_master'] is True
    assert contract['coverage_pct'] == 100.0
    assert contract['coverage_failure'] is False
    assert contract['exchange_counts']['Euronext Growth Oslo'] == 1
    assert contract['exchange_scanned_counts']['Euronext Expand Oslo'] == 1
