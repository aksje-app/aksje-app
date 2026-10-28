"""Ordinary entrypoints route only to an explicitly selected signed NOK account.

No selection -> existing behavior. A broken/stopped selection raises, never falls
back. Market data are fetched before the ledger transaction; no guessed FX/fees.
"""
from copy import deepcopy
from datetime import datetime,timezone
from uuid import uuid4
from services import production_restart as control
from services.economic_opening import digest


def completed(chosen,run_id,source_input):
    family=chosen['pointer']['family']
    for event in chosen['bundle']['accounts'][family]['events']:
        if event['kind']=='STRATEGY_RUN' and event['payload']['run_id']==run_id:
            if digest(event['payload']['request'].get('routing_input'))!=digest(source_input):
                raise ValueError('Job ID reused with different ordinary inputs')
            return deepcopy(event['payload']['result'])
    return None


def market_evidence(ticker,*,currency=None,quote=None,fx_quote=None,at,cost_policy):
    from services.trading_costs import validate
    validate(cost_policy)
    import yfinance as yf
    from scanner_fresh_quote import fresh_paper_buy_quote,validate_execution_quote
    quote=deepcopy(quote or {})
    valid,_=validate_execution_quote(quote.get('price'),{'execution_quote':quote,'market_data_at':quote.get('market_data_at')},now=datetime.fromisoformat(at))
    if not valid:
        quote,error=fresh_paper_buy_quote(ticker,now=datetime.fromisoformat(at))
        if not quote:raise ValueError('Missing documented execution price: '+ticker+'; '+error)
    valid,error=validate_execution_quote(quote.get('price'),{'execution_quote':quote,'market_data_at':quote.get('market_data_at')},now=datetime.fromisoformat(at))
    if not valid:raise ValueError(error)
    if not currency:
        currency=yf.Ticker(ticker).fast_info['currency']
    if not isinstance(currency,str) or len(currency)!=3:raise ValueError('Documented instrument currency required')
    currency=currency.upper();fx=None
    if currency!='NOK':
        from services.economic_ledger import fx_rate
        try:fx_rate(currency,'NOK',fx_quote,at=at);fx=deepcopy(fx_quote)
        except (ValueError,KeyError,TypeError):
            fxq,error=fresh_paper_buy_quote(currency+'NOK=X',now=datetime.fromisoformat(at))
            if not fxq:raise ValueError('Missing documented FX: '+currency+'; '+error)
            fx=dict(currency=currency,base_currency='NOK',rate=fxq['price'],observed_at=fxq['market_data_at'],source=fxq['source']+':'+currency+'NOK=X')
    costs = dict(cost_policy=deepcopy(cost_policy)) if 'schema' in cost_policy else dict(cost_components=deepcopy(cost_policy['components_per_fill']))
    return dict(price=quote['price'],currency=currency,observed_at=quote['market_data_at'],source=quote['source'],
        fx_quote=fx,cost_source_ref=cost_policy['source_ref'],**costs)


def context(family,run_id,rows,*,storage=None,at=None):
    from services.restart_trading import account_reference
    chosen=control.selected(family,storage=storage)
    if chosen is None:return None
    p=chosen['approval'];doc=chosen['bundle']['accounts'][family]
    at=at or datetime.now(timezone.utc).isoformat()
    rows={str(r['ticker']).upper():r for r in rows}
    evidence={};blocked=[]
    for ticker in sorted(set(rows)|set(doc['account']['positions'])):
        row=rows.get(ticker,{})
        held=doc['account']['positions'].get(ticker,{})
        cached=(chosen['bundle']['accounts'][family].get('events') or [])
        # Strategy metadata may supply a documented quote, never numeric marks.
        quote=row.get('execution_quote')
        from scanner_fresh_quote import validate_execution_quote
        valid,_=validate_execution_quote((quote or {}).get('price'),{'execution_quote':quote or {},'market_data_at':(quote or {}).get('market_data_at')},now=datetime.fromisoformat(at))
        if not valid:
            runs=[e['payload'] for e in cached if e['kind']=='STRATEGY_RUN']
            quote=((runs[-1]['state'].get('positions',{}).get(ticker,{}) if runs else {}).get('execution_quote'))
        try:
            evidence[ticker]=market_evidence(ticker,currency=held.get('currency') or row.get('currency'),quote=quote,
                fx_quote=held.get('fx_quote') or row.get('fx_quote'),at=at,cost_policy=p['cost_policy'])
        except Exception:
            if ticker in doc['account']['positions'] or family=='paper':raise
            blocked.append(dict(ticker=ticker,action='NO_EXECUTION',reason='Missing documented execution/FX evidence'))
    return dict(period_id=p['period_id'],run_id=run_id,at=at,evidence=evidence,
        account_ref=account_reference(p['period_id'],family,storage=storage),storage=storage,evidence_blocks=blocked)


