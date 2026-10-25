"""Documented model cash flows and corporate actions; no provider inference.

These functions book supplied evidence only. They never fetch actions, alter a
strategy, infer historical entitlement or create missing transactions.
"""
from copy import deepcopy
from datetime import timedelta
from services.economic_ledger import SCHEMA, number, stamp, fx_rate, execute, new_account

TYPES = {'DEPOSIT', 'WITHDRAWAL', 'DIVIDEND', 'SPLIT'}


def _entries(account):
    return deepcopy(account.get('economic_entries', [
        {'kind':'FILL','id':t['trade_id']} for t in account.get('trades',[])]))


def _fresh_mark(pos, mark, at):
    if not mark.get('source') or not timedelta(0) <= stamp(at)-stamp(mark['observed_at']) <= timedelta(minutes=15):
        raise ValueError('Dated market evidence required at cash-flow/action time')
    rate = fx_rate(pos['currency'],'NOK',mark.get('fx_quote'),at=at)
    pos.update(last_price=number(mark['price'],positive=True),price_source=mark['source'],
               price_observed_at=mark['observed_at'],fx_quote=deepcopy(mark.get('fx_quote')))
    return pos['quantity']*pos['last_price']*rate


def book_event(account, event):
    """Apply a fully evidenced event atomically in memory, with stable identity.

    Costs are explicit NOK components. Dividends require documented entitlement
    independent of today's holdings. Splits require an actual post-action mark.
    Cash flows issue/redeem performance units at documented pre-flow NAV.
    """
    if account.get('accounting_schema') != SCHEMA or account.get('base_currency') != 'NOK':
        raise ValueError('Explicit NOK account required')
    if event.get('type') not in TYPES or not event.get('event_id') or not event.get('source_ref'):
        raise ValueError('Known economic event, stable ID and model evidence required')
    for old in account.get('economic_events',[]):
        if old['input']['event_id']==event['event_id']:
            if old['input']!=event:raise ValueError('Event ID reused with different input')
            return deepcopy(account)
    at=event['at']
    previous=max(stamp(account['created_at']),stamp(account.get('last_economic_at',account['created_at'])),
                 stamp(account.get('marked_at',account['created_at'])),
                 stamp(account['trades'][-1]['timestamp']) if account['trades'] else stamp(account['created_at']))
    if stamp(at)<previous:raise ValueError('Out-of-order economic event')
    if event.get('cost_currency')!='NOK' or not event.get('cost_source_ref'):
        raise ValueError('Explicit model cost evidence in NOK required')
    components=event['cost_components']
    if set(components)!={'brokerage_nok','fx_cost_nok','other_nok'}:
        raise ValueError('Complete cost components required, including documented zero')
    fee=sum(number(v) for v in components.values())
    result=deepcopy(account); cash=number(account['cash']); kind=event['type']
    external=0.; income=0.; withholding=0.
    units=number(account.get('performance_units',account['initial_cash']),positive=True)
    if kind in {'DEPOSIT','WITHDRAWAL'}:
        amount=number(event['amount_nok'],positive=True)
        marks=event['valuation_marks']
        if set(marks)!=set(account['positions']):raise ValueError('Complete pre-flow valuation required')
        nav=cash+sum(_fresh_mark(p,marks[t],at) for t,p in result['positions'].items())
        unit_price=number(nav/units,positive=True)
        external=amount if kind=='DEPOSIT' else -amount
        if kind=='DEPOSIT' and fee>amount:raise ValueError('Deposit costs exceed supplied capital')
        if kind=='WITHDRAWAL' and amount>=nav:raise ValueError('Full capital redemption requires explicit period closure')
        cash+=external-fee; units+=external/unit_price
        result.setdefault('cash_flows',[]).append({'event_id':event['event_id'],'at':at,'amount_nok':external})
        result['return_method']='UNITIZED_TWR_V1'
        result['performance_units']=number(units,positive=True)
    elif kind=='DIVIDEND':
        if not event.get('ticker') or not event.get('entitlement_source_ref'):
            raise ValueError('Documented dividend entitlement required; do not infer from current shares')
        if stamp(event['entitlement_at'])>stamp(at):raise ValueError('Future dividend entitlement')
        gross=number(event['entitled_quantity'],positive=True)*number(event['per_share_local'],positive=True)
        gross*=fx_rate(event['currency'],'NOK',event.get('fx_quote'),at=at)
        withholding=number(event['withholding_nok'])
        if fee+withholding>gross:raise ValueError('Dividend deductions exceed documented gross income')
        income=gross-withholding-fee; cash+=income
    else:
        ticker=event['ticker']; pos=result['positions'].get(ticker)
        if not pos or number(event['quantity_before'],positive=True)!=pos['quantity']:
            raise ValueError('Split must match documented pre-action holdings')
        factor=number(event['numerator'],positive=True)/number(event['denominator'],positive=True)
        if event.get('cash_in_lieu') is not False:
            raise ValueError('Fractional cash settlement is not supported without a separate documented event')
        pos['quantity']=number(pos['quantity']*factor,positive=True)
        pos['average_cost_base']=pos['cost_basis_base']/pos['quantity']
        if pos.get('average_price') is not None:pos['average_price']/=factor
        _fresh_mark(pos,event['post_action_mark'],at)
        cash-=fee
    result['cash']=number(cash)
    result['fees_paid']=number(result.get('fees_paid',0))+fee
    result['dividend_income_nok']=number(result.get('dividend_income_nok',0))+income
    result['withholding_nok']=number(result.get('withholding_nok',0))+withholding
    result['last_economic_at']=at
    result.setdefault('economic_events',[]).append(dict(input=deepcopy(event),fee=fee,
        external_flow_nok=external,dividend_income_nok=income,withholding_nok=withholding,
        cash_delta=cash-account['cash']))
    result['economic_entries']=_entries(account)+[{'kind':'EVENT','id':event['event_id']}]
    return result


