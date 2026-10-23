"""Explicit, atomic strategy execution against an archived restart period.

No active-account pointer, legacy sync, network fetch, learning write or production
activation. Strategy rules remain in their ordinary engines. Only this session's
ledger supplies balances; strategy metadata cannot supply quantities or cash.
"""
from contextvars import ContextVar
from copy import deepcopy
from datetime import timedelta
import math
import os
from services import portfolio_accounting as ledger
from services import simulation_restart as restart
from services.economic_ledger import number, stamp, fx_rate
from services.economic_opening import digest
from services.storage_service import get_storage_service

_CURRENT = ContextVar('explicit_restart_trading_session', default=None)


def current(family=None):
    session = _CURRENT.get()
    if session is not None and family and session.family != family:
        raise ValueError('Strategy attempted to use another account family')
    return session


class Memory:
    def __init__(self, bundle, key): self.bundle, self.key = deepcopy(bundle), key
    def read_json(self, key, default=None):
        if key != self.key: raise ValueError('Only explicit restart bundle is accessible')
        return deepcopy(self.bundle)
    def mutate_json(self, key, transform, default=None):
        if key != self.key: raise ValueError('Only explicit restart bundle is accessible')
        self.bundle = deepcopy(transform(deepcopy(self.bundle)))
        return deepcopy(self.bundle)