def paper(ticker,operation,*,signal=None,confidence=0,trade_context=None,price=None,**details):
    from services import restart_trading as trading
    if trading.current() is not None:return None
    ctx=trade_context or {};ticker=str(ticker).upper()
    run_id=str(ctx.get('run_id') or ctx.get('execution_id') or uuid4())+':'+ticker+':'+operation
    selected=control.selected('paper')
    if selected is None:return None
    signals=[dict(ticker=ticker,operation=operation,signal=signal,confidence=confidence,trade_context=ctx,**details)]
    cached=completed(selected,run_id,signals)
    if cached is not None:
        outcome=cached['outcomes'][0];return outcome['ok'],outcome['message']
    common=context('paper',run_id,[{'ticker':ticker,'execution_quote':ctx.get('execution_quote')}])
    if common is None:return None
    common.pop('evidence_blocks')
    result=trading.paper(**common,rules=strategy_settings('paper'),signals=signals,routing_input=signals)
    outcome=result['outcomes'][0]
    return outcome['ok'],outcome['message']


def autonomy(candidates,run_id):
    from services import restart_trading as trading,autonomy_nok_companion as companion
    if trading.current() is not None:return None
    chosen=control.selected('autonomy',require_running=False)
    if chosen is None:return None
    storage=control.get_storage_service();run_id=run_id or 'manual-'+str(uuid4())
    source_input=deepcopy(candidates)
    if chosen['bundle']['production_controls']['autonomy']['status']!='RUNNING':
        # Match the established separation: pausing the financial account must
        # not freeze independent learning observations or revive legacy cash.
        prepared=companion.prepare(chosen,run_id,candidates,storage=storage)
        state=view('autonomy',storage=storage)
        decisions=[dict(ticker=t,action='HOLD',reason_code='PAUSED',risk_execution_blocked=True) for t in state['positions']]
        learning=companion.complete(chosen,run_id,prepared,state,[],decisions,storage=storage)
        from autonomous_portfolio import calculate_performance
        return {**learning,'family':'autonomy','period_id':chosen['pointer']['period_id'],'run_id':run_id,
            'portfolio':state,'portfolio_decisions':decisions,'decisions':decisions,'portfolio_trades':[],
            'production_changed':False,'financial_status':'PAUSED','execution_integrity':{'ok':True},'performance':calculate_performance(state)}
    result=completed(chosen,run_id,candidates)
    already=result is not None
    if already:
        prepared=storage.read_json(companion.preparation_key(chosen,run_id))
    else:
        prepared=companion.prepare(chosen,run_id,candidates,storage=storage)
        candidates=prepared['candidates']
        common=context('autonomy',run_id,candidates,storage=storage)
        candidates=[row for row in candidates if str(row['ticker']).upper() in common['evidence']]
        result=trading.autonomy(**common,parameters=prepared['settings'],candidates=candidates,routing_input=source_input)
    state=view('autonomy');doc=control.selected('autonomy')['bundle']['accounts']['autonomy']
    receipts=[e['payload'] for e in doc['events'] if e['kind']=='STRATEGY_RUN']
    last=next(e for e in reversed(receipts) if e['run_id']==run_id)
    trade_ids={r.get('trade_id') for r in last['decisions']}
    trades=[t for t in doc['account']['trades'] if t['trade_id'] in trade_ids]
    learning=companion.complete(chosen,run_id,prepared,state,trades,result['decisions'],storage=storage)
    from autonomous_portfolio import calculate_performance
    return {**result,**learning,'portfolio':state,'portfolio_decisions':result['decisions'],
        'portfolio_trades':trades,'run_id':run_id,'production_changed':True,'already_committed':already,
        'performance':calculate_performance(state),
        'market_snapshot':prepared['market_snapshot'],'parallel_strategy_run':prepared['parallel_strategy_run'],
        'technical_contribution':prepared['technical_contribution']}


