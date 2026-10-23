"""Separate, approval-gated NOK periods; legacy stores are never written.

One document is the transaction boundary for approval, opening, fills, marks and
balances. The existing basis-currency engine is the only share accounting engine.
Only explicit actual-share fills may enter: legacy weights/units are not orders.
"""
from copy import deepcopy
from datetime import timedelta
import os

from services.economic_ledger import execute, reconcile, stamp, number, fx_rate
from services.economic_opening import opening_account, digest
from services.economic_accounting_audit import audit
from services.storage_service import get_storage_service

FAMILIES = {'paper': 'Paper Trading', 'autonomy': 'Autonomi', 'super_portfolio': 'Superporteføljen'}
MISSING = ['Datert kontantbeholdning i NOK med kilde',
           'Faktisk aksjeantall og instrumentvaluta per posisjon med kilde',
           'Dokumentert gjenværende historisk kostpris i NOK, inkludert kostnader',
           'Daterte åpningskurser og valutakurser med kilder',
           'Avstemming mot komplett tilgjengelig handelshistorikk og forklaring av hull',
           'Uttrykkelig godkjenning av familie, åpningsdokument og startdato']


def key(family):
    if family not in FAMILIES:
        raise ValueError('Unknown share-account family; Superfond retains its native model')
    return 'economic_accounts/' + family + '.json'


def _append(doc, kind, payload):
    events = doc.setdefault('events', [])
    event = {'sequence':len(events)+1, 'kind':kind, 'payload':deepcopy(payload),
             'previous_hash':events[-1]['hash'] if events else None}
    event['hash'] = digest(event)
    events.append(event)


def verify(doc):
    if not doc:
        return
    if not doc.get('events') or doc['events'][0].get('kind') != 'PREPARED':
        raise ValueError('Documented preparation event required')
    previous = None
    for i, event in enumerate(doc['events'], 1):
        body = {k:v for k,v in event.items() if k != 'hash'}
        if event['sequence'] != i or event['previous_hash'] != previous or digest(body) != event['hash']:
            raise ValueError('Economic journal integrity failure')
        previous = event['hash']
    baseline = opening_account(doc['account']['opening_document'])
    if baseline['opening_balance'] != doc['account']['opening_balance']:
        raise ValueError('Opening balance does not match source document')
    if doc['opening_sha256'] != digest(doc['account']['opening_document']):
        raise ValueError('Opening document fingerprint changed')
    # Replay events with the SAME engine, including marks; hashes alone are not
    # accounting proof. This also detects missing journal rows or altered balances.
    account = baseline
    approval = None
    for event in doc['events']:
        payload = event['payload']
        if event['kind'] == 'PREPARED':
            if event['sequence'] != 1 or payload['opening_sha256'] != doc['opening_sha256']:
                raise ValueError('Invalid opening event')
        elif event['kind'] == 'APPROVED':
            if approval is not None:
                raise ValueError('Duplicate activation')
            approval = payload
        elif event['kind'] == 'FILL':
            if approval is None:
                raise ValueError('Unapproved fill')
            account, _ = execute(account, **payload)
        elif event['kind'] == 'MARK':
            if approval is None:
                raise ValueError('Unapproved mark')
            account = _marks(account, **payload)
        else:
            raise ValueError('Unknown journal event')
    if account != doc['account'] or reconcile(account):
        raise ValueError('Account and transaction journal disagree')
    if doc['status'] != ('ACTIVE' if approval else 'DRAFT') or doc.get('approval') != approval:
        raise ValueError('Approval does not reconcile')


def prepare(family, document, *, prepared_by, storage=None):
    """Create one immutable draft. Repeating identical input is safe; never reset."""
    if not prepared_by:
        raise ValueError('Preparation actor required')
    account = opening_account(document)
    sha = digest(document)
    def mutation(current):
        if current:
            verify(current)
            if current['opening_sha256'] != sha:
                raise ValueError('Existing accounting period cannot be overwritten')
            return current
        doc = dict(family=family, status='DRAFT', opening_sha256=sha, account=account,
                   approval=None, events=[])
        _append(doc, 'PREPARED', {'opening_sha256':sha, 'prepared_by':prepared_by})
        return doc
    return (storage or get_storage_service()).mutate_json(key(family), mutation)


def approve(family, approval, *, storage=None):
    """Operator API only. No UI/scheduler calls; production is disabled by default.

    Approval must bind the immutable opening fingerprint, exact family and start
    date. Test approval is refused outside test/development, and vice versa.
    """
    env = os.getenv('APP_ENVIRONMENT', 'production').lower()
    production = env not in {'test', 'development'}
    if production and os.getenv('ECONOMIC_PRODUCTION_ACTIVATION_ENABLED') != 'true':
        raise ValueError('Production activation requires explicit operator approval and enablement')
    def mutation(current):
        verify(current)
        if not current:
            raise ValueError('Documented draft required')
        if (not approval.get('approved_by') or not approval.get('approval_ref')
            or approval.get('family') != family
            or approval.get('opening_sha256') != current['opening_sha256']
            or approval.get('start_at') != current['account']['created_at']
            or approval.get('scope') != ('production' if production else 'test')):
            raise ValueError('Explicit approval must bind family, opening, start, scope and actor')
        if stamp(approval['approved_at']) < stamp(approval['start_at']):
            raise ValueError('Approval predates documented opening')
        if current['status'] == 'ACTIVE':
            if current['approval'] != approval:
                raise ValueError('Already activated with a different approval')
            return current
        result = deepcopy(current)
        result.update(status='ACTIVE', approval=deepcopy(approval))
        _append(result, 'APPROVED', approval)
        return result
    return (storage or get_storage_service()).mutate_json(key(family), mutation)