class Session:
    def __init__(self, *, period_id, family, run_id, at, evidence, settings, memory):
        self.period_id, self.family, self.run_id, self.at = period_id, family, run_id, at
        self.evidence, self.settings = deepcopy(evidence), deepcopy(settings)
        self.memory = memory
        self.storage = restart.AccountStorage(period_id, memory)
        doc = self.storage.read_json(ledger.key(family))
        runs = [e['payload'] for e in doc['events'] if e['kind'] == 'STRATEGY_RUN']
        self.state = deepcopy(runs[-1]['state'] if runs else {})
        # Splits adjust price-based strategy memories, not strategy thresholds.
        last_run = max((e['sequence'] for e in doc['events'] if e['kind']=='STRATEGY_RUN'),default=0)
        for event in doc['events']:
            if event['sequence']<=last_run or event['kind']!='ECONOMIC_EVENT' or event['payload']['type']!='SPLIT': continue
            action=event['payload'];factor=action['numerator']/action['denominator']
            pos=self.state.get('positions',{}).get(action['ticker'],{})
            for field in ('highest_price','peak_price','entry_price','avg_price','stop_loss','take_profit',
                          'trailing_stop','trailing_stop_level','effective_stop_price','profit_floor_price','target_price'):
                if pos.get(field) is not None: pos[field]/=factor
        self.decisions, self.actions = [], {}
        self.validate_evidence()

    def doc(self): return self.storage.read_json(ledger.key(self.family))
    def account(self): return self.doc()['account']
    def quote(self, ticker):
        if ticker not in self.evidence: raise ValueError('Missing explicit market/currency/cost evidence: '+ticker)
        return self.evidence[ticker]
    def rate(self, ticker):
        row = self.quote(ticker)
        return fx_rate(row['currency'], 'NOK', row.get('fx_quote'), at=self.at)
    def fee(self, ticker):
        return sum(number(v) for v in self.quote(ticker)['cost_components'].values())
    def validate_evidence(self):
        for ticker, row in self.evidence.items():
            if not ticker or ticker != ticker.upper(): raise ValueError('Canonical instrument ID required')
            number(row['price'], positive=True)
            if not row.get('source') or not timedelta(0) <= stamp(self.at)-stamp(row['observed_at']) <= timedelta(minutes=15):
                raise ValueError('Fresh sourced execution price required')
            if set(row.get('cost_components', {})) != {'brokerage_nok','fx_cost_nok','other_nok'} or not row.get('cost_source_ref'):
                raise ValueError('Explicit simulation cost assumption required, including zero costs')
            self.rate(ticker); self.fee(ticker)
        if not set(self.account()['positions']) <= set(self.evidence):
            raise ValueError('Complete fresh evidence for held instruments required')
    def mark(self):
        marks = {t:dict(price=self.quote(t)['price'], observed_at=self.quote(t)['observed_at'],
                        source=self.quote(t)['source'], fx_quote=self.quote(t).get('fx_quote'))
                 for t in self.account()['positions']}
        ledger.mark(self.family, marks, at=self.at, storage=self.storage)
    def market_value(self, ticker, quantity, price): return quantity*price*self.rate(ticker)
    def size_buy(self, ticker, budget):
        row = self.quote(ticker)
        return math.floor(max(0, budget-self.fee(ticker))/(row['price']*self.rate(ticker))*10000)/10000
    def fill(self, ticker, side, quantity, price, reason):
        row = self.quote(ticker)
        if abs(number(price, positive=True)-row['price']) > 1e-8:
            raise ValueError('Strategy price differs from documented execution')
        if ticker in self.actions:
            raise ValueError('Repeated instrument action in the same strategy job')
        fill = dict(trade_id=digest(dict(period=self.period_id,family=self.family,run=self.run_id,ticker=ticker,side=side)),
            ticker=ticker,side=side,quantity=quantity,price=price,currency=row['currency'],
            observed_at=row['observed_at'],source=row['source'],at=self.at,fee=self.fee(ticker),
            cost_currency='NOK',fx_quote=row.get('fx_quote'),cost_components=row['cost_components'],
            cost_source_ref=row['cost_source_ref'])
        old = self.account()['positions'].get(ticker,{})
        doc = ledger.settle(self.family, fill, storage=self.storage)
        self.actions[ticker] = side
        self.decisions.append(dict(ticker=ticker,side=side,reason=reason,trade_id=fill['trade_id'],
            entry_price=old.get('average_price'),pnl_pct=(price/old['average_price']-1)*100 if old.get('average_price') else 0))
        return doc['account']['trades'][-1]
    def projection(self):
        account = self.account()
        positions = {}
        for ticker, pos in account['positions'].items():
            meta = deepcopy((self.state.get('positions') or {}).get(ticker, {}))
            # Ledger fields ALWAYS win over cached strategy state.
            positions[ticker] = {**meta, **deepcopy(pos), 'ticker':ticker,
                'shares':pos['quantity'],'units':pos['quantity'],
                'entry_price':pos.get('average_price'), 'avg_price':pos.get('average_price'),
                'market_value':self.market_value(ticker,pos['quantity'],pos['last_price']),
                'market_data_at':pos['price_observed_at'], 'asset_type':'Aksje',
                'target_weight_pct':self.market_value(ticker,pos['quantity'],pos['last_price'])/self.nav()*100}
        receipts = [e['payload'] for e in self.doc()['events'] if e['kind']=='STRATEGY_RUN']
        reasons = {d['trade_id']:d for run in receipts for d in run['decisions'] if d.get('trade_id')}
        reasons.update({d['trade_id']:d for d in self.decisions if d.get('trade_id')})
        trades = [{**deepcopy(reasons.get(t['trade_id'],{})),**deepcopy(t),'type':t['action'],'shares':t['quantity'],'time':t['timestamp'],
                   'amount':t['gross_value'],'pnl_amount':t['pnl']} for t in (reversed(account['trades']) if self.family=='paper' else account['trades'])]
        return {**deepcopy(self.state),'cash':account['cash'],'initial_cash':account['initial_cash'],
                'status':'ACTIVE','positions':positions,'trades':trades,'realized_pnl':account['realized_pnl'],
                'portfolio_value':self.nav(),'high_watermark':max(self.state.get('high_watermark',0),self.nav())}
    def nav(self):
        report = ledger.report(self.family,storage=self.storage,at=stamp(self.at))['new_period']
        if report['verification']['status'] != 'BESTÅTT': raise ValueError('Unreconciled or unverified NAV blocks trading')
        return report['verification']['verified_nav']
    def save_strategy(self, portfolio):
        # Cache only non-authoritative strategy information, never balances/trades.
        self.state = {k:deepcopy(v) for k,v in portfolio.items()
                      if k not in {'cash','initial_cash','trades','realized_pnl','portfolio_value','history'}}
    def paper_buy(self,ticker,price,budget,confidence,reason,ctx):
        import trading_engine as engine
        quantity = self.size_buy(ticker,budget)
        if quantity <= 0: return False,'Utilstrekkelig kapital etter kostnader'
        old = self.projection()['positions'].get(ticker,{})
        self.fill(ticker,'BUY',quantity,price,reason)
        pos = self.projection()['positions'][ticker]
        high = max(price,old.get('highest_price',price),pos['average_price'])
        trailing = engine.position_trailing_stop_pct_v18674d(old,self.settings)
        sl,tp,tr = engine.calc_levels(pos['average_price'],high,trailing_stop_pct=trailing)
        pos.update(opened_at=old.get('opened_at',self.at),highest_price=high,stop_loss=sl,take_profit=tp,
                   trailing_stop=tr,trailing_stop_pct=trailing,confidence=confidence,last_added_at=self.at,
                   entry_score=old.get('entry_score',ctx.get('current_score')),sector=ctx.get('sector','Unknown'),
                   decision_snapshot=ctx.get('decision_snapshot'),entry_confirmation=ctx.get('entry_confirmation'))
        view = self.projection();view['positions'][ticker]=pos;self.save_strategy(view)
        return True,'NOK-PAPER-KJØP '+ticker
    def paper_sell(self,ticker,price,quantity,reason):
        self.fill(ticker,'SELL',quantity,price,reason)
        self.save_strategy(self.projection())
        return True,'NOK-PAPER-SALG '+ticker
    def settle_targets(self,before,positions,changes,decision_at):
        nav_before = self.nav(); trades=[]
        for change in sorted(changes,key=lambda c:0 if c['action'] in {'SELL','REDUCE'} else 1):
            ticker,action = change['ticker'],change['action']
            pos = self.account()['positions'].get(ticker,{})
            delta = abs(float(change.get('to_pct',0))-float(change.get('from_pct',0)))
            if action in {'SELL','REDUCE'}:
                fraction = 1 if action=='SELL' else min(1,delta/max(float(change['from_pct']),1e-12))
                quantity = pos.get('quantity',0)*fraction
                side = 'SELL'
            elif action in {'BUY','ADD'}:
                budget = min(nav_before*delta/100,self.account()['cash'])
                quantity = self.size_buy(ticker,budget);side='BUY'
            else: raise ValueError('Unknown strategy action')
            price = change.get('execution_price')
            if price is None: price = self.quote(ticker)['price']
            trade = self.fill(ticker,side,quantity,price,change.get('reason','Super Portfolio target'))
            trades.append({**change,**trade,'strategy_action':action,'quantity_unit':'ACTUAL_SHARES','execution_price':price,
                           'cash_after':self.account()['cash']})
        self.state['positions'] = deepcopy(positions)
        projection=self.projection();self.save_strategy(projection)
        nav=self.nav();costs=sum(t['fee'] for t in trades)
        return dict(positions=projection['positions'],cash=self.account()['cash'],portfolio_value=nav,
            portfolio_value_before=nav_before,transaction_cost=costs,
            portfolio_return_pct=(nav/self.account()['initial_cash']-1)*100,
            period_return_pct=(nav/nav_before-1)*100,accounting_schema='BASE_CURRENCY_SHARES_V1',
            accounting_opening_balance=self.account()['opening_balance'],transactions=trades,
            turnover_costs=dict(estimated_cost=costs,traded_value=sum(t['gross_value'] for t in trades),
                               net_return_pct=(nav/nav_before-1)*100))