def super_portfolio(pipeline,policy,*,scheduled=False):
    from services import restart_trading as trading
    if trading.current() is not None:return None
    chosen=control.selected('super_portfolio')
    if chosen is None:return None
    if pipeline is None:
        import super_portfolio as engine
        from dataclasses import fields
        cfg=engine.SuperPortfolioConfig(**{k:v for k,v in strategy_settings('super_portfolio').items() if k in {f.name for f in fields(engine.SuperPortfolioConfig)}})
        pipeline=engine.get_or_build_super_portfolio_market_pipeline(cfg=cfg,force_refresh=engine._rebalance_due(view('super_portfolio'),datetime.now(timezone.utc),cfg,policy))
    run_id=str(pipeline.get('run_id') or '')
    if not run_id:raise ValueError('Stable pipeline run ID required')
    source_input=dict(pipeline=pipeline,policy=policy)
    cached=completed(chosen,run_id,source_input)
    if cached is not None:
        if scheduled:return super_risk()
        return {**cached,'state':view('super_portfolio'),'already_committed':True,'stop_alerts':[]}
    common=context('super_portfolio',run_id,pipeline.get('candidates',[]))
    blocks=common.pop('evidence_blocks')
    pipeline=deepcopy(pipeline)
    pipeline['execution_evidence_blocks']=blocks
    pipeline['candidates']=[row for row in pipeline.get('candidates',[]) if str(row['ticker']).upper() in common['evidence']]
    result=trading.super_portfolio(**common,config=strategy_settings('super_portfolio'),pipeline=pipeline,rebalance_policy=policy,routing_input=source_input)
    return {**result,'state':view('super_portfolio'),'stop_alerts':[],'rebalance_due':bool(result['changes'])}


