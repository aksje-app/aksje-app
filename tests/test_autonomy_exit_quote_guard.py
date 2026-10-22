from datetime import datetime, timezone
from dataclasses import asdict
from autonomous_portfolio import AutonomousParameters, default_portfolio, simulate_autonomy_cycle

def _portfolio():
    p=default_portfolio(AutonomousParameters())
    p['status']='ACTIVE'
    p['cash']-=1990
    p['positions']={'CMBTO.OL':{'ticker':'CMBTO.OL','quantity':10,'average_price':199,
       'last_price':182.8,'highest_price':199,'entry_score':73.5,'last_score':70,
       'opened_at':'2026-10-12T14:00:00+00:00','score_path':[73.5,70]}}
    return p

def test_missing_candidate_must_not_execute_sale_from_cached_price():
    p=_portfolio()
    result=simulate_autonomy_cycle([],parameters=asdict(AutonomousParameters()),
        portfolio=p,trades=[],now=datetime(2026,10,14,18,0,tzinfo=timezone.utc),run_id='AUDIT-MISSING')
    assert 'CMBTO.OL' in result['portfolio']['positions']
    assert not [t for t in result['trades'] if t.get('ticker')=='CMBTO.OL']
    assert any(d.get('reason_code')=='NO_CURRENT_CANDIDATE' for d in result['portfolio_decisions'])

def test_candidate_without_quote_must_not_sell_at_entry_price():
    p=_portfolio()
    candidate={'ticker':'CMBTO.OL','investment_score':70}
    result=simulate_autonomy_cycle([candidate],parameters=asdict(AutonomousParameters()),
        portfolio=p,trades=[],now=datetime(2026,10,14,18,0,tzinfo=timezone.utc),run_id='AUDIT-NO-PRICE')
    assert 'CMBTO.OL' in result['portfolio']['positions']
    assert not [t for t in result['trades'] if t.get('ticker')=='CMBTO.OL']
    assert any(d.get('reason_code')=='INVALID_EXECUTION_QUOTE' for d in result['portfolio_decisions'])