def account_reference(period_id,family,*,storage=None):
    """Capture with a queued job; recheck exact approval/opening before execution."""
    scoped=restart.AccountStorage(period_id,storage)
    doc=scoped.read_json(ledger.key(family))
    if doc['status']!='ACTIVE': raise ValueError('Approved account reference required')
    return dict(period_id=period_id,family=family,opening_sha256=doc['opening_sha256'],
                approval_sha256=digest(doc['approval']),scope=doc['approval']['scope'])


def run(*, period_id, family, run_id, at, evidence, settings, operation, strategy_input, account_ref=None, storage=None):
    """One transaction for all marks, fills, strategy decisions and retry receipt.

    Only isolated test execution is enabled in this release. A production rollout
    requires a separately reviewed activation path and exact approval.
    """
    if os.getenv('APP_ENVIRONMENT','production').lower() != 'test':
        raise ValueError('Restart strategy execution requires separate production enablement; test only')
    if current() is not None: raise ValueError('Nested or cross-account strategy jobs are forbidden')
    if family not in ledger.FAMILIES or not run_id: raise ValueError('Explicit family and stable job ID required')
    stamp(at)
    key = restart._key(period_id)
    request = dict(period=period_id,family=family,run_id=run_id,at=at,evidence=evidence,
                   settings=settings,strategy_input=strategy_input,account_ref=account_ref)
    request_hash = digest(request)
    answer = {}
    def mutation(bundle):
        if not bundle: raise ValueError('Explicit prepared restart period required')
        restart.verify_bundle(bundle)
        if bundle['period_id'] != period_id: raise ValueError('Period identity mismatch')
        doc = bundle['accounts'][family]
        if doc['status'] != 'ACTIVE': raise ValueError('Draft accounts cannot trade')
        ledger._require_scope(doc)
        expected=dict(period_id=period_id,family=family,opening_sha256=doc['opening_sha256'],
                      approval_sha256=digest(doc['approval']),scope=doc['approval']['scope'])
        if account_ref!=expected: raise ValueError('Job account/period/approval reference mismatch')
        for event in doc['events']:
            if event['kind']=='STRATEGY_RUN' and event['payload']['run_id']==run_id:
                if event['payload']['request_sha256']!=request_hash: raise ValueError('Job ID reused with different inputs')
                answer.update(deepcopy(event['payload']['result']));return bundle
        memory=Memory(bundle,key)
        session=Session(period_id=period_id,family=family,run_id=run_id,at=at,evidence=evidence,
                        settings=settings,memory=memory)
        session.mark()
        token=_CURRENT.set(session)
        try: result=operation(session)
        finally: _CURRENT.reset(token)
        session.nav()
        result=deepcopy(result)
        payload=dict(run_id=run_id,request_sha256=request_hash,request=deepcopy(request),at=at,period_id=period_id,family=family,
                     state=deepcopy(session.state),decisions=session.decisions,result=result)
        def journal(current_doc):
            ledger.verify(current_doc);updated=deepcopy(current_doc)
            ledger._append(updated,'STRATEGY_RUN',payload);ledger.verify(updated);return updated
        session.storage.mutate_json(ledger.key(family),journal)
        restart.verify_bundle(memory.bundle)
        answer.update(result)
        return memory.bundle
    (storage or get_storage_service()).mutate_json(key,mutation)
    return answer


