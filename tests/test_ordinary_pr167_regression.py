"""Ordinary production-code paths with isolated I/O, restart_context explicitly None.

The baseline tests are also run unchanged against fetched main in a detached
worktree. Network providers and notifications are substituted, not strategy rules.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import inspect
import json
import pytest
from services.storage_service import StorageService

NOW=datetime(2026,10,23,15,0,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def verify_differential_source_root():
    import os
    from pathlib import Path
    expected=os.getenv('ORDINARY_EXPECTED_ROOT')
    if expected:
        import autonomous_portfolio,trading_engine,super_portfolio
        for module in (autonomous_portfolio,trading_engine,super_portfolio):
            assert Path(module.__file__).resolve().parent==Path(expected).resolve()


def ordinary(function,*args,**kwargs):
    if 'restart_context' in inspect.signature(function).parameters:kwargs['restart_context']=None
    return function(*args,**kwargs)


def quote(price=94,at=NOW):
    return dict(price=price,market_data_at=at.isoformat(),source='yfinance 5m Close',adjustment='raw')


@pytest.fixture
def autonomy_runtime(monkeypatch,tmp_path):
    import autonomous_portfolio as ap
    import learning_runtime,scanner_fresh_quote
    store=StorageService(tmp_path/'ordinary-autonomy',database_url='',mode='local')
    params=replace(ap.AutonomousParameters(),enable_learning_probe_buys=False,notify_trades=False,notify_risk_events=False)
    pos=dict(ticker='OWNED',quantity=10,average_price=100,last_price=100,highest_price=100,
             opened_at=(NOW-timedelta(hours=1)).isoformat(),entry_score=90,last_score=90,sector='Technology')
    portfolio=dict(cash=99000,initial_cash=100000,high_watermark=100000,status='ACTIVE',positions={'OWNED':pos})
    store.write_json(ap.PORTFOLIO_PATH.name,portfolio)
    monkeypatch.setattr(ap,'_read',lambda path,default:store.read_json(path.name,deepcopy(default)))
    monkeypatch.setattr(ap,'_write',lambda path,value:store.write_json(path.name,value))
    monkeypatch.setattr(ap,'load_portfolio',lambda:store.read_json(ap.PORTFOLIO_PATH.name))
    monkeypatch.setattr(ap,'load_parameters',lambda:params)
    monkeypatch.setattr(ap,'load_learning_portfolio',lambda:dict(positions={},cash=0))
    monkeypatch.setattr(ap,'_clock',lambda tz=None:NOW)
    monkeypatch.setattr(ap,'_now',lambda:NOW.isoformat())
    monkeypatch.setattr(ap,'_append_audit',lambda *a,**kw:None)
    monkeypatch.setattr(ap,'get_market_snapshot_service',lambda:(_ for _ in ()).throw(RuntimeError('TEST offline snapshot')))
    monkeypatch.setattr(ap,'get_strategy_account_service',lambda:(_ for _ in ()).throw(RuntimeError('TEST secondary sync disabled')))
    monkeypatch.setattr(learning_runtime,'capture_autonomy',lambda *a,**kw:None)
    monkeypatch.setattr(scanner_fresh_quote,'fresh_paper_buy_quote',lambda *a,**kw:(None,'TEST provider unavailable'))
    return ap,store,portfolio


@pytest.mark.parametrize('price,peak,remaining',[(94,100,0),(114,114,7.5),(100.8,102,0)])
def test_baseline_ordinary_risk_exit_and_persisted_reports(autonomy_runtime,price,peak,remaining):
    ap,store,portfolio=autonomy_runtime
    portfolio['positions']['OWNED']['highest_price']=peak
    store.write_json(ap.PORTFOLIO_PATH.name,portfolio)
    candidate=dict(ticker='OWNED',price=price,investment_score=90,valid_for_decision=False,
        evidence_valid_for_decision=False,final_decision_ready=False,portfolio_action='AVOID',execution_quote=quote(price))
    result=ordinary(ap.run_autonomous_cycle,[candidate],'ORDINARY-RISK')
    assert result['execution_integrity']['ok']
    assert len(result['portfolio_trades'])==1
    trade=result['portfolio_trades'][0]
    assert trade['price']==price and trade['quantity']==10-remaining
    assert store.read_json(ap.PORTFOLIO_PATH.name)['positions'].get('OWNED',{}).get('quantity',0)==remaining
    assert store.read_json(ap.TRADES_PATH.name)[0]['trade_id']==trade['trade_id']
    assert store.read_json(ap.PERFORMANCE_PATH.name)['equity']==result['performance']['equity']
    assert store.read_json(ap.EQUITY_HISTORY_PATH.name)
    assert result['portfolio']['cash']==99000+price*(10-remaining)


def test_baseline_paper_buy_sell_real_local_persistence_and_profit_rule(monkeypatch,tmp_path):
    import trading_engine as engine,paper_store
    from trading_settings import DEFAULT_RULES
    storage=StorageService(tmp_path/'ordinary-paper',database_url='',mode='local')
    monkeypatch.setenv('PAPER_TRADING_ENABLED','true');monkeypatch.setenv('ALLOW_PAPER_TRADING_IN_TEST','true')
    monkeypatch.setattr(paper_store,'_storage',lambda:storage)
    monkeypatch.setattr(paper_store,'using_postgres',lambda:False)
    monkeypatch.setattr(engine,'load_rules',lambda:dict(DEFAULT_RULES))
    monkeypatch.setattr(engine,'notify_executed_trade',lambda *a,**kw:None)
    monkeypatch.setattr(engine,'audit_state_transition',lambda *a,**kw:None)
    paper_store.save_portfolio(dict(cash=100000,positions={},trades=[]))
    ok,message=engine.paper_buy('OWNED',100,90,amount_override=10000)
    assert ok,message
    saved=paper_store.load_portfolio()
    assert saved['cash']==90000 and saved['positions']['OWNED']['shares']==100
    assert engine.paper_sell('OWNED',110,sell_pct=20)[0]
    assert paper_store.load_portfolio()['positions']['OWNED']['shares']==80
    stamp=datetime.now(timezone.utc);q=quote(120,stamp)
    result=ordinary(engine.auto_trade,'OWNED',120,'HOLD',90,trade_context={'execution_quote':q,'market_data_at':q['market_data_at'],'run_id':'ORDINARY-PAPER-TP'})
    assert result[0],result
    saved=paper_store.load_portfolio()
    assert not saved['positions'] and saved['cash']==101800
    assert len(saved['trades'])==3
    assert any('profit' in t['reason'].lower() for t in saved['trades'] if t['type']=='SELL')


def test_baseline_superportfolio_ordinary_settlement_and_pdf(monkeypatch,tmp_path):
    import super_portfolio as sp
    from services import super_portfolio_store as journal
    storage=StorageService(tmp_path/'ordinary-sp',database_url='',mode='local')
    monkeypatch.setattr(journal,'get_storage_service',lambda:storage)
    monkeypatch.setattr(sp,'get_storage_service',lambda:storage,raising=False)
    monkeypatch.setattr(sp,'append_event',lambda *a,**kw:None)
    monkeypatch.setattr(sp,'_execution_quotes',lambda *a:{})
    state=sp.default_state(sp.SuperPortfolioConfig(auto_pushover=False))
    monkeypatch.setattr(sp,'load_state',lambda:deepcopy(state))
    # Frozen pipeline stays ordinary but has explicit synthetic candidates.
    candidate=dict(ticker='OWNED',investment_score=90,risk_score=10,data_quality_score=100,price=100,
                   market='USA',sector='Technology',raw={'last_price':100,'volatility_pct':20})
    result=ordinary(sp.evaluate,pipeline=dict(run_id='ORDINARY-SP',candidates=[candidate]),persist=False,now=NOW)
    assert result['changes'] and result['state']['positions']
    assert all(p['quantity']>0 for p in result['state']['positions'].values())
    assert sp.build_pdf(result['state']).startswith(b'%PDF-')
    # Real native store commit and reload, not restart AccountStorage.
    journal.commit(result['state'],operation_id='ordinary-sp-save',trades=result['changes'],storage=storage)
    assert storage.read_json(journal.STATE_KEY)['positions']==result['state']['positions']
    assert len(journal.transactions(storage))==len(result['changes'])


@pytest.mark.parametrize('price,peak,remaining',[(94,100,0),(114,114,7.5),(100.8,102,0)])
@pytest.mark.parametrize('source',['provider','cached-proof','rejected-candidate'])
def test_regression_owned_ticker_supervision_independent_of_buy_filters(autonomy_runtime,monkeypatch,price,peak,remaining,source):
    ap,store,portfolio=autonomy_runtime
    import scanner_fresh_quote
    portfolio['positions']['OWNED']['highest_price']=peak
    candidates=[];calls=[]
    if source=='provider':
        monkeypatch.setattr(scanner_fresh_quote,'fresh_paper_buy_quote',lambda ticker,**kw:(calls.append(ticker) or quote(price),''))
    elif source=='cached-proof':
        portfolio['positions']['OWNED']['execution_quote']=quote(price)
        monkeypatch.setattr(scanner_fresh_quote,'fresh_paper_buy_quote',lambda *a,**kw:pytest.fail('Valid received quote should not need provider'))
    else:
        candidates=[dict(ticker='OWNED',price=price,investment_score=90,portfolio_action='AVOID',
            valid_for_decision=False,evidence_valid_for_decision=False,final_decision_ready=False,execution_quote=quote(price))]
        monkeypatch.setattr(scanner_fresh_quote,'fresh_paper_buy_quote',lambda *a,**kw:pytest.fail('Candidate quote already documented'))
    store.write_json(ap.PORTFOLIO_PATH.name,portfolio)
    result=ordinary(ap.run_autonomous_cycle,candidates,'RISK-WITHOUT-BUY-APPROVAL')
    assert len(result['portfolio_trades'])==1,result['portfolio_decisions']
    assert result['portfolio_trades'][0]['quantity']==10-remaining
    assert result['portfolio_trades'][0]['price_observed_at']==NOW.isoformat()
    if source=='provider':assert calls==['OWNED']


@pytest.mark.parametrize('bad_quote',[None,quote(94,NOW-timedelta(minutes=16)),quote(94,NOW+timedelta(minutes=2)),{'price':94}])
def test_regression_provider_outage_without_valid_quote_never_invents_sale(autonomy_runtime,monkeypatch,bad_quote):
    ap,store,portfolio=autonomy_runtime
    import scanner_fresh_quote
    portfolio['positions']['OWNED']['execution_quote']=bad_quote
    store.write_json(ap.PORTFOLIO_PATH.name,portfolio)
    calls=[]
    def unavailable(ticker,**kw):calls.append(ticker);raise ConnectionError('TEST provider unavailable')
    monkeypatch.setattr(scanner_fresh_quote,'fresh_paper_buy_quote',unavailable)
    result=ordinary(ap.run_autonomous_cycle,[],'RISK-NO-PROOF')
    assert calls==['OWNED']
    assert not result['portfolio_trades'] and result['portfolio']['cash']==portfolio['cash']
    assert result['portfolio']['positions']==portfolio['positions']
    assert any(d.get('risk_execution_blocked') for d in result['portfolio_decisions'])


def test_baseline_scheduler_due_slot_survives_sleep_and_respects_timezone():
    import market_intelligence as mi
    job=mi.JobProfile(name='TEST ordinary morning',enabled=True,weekdays=[3],schedules=['08:30'],
        scan_windows=[],timezone_name='Europe/Oslo',last_run_at='2026-07-22T20:36:10+00:00')
    assert mi._slot_due(job,datetime(2026,7,23,8,16,tzinfo=timezone.utc))
    assert not mi._slot_due(job,datetime(2026,7,23,6,0,tzinfo=timezone.utc))