def reconcile_events(account):
    """Replay economic entries with the same functions; valuations stay separate."""
    from services.economic_opening import opening_account
    baseline=opening_account(account['opening_document']) if account.get('opening_balance') else new_account(
        account['initial_cash'],base_currency='NOK',at=account['created_at'])
    if account.get('opening_balance') and account['opening_balance']!=baseline['opening_balance']:
        return ['OPENING_BALANCE_DOES_NOT_RECONCILE']
    trades={t['trade_id']:t for t in account['trades']}
    events={e['input']['event_id']:e for e in account['economic_events']}
    if len(trades)!=len(account['trades']) or len(events)!=len(account['economic_events']):
        return ['DUPLICATE_ECONOMIC_ID']
    seen=set()
    for entry in account['economic_entries']:
        ident=(entry['kind'],entry['id'])
        if ident in seen:raise ValueError('Duplicate economic entry')
        seen.add(ident)
        if entry['kind']=='FILL':
            t=trades[entry['id']]
            args=dict(trade_id=t['trade_id'],ticker=t['ticker'],side=t['action'],quantity=t['quantity'],
                price=t['price'],currency=t['currency'],observed_at=t['price_observed_at'],source=t['price_source'],
                at=t['timestamp'],fee=t['fee'],cost_currency=t['cost_currency'],fx_quote=t.get('fx_quote'))
            if 'cost_components' in t:args.update(cost_components=t['cost_components'],cost_source_ref=t['cost_source_ref'])
            if 'cost_calculation' in t:args['cost_calculation']=t['cost_calculation']
            baseline,_=execute(baseline,**args)
        elif entry['kind']=='EVENT':baseline=book_event(baseline,events[entry['id']]['input'])
        else:raise ValueError('Unknown economic entry')
    if seen!={('FILL',k) for k in trades}|{('EVENT',k) for k in events}:
        raise ValueError('Missing economic entries')
    fields=('cash','initial_cash','created_at','fees_paid','realized_pnl','cash_flows','performance_units',
            'return_method','dividend_income_nok','withholding_nok','economic_events','economic_entries','trades','last_economic_at')
    issues=['ECONOMIC_EVENTS_DO_NOT_RECONCILE'] if any(baseline.get(k)!=account.get(k) for k in fields) else []
    def holdings(a):
        return {t:{k:p.get(k) for k in ('quantity','quantity_unit','currency','cost_basis_base','average_cost_base','average_price')}
                for t,p in a['positions'].items()}
    if holdings(baseline)!=holdings(account):issues.append('EVENT_HOLDINGS_DO_NOT_RECONCILE')
    return issues