def paper(*, period_id,run_id,at,evidence,rules,signals,account_ref=None,storage=None):
    def operation(session):
        import trading_engine as engine
        outcomes=[]
        for signal in signals:
            ticker=signal['ticker'];row=session.quote(ticker)
            quote=dict(price=row['price'],market_data_at=row['observed_at'],source=row['source'],adjustment='raw')
            ctx={**signal.get('trade_context',{}),'run_id':run_id,'execution_quote':quote,'market_data_at':row['observed_at']}
            action=signal.get('operation','AUTO')
            if action=='BUY':
                ok,message=engine.paper_buy(ticker,row['price'],signal.get('confidence',0),
                    signal.get('reason','BUY signal'),ctx,amount_override=signal.get('amount_nok'))
            elif action=='SELL':
                ok,message=engine.paper_sell(ticker,row['price'],signal.get('reason','SELL signal'),ctx,
                                             sell_pct=signal.get('sell_pct',100),sell_shares=signal.get('quantity'))
            elif action=='AUTO':
                ok,message=engine.auto_trade(ticker,row['price'],signal['signal'],signal.get('confidence',0),
                                            rsi=signal.get('rsi'),prev_rsi=signal.get('prev_rsi'),trade_context=ctx)
            else: raise ValueError('Unknown ordinary Paper action')
            outcomes.append(dict(ticker=ticker,ok=ok,message=message))
        return dict(family='paper',period_id=period_id,run_id=run_id,outcomes=outcomes)
    return run(period_id=period_id,family='paper',run_id=run_id,at=at,evidence=evidence,settings=rules,
               operation=operation,strategy_input=signals,account_ref=account_ref,storage=storage)


