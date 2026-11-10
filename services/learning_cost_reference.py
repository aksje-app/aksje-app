"""Costed research reference, never an executed fill or portfolio profit.

The normalized total-return unit assumes provider reinvestment, no intermediate
reinvestment charges and no tax. Only the pinned proportional Autonomy policy
is supported. Foreign currency needs supplied, timestamped endpoint references.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from math import isfinite
import re

from services.economic_ledger import fx_rate, number, stamp
from services.learning_outcome_integrity import digest
from services.trading_costs import calculate

METHOD='AUTONOMY_COSTED_TOTAL_RETURN_REFERENCE_V1'
KEY='controlled_learning/measurement_contracts/'+METHOD+'.json'
DEFINITION_KEY=KEY[:-5]+'_definition.json'
SOURCE='USER_APPROVED_SIMULATION_MODEL:SHA256:d36bd7ed61f898c93403910a50b32971595504581f73baf37a190faee4b0a131:section_3:autonomy'
COST_POLICY={'schema':'NOK_COST_POLICY_V2','source_ref':SOURCE,'components':{
    'model_transaction_cost_nok':{'rate_bps':20,'source_ref':SOURCE+':base_model_cost'},
    'fx_cost_nok':{'rate_bps':25,'source_ref':SOURCE+':additional_fx_on_actual_conversion'}}}
DEFINITION={'schema':1,'method':METHOD,'cost_policy':COST_POLICY,
    'scope':'AUTONOMY_MODEL_COST_REFERENCE_NOT_PORTFOLIO_PROFIT',
    'return_unit':'PROVIDER_ADJUSTED_TOTAL_RETURN_UNIT_100',
    'funding':'NOK_SETTLED_TEST_POSITION; FX_CONVERSION_AT_BOTH_ENDPOINTS_IF_FOREIGN',
    'fx_policy':'SUPPLIED_TIMESTAMPED_SPOT_REFERENCE_WITHIN_15_MINUTES_OF_EACH_ENDPOINT',
    'limitations':'PROVIDER_REINVESTMENT_PROXY; NO_INTERMEDIATE_REINVESTMENT_FEES; BEFORE_TAX',
    'trade_authorized':False,'strategy_validated':False}


def _definition(commit):
    if not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):
        raise ValueError('Traceable full release commit required')
    record={**deepcopy(DEFINITION),'commit':commit}
    return {**record,'sha256':digest(record)}


def make_contract(*,at,commit):
    definition=_definition(commit)
    record={**deepcopy(DEFINITION),'recorded_at':stamp(at).isoformat(),'commit':commit,
            'definition_sha256':definition['sha256']}
    return {**record,'sha256':digest(record)}


def validate_contract(contract,*,before=None):
    if not isinstance(contract,dict) or set(contract)!=set(DEFINITION)|{'recorded_at','commit','sha256','definition_sha256'}:
        raise ValueError('Missing or unknown cost contract')
    record=make_contract(at=contract['recorded_at'],commit=contract['commit'])
    if record!=contract:
        raise ValueError('Cost contract policy or provenance changed')
    if before is not None and stamp(contract['recorded_at'])>=stamp(before):
        raise ValueError('Cost contract was not recorded before entry')
    return deepcopy(contract)


def ensure_contract(storage,*,commit,clock=None):
    if not storage.using_postgres() or storage.allow_local_fallback:
        return None
    definition=storage.write_json_immutable(DEFINITION_KEY,_definition(commit))
    if not isinstance(definition,dict) or definition!=_definition(definition.get('commit')):
        raise ValueError('Cost definition conflict')
    # The bound is taken AFTER the definition transaction commits, never from
    # scheduler start time. A delayed write cannot manufacture a pre-entry policy.
    clock=clock or (lambda:datetime.now(timezone.utc))
    proposed=make_contract(at=clock(),commit=definition['commit'])
    saved=storage.write_json_immutable(KEY,proposed)
    validate_contract(saved)
    if saved['definition_sha256']!=definition['sha256'] or stamp(saved['recorded_at'])>stamp(clock()):
        raise ValueError('Cost contract publication conflicts with committed definition')
    return saved


def read_contract(read_json):
    try:
        contract=validate_contract(read_json(KEY))
        if read_json(DEFINITION_KEY)!=_definition(contract['commit']):
            return None
        return contract
    except Exception:
        # Optional financial-reference evidence fails closed; valid gross
        # measurements remain available and the unqualified count stays explicit.
        return None


def cost_reference(*,gross_factor,currency,entry_at,exit_at,contract,fx_entry=None,fx_exit=None):
    result={'method':METHOD,'status':'UNQUALIFIED_COST_CONTRACT',
            'model_return_after_costs_pct':None,'actual_portfolio_result_verified':False}
    try:
        contract=validate_contract(contract,before=entry_at)
    except (ValueError,TypeError,KeyError):
        return result
    result['contract_sha256']=contract['sha256']
    if not isinstance(currency,str) or len(currency)!=3 or not currency.isascii() or not currency.isalpha() or currency!=currency.upper():
        return {**result,'status':'UNQUALIFIED_CURRENCY'}
    try:
        if stamp(exit_at)<=stamp(entry_at):
            raise ValueError('Exit must follow entry')
        factor=number(gross_factor,positive=True)
    except (ValueError,TypeError):
        return {**result,'status':'UNQUALIFIED_RETURN_OR_TIME'}
    try:
        if currency=='NOK':
            if fx_entry is not None or fx_exit is not None:
                raise ValueError('NOK identity must not carry contradictory FX')
            entry_rate=exit_rate=1.
        else:
            fields={'currency','base_currency','rate','observed_at','source','quote_kind'}
            for quote in (fx_entry,fx_exit):
                if (not isinstance(quote,dict) or set(quote)!=fields
                    or quote['quote_kind']!='TIMESTAMPED_FX_SPOT_REFERENCE'
                    or not isinstance(quote['source'],str) or not quote['source'].strip()):
                    raise ValueError('Documented timestamped endpoint FX required')
            entry_rate=fx_rate(currency,'NOK',fx_entry,at=entry_at)
            exit_rate=fx_rate(currency,'NOK',fx_exit,at=exit_at)
        buy=calculate(contract['cost_policy'],quantity=1.,reference_price=100.,
                      side='BUY',currency=currency,nok_rate=entry_rate)
        sell=calculate(contract['cost_policy'],quantity=1.,reference_price=100.*factor,
                       side='SELL',currency=currency,nok_rate=exit_rate)
        after=(sell['gross_nok']-sell['fee_nok'])/(buy['gross_nok']+buy['fee_nok'])
        if not isfinite(after):
            raise ValueError('Non-finite cost reference')
    except (ValueError,TypeError,OverflowError):
        return {**result,'status':'UNQUALIFIED_FX'}
    return {**result,'status':'COSTED_REFERENCE_AVAILABLE','currency':currency,
            'entry_at':stamp(entry_at).isoformat(),'exit_at':stamp(exit_at).isoformat(),
            'entry_gross_nok':buy['gross_nok'],'exit_gross_nok':sell['gross_nok'],
            'entry_cost_nok':buy['fee_nok'],'exit_cost_nok':sell['fee_nok'],
            'gross_nok_return_pct':round(100*(sell['gross_nok']/buy['gross_nok']-1),4),
            'model_return_after_costs_pct':round(100*(after-1),4),
            'fx_entry':deepcopy(fx_entry),'fx_exit':deepcopy(fx_exit)}


def reference_changed(old,fresh):
    if not isinstance(old,dict) or not isinstance(fresh,dict):
        return False
    if old.get('status')!=fresh.get('status') or old.get('status')!='COSTED_REFERENCE_AVAILABLE':
        return False  # Disappearance never replaces the original frozen evidence.
    return any(old.get(k)!=fresh.get(k) for k in
        ('contract_sha256','currency','entry_at','exit_at','gross_nok_return_pct',
         'model_return_after_costs_pct','fx_entry','fx_exit'))


@lru_cache(maxsize=256)
def _expected_window(market,signal_at):
    from services.learning_signal_measurement import sessions
    signal=stamp(signal_at)
    calendar=sessions(market,signal.date().isoformat(),(signal+timedelta(days=70)).date().isoformat())
    eligible=[s for s in calendar if s[1]>signal]
    if len(eligible)<20:
        raise ValueError('Insufficient documented exchange sessions')
    return eligible[0][1],eligible[19][0],eligible[19][2]


def summarize(rows,contract,*,as_of=None):
    """Replay frozen evidence before including STRICT references in a mean."""
    from services.learning_signal_measurement import POLICY, RETURN_BASIS
    from services.learning_outcome_integrity import usable
    report_at=stamp(as_of if as_of is not None else datetime.now(timezone.utc))
    values=[]
    measured=0
    for row in rows:
        if row.get('measurement_policy')!=POLICY or row.get('group')!='STRICT' or not usable(row):
            continue
        reading=(row.get('horizon_measurements') or {}).get('20') or {}
        if reading.get('return_pct') is None:
            continue
        measured+=1
        try:
            claimed=reading['cost_reference']
            basis=reading['source_basis']
            if not isinstance(claimed,dict) or not isinstance(basis,dict):
                continue
            if reading.get('horizon_days')!=20:
                continue
            entry_open,exit_day,exit_close=_expected_window(row['market'],stamp(row['entry_at']).isoformat())
            if (stamp(row['entry_reference']['market_open_at'])!=entry_open
                or reading.get('market_date')!=exit_day
                or stamp(basis['exit_session_close_at'])!=exit_close
                or exit_close+timedelta(minutes=15)>report_at):
                continue
            if reading.get('measurement_policy')!=POLICY or reading.get('return_basis')!=RETURN_BASIS:
                continue
            factor=number(basis['stock_adjusted_exit_close'],positive=True)/number(basis['stock_adjusted_entry_open'],positive=True)
            if abs(100*(factor-1)-float(reading['return_pct']))>.0002:
                continue
            if stamp(basis['exit_session_close_at']).date().isoformat()!=reading['market_date']:
                continue
            expected=cost_reference(gross_factor=factor,
                currency=(row.get('signal_reference') or {}).get('reference_currency'),
                entry_at=row['entry_reference']['market_open_at'],exit_at=basis['exit_session_close_at'],
                contract=contract,fx_entry=claimed.get('fx_entry'),fx_exit=claimed.get('fx_exit'))
            if expected['status']!='COSTED_REFERENCE_AVAILABLE' or expected!=claimed:
                continue
            fields=('entry_gross_nok','exit_gross_nok','entry_cost_nok','exit_cost_nok',
                    'gross_nok_return_pct','model_return_after_costs_pct')
            if any(isinstance(claimed[k],bool) or not isfinite(float(claimed[k])) for k in fields):
                continue
            values.append(expected['model_return_after_costs_pct'])
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
    return {'method':METHOD,'horizon_days':20,'count':len(values),
            'unqualified_measured':measured-len(values),
            'mean_model_return_after_costs_pct':round(sum(values)/len(values),4) if values else None,
            'scope':'EQUAL_WEIGHTED_STRICT_SAMPLED_OBSERVATIONS_NOT_TRADES',
            'cost_scope':DEFINITION['scope'],'limitations':DEFINITION['limitations'],
            'actual_portfolio_result_verified':False,'strategy_validated':False}


def report_text(summary):
    count=int(summary.get('count') or 0)
    value=summary.get('mean_model_return_after_costs_pct')
    if count and value is not None:
        value=f'{float(value):+.2f}'.replace('.',',')+' %'
        result=f"{value} ({count} {'aksje' if count==1 else 'aksjer'})"
    else:
        result='ikke kvalifisert målegrunnlag ennå'
    missing=int(summary.get('unqualified_measured') or 0)
    if missing:
        result+=f' ({missing} målte observasjoner uten godkjent kostnads-/valutagrunnlag)'
    return ('Autonomis kostnadsreferanse i NOK (20 børsdager): '+result+'. '
            'Modell etter kjøps-/salgskostnader, før skatt; ikke porteføljeresultat.')
