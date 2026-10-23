"""Accounting regressions use explicit simulated prices and fees, never live returns."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from test_revision_trade_postgres import pg
from services.economic_ledger import new_account, execute, reconcile
from services.economic_accounting_audit import audit

NOW = datetime.now(timezone.utc).replace(microsecond=0)
AT = NOW.isoformat()


def fx(rate=10, currency='USD'):
    return dict(currency=currency, base_currency='NOK', rate=rate, observed_at=AT, source='synthetic')


def fill(state, *, identity='BUY-1', side='BUY', quantity=10, price=100, rate=10, fee=10):
    return execute(state, trade_id=identity, ticker='TEST', side=side, quantity=quantity,
                   price=price, currency='USD', observed_at=AT, source='synthetic raw', at=AT,
                   fee=fee, cost_currency='NOK', fx_quote=fx(rate))


def test_buy_add_partial_sell_and_final_exit_reconcile_in_nok():
    initial = new_account(100000, base_currency='NOK', at=AT)
    bought, first = fill(initial)
    assert initial['cash'] == 100000 and initial['positions'] == {}
    assert bought['cash'] == 89990
    assert bought['positions']['TEST']['quantity'] == 10
    assert bought['positions']['TEST']['cost_basis_base'] == 10010
    assert audit(bought, at=NOW)['verified_net_return_pct'] == pytest.approx(-.01)
    added, _ = fill(bought, identity='ADD', quantity=5, fee=5)
    partial, sale = fill(added, identity='PARTIAL', side='SELL', quantity=3, price=110, rate=11, fee=3)
    assert sale['pnl'] == pytest.approx(624)
    assert partial['positions']['TEST']['quantity'] == 12
    assert partial['positions']['TEST']['cost_basis_base'] == pytest.approx(12012)
    closed, _ = fill(partial, identity='FINAL', side='SELL', quantity=12, price=110, rate=11, fee=12)
    assert not closed['positions']
    assert closed['cash'] == pytest.approx(103120)
    assert closed['realized_pnl'] == pytest.approx(3120)
    assert closed['fees_paid'] == 30
    assert reconcile(closed) == []
    assert audit(closed, at=NOW)['verified_net_return_pct'] == pytest.approx(3.12)


def test_fx_movement_changes_nok_nav_even_when_local_price_is_unchanged():
    bought, _ = fill(new_account(100000, base_currency='NOK', at=AT))
    bought['positions']['TEST']['fx_quote'] = fx(11)
    assert audit(bought, at=NOW)['verified_nav'] == pytest.approx(100990)
    assert audit(bought, at=NOW)['verified_net_return_pct'] == pytest.approx(.99)


def test_retries_are_idempotent_and_conflicting_trade_ids_are_rejected():
    bought, first = fill(new_account(100000, base_currency='NOK', at=AT))
    retried, duplicate = fill(bought)
    assert bought == retried and duplicate == first
    with pytest.raises(ValueError, match='reused'):
        fill(bought, price=101)


@pytest.mark.parametrize('field,value', [('quantity',0),('quantity',float('nan')),
    ('quantity',True),('price',-1),('fee',-1),('cost_currency','USD'),
    ('currency',''),('observed_at',(NOW-timedelta(minutes=16)).isoformat()),
    ('observed_at',(NOW+timedelta(seconds=1)).isoformat()),('source','')])
def test_bad_economic_input_never_mutates_balances(field,value):
    state=new_account(100000,base_currency='NOK',at=AT)
    original=deepcopy(state)
    args=dict(trade_id='BAD',ticker='TEST',side='BUY',quantity=10,price=100,currency='USD',
              observed_at=AT,source='synthetic raw',at=AT,fee=10,cost_currency='NOK',fx_quote=fx())
    args[field]=value
    with pytest.raises(ValueError): execute(state,**args)
    assert state==original


@pytest.mark.parametrize('change', ['missing','stale','future','mismatch'])
def test_unproven_fx_blocks_execution(change):
    state=new_account(100000,base_currency='NOK',at=AT)
    quote=fx()
    if change=='missing':quote={}
    if change=='stale':quote['observed_at']=(NOW-timedelta(minutes=16)).isoformat()
    if change=='future':quote['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
    if change=='mismatch':quote['base_currency']='EUR'
    with pytest.raises(ValueError):
        execute(state,trade_id='BAD',ticker='TEST',side='BUY',quantity=1,price=100,
                currency='USD',observed_at=AT,source='synthetic',at=AT,fee=0,cost_currency='NOK',fx_quote=quote)


def test_cash_and_share_tampering_remove_verified_return():
    bought,_=fill(new_account(100000,base_currency='NOK',at=AT))
    bought['cash']+=1
    result=audit(bought,at=NOW)
    assert result['verified_net_return_pct'] is None
    assert 'CASH_DOES_NOT_RECONCILE' in result['issues']
    bought['cash']-=1
    bought['positions']['TEST']['quantity']+=1
    assert 'SHARES_DO_NOT_RECONCILE' in audit(bought,at=NOW)['issues']


def test_legacy_model_balances_cannot_be_silently_relabelled():
    with pytest.raises(ValueError,match='opening balance'):
        fill(dict(cash=100000,positions={}))


def test_shared_execution_books_fx_costs_and_retry_once(tmp_path):
    from repositories.application import RepositoryRegistry
    from services.storage_service import StorageService
    from services.strategy_account_service import StrategyAccountService
    from services.simulated_execution_service import SimulatedExecutionService
    repos=RepositoryRegistry(StorageService(tmp_path,mode='local',database_url=''))
    accounts=StrategyAccountService(repos)
    accounts.ensure_defaults()
    account=accounts.get('technical_benchmark_main')
    account.update(new_account(100000,base_currency='NOK',at=AT))
    accounts.upsert(account)
    engine=SimulatedExecutionService(repos,accounts)
    intent=engine.create_intent(account_id='technical_benchmark_main',run_id='ECONOMIC',ticker='TEST',side='BUY',
        reference_price=100,quantity=10,execution_authorized=True,
        metadata=dict(currency='USD',price_observed_at=AT,price_source='synthetic raw',execution_at=AT,
                      transaction_cost=10,cost_currency='NOK',fx_quote=fx()))
    result=engine.execute(intent)
    assert result['ok']
    assert result['account']['cash']==89990
    assert accounts.equity(result['account'])==99990
    metrics=accounts.metrics('technical_benchmark_main')
    assert metrics['positions_value']==10000
    assert metrics['return_pct']==pytest.approx(-.01)
    retry=engine.execute(intent)
    assert retry['ok'] and retry['account']['cash']==89990
    assert len(engine.recent_fills())==1


def test_three_currencies_share_one_cash_balance_and_net_return():
    state=new_account(10000,base_currency='NOK',at=AT)
    for ticker,currency,quantity,price,rate,fee in [
        ('US','USD',2,50,10,5),('EU','EUR',1,100,11,3),('NO','NOK',10,50,1,2)]:
        state,_=execute(state,trade_id=ticker,ticker=ticker,side='BUY',quantity=quantity,price=price,
            currency=currency,observed_at=AT,source='synthetic raw',at=AT,fee=fee,cost_currency='NOK',
            fx_quote=fx(rate,currency) if currency!='NOK' else None)
    result=audit(state,at=NOW)
    assert state['cash']==7390
    assert result['converted_position_values']=={'US':1000,'EU':1100,'NO':500}
    assert result['verified_nav']==9990
    assert result['verified_net_return_pct']==pytest.approx(-.1)


@pytest.mark.parametrize('field', ['cost_basis_base','fees_paid','fx_rate','pnl'])
def test_inconsistent_accounting_evidence_never_verifies(field):
    state,_=fill(new_account(100000,base_currency='NOK',at=AT))
    state,_=fill(state,identity='SELL',side='SELL',quantity=5,price=110,fee=5)
    if field=='cost_basis_base':state['positions']['TEST'][field]+=1
    elif field=='fees_paid':state[field]+=1
    else:state['trades'][-1][field]+=1
    assert audit(state,at=NOW)['verified_net_return_pct'] is None


@pytest.mark.parametrize('same_order', [True, False])
@pytest.mark.parametrize('backend', ['local', 'postgres'])
def test_concurrent_orders_cannot_spend_the_same_cash(tmp_path, same_order, backend, request):
    from concurrent.futures import ThreadPoolExecutor
    from repositories.application import RepositoryRegistry
    from services.storage_service import StorageService
    from services.strategy_account_service import StrategyAccountService
    from services.simulated_execution_service import SimulatedExecutionService
    storage = request.getfixturevalue('pg') if backend == 'postgres' else StorageService(tmp_path,mode='local',database_url='')
    repos=RepositoryRegistry(storage)
    accounts=StrategyAccountService(repos);accounts.ensure_defaults()
    account=accounts.get('technical_benchmark_main')
    account.update(new_account(100000,base_currency='NOK',at=AT));accounts.upsert(account)
    engine=SimulatedExecutionService(repos,accounts)
    def order(run):
        return engine.create_intent(account_id=account['account_id'],run_id=run,ticker='TEST',side='BUY',
            reference_price=100,quantity=60,execution_authorized=True,
            metadata=dict(currency='USD',price_observed_at=AT,price_source='synthetic raw',execution_at=AT,
                          transaction_cost=0,cost_currency='NOK',fx_quote=fx()))
    first=order('ONE');second=first if same_order else order('TWO')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(engine.execute,[first,second]))
    saved=accounts.get(account['account_id'])
    assert saved['cash']==40000 and saved['positions']['TEST']['quantity']==60
    assert len(saved['trades'])==1
    assert sum(r['ok'] for r in results)==(2 if same_order else 1)
    assert reconcile(saved)==[]
    assert len(engine.recent_fills())==1


def test_projection_failure_retry_keeps_one_authoritative_fill(tmp_path, monkeypatch):
    from repositories.application import RepositoryRegistry
    from services.storage_service import StorageService
    from services.strategy_account_service import StrategyAccountService
    from services.simulated_execution_service import SimulatedExecutionService
    repos=RepositoryRegistry(StorageService(tmp_path,mode='local',database_url=''))
    accounts=StrategyAccountService(repos);accounts.ensure_defaults()
    account=accounts.get('technical_benchmark_main')
    account.update(new_account(100000,base_currency='NOK',at=AT));accounts.upsert(account)
    engine=SimulatedExecutionService(repos,accounts)
    intent=engine.create_intent(account_id=account['account_id'],run_id='RETRY',ticker='TEST',side='BUY',
        reference_price=100,quantity=10,execution_authorized=True,
        metadata=dict(currency='USD',price_observed_at=AT,price_source='synthetic raw',execution_at=AT,
                      transaction_cost=10,cost_currency='NOK',fx_quote=fx()))
    original=engine.fills.upsert
    def interrupted(*args,**kwargs):
        raise RuntimeError('projection interrupted')
    monkeypatch.setattr(engine.fills,'upsert',interrupted)
    with pytest.raises(RuntimeError,match='projection interrupted'):engine.execute(intent)
    assert accounts.get(account['account_id'])['cash']==89990
    monkeypatch.setattr(engine.fills,'upsert',original)
    assert engine.execute(intent)['ok']
    assert len(accounts.get(account['account_id'])['trades'])==1
    assert len(engine.recent_fills())==1
    rejected=engine.execute({**intent,'reference_price':101})
    assert not rejected['ok']
    assert engine.orders.get(intent['order_id'])['status']=='FILLED'
    assert accounts.get(account['account_id'])['cash']==89990