def autonomy(*,period_id,run_id,at,evidence,parameters,candidates,account_ref=None,storage=None):
    def operation(session):
        from autonomous_portfolio import simulate_autonomy_cycle
        view=session.projection()
        prepared=[]
        for item in candidates:
            row=deepcopy(item);quote=session.quote(row['ticker'])
            if row.get('currency') and row['currency']!=quote['currency']: raise ValueError('Instrument currency mismatch')
            row.update(price=quote['price'],market_data_at=quote['observed_at'],
                execution_quote=dict(price=quote['price'],market_data_at=quote['observed_at'],source=quote['source'],adjustment='raw'))
            prepared.append(row)
        result=simulate_autonomy_cycle(prepared,parameters=parameters,portfolio=view,trades=view['trades'],
                                      now=stamp(at),run_id=run_id,restart_state=session.state)
        session.save_strategy(result['portfolio'])
        session.state['pending_entries']=deepcopy(result['pending_entries'])
        return dict(family='autonomy',period_id=period_id,run_id=run_id,
                    decisions=result['portfolio_decisions'],execution_integrity=result['execution_integrity'])
    return run(period_id=period_id,family='autonomy',run_id=run_id,at=at,evidence=evidence,settings=parameters,
               operation=operation,strategy_input=candidates,account_ref=account_ref,storage=storage)


def super_portfolio(*,period_id,run_id,at,evidence,config,pipeline,rebalance_policy='AUTO',account_ref=None,storage=None):
    if not isinstance(pipeline,dict): raise ValueError('Explicit completed market pipeline required')
    if any(row.get('source') != 'Super Portfolio independent market universe' for row in pipeline.get('candidates',[])):
        raise ValueError('Restart requires documented ordinary market-pipeline candidates')
    if str(pipeline.get('run_id'))!=str(run_id): raise ValueError('Pipeline belongs to another job')
    def operation(session):
        import super_portfolio as engine
        state=session.projection();state['config']=deepcopy(config)
        result=engine.evaluate(pipeline=pipeline,persist=False,now=stamp(at),rebalance_policy=rebalance_policy,
                               simulation_state=state)
        session.save_strategy(result['state'])
        return dict(family='super_portfolio',period_id=period_id,run_id=run_id,
                    changes=result['changes'],entry_gate=result['entry_gate'],ranking=result['snapshot']['ranking'])
    return run(period_id=period_id,family='super_portfolio',run_id=run_id,at=at,evidence=evidence,settings=config,
               operation=operation,strategy_input=dict(pipeline=pipeline,rebalance_policy=rebalance_policy),account_ref=account_ref,storage=storage)
