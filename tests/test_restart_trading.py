"""Real ordinary strategy engines in isolated archived NOK periods, no providers."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_simulation_restart import certificate,sources,dump_program,sealed,storage,prepare
from test_revision_trade_postgres import pg
from services import portfolio_accounting as ledger,simulation_restart as restart,restart_trading as trading
from services.economic_ledger import reconcile


@pytest.fixture
def active(storage,sealed,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test');monkeypatch.setenv('PAPER_TRADING_ENABLED','true');monkeypatch.setenv('ALLOW_PAPER_TRADING_IN_TEST','true')
    bundle=prepare(storage,sealed);scoped=restart.AccountStorage(bundle['period_id'],storage)
    for family,doc in bundle['accounts'].items():
        ledger.approve(family,dict(approved_by='TEST reviewer',approval_ref='TEST new capital approval',family=family,
            opening_sha256=doc['opening_sha256'],start_at=bundle['start_at'],approved_at=bundle['start_at'],scope='test'),storage=scoped)
    return storage,bundle,scoped


def evidence(at,price=100,rate=10,currency='USD',fee=10):
    return {'TEST':dict(price=price,currency=currency,observed_at=at,source='yfinance 5m Close',
        fx_quote=dict(currency=currency,base_currency='NOK',rate=rate,observed_at=at,source='TEST ONLY FX fixing'),
        cost_components=dict(brokerage_nok=fee*.6,fx_cost_nok=fee*.4,other_nok=0),
        cost_source_ref='TEST ONLY explicit model cost assumption')}


def execute(active,family,run_id,at,inputs=None,ev=None,**kw):
    storage,bundle,scoped=active
    common=dict(period_id=bundle['period_id'],run_id=run_id,at=at,evidence=ev or evidence(at),account_ref=trading.account_reference(bundle['period_id'],family,storage=storage),storage=storage)
    if family=='paper':
        from trading_settings import DEFAULT_RULES
        return trading.paper(**common,rules={**DEFAULT_RULES,**kw.get('rules',{})},signals=inputs or [])
    if family=='autonomy':
        from autonomous_portfolio import AutonomousParameters,run_autonomous_cycle
        return run_autonomous_cycle(inputs or [],run_id,restart_context={k:v for k,v in common.items() if k!='run_id'} | {'parameters':asdict(AutonomousParameters())})
    import super_portfolio as sp
    pipeline=dict(run_id=run_id,created_at=at,candidates=inputs or [],market_activation_levels={'USA':'PRODUCTION'},regime_fit_score=70)
    return sp.evaluate(restart_context={**common,'config':asdict(sp.SuperPortfolioConfig())},pipeline=pipeline,rebalance_policy='FORCE')


def candidate(at,session_date=None,price=100):
    return dict(ticker='TEST',investment_score=90,risk_score=10,data_quality_score=100,price=price,
        sector='Technology',market='USA',portfolio_action='BUY',autonomy_outcome_code='KJØPSKANDIDAT',
        valid_for_decision=True,evidence_valid_for_decision=True,final_decision_ready=True,
        session_date=session_date or at[:10],session_open=price,previous_close=price-1,
        source='Super Portfolio independent market universe',market_data_at=at,
        raw={'last_price':price,'volatility_pct':20})


def at(active,days=0):
    start=datetime.fromisoformat(active[1]['start_at'])
    return ((start+timedelta(days=(7-start.weekday())%7 or 7)).replace(hour=15,minute=0,second=0,microsecond=0)+timedelta(days=days)).isoformat()


def test_autonomy_ordinary_decisions_pending_buy_stop_and_retries(active):
    first=at(active);second=at(active,3)
    a=execute(active,'autonomy','search-1',first,[candidate(first)])
    assert not active[2].read_json(ledger.key('autonomy'))['account']['trades']
    b=execute(active,'autonomy','buy-2',second,[candidate(second)])
    doc=active[2].read_json(ledger.key('autonomy'));account=doc['account']
    assert len(account['trades'])==1
    assert account['positions']['TEST']['quantity']<20 # 3% of NOK500k, USD100/FX10
    assert account['cash']==pytest.approx(500000-account['trades'][0]['gross_value']-10)
    assert execute(active,'autonomy','buy-2',second,[candidate(second)])==b
    third=at(active,4)
    execute(active,'autonomy','stop-3',third,[candidate(third,price=80)],evidence(third,price=80))
    final=active[2].read_json(ledger.key('autonomy'))['account']
    assert final['positions']=={} and len(final['trades'])==2
    assert final['realized_pnl']<0 and reconcile(final)==[]


def test_superportfolio_ordinary_search_rank_entry_and_stop(active):
    first=at(active);second=at(active,3)
    result=execute(active,'super_portfolio','sp-search',first,[candidate(first)])
    assert result['ranking'] and not active[2].read_json(ledger.key('super_portfolio'))['account']['trades']
    result=execute(active,'super_portfolio','sp-buy',second,[candidate(second)])
    account=active[2].read_json(ledger.key('super_portfolio'))['account']
    assert account['positions'] and len(account['trades'])==1
    third=at(active,4)
    execute(active,'super_portfolio','sp-stop',third,[candidate(third,price=80)],evidence(third,price=80))
    account=active[2].read_json(ledger.key('super_portfolio'))['account']
    assert account['positions']=={} and account['realized_pnl']<0
    assert reconcile(account)==[]


def paper_signal(at,signal='BUY',price=100):
    first=(datetime.fromisoformat(at)-timedelta(minutes=10)).isoformat()
    proof={'ticker':'TEST','samples':[dict(run_id='scan-old',market_data_at=first,observed_at=first,price=price,score=9,confidence=90),
            dict(run_id='scan-new',market_data_at=at,observed_at=at,price=price,score=9,confidence=90)]}
    return dict(ticker='TEST',signal=signal,confidence=90,trade_context=dict(candidate=candidate(at,price=price),entry_confirmation=proof,current_score=9))


def test_paper_ordinary_auto_trade_buy_profit_protect(active,monkeypatch):
    result=execute(active,'paper','paper-buy',at(active),[paper_signal(at(active))])
    assert result['outcomes'][0]['ok'],result
    doc=active[2].read_json(ledger.key('paper'))
    assert doc['account']['positions']['TEST']['quantity']==pytest.approx(9.99)
    assert doc['account']['cash']==90000
    next_at=at(active,1)
    result=execute(active,'paper','paper-tp',next_at,[paper_signal(next_at,'HOLD',price=120)],evidence(next_at,price=120))
    assert result['outcomes'][0]['ok'],result
    account=active[2].read_json(ledger.key('paper'))['account']
    assert account['positions']=={} and account['realized_pnl']>0


@pytest.mark.parametrize('failure',['stale','fx','wrong-period','draft','integrity','scope','costs'])
def test_failures_never_fall_back_or_change_any_account(active,failure,monkeypatch):
    storage,bundle,scoped=active;time=at(active);ev=evidence(time)
    if failure=='stale':ev['TEST']['observed_at']=(datetime.fromisoformat(time)-timedelta(hours=1)).isoformat()
    if failure=='fx':ev['TEST']['fx_quote']=None
    if failure=='costs':ev['TEST'].pop('cost_source_ref')
    period=bundle['period_id']
    if failure=='wrong-period':period='not-this-period'
    if failure in {'draft','integrity'}:
        raw=storage.read_json(restart._key(period));raw['accounts']['paper']['status']='DRAFT'
        if failure=='integrity':raw['accounts']['paper']['account']['cash']=1
        storage.write_json(restart._key(period),raw)
    if failure=='scope':monkeypatch.setenv('APP_ENVIRONMENT','production')
    before=storage.read_json(restart._key(bundle['period_id']))
    with pytest.raises((ValueError,KeyError,TypeError)):
        trading.paper(period_id=period,run_id='bad',at=time,evidence=ev,rules={},signals=[],storage=storage)
    assert storage.read_json(restart._key(bundle['period_id']))==before


def test_job_retry_atomic_conflict_and_concurrent_delivery(active):
    storage,bundle,scoped=active;time=at(active)
    def operation(session):
        session.fill('TEST','BUY',10,100,'TEST delivered ordinary decision');return {'ok':True}
    kwargs=dict(period_id=bundle['period_id'],family='paper',run_id='atomic',at=time,evidence=evidence(time),settings={},strategy_input={},account_ref=trading.account_reference(bundle['period_id'],'paper',storage=storage),storage=storage)
    before=storage.read_json(restart._key(bundle['period_id']))
    def interrupted(session): operation(session);raise RuntimeError('interrupted before commit')
    with pytest.raises(RuntimeError):trading.run(**kwargs,operation=interrupted)
    assert storage.read_json(restart._key(bundle['period_id']))==before
    with ThreadPoolExecutor(max_workers=4) as pool:
        answers=list(pool.map(lambda _:trading.run(**kwargs,operation=operation),range(4)))
    assert all(x=={'ok':True} for x in answers)
    assert len(scoped.read_json(ledger.key('paper'))['account']['trades'])==1
    with pytest.raises(ValueError,match='reused'):trading.run(**{**kwargs,'settings':{'changed':1}},operation=operation)


def test_paper_add_partial_split_fx_flows_dividend_and_reports(active):
    from services.restart_reporting import snapshot,export
    import zipfile,json
    from io import BytesIO
    import pandas as pd
    time=at(active);storage,bundle,scoped=active
    def command(run_id,operation,price=100,rate=10,**details):
        return execute(active,'paper',run_id,time,[dict(ticker='TEST',operation=operation,confidence=90,**details)],evidence(time,price,rate))
    command('first','BUY',amount_nok=10010)
    command('addition','BUY',amount_nok=5010)
    account=scoped.read_json(ledger.key('paper'))['account']
    assert account['positions']['TEST']['quantity']==15
    assert account['positions']['TEST']['cost_basis_base']==15020
    command('partial','SELL',price=110,rate=11,sell_pct=20)
    assert scoped.read_json(ledger.key('paper'))['account']['positions']['TEST']['quantity']==12
    def mark(price=110,rate=11):
        return dict(price=price,observed_at=time,source='TEST ONLY action mark',fx_quote=evidence(time,price,rate)['TEST']['fx_quote'])
    def event(kind,identity,**details):
        row=dict(type=kind,event_id=identity,at=time,source_ref='TEST ONLY model event',cost_currency='NOK',
                 cost_source_ref='TEST ONLY zero action costs',cost_components=dict(brokerage_nok=0,fx_cost_nok=0,other_nok=0),**details)
        return ledger.record_event('paper',row,storage=scoped)
    pre=ledger.report('paper',storage=scoped,at=datetime.fromisoformat(time))['new_period']
    event('DEPOSIT','deposit',amount_nok=10000,valuation_marks={'TEST':mark()})
    event('WITHDRAWAL','withdrawal',amount_nok=5000,valuation_marks={'TEST':mark()})
    after=ledger.report('paper',storage=scoped,at=datetime.fromisoformat(time))['new_period']
    assert after['period_net_pnl_nok']==pre['period_net_pnl_nok']
    assert after['verification']['verified_net_return_pct']==pytest.approx(pre['verification']['verified_net_return_pct'])
    event('DIVIDEND','dividend',ticker='TEST',entitlement_source_ref='TEST ONLY entitlement record',entitlement_at=time,
          entitled_quantity=12,per_share_local=1,currency='USD',fx_quote=mark()['fx_quote'],withholding_nok=10)
    event('SPLIT','split',ticker='TEST',quantity_before=12,numerator=2,denominator=1,cash_in_lieu=False,post_action_mark=mark(55))
    result=command('post-split-hold','AUTO',price=55,rate=11,signal='HOLD')
    assert not result['outcomes'][0]['ok'],result # no false stop from unadjusted old peak
    command('final','SELL',price=55,rate=11)
    data=snapshot(bundle['period_id'],'paper',storage=storage,at=datetime.fromisoformat(time))
    p=data['account']['new_period']
    assert p['positions']=={} and len(p['trades'])==4 and p['external_net_flows_nok']==5000
    assert p['dividend_income_nok']==122 and p['verification']['status']=='BESTÅTT'
    assert len(data['nav_history'])>=8
    assert data['nav_history'][-1]['nav_nok']==p['verification']['verified_nav']
    assert export(data,'pdf').startswith(b'%PDF-')
    book=pd.read_excel(BytesIO(export(data,'xlsx')),sheet_name=None)
    assert set(book)=={'Oversikt','Beholdning','Handler','NAV'} and len(book['Handler'])==4
    assert 'nettoresultat_nok' in export(data,'csv').decode('utf-8-sig')
    with zipfile.ZipFile(BytesIO(export(data,'zip'))) as z:
        manifest=json.loads(z.read('manifest.json'))
        assert manifest['read_only'] and not manifest['legacy_data_included']
        assert len(json.loads(z.read('nok_periode.json'))['account']['new_period']['trades'])==4


def test_autonomy_addition_limit_and_ordinary_partial_profit(active):
    import autonomous_portfolio as ap
    storage,bundle,scoped=active;params=asdict(ap.AutonomousParameters());params['allow_additions']=True
    def cycle(day,run_id,price=100,weight=1,score=90):
        time=at(active,day);row=candidate(time,price=price);row['proposed_position_pct']=weight;row['investment_score']=score
        return trading.autonomy(period_id=bundle['period_id'],run_id=run_id,at=time,evidence=evidence(time,price),
                parameters=params,candidates=[row],account_ref=trading.account_reference(bundle['period_id'],'autonomy',storage=storage),storage=storage)
    cycle(0,'scan');cycle(3,'buy')
    first=scoped.read_json(ledger.key('autonomy'))['account']['positions']['TEST']['quantity']
    cycle(4,'add',weight=3)
    account=scoped.read_json(ledger.key('autonomy'))['account']
    assert account['positions']['TEST']['quantity']>first
    assert account['positions']['TEST']['quantity']*1000<=500000*.03
    cycle(5,'profit',price=120,weight=3)
    account=scoped.read_json(ledger.key('autonomy'))['account']
    assert any(t['action']=='SELL' for t in account['trades'])
    assert account['positions']['TEST']['quantity']<15
    assert reconcile(account)==[]


def test_new_engine_never_syncs_legacy_or_resets_learning(active,monkeypatch):
    import autonomous_portfolio as ap,super_portfolio as sp,trading_engine as pe
    def forbidden(*args,**kwargs): raise AssertionError('Legacy state or learning write attempted')
    monkeypatch.setattr(ap,'_write',forbidden);monkeypatch.setattr(ap,'load_portfolio',forbidden)
    monkeypatch.setattr(ap,'get_strategy_account_service',forbidden)
    monkeypatch.setattr(sp,'load_state',forbidden);monkeypatch.setattr(sp,'save_state',forbidden)
    monkeypatch.setattr(pe,'_legacy_load_portfolio',forbidden);monkeypatch.setattr(pe,'_legacy_save_portfolio',forbidden)
    storage=active[0];legacy={'cash':12,'positions':{'OLD':{'quantity':7}},'loss':-25000}
    learning={'observations':81,'weights':[.3,.7]}
    storage.write_json('paper_trading/portfolio.json',legacy);storage.write_json('learning/model.json',learning)
    time=at(active)
    execute(active,'autonomy','scan',time,[candidate(time)])
    execute(active,'super_portfolio','search',time,[candidate(time)])
    execute(active,'paper','buy',time,[dict(ticker='TEST',operation='BUY',confidence=90)])
    assert storage.read_json('paper_trading/portfolio.json')==legacy
    assert storage.read_json('learning/model.json')==learning


def test_pg_ordinary_strategy_job_rollback_retry_and_restart(pg,sealed,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test');monkeypatch.setenv('PAPER_TRADING_ENABLED','true');monkeypatch.setenv('ALLOW_PAPER_TRADING_IN_TEST','true')
    bundle=prepare(pg,sealed);scoped=restart.AccountStorage(bundle['period_id'],pg)
    for family,doc in bundle['accounts'].items():
        ledger.approve(family,dict(approved_by='TEST reviewer',approval_ref='TEST capital',family=family,
            opening_sha256=doc['opening_sha256'],start_at=bundle['start_at'],approved_at=bundle['start_at'],scope='test'),storage=scoped)
    ctx=(pg,bundle,scoped);time=at(ctx)
    args=dict(period_id=bundle['period_id'],run_id='pg-buy',at=time,evidence=evidence(time),rules={},
              signals=[dict(ticker='TEST',operation='BUY',confidence=90,amount_nok=10010)],account_ref=trading.account_reference(bundle['period_id'],'paper',storage=pg),storage=pg)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:trading.paper(**args),range(4)))
    assert all(r==results[0] for r in results)
    assert len(scoped.read_json(ledger.key('paper'))['account']['trades'])==1
    # A DB error AFTER all strategy/fill work must roll back the whole bundle.
    connection=pg._conn()
    with connection.cursor() as cur:
        cur.execute("""CREATE FUNCTION reject_restart_update() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.name LIKE 'simulation_restarts/%' THEN RAISE EXCEPTION 'test restart commit interrupted'; END IF; RETURN NEW; END $$""")
        cur.execute('CREATE TRIGGER reject_restart BEFORE UPDATE ON app_kv_store FOR EACH ROW EXECUTE FUNCTION reject_restart_update()')
    connection.commit();connection.close()
    before=pg.read_json(restart._key(bundle['period_id']))
    args['run_id']='pg-add'
    with pytest.raises(Exception,match='interrupted'):trading.paper(**args)
    assert pg.read_json(restart._key(bundle['period_id']))==before
    connection=pg._conn()
    with connection.cursor() as cur:cur.execute('DROP TRIGGER reject_restart ON app_kv_store')
    connection.commit();connection.close()
    trading.paper(**args)
    assert len(scoped.read_json(ledger.key('paper'))['account']['trades'])==2


def test_superportfolio_existing_rebalance_add_reduce_and_fx(active):
    import super_portfolio as sp
    storage,bundle,scoped=active
    def cycle(day,identity,limit,rate=10):
        time=at(active,day)
        pipeline=dict(run_id=identity,created_at=time,candidates=[candidate(time)],market_activation_levels={'USA':'PRODUCTION'},regime_fit_score=70)
        config=asdict(sp.SuperPortfolioConfig());config['max_position_pct']=limit
        return trading.super_portfolio(period_id=bundle['period_id'],run_id=identity,at=time,evidence=evidence(time,rate=rate),
            config=config,pipeline=pipeline,rebalance_policy='FORCE',account_ref=trading.account_reference(bundle['period_id'],'super_portfolio',storage=storage),storage=storage)
    cycle(0,'scan',5);cycle(3,'initial',5)
    initial=scoped.read_json(ledger.key('super_portfolio'))['account']['positions']['TEST']['quantity']
    added=cycle(4,'increase',15)
    account=scoped.read_json(ledger.key('super_portfolio'))['account']
    assert account['positions']['TEST']['quantity']>initial
    assert any(t['strategy_action']=='ADD' for t in added['changes'])
    reduced=cycle(7,'reduce',5,rate=11)
    account=scoped.read_json(ledger.key('super_portfolio'))['account']
    assert any(t['strategy_action']=='REDUCE' for t in reduced['changes'])
    assert account['positions']['TEST']['quantity']<initial and account['realized_pnl']>0
    assert reconcile(account)==[]


def test_job_account_reference_is_bound_to_period_family_and_approval(active):
    storage,bundle,scoped=active;time=at(active)
    reference=trading.account_reference(bundle['period_id'],'paper',storage=storage)
    for field in ('period_id','family','opening_sha256','approval_sha256','scope'):
        bad={**reference,field:'wrong'}
        before=storage.read_json(restart._key(bundle['period_id']))
        with pytest.raises(ValueError,match='reference mismatch'):
            trading.paper(period_id=bundle['period_id'],run_id='wrong-'+field,at=time,evidence=evidence(time),
                          rules={},signals=[],account_ref=bad,storage=storage)
        assert storage.read_json(restart._key(bundle['period_id']))==before


def test_lost_job_acknowledgement_recovers_without_addition(active,monkeypatch):
    storage,bundle,scoped=active;time=at(active);original=storage.mutate_json
    def lose_ack(key,transform,default=None):
        original(key,transform,default)
        raise ConnectionError('TEST committed but acknowledgement lost')
    monkeypatch.setattr(storage,'mutate_json',lose_ack)
    signals=[dict(ticker='TEST',operation='BUY',confidence=90,amount_nok=10010)]
    with pytest.raises(ConnectionError): execute(active,'paper','lost-ack',time,signals)
    before=storage.read_json(restart._key(bundle['period_id']))
    monkeypatch.setattr(storage,'mutate_json',original)
    result=execute(active,'paper','lost-ack',time,signals)
    assert result['outcomes'][0]['ok']
    assert storage.read_json(restart._key(bundle['period_id']))==before
    assert len(scoped.read_json(ledger.key('paper'))['account']['trades'])==1


def test_paper_automatic_addition_cooldown_uses_latest_not_oldest_buy(active):
    import trading_engine as engine
    storage,bundle,scoped=active
    for day,run in [(0,'old-buy'),(3,'latest-buy')]:
        execute(active,'paper',run,at(active,day),[dict(ticker='TEST',operation='BUY',confidence=90,amount_nok=10010)])
    time=(datetime.fromisoformat(at(active,3))+timedelta(hours=1)).isoformat()
    def inspect(session):
        blocked,message=engine._automatic_repeat_buy_block_v1931ay(session.projection(),'TEST',{'automatic_same_ticker_buy_cooldown_hours':24},now=datetime.fromisoformat(time).replace(tzinfo=None))
        assert blocked,message
        return dict(blocked=blocked)
    result=trading.run(period_id=bundle['period_id'],family='paper',run_id='cooldown-check',at=time,evidence=evidence(time),
        settings={},operation=inspect,strategy_input={},account_ref=trading.account_reference(bundle['period_id'],'paper',storage=storage),storage=storage)
    assert result['blocked'] and len(scoped.read_json(ledger.key('paper'))['account']['trades'])==2
