"""Documented opening balances for a new, separately approved accounting period."""
from copy import deepcopy
import hashlib
import json
import math
from datetime import timedelta

from services.economic_ledger import new_account, number, stamp, fx_rate


_NATIVE_CANONICAL_BYTES = 8 * 1024**2
_NATIVE_CANONICAL_NODES = 262144


def _native_canonical_fits(value):
    """Bound native encoding's temporary allocation, not the stored history.

    Only exact JSON builtin types qualify. Large/unsupported/shared graphs
    retain the existing streaming encoder and its exact validation behavior.
    Six bytes per input character bounds UTF-8 JSON escaping; float/integer
    bounds also include their full lexical representation.
    """
    remaining = _NATIVE_CANONICAL_BYTES
    nodes = _NATIVE_CANONICAL_NODES - 1
    pending = [value]
    seen = set()
    while pending:
        item = pending.pop()
        if nodes < 0 or remaining < 0:
            return False
        kind = type(item)
        if kind is str:
            remaining -= 6 * len(item) + 2
        elif kind is int:
            remaining -= item.bit_length() // 3 + 3
        elif kind is float:
            if not math.isfinite(item):
                return False
            remaining -= 32
        elif kind is bool or item is None:
            remaining -= 5
        elif kind in (dict, list, tuple):
            identity = id(item)
            if identity in seen:
                return False
            seen.add(identity)
            count = len(item) * (2 if kind is dict else 1)
            if count > nodes:
                return False
            nodes -= count
            remaining -= count + 2
            if remaining < 0:
                return False
            if kind is dict:
                if any(type(key) is not str for key in item):
                    return False
                pending.extend(item.keys())
                pending.extend(item.values())
            else:
                pending.extend(item)
        else:
            return False
    return remaining >= 0


def _canonical_chunks(value, encoder, active):
    if _native_canonical_fits(value):
        yield json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False)
        return
    kind = type(value)
    if kind not in (dict, list, tuple) or (
            kind is dict and any(type(key) is not str for key in value)):
        yield from encoder.iterencode(value)
        return
    identity = id(value)
    if identity in active:
        raise ValueError('Circular reference detected')
    active.add(identity)
    try:
        if kind is dict:
            yield '{'
            for index, key in enumerate(sorted(value)):
                if index:
                    yield ','
                yield encoder.encode(key)
                yield ':'
                yield from _canonical_chunks(value[key], encoder, active)
            yield '}'
        else:
            yield '['
            # Bounded blocks also accelerate long arrays of primitive values.
            for offset in range(0, len(value), 256):
                block = value[offset:offset + 256]
                if offset:
                    yield ','
                if _native_canonical_fits(block):
                    encoded = json.dumps(block, sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=False, allow_nan=False)
                    yield encoded[1:-1]
                else:
                    for index, item in enumerate(block):
                        if index:
                            yield ','
                        yield from _canonical_chunks(item, encoder, active)
            yield ']'
    finally:
        active.remove(identity)


def digest(value):
    # Native encoding is limited to bounded subtrees; every historical byte
    # still participates in the same canonical SHA-256 calculation.
    hasher = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'),
                               ensure_ascii=False, allow_nan=False)
    for chunk in _canonical_chunks(value, encoder, set()):
        hasher.update(chunk.encode())
    return hasher.hexdigest()


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
