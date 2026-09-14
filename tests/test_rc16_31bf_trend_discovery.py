from __future__ import annotations
import os
import pandas as pd
from candidate_market_data import _technical_fields
from trend_intelligence import build_trend_receipt, annotate_run


def test_technical_fields_expose_compact_real_trend_series():
    idx = pd.date_range('2026-05-01', periods=90, freq='B')
    hist = pd.DataFrame({'Close':[100+i*0.3 for i in range(90)], 'Volume':[1000+i*5 for i in range(90)]}, index=idx)
    fields, _ = _technical_fields(hist)
    assert len(fields['price_trend_60d']) == 60
    assert fields['return_5d'] > 0
    assert fields['return_20d'] > 0
    assert fields['sma20'] is not None
    assert fields['sma50'] is not None
    assert fields['volume_ratio_20'] is not None


def test_receipt_tracks_first_seen_rank_and_phase_without_changing_score():
    candidate={'ticker':'TEST.OL','rank':2,'investment_score':77.0,'raw':{
        'return_5d':3.0,'return_20d':9.0,'return_60d':18.0,'last_price':110,'sma20':104,'sma50':100,
        'volume_ratio_20':1.6,'distance_from_20d_high_pct':-0.8,
        'price_trend_60d':[{'date':f'2026-08-{i:02d}','close':90+i} for i in range(1,21)]}}
    history={'first_seen':'2026-08-05T08:00:00+00:00','observations':[{'rank':5}], 'times_in_list':4}
    before=candidate['investment_score']
    receipt=build_trend_receipt(candidate, history)
    assert receipt['trend_phase'] == 'ETABLERT TREND'
    assert receipt['rank_change'] == 3
    run={'markets':['Norge'],'candidates':[candidate]}
    annotate_run(run, {'TEST.OL':history})
    assert candidate['investment_score'] == before
    assert run['trend_discovery']['production_scoring_changed'] is False


def test_norway_stabilization_source_contracts_present():
    from pathlib import Path
    scanner = Path('scanner_worker.py').read_text(encoding='utf-8')
    runner = Path('market_intelligence.py').read_text(encoding='utf-8')
    assert 'PRODUCTION_NORWAY_ONLY' in scanner
    assert 'AUTOMATED_SCANNER_MARKETS = ((\"NORGE\",)' in scanner
    assert 'NORWAY_PRODUCTION_STABILIZATION' in runner
    assert 'effective_job = replace(job, markets=[\"Norge\"]' in runner