def super_risk(*,at=None):
    from services import restart_trading as trading
    if trading.current() is not None:return None
    chosen=control.selected('super_portfolio')
    if chosen is None:return None
    instant=at or datetime.now(timezone.utc)
    slot=instant.replace(minute=instant.minute//15*15,second=0,microsecond=0).isoformat()
    run_id='stop:'+slot;source_input={'stop_slot':slot}
    cached=completed(chosen,run_id,source_input)
    if cached is not None:return {**cached,'already_committed':True}
    common=context('super_portfolio',run_id,[],at=instant.isoformat());common.pop('evidence_blocks')
    def operation(session):
        import super_portfolio as engine
        return engine.run_lightweight_stop_surveillance(state=session.projection(),now=instant)
    return trading.run(**common,family='super_portfolio',settings=strategy_settings('super_portfolio'),operation=operation,
        strategy_input=source_input,routing_input=source_input)


def view(family,*,storage=None):
    """Read projection without fresh-data fetches; reports retain verification age."""
    chosen=control.selected(family,storage=storage,require_running=False)
    if chosen is None:return None
    from services import portfolio_accounting as ledger
    p=chosen['approval'];doc=chosen['bundle']['accounts'][family];account=doc['account']
    receipts=[e['payload'] for e in doc['events'] if e['kind']=='STRATEGY_RUN']
    meta=deepcopy(receipts[-1]['state'] if receipts else {})
    positions={}
    report=ledger.report(family,storage=__import__('services.simulation_restart',fromlist=['AccountStorage']).AccountStorage(p['period_id'],storage))['new_period']
    nav=report['verification']['verified_nav']
    for ticker,pos in account['positions'].items():
        positions[ticker]={**deepcopy(meta.get('positions',{}).get(ticker,{})),**deepcopy(pos),
            'ticker':ticker,'shares':pos['quantity'],'units':pos['quantity'],'entry_price':pos['average_price'],
            'avg_price':pos['average_price'],'market_data_at':pos['price_observed_at'],
            'market_value':report['verification']['converted_position_values'].get(ticker)}
    trades=[{**deepcopy(t),'type':t['action'],'shares':t['quantity'],'time':t['timestamp'],'amount':t['gross_value'],'pnl_amount':t['pnl']} for t in account['trades']]
    return {**meta,**deepcopy(account),'cash':account['cash'],'initial_cash':account['initial_cash'],'positions':positions,
        'trades':trades,'realized_pnl':account['realized_pnl'],'portfolio_value':nav,
        'status':'ACTIVE' if chosen['bundle']['production_controls'][family]['status']=='RUNNING' else 'PAUSED',
        'config':deepcopy(p['settings']),'economic_period_id':p['period_id'],'economic_verification':report['verification'],
        'portfolio_return_pct':report['verification']['verified_net_return_pct']}


def guard_legacy_write(family):
    if control.selected(family,require_running=False) is not None:
        raise ValueError('Selected NOK account: legacy balance writes are forbidden; use the authoritative strategy journal')


def legacy_history(family,*,storage=None):
    """Frozen legacy data, deliberately separate from active projection/NAV."""
    from services.storage_service import get_storage_service
    from storage_architecture import get_runtime_paths,PROJECT_ROOT
    import json
    storage=storage or get_storage_service()
    prefix={'paper':'paper_trading','autonomy':'autonomous_portfolio','super_portfolio':'super_portfolio'}[family]
    keys={'paper':['portfolio.json'],'autonomy':['portfolio.json','trades.json','equity_history.json','performance.json'],
          'super_portfolio':['state.json','transactions.jsonl']}[family]
    result={'classification':'HISTORISK MODELLRESULTAT – KAN VÆRE UVERIFISERT','active_account_data':False,'documents':{}}
    for key in keys:
        name=prefix+'/'+key
        value=storage.read_json(name,None) if key.endswith('.json') else storage.read_jsonl(name)
        if value is None:
            path=get_runtime_paths(create=False).data/name
            if path.is_file() and key.endswith('.json'):value=json.loads(path.read_text())
        if value is not None:result['documents'][name]=value
    if family=='paper' and storage.using_postgres():
        connection=storage._conn()
        try:
            connection.set_session(readonly=True)
            with connection.cursor() as cur:
                for table in ('paper_state','paper_positions','paper_trades'):
                    cur.execute('SELECT to_regclass(%s)',(table,))
                    if cur.fetchone()[0]:
                        from psycopg2 import sql
                        cur.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table)))
                        fields=[c.name for c in cur.description]
                        result['documents'][table]=[dict(zip(fields,row)) for row in cur.fetchall()]
        finally:connection.close()
    if family=='paper' and (PROJECT_ROOT/'paper_portfolio.json').is_file():
        result['documents']['legacy_file']=json.loads((PROJECT_ROOT/'paper_portfolio.json').read_text())
    return result


