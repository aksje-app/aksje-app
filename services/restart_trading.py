"""Explicit, atomic strategy execution against an archived restart period.

Production callers require a signed, explicitly selected operator grant. No legacy
sync, network fetch or learning write occurs inside the atomic session. Strategy
rules remain in their ordinary engines. Only the journal supplies balances.
"""
from contextvars import ContextVar
from copy import deepcopy
from datetime import timedelta
import os
from services import portfolio_accounting as ledger
from services import simulation_restart as restart
from services.economic_ledger import number, stamp, fx_rate
from services.economic_opening import digest
from services.storage_service import get_storage_service

_CURRENT = ContextVar('explicit_restart_trading_session', default=None)
_PREVIEW = ContextVar('non_persistent_production_preview', default=False)


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
        self._bound_cost_policies = {ticker:self.cost_policy(ticker) for ticker in self.evidence}

    def doc(self): return self.storage.read_json(ledger.key(self.family))
    def account(self): return self.doc()['account']
    def quote(self, ticker):
        if ticker not in self.evidence: raise ValueError('Missing explicit market/currency/cost evidence: '+ticker)
        return self.evidence[ticker]
    def rate(self, ticker):
        row = self.quote(ticker)
        return fx_rate(row['currency'], 'NOK', row.get('fx_quote'), at=self.at)
    def cost_policy(self, ticker):
        from services.trading_costs import validate
        row = self.quote(ticker)
        if 'cost_policy' in row:
            policy = validate(row['cost_policy'])
            if 'cost_components' in row or row.get('cost_source_ref') != policy['source_ref']:
                raise ValueError('Ambiguous or mismatched cost policy evidence')
        else:
            policy = validate(dict(components_per_fill=row.get('cost_components'),source_ref=row.get('cost_source_ref')))
        bound = getattr(self,'_bound_cost_policies',None)
        if bound is not None and policy != bound[ticker]:
            raise ValueError('Strategy cannot change the approved cost policy during execution')
        return policy
    def validate_evidence(self):
        for ticker, row in self.evidence.items():
            if not ticker or ticker != ticker.upper(): raise ValueError('Canonical instrument ID required')
            number(row['price'], positive=True)
            if not row.get('source') or not timedelta(0) <= stamp(self.at)-stamp(row['observed_at']) <= timedelta(minutes=15):
                raise ValueError('Fresh sourced execution price required')
            self.cost_policy(ticker); self.rate(ticker)
        if not set(self.account()['positions']) <= set(self.evidence):
            raise ValueError('Complete fresh evidence for held instruments required')
        for ticker,pos in self.account()['positions'].items():
            row=self.evidence[ticker]
            if row['currency']!=pos['currency']:
                raise ValueError('Instrument currency differs from documented holding')
            if stamp(row['observed_at'])<stamp(pos['price_observed_at']):
                raise ValueError('Execution evidence predates the latest documented position quote')
    def mark(self):
        marks = {t:dict(price=self.quote(t)['price'], observed_at=self.quote(t)['observed_at'],
                        source=self.quote(t)['source'], fx_quote=self.quote(t).get('fx_quote'))
                 for t in self.account()['positions']}
        ledger.mark(self.family, marks, at=self.at, storage=self.storage)
    def market_value(self, ticker, quantity, price): return quantity*price*self.rate(ticker)
    def size_buy(self, ticker, budget):
        row = self.quote(ticker)
        from services.trading_costs import affordable_quantity
        return affordable_quantity(self.cost_policy(ticker),budget_nok=budget,reference_price=row['price'],
                                   currency=row['currency'],nok_rate=self.rate(ticker))
    def fill(self, ticker, side, quantity, price, reason):
        row = self.quote(ticker)
        if abs(number(price, positive=True)-row['price']) > 1e-8:
            raise ValueError('Strategy price differs from documented execution')
        if ticker in self.actions:
            raise ValueError('Repeated instrument action in the same strategy job')
        from services.trading_costs import calculate
        policy = self.cost_policy(ticker)
        costs = calculate(policy,quantity=quantity,reference_price=price,side=side,
                          currency=row['currency'],nok_rate=self.rate(ticker))
        fill = dict(trade_id=digest(dict(period=self.period_id,family=self.family,run=self.run_id,ticker=ticker,side=side)),
            ticker=ticker,side=side,quantity=quantity,price=costs['price'],currency=row['currency'],
            observed_at=row['observed_at'],source=row['source'],at=self.at,fee=costs['fee_nok'],
            cost_currency='NOK',fx_quote=row.get('fx_quote'),cost_components=costs['cost_components'],
            cost_source_ref=costs['cost_source_ref'])
        if 'schema' in policy: fill['cost_calculation'] = costs['cost_calculation']
        old = self.account()['positions'].get(ticker,{})
        doc = ledger.settle(self.family, fill, storage=self.storage)
        if costs['price'] != row['price']:
            # Value held shares at the unadjusted market observation: slippage
            # is already paid in execution and must affect NAV immediately.
            self.mark()
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
                'execution_quote':dict(price=self.quote(ticker)['price'],market_data_at=self.quote(ticker)['observed_at'],source=self.quote(ticker)['source'],adjustment='raw'),
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
                      if k not in {'cash','initial_cash','trades','realized_pnl','portfolio_value','history','_pending_commit'}}
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
            trades.append({**change,**trade,'strategy_action':action,'quantity_unit':'ACTUAL_SHARES','execution_price':trade['price'],
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


def run(*, period_id, family, run_id, at, evidence, settings, operation, strategy_input, account_ref=None, storage=None, routing_input=None):
    """One transaction for all marks, fills, strategy decisions and retry receipt.

    Production execution revalidates the selected signed account and stop barrier
    under the same transaction lock as every fill and retry receipt.
    """
    environment=os.getenv('APP_ENVIRONMENT','production').lower()
    production=environment=='production'
    if environment != 'test' and not production:
        raise ValueError('Restart strategy execution requires test or explicitly approved production environment')
    if current() is not None: raise ValueError('Nested or cross-account strategy jobs are forbidden')
    if family not in ledger.FAMILIES or not run_id: raise ValueError('Explicit family and stable job ID required')
    stamp(at)
    key = restart._key(period_id)
    request = dict(period=period_id,family=family,run_id=run_id,at=at,evidence=evidence,
                   settings=settings,strategy_input=strategy_input,account_ref=account_ref,routing_input=routing_input)
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
    backend=storage or get_storage_service()
    def authorized(bundle):
        from services import production_restart as control
        if production and not _PREVIEW.get():
            chosen=control.selected(family,storage=backend)
            if chosen is None or chosen['pointer']['period_id']!=period_id:raise ValueError('No explicitly selected production account')
            grant=control._check_record(bundle,family,running=True)
            from services.production_routing import strategy_settings
            if digest(settings)!=digest(strategy_settings(family,storage=backend)):raise ValueError('Production strategy settings differ from canonical governance')
            from services.trading_costs import validate_family
            validate_family(grant['cost_policy'],family,settings)
            for row in evidence.values():
                policy=grant['cost_policy']
                if 'schema' in policy:
                    if row.get('cost_policy')!=policy or 'cost_components' in row:
                        raise ValueError('Unapproved simulation cost assumptions')
                elif row.get('cost_components')!=policy['components_per_fill'] or 'cost_policy' in row:
                    raise ValueError('Unapproved simulation cost assumptions')
                if row.get('cost_source_ref')!=policy['source_ref']:
                    raise ValueError('Unapproved simulation cost assumptions')
        with control.permission(period_id,family):return mutation(bundle)
    if production and not _PREVIEW.get():
        from services.production_restart import require_backend
        require_backend(backend)
    backend.mutate_json(key,authorized)
    return answer


def preview(*,period_id,family,at,evidence,settings,strategy_input,storage=None):
    """Run the REAL strategies in private memory; no persistent approval or orders.

    APP_ENVIRONMENT remains production. This API cannot return its memory backend
    or install routing, and the before/after source document must be identical.
    """
    from services.production_restart import permission
    backend=storage or get_storage_service();key=restart._key(period_id)
    before=backend.read_json(key);restart.verify_bundle(before)
    memory=Memory(before,key);scoped=restart.AccountStorage(period_id,memory)
    doc=scoped.read_json(ledger.key(family))
    if doc['status']=='DRAFT':
        scope='test' if os.getenv('APP_ENVIRONMENT') in {'test','development'} else 'production'
        approval=dict(approved_by='NON_PERSISTENT_PREVIEW',approval_ref='NO ACTIVATION OR ORDER',family=family,
            opening_sha256=doc['opening_sha256'],start_at=doc['account']['created_at'],approved_at=at,scope=scope)
        with permission(period_id,family):ledger.approve(family,approval,storage=scoped)
    token=_PREVIEW.set(True)
    try:
        common=dict(period_id=period_id,run_id='preview:'+digest(dict(at=at,evidence=evidence,input=strategy_input)),
            at=at,evidence=evidence,account_ref=account_reference(period_id,family,storage=memory),storage=memory)
        if family=='paper':result=paper(**common,rules=settings,signals=strategy_input)
        elif family=='autonomy':result=autonomy(**common,parameters=settings,candidates=strategy_input)
        else:
            common['run_id']=strategy_input['run_id']
            result=super_portfolio(**common,config=settings,pipeline=strategy_input,rebalance_policy='AUTO')
        result=dict(result=result,account=ledger.report(family,storage=scoped,at=stamp(at)),mode='DRY_RUN_NO_ORDERS_NO_PERSISTENT_WRITES',
            source_sha256=digest(before),evidence=deepcopy(evidence),settings=deepcopy(settings))
    finally:_PREVIEW.reset(token)
    if backend.read_json(key)!=before:raise ValueError('Source changed during preview; repeat on a stable snapshot')
    return result


def paper(*, period_id,run_id,at,evidence,rules,signals,account_ref=None,storage=None,routing_input=None):
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
               operation=operation,strategy_input=signals,account_ref=account_ref,storage=storage,routing_input=routing_input)


def autonomy(*,period_id,run_id,at,evidence,parameters,candidates,account_ref=None,storage=None,evidence_blocks=None,routing_input=None):
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
                    decisions=result['portfolio_decisions']+list(evidence_blocks or []),execution_integrity=result['execution_integrity'])
    return run(period_id=period_id,family='autonomy',run_id=run_id,at=at,evidence=evidence,settings=parameters,
               operation=operation,strategy_input=dict(candidates=candidates,evidence_blocks=evidence_blocks) if evidence_blocks else candidates,account_ref=account_ref,storage=storage,routing_input=routing_input)


def super_portfolio(*,period_id,run_id,at,evidence,config,pipeline,rebalance_policy='AUTO',account_ref=None,storage=None,routing_input=None):
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
               operation=operation,strategy_input=dict(pipeline=pipeline,rebalance_policy=rebalance_policy),account_ref=account_ref,storage=storage,routing_input=routing_input)
