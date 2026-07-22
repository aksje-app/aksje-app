from datetime import datetime, timedelta, timezone

import historical_learning as hl


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(hl, 'ROOT', tmp_path)
    monkeypatch.setattr(hl, 'SNAPSHOTS_PATH', tmp_path / 'snapshots.json')
    monkeypatch.setattr(hl, 'write_persistent_json', lambda *a, **k: None)


def test_register_run_is_idempotent(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    run = {'run_id':'MI-1','created_at':datetime.now(timezone.utc).isoformat(),'job_name':'Morning','report_identity':{'type':'MORGENRAPPORT'},'proposals':[{'ticker':'AAA','market':'USA','investment_score':82,'technical_score':75,'raw':{'current_price':100,'insider_score':80,'news_score':72}}]}
    assert hl.register_run(run) == 1
    assert hl.register_run(run) == 0
    assert hl._read()[0]['entry_price'] == 100


def test_update_and_analytics(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    old = (datetime.now(timezone.utc)-timedelta(days=50)).isoformat()
    hl._write([{'run_id':'R','ticker':'AAA','created_at':old,'entry_price':100,'market':'USA','insider_score':80,'news_score':75,'technical_score':80,'fundamental_score':60,'evaluations':{}}])
    result = hl.update_due_evaluations(lambda ticker, horizon: {1:101,5:105,30:120,90:None})
    assert result['updated'] >= 3
    data = hl.analytics()
    assert data['horizons']['30']['average_return'] == 20.0
    assert data['horizons']['30']['hit_rate'] == 100.0


def test_missing_entry_price_is_safe(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    hl._write([{'run_id':'R','ticker':'AAA','created_at':'bad','entry_price':None,'evaluations':{}}])
    assert hl.update_due_evaluations(lambda *_: {})['updated'] == 0


def test_report_performance(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    hl._write([{'run_id':'R','ticker':'A','evaluations':{'5':{'return_pct':10}}},{'run_id':'R','ticker':'B','evaluations':{'5':{'return_pct':-2}}}])
    card=hl.report_performance('R')
    assert card['evaluated']==2 and card['winners']==1 and card['best'][0]=='A'