def strategy_settings(family,*,storage=None,require_stored=False):
    """Snapshot the existing configured strategy; never invent restart settings."""
    from dataclasses import asdict
    storage=storage or control.get_storage_service()
    def approved_fallback():
        chosen=control.selected(family,storage=storage,require_running=False)
        return deepcopy(chosen['approval']['settings']) if chosen is not None else None
    if family=='paper':
        import json
        from pathlib import Path
        from trading_settings import DEFAULT_RULES,STORAGE_KEY,LOCAL_RULES_FILE
        rules=deepcopy(DEFAULT_RULES);value=None
        if storage.using_postgres():
            connection=storage._conn()
            try:
                connection.set_session(readonly=True)
                with connection.cursor() as cur:
                    cur.execute("SELECT to_regclass('trading_rules')")
                    if cur.fetchone()[0]:
                        cur.execute('SELECT rules FROM trading_rules WHERE id=1');row=cur.fetchone()
                        if row:value=json.loads(row[0]) if isinstance(row[0],str) else row[0]
            finally:connection.close()
        if not value:value=storage.read_json(STORAGE_KEY,None)
        if require_stored and (not isinstance(value,dict) or not set(value).intersection(DEFAULT_RULES)):
            raise ValueError('Stored Paper strategy settings required; no restart defaults')
        if value is None:
            approved=approved_fallback()
            if approved is not None:return approved
        if value is None and Path(LOCAL_RULES_FILE).is_file():value=json.loads(Path(LOCAL_RULES_FILE).read_text())
        if value:rules.update(value)
        return rules
    if family=='autonomy':
        from autonomous_portfolio import AutonomousParameters,_read,PARAMETERS_PATH
        raw=storage.read_json('autonomous_portfolio/parameters.json',None)
        if require_stored and (not isinstance(raw,dict) or not set(raw).intersection(AutonomousParameters.__dataclass_fields__)):
            raise ValueError('Stored Autonomy strategy settings required; no restart defaults')
        if raw is None:
            approved=approved_fallback()
            if approved is not None:return approved
            import json
            raw=json.loads(PARAMETERS_PATH.read_text()) if PARAMETERS_PATH.is_file() else {}
        return asdict(AutonomousParameters(**{k:v for k,v in raw.items() if k in AutonomousParameters.__dataclass_fields__}).normalized())
    import super_portfolio as engine
    value=storage.read_json(engine.STATE_KEY,None)
    if require_stored and (not isinstance(value,dict) or not isinstance(value.get('config'),dict)
                          or not set(value['config']).intersection(engine.SuperPortfolioConfig.__dataclass_fields__)):
        raise ValueError('Stored Super Portfolio strategy settings required; no restart defaults')
    if value is None:
        approved=approved_fallback()
        if approved is not None:return approved
        import json
        value=json.loads(engine.STATE_PATH.read_text()) if engine.STATE_PATH.is_file() else {}
    state=engine._normalized_loaded_state(value);allowed=set(engine.SuperPortfolioConfig.__dataclass_fields__)
    return asdict(engine.SuperPortfolioConfig(**{k:v for k,v in state.get('config',{}).items() if k in allowed}))


