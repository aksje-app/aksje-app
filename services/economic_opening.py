"""Documented opening balances for a new, separately approved accounting period."""
from copy import deepcopy
import hashlib
import json
from datetime import timedelta

from services.economic_ledger import new_account, number, stamp, fx_rate


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def opening_account(document):
    """Validate supplied facts. Never infer shares, cost basis, FX or cash."""
    doc = deepcopy(document)
    when = doc['at']
    stamp(when)
    if doc.get('base_currency') != 'NOK' or not doc.get('source_ref'):
        raise ValueError('Documented NOK opening source required')
    if not isinstance(doc.get('positions'), dict):
        raise ValueError('Explicit documented holdings, including an explicit empty list, required')
    cash = number(doc['cash_nok'])
    positions = {}
    for ticker, item in doc.get('positions', {}).items():
        if not ticker or not item.get('source_ref') or not item.get('cost_basis_source_ref'):
            raise ValueError('Position and historical cost basis require source references')
        quantity = number(item['quantity'], positive=True)
        basis = number(item['cost_basis_nok'])
        price = number(item['price'], positive=True)
        observed = stamp(item['price_observed_at'])
        if not item.get('price_source') or not timedelta(0) <= stamp(when)-observed <= timedelta(days=5):
            raise ValueError('Opening mark must be documented, dated and current at opening')
        rate = fx_rate(item['currency'], 'NOK', item.get('fx_quote'), at=when, max_age=timedelta(days=5))
        positions[ticker] = dict(quantity=quantity, quantity_unit='ACTUAL_SHARES',
            currency=item['currency'], cost_basis_base=basis, average_cost_base=basis/quantity,
            last_price=price, price_observed_at=item['price_observed_at'], price_source=item['price_source'],
            fx_quote=deepcopy(item.get('fx_quote')), opening_source_ref=item['source_ref'],
            cost_basis_source_ref=item['cost_basis_source_ref'])
    nav = cash + sum(p['quantity']*p['last_price']*fx_rate(p['currency'], 'NOK', p['fx_quote'],
                    at=when, max_age=timedelta(days=5)) for p in positions.values())
    account = new_account(nav, base_currency='NOK', at=when)
    account.update(cash=cash, positions=positions,
        opening_balance={'cash':cash, 'positions':deepcopy(positions), 'nav':nav,
                         'at':when, 'source_ref':doc['source_ref'], 'document_sha256':digest(doc)},
        opening_document=doc)
    return account