def _require_scope(doc):
    scope = 'test' if os.getenv('APP_ENVIRONMENT','production').lower() in {'test','development'} else 'production'
    if doc['approval']['scope'] != scope:
        raise ValueError('Approval scope differs from execution environment')


def settle(family, fill, *, storage=None):
    """Atomic actual-share execution adapter for the three portfolio families.

    No model-unit conversion, fee estimation or currency inference is permitted.
    A caller must submit an executed fill with dated FX and separated costs.
    """
    if fill.get('cost_components') is None or not fill.get('cost_source_ref'):
        raise ValueError('Separated, documented trading and FX costs required')
    def mutation(current):
        verify(current)
        if not current or current['status'] != 'ACTIVE':
            raise ValueError('Explicitly approved active NOK period required')
        _require_scope(current)
        result = deepcopy(current)
        result['account'], _ = execute(current['account'], **fill)
        if result['account'] == current['account']:
            return current  # A lost acknowledgement remains retryable after later marks.
        if stamp(fill['at']) < max(stamp(current['approval']['approved_at']), stamp(current['account'].get('marked_at',current['account']['created_at']))):
            raise ValueError('Fill predates approval or current valuation')
        _append(result, 'FILL', fill)
        verify(result)
        return result
    return (storage or get_storage_service()).mutate_json(key(family), mutation)


def _marks(account, *, marks, at):
    if set(marks) != set(account['positions']):
        raise ValueError('Complete marks for all open positions required')
    if stamp(at) < max(stamp(account.get('marked_at',account['created_at'])),
                       stamp(account['trades'][-1]['timestamp'] if account['trades'] else account['created_at'])):
        raise ValueError('Out-of-order valuation')
    result = deepcopy(account)
    for ticker, mark in marks.items():
        pos = result['positions'][ticker]
        if not mark.get('source') or not timedelta(0) <= stamp(at)-stamp(mark['observed_at']) <= timedelta(days=5):
            raise ValueError('Documented dated valuation required')
        fx_rate(pos['currency'], 'NOK', mark.get('fx_quote'), at=at, max_age=timedelta(days=5))
        pos.update(last_price=number(mark['price'], positive=True), price_observed_at=mark['observed_at'],
                   price_source=mark['source'], fx_quote=deepcopy(mark.get('fx_quote')))
    result['marked_at'] = at
    return result


def mark(family, marks, *, at, storage=None):
    payload = dict(marks=marks, at=at)
    def mutation(current):
        verify(current)
        if not current or current['status'] != 'ACTIVE':
            raise ValueError('Approved active NOK period required')
        _require_scope(current)
        if stamp(at) < stamp(current['approval']['approved_at']):
            raise ValueError('Mark predates approval')
        result = deepcopy(current)
        result['account'] = _marks(result['account'], **payload)
        if result['account'] != current['account']:
            _append(result, 'MARK', payload)
        return result
    return (storage or get_storage_service()).mutate_json(key(family), mutation)


def report(family, *, storage=None, at=None):
    doc = (storage or get_storage_service()).read_json(key(family), None)
    result = dict(family=family, label=FAMILIES[family], status='NOT_PREPARED',
                  legacy_result_basis='HISTORISK – IKKE VERIFISERT NETTO NOK',
                  legacy_history_preserved=True, missing_opening_evidence=MISSING,
                  new_period=None)
    if not doc:
        return result
    try:
        verify(doc)
    except (ValueError, KeyError, TypeError) as exc:
        result.update(status='INTEGRITY_ERROR', issues=[str(exc)])
        return result
    account = doc['account']
    checked = audit(account, at=at)
    nav = checked['verified_nav']
    basis = sum(p['cost_basis_base'] for p in account['positions'].values())
    opening_basis = sum(p['cost_basis_base'] for p in account['opening_balance']['positions'].values())
    costs = {k:sum(t['cost_components'][k] for t in account['trades'])
             for k in ('brokerage_nok','fx_cost_nok','other_nok')}
    result.update(status=doc['status'], missing_opening_evidence=[],
        new_period=dict(start_at=account['created_at'], opening_nav_nok=account['initial_cash'],
            opening_sha256=doc['opening_sha256'], approval=doc['approval'],
            cash_nok=account['cash'], positions=account['positions'], verification=checked,
            realized_pnl_nok=account['realized_pnl'],
            unrealized_pnl_nok=nav-account['cash']-basis if nav is not None else None,
            carried_opening_unrealized_nok=account['initial_cash']-account['opening_balance']['cash']-opening_basis,
            period_net_pnl_nok=nav-account['initial_cash'] if nav is not None else None,
            costs_nok=costs, journal=doc['events'], trades=account['trades'],
            opening_document=account['opening_document']))
    return result
