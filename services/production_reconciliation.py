"""Fail-closed readiness of supplied model evidence, not a broker attestation.

No application loaders: some initialize missing portfolios. No production writes.
Missing records stay unknown; old quantities are never relabelled as shares.
"""
from copy import deepcopy
from services.economic_accounting_audit import audit
from services.economic_opening import opening_account
from services.economic_ledger import execute, reconcile, SCHEMA, number, stamp
from services.superfund_accounting import audit_native

FAMILIES=('paper','autonomy','super_portfolio','superfund')


def assess(family, evidence=None):
    if family not in FAMILIES:raise ValueError('Unknown family')
    result=dict(family=family,status='STOPPED',production_data_checked=False,
        trial_performed=False,source_unchanged=True,issues=[],verified_opening=None)
    if not evidence:
        result['issues']=['NO_PRODUCTION_SOURCE_AVAILABLE'];return result
    # The operator must supply provenance; generated fixtures are not production.
    if evidence.get('source_kind') not in {'SUPPLIED_MODEL_DIAGNOSTIC_ARCHIVE','READ_ONLY_POSTGRES_EXPORT'} or not evidence.get('source_sha256'):
        result['issues']=['MISSING_OR_TEST_ONLY_SOURCE_PROVENANCE'];return result
    result['production_data_checked']=True
    source=deepcopy(evidence)
    try:stamp(evidence.get('as_of'))
    except ValueError:
        result['issues']=['MISSING_OR_INVALID_SOURCE_TIME'];return result
    state=evidence.get('state')
    if not isinstance(state,dict):result['issues']=['MISSING_ACCOUNT_STATE'];return result
    if family=='superfund':
        checked=audit_native(state,at=evidence['as_of'])
        result['issues']=checked['issues']
        result['status']='RECONCILED_NATIVE_MODEL' if checked['verified_nav_nok'] is not None else 'STOPPED'
        result['native_verification']=checked
        return result
    if state.get('accounting_schema')==SCHEMA:
        from datetime import datetime
        checked=audit(state,at=datetime.fromisoformat(evidence['as_of'].replace('Z','+00:00')))
        result['issues']=checked['issues'];result['status']='RECONCILED_NOK_MODEL' if checked['status']=='BESTÅTT' else 'STOPPED'
        result['verification']=checked
        return result
    # A reported historical model NAV/weight is evidence of a model result, not
    # sufficient evidence of holdings, opening cash or a complete economic book.
    if not evidence.get('opening_document'):
        result['issues'].append('MISSING_DOCUMENTED_OPENING_BALANCE')
    rows=evidence.get('documented_fills')
    if rows is None:result['issues'].append('MISSING_COMPLETE_DOCUMENTED_FILL_JOURNAL')
    if evidence.get('history_complete') is not True:result['issues'].append('HISTORICAL_EVENT_COVERAGE_UNCONFIRMED')
    if result['issues']:return result
    try:
        account=opening_account(evidence['opening_document'])
        for fill in rows:
            if not fill.get('cost_components') or not fill.get('cost_source_ref'):
                raise ValueError('Incomplete model cost assumptions')
            account,_=execute(account,**fill)
        # Recorded closing shares/cash must be supplied explicitly in NOK/share
        # units, independently of this replay. No mapping from old weight units.
        closing=evidence['documented_closing']
        if not closing.get('source_ref'):raise ValueError('Documented closing source required')
        if abs(account['cash']-number(closing['cash_nok']))>1e-5:raise ValueError('Closing cash differs from journal')
        actual={t:(p['quantity'],p['cost_basis_base']) for t,p in account['positions'].items()}
        supplied={t:(number(p['quantity'],positive=True),number(p['cost_basis_nok'])) for t,p in closing['positions'].items()}
        if set(actual)!=set(supplied) or any(abs(a-b)>1e-6 for t in actual for a,b in zip(actual[t],supplied[t])):
            raise ValueError('Closing shares/cost basis differ from journal')
        if reconcile(account):raise ValueError('Journal does not reconcile')
        from services.portfolio_accounting import _marks
        from datetime import datetime
        account=_marks(account,marks=closing['valuation_marks'],at=evidence['as_of'])
        verified=audit(account,at=datetime.fromisoformat(evidence['as_of'].replace('Z','+00:00')))
        if verified['verified_nav'] is None or abs(verified['verified_nav']-number(closing['nav_nok']))>1e-5:
            raise ValueError('Documented closing NOK NAV does not reconcile')
        result.update(status='ISOLATED_REPLAY_RECONCILED',trial_performed=True,
                      verified_opening=account['opening_balance'],replayed_account=account)
    except (ValueError,KeyError,TypeError) as exc:
        result['issues'].append(str(exc))
    if evidence!=source:raise AssertionError('Read-only source modified')
    return result
