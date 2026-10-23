"""Prepare fresh, separately namespaced simulation periods after archive review.

No legacy reset or production activation. Learning stays in its existing stores.
The economic ledger owns balances; historical model state is never a fallback.
"""
from copy import deepcopy
import os
import re
from services import portfolio_accounting as accounting
from services.economic_ledger import stamp
from services.economic_opening import digest
from services.simulation_archive import verify_archive
from services.storage_service import get_storage_service

CAPITALS={'paper':100000.0,'autonomy':500000.0,'super_portfolio':1000000.0}
CAPITAL_EVIDENCE={'paper':'CODE_DEFAULT:trading_settings.DEFAULT_RULES.start_cash + paper_store.DEFAULT_PORTFOLIO.cash',
    'autonomy':'USER_DECISION:NEW_SIMULATED_CAPITAL_NOK_500000',
    'super_portfolio':'USER_DECISION:NEW_SIMULATED_CAPITAL_NOK_1000000'}


def _key(period_id):
    if not isinstance(period_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',period_id):
        raise ValueError('Explicit safe period ID required')
    return 'simulation_restarts/'+period_id+'/bundle.json'


def plan(period_id, *, start_at, prepared_by):
    _key(period_id);stamp(start_at)
    if not prepared_by:raise ValueError('Preparation actor required')
    return dict(period_id=period_id,status='WAITING_FOR_VERIFIED_ARCHIVE',start_at=start_at,
        prepared_by=prepared_by,activation_enabled=False,
        capital_kind='NEW_SIMULATED_CAPITAL_NOT_BROKER_BALANCE',
        capitals_nok=deepcopy(CAPITALS),capital_evidence=deepcopy(CAPITAL_EVIDENCE),
        initial_positions={family:{} for family in CAPITALS},
        prior_learning_policy='PRESERVE_MODELS_PARAMETERS_AND_OBSERVATIONS',
        historical_results_label='HISTORISK MODELLRESULTAT – KAN VÆRE UVERIFISERT',
        new_results_label='DOKUMENTERT NOK-NETTORESULTAT FRA NY PERIODSTART')


class _Drafts:
    """Build all three drafts in memory before one atomic bundle commit."""
    def __init__(self):self.accounts={}
    def mutate_json(self,key,transform,default=None):
        result=transform(deepcopy(self.accounts.get(key,default)))
        self.accounts[key]=deepcopy(result)
        return result


def prepare(period_id, *, start_at, prepared_by, archive_root, archive_id,
            certificate, private_key, storage=None):
    request=plan(period_id,start_at=start_at,prepared_by=prepared_by)
    storage=storage or get_storage_service()
    existing=storage.read_json(_key(period_id),None)
    if existing: verify_bundle(existing)
    reviewed=verify_archive(archive_root,archive_id,certificate=certificate,private_key=private_key)
    if stamp(start_at)<=stamp(reviewed['created_at']):raise ValueError('New period cannot predate its source archive')
    review_at=existing.get('archive_review_at',reviewed['verified_at']) if existing else reviewed['verified_at']
    if stamp(start_at)<=stamp(review_at):raise ValueError('New start must follow verified archive review')
    archive_proof={k:reviewed[k] for k in ('archive_id','cipher_sha256','manifest_sha256','file_count')}
    builder=_Drafts()
    accounts={}
    for family,capital in CAPITALS.items():
        opening=dict(at=start_at,base_currency='NOK',cash_nok=capital,positions={},
            source_ref='NEW_SIMULATION_CAPITAL:'+period_id+':'+CAPITAL_EVIDENCE[family],
            capital_kind=request['capital_kind'],source_archive=archive_proof)
        accounts[family]=accounting.prepare(family,opening,prepared_by=prepared_by,storage=builder)
    bundle={**request,'status':'PREPARED_NOT_ACTIVE','archive':archive_proof,'accounts':accounts,
            'learning_reset':False,'legacy_positions_transferred':False,'legacy_sales_created':False,'archive_review_at':review_at}
    bundle['opening_sha256s']={f:a['opening_sha256'] for f,a in accounts.items()}
    bundle['preparation_sha256']=digest({k:v for k,v in bundle.items() if k!='accounts'})
    def mutation(current):
        if current:
            verify_bundle(current)
            if current['preparation_sha256']!=bundle['preparation_sha256']:
                raise ValueError('Existing restart period cannot be overwritten')
            return current
        return bundle
    return (storage or get_storage_service()).mutate_json(_key(period_id),mutation)


class AccountStorage:
    """Only a selected new period's accounts. No reads from legacy/default keys."""
    def __init__(self,period_id,storage=None):
        self.key=_key(period_id);self.storage=storage or get_storage_service()
    def _family(self,key):
        allowed={accounting.key(f):f for f in CAPITALS}
        if key not in allowed:raise ValueError('Legacy/learning access is forbidden through restart account storage')
        return allowed[key]
    def read_json(self,key,default=None):
        family=self._family(key)
        bundle=self.storage.read_json(self.key,None)
        if not bundle or bundle.get('status')!='PREPARED_NOT_ACTIVE':
            raise ValueError('Explicit prepared restart period required; no legacy fallback')
        verify_bundle(bundle)
        return deepcopy(bundle['accounts'][family])
    def mutate_json(self,key,transform,default=None):
        family=self._family(key)
        def mutation(bundle):
            if not bundle or bundle.get('status')!='PREPARED_NOT_ACTIVE':
                raise ValueError('Explicit prepared restart period required')
            verify_bundle(bundle)
            current=deepcopy(bundle['accounts'][family]);candidate=transform(current)
            if candidate.get('status')!='DRAFT' and os.getenv('APP_ENVIRONMENT','production').lower()!='test':
                raise ValueError('Restart activation is not implemented for production or development')
            result=deepcopy(bundle);result['accounts'][family]=candidate
            verify_bundle(result)
            return result
        updated = self.storage.mutate_json(self.key,mutation)
        return deepcopy(updated['accounts'][family])


def report(period_id, *, storage=None, at=None):
    scoped=AccountStorage(period_id,storage)
    bundle=scoped.storage.read_json(scoped.key,None)
    if not bundle:raise ValueError('Unknown period; no legacy fallback')
    verify_bundle(bundle)
    return dict(period_id=period_id,status=bundle['status'],start_at=bundle['start_at'],
        archive=deepcopy(bundle['archive']),capital_kind=bundle['capital_kind'],
        learning_reset=False,legacy_positions_transferred=False,
        prior_learning='BEVART – EGEN STRATEGILÆRING, IKKE NYTT ØKONOMISK RESULTAT',
        historical_results=bundle['historical_results_label'],new_results=bundle['new_results_label'],
        accounts={family:accounting.report(family,storage=scoped,at=at) for family in CAPITALS})


def verify_bundle(bundle):
    immutable={k:v for k,v in bundle.items() if k not in {'accounts','preparation_sha256'}}
    if digest(immutable)!=bundle.get('preparation_sha256') or set(bundle['accounts'])!=set(CAPITALS):
        raise ValueError('Restart preparation integrity failure')
    for family,doc in bundle['accounts'].items():
        accounting.verify(doc)
        opening=doc['account']['opening_document']
        if (doc['family']!=family or doc['opening_sha256']!=bundle['opening_sha256s'][family]
                or opening['positions']!={} or opening['cash_nok']!=bundle['capitals_nok'][family]
                or opening['at']!=bundle['start_at'] or opening['source_archive']!=bundle['archive']):
            raise ValueError('Restart account does not match its documented fresh opening')
