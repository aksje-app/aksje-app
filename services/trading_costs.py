"""Pure, source-bound NOK cost policies; no defaults, storage or activation.

V1 fixed NOK grants remain replayable. V2 supports proportional/fixed components
and optional adverse slippage in the fill price. Aggregate model costs are never
mislabelled brokerage. An unresolved FX component is not an assumed zero fee.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_FLOOR
from services.economic_ledger import number

SCHEMA = 'NOK_COST_POLICY_V2'
ITEMIZED = {'brokerage_nok', 'fx_cost_nok', 'other_nok'}
AGGREGATE = {'model_transaction_cost_nok', 'fx_cost_nok'}


def component_names(components):
    if not isinstance(components, dict) or set(components) not in (ITEMIZED, AGGREGATE):
        raise ValueError('Explicit itemized costs or aggregate model cost plus FX required')
    for value in components.values(): number(value)
    return set(components)


def _rule(rule, *, slippage=False):
    if not isinstance(rule, dict) or not isinstance(rule.get('source_ref'), str) or not rule['source_ref'].strip():
        raise ValueError('Each cost component requires documented terms and a source')
    allowed = {'rate_bps', 'rate_pct', 'source_ref'} | (set() if slippage else {'fixed_nok'})
    if set(rule)-allowed or not (set(rule) & (allowed-{'source_ref'})):
        raise ValueError('Explicit fixed NOK or proportional cost terms required')
    if 'rate_bps' in rule and 'rate_pct' in rule:
        raise ValueError('Use one proportional unit, not both percent and basis points')
    for key in set(rule)-{'source_ref'}: number(rule[key])
    if slippage and _rate(rule) >= 1:
        raise ValueError('Slippage must leave a positive sell price')


def validate(policy):
    if not isinstance(policy, dict) or not isinstance(policy.get('source_ref'), str) or not policy['source_ref'].strip():
        raise ValueError('Documented model-cost policy required')
    if 'schema' not in policy:
        if set(policy) != {'source_ref', 'components_per_fill'}:
            raise ValueError('Unknown fixed cost policy terms')
        if not isinstance(policy.get('components_per_fill'),dict) or set(policy['components_per_fill']) != ITEMIZED:
            raise ValueError('Documented fixed brokerage, FX and other costs required')
        component_names(policy['components_per_fill'])
    else:
        if policy['schema'] != SCHEMA or set(policy)-{'schema','source_ref','components','slippage'}:
            raise ValueError('Unknown cost policy schema or terms')
        components = policy.get('components')
        if not isinstance(components, dict) or set(components) not in (ITEMIZED, AGGREGATE):
            raise ValueError('No mixing or double charging of aggregate and itemized model costs')
        for rule in components.values(): _rule(rule)
        if 'slippage' in policy: _rule(policy['slippage'], slippage=True)
    return deepcopy(policy)


def _decimal(value):
    number(value)
    return Decimal(str(value))


def _rate(rule):
    if 'rate_bps' in rule: return _decimal(rule['rate_bps'])/10000
    if 'rate_pct' in rule: return _decimal(rule['rate_pct'])/100
    return Decimal(0)  # The explicitly documented rule is fixed-only.


def _terms(policy, currency):
    validate(policy)
    if currency is None or not isinstance(currency, str) or len(currency) != 3 or currency != currency.upper() or not currency.isascii() or not currency.isalpha():
        raise ValueError('Explicit canonical instrument currency required')
    if 'schema' not in policy:
        # Signed V1 policies historically applied exactly these fixed amounts.
        return {k: (Decimal(str(v)), Decimal(0)) for k,v in policy['components_per_fill'].items()}
    return {k: (Decimal(0), Decimal(0)) if k=='fx_cost_nok' and currency=='NOK' else
            (_decimal(rule['fixed_nok']) if 'fixed_nok' in rule else Decimal(0), _rate(rule))
            for k,rule in policy['components'].items()}


def fill_price(policy, reference_price, side):
    validate(policy)
    if side not in {'BUY','SELL'}: raise ValueError('Explicit buy/sell side required')
    price = _decimal(reference_price)
    if price <= 0: raise ValueError('Positive reference price required')
    slip = _rate(policy['slippage']) if 'slippage' in policy else Decimal(0)
    result = float(price*(1+slip if side=='BUY' else 1-slip))
    return number(result, positive=True)


def calculate(policy, *, quantity, reference_price, side, currency, nok_rate):
    terms = _terms(policy, currency)
    q, rate = _decimal(quantity), _decimal(nok_rate)
    if q <= 0 or rate <= 0: raise ValueError('Positive shares and documented FX rate required')
    if currency == 'NOK' and rate != 1: raise ValueError('NOK/NOK must be identity')
    price = fill_price(policy, reference_price, side)
    gross = q*_decimal(price)*rate
    components = {k:float(fixed+gross*proportional) for k,(fixed,proportional) in terms.items()}
    component_names(components)
    gross_value = number(float(gross), positive=True)
    fee = number(sum(components.values()))
    return dict(price=price, gross_nok=gross_value, cost_components=components, fee_nok=fee,
                cost_source_ref=policy['source_ref'],
                cost_calculation=dict(policy=deepcopy(policy), reference_price=reference_price,
                                      side=side, nok_rate=nok_rate, currency=currency,
                                      fx_treatment='NO_CURRENCY_CONVERSION' if currency=='NOK' else 'DOCUMENTED_FX'))


def affordable_quantity(policy, *, budget_nok, reference_price, currency, nok_rate):
    terms = _terms(policy, currency)
    budget = _decimal(budget_nok)
    fixed = sum((v[0] for v in terms.values()), Decimal(0))
    rate = sum((v[1] for v in terms.values()), Decimal(0))
    unit = _decimal(fill_price(policy, reference_price, 'BUY'))*_decimal(nok_rate)
    if unit <= 0: raise ValueError('Positive documented unit value required')
    q = max(Decimal(0), (budget-fixed)/(unit*(1+rate)))
    q = q.quantize(Decimal('0.0001'), rounding=ROUND_FLOOR)
    if q:
        # Match the existing float ledger's final cash comparison at boundaries.
        result = calculate(policy,quantity=float(q),reference_price=reference_price,
                           side='BUY',currency=currency,nok_rate=nok_rate)
        if float(q)*result['price']*float(nok_rate)+result['fee_nok'] > float(budget_nok):
            q = max(Decimal(0),q-Decimal('0.0001'))
    return float(q)


def validate_family(policy, family, settings):
    validate(policy)
    if family == 'super_portfolio':
        # New requests preserve the existing configured cost once, not a second
        # report estimate or an invented split into brokerage/FX/other costs.
        if policy.get('schema') != SCHEMA or set(policy['components']) != AGGREGATE:
            raise ValueError('Super Portfolio requires its documented proportional aggregate cost')
        model = policy['components']['model_transaction_cost_nok']
        expected = number(settings['transaction_cost_bps'])
        if set(model) != {'rate_bps','source_ref'} or number(model['rate_bps']) != expected:
            raise ValueError('Preserve the configured Super Portfolio basis-point cost exactly once')


def super_portfolio_proposal(settings, *, source_ref, fx_component=None):
    """Unapproved proposal, not a grant. None means unresolved and fails validate.

    No FX, brokerage split or slippage default is invented by account creation.
    """
    return dict(schema=SCHEMA, source_ref=source_ref, components={
        'model_transaction_cost_nok':dict(rate_bps=number(settings['transaction_cost_bps']),source_ref=source_ref),
        'fx_cost_nok':deepcopy(fx_component)})


def verify_calculation(calculation, *, quantity, price, side, currency, nok_rate,
                       cost_components, cost_source_ref, fee):
    if not isinstance(calculation,dict) or set(calculation) != {'policy','reference_price','side','nok_rate','currency','fx_treatment'}:
        raise ValueError('Incomplete cost calculation evidence')
    expected = calculate(calculation['policy'], quantity=quantity,
        reference_price=calculation['reference_price'], side=side, currency=currency, nok_rate=nok_rate)
    if (expected['cost_calculation'] != calculation or expected['cost_components'] != cost_components or
        expected['cost_source_ref'] != cost_source_ref or abs(expected['price']-price)>1e-10 or
        abs(expected['fee_nok']-fee)>1e-8):
        raise ValueError('Fill differs from documented cost or slippage calculation')