def live_preview(period_id,family,*,strategy_input,cost_policy,storage=None):
    """Real provider evidence plus existing settings and read-only source inputs.

    Missing proof is an error, not a synthetic dry-run success. No scanner worker
    is imported (its startup may migrate stores); use completed actual scan rows.
    """
    from services import restart_trading as trading,simulation_restart as restart
    from services.storage_service import get_storage_service
    storage=storage or get_storage_service();bundle=storage.read_json(restart._key(period_id))
    restart.verify_bundle(bundle);doc=bundle['accounts'][family]
    settings=strategy_settings(family,storage=storage,require_stored=True)
    from services.trading_costs import validate_family
    validate_family(cost_policy,family,settings)
    rows=strategy_input.get('candidates',[]) if family=='super_portfolio' else strategy_input
    rows={r['ticker']:r for r in rows};at=datetime.now(timezone.utc).isoformat();evidence={}
    blocked=[]
    for ticker in sorted(set(rows)|set(doc['account']['positions'])):
        row=rows.get(ticker,{});held=doc['account']['positions'].get(ticker,{})
        try:
            evidence[ticker]=market_evidence(ticker,currency=held.get('currency') or row.get('currency'),quote=row.get('execution_quote'),
                fx_quote=held.get('fx_quote') or row.get('fx_quote'),at=at,cost_policy=cost_policy)
        except ValueError as exc:
            # This is preflight only. Live autonomy/super-portfolio routing already
            # excludes non-held candidates without fresh execution evidence.
            # Never skip held positions (NAV) or Paper's ordinary signals.
            if family=='paper' or ticker in doc['account']['positions']:
                raise
            blocked.append(dict(ticker=ticker,action='NO_EXECUTION',reason=str(exc)[:200]))
    # Startup is not an order: full candidate-universe quote coverage is not
    # required. Missing quotes are recorded as NO_EXECUTION, independent of
    # how many markets are closed or providers are delayed. Actual held
    # positions and Paper execution inputs still fail closed above.
    # A genuine preview with at least one verified candidate remains mandatory.
    if not evidence or (rows and not set(rows).intersection(evidence)):
        raise ValueError('No actual candidate execution evidence; cannot preview')
    if blocked:
        if family=='super_portfolio':
            selected=deepcopy(strategy_input)
            selected['candidates']=[r for r in strategy_input['candidates'] if r['ticker'] in evidence]
            selected['execution_evidence_blocks']=blocked
        else:
            selected=[r for r in strategy_input if r['ticker'] in evidence]
    else:
        selected=strategy_input
    # Archived, independently produced SP pipelines may predate the explicit
    # frozen-levels field. For this *in-memory preview only*, snapshot the
    # currently governed canonical activation map; never elevate any market
    # beyond the actual production policy or rewrite persisted source input.
    policy_snapshot=None
    if family=='super_portfolio':
        from market_universe import MARKET_ACTIVATION_LEVELS
        policy_snapshot=deepcopy(MARKET_ACTIVATION_LEVELS)
        selected=deepcopy(selected)
        frozen=selected.get('market_activation_levels')
        if frozen is None:
            selected['market_activation_levels']=deepcopy(policy_snapshot)
        elif not isinstance(frozen,dict) or {str(k).upper():v for k,v in frozen.items()} != {str(k).upper():v for k,v in policy_snapshot.items()}:
            raise ValueError('Frozen market activation levels differ from governed production policy')
    receipt=trading.preview(period_id=period_id,family=family,at=at,evidence=evidence,settings=settings,
        strategy_input=selected,storage=storage)
    if policy_snapshot is not None:
        receipt['preflight_market_activation_policy']=policy_snapshot
        receipt['preflight_market_activation_policy_sha256']=digest(policy_snapshot)
    receipt['preflight_excluded_candidates']=blocked
    receipt['original_strategy_input_sha256']=digest(strategy_input)
    return receipt


def metrics(family,*,storage=None):
    """Verified, flow-adjusted metrics for existing overview consumers."""
    chosen=control.selected(family,storage=storage,require_running=False)
    if chosen is None:return None
    from services.restart_reporting import snapshot
    data=snapshot(chosen['pointer']['period_id'],family,storage=storage)
    period=data['account']['new_period'];verified=period['verification']
    values=[1+r['net_return_pct']/100 for r in data['nav_history'] if r['net_return_pct'] is not None]
    current=verified['verified_net_return_pct'];drawdown=None
    if current is not None:
        unit=1+current/100;peak=max([1,unit]+values)
        drawdown=max(0,(1-unit/peak)*100)
    return dict(equity=verified['verified_nav'],cash=period['cash_nok'],total_return_pct=current,
        realized_pnl=period['realized_pnl_nok'],drawdown_pct=drawdown,open_positions=len(period['positions']),
        economic_verification=verified,return_basis='DOCUMENTED_NOK_NET_UNITIZED_WHEN_FLOWS',
        economic_period_id=chosen['pointer']['period_id'])
