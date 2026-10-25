"""Operator-approved production routing. No import/startup side effects.

Signed grants bind installation, account, period, capital, opening and archive.
Routing is explicit and sticky: pause/rollback never revives legacy balances.
All strategy writes and stop/resume transitions serialize on the bundle row.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
from services.economic_opening import digest
from services.economic_ledger import stamp
from services.storage_service import get_storage_service

_PERMISSION=ContextVar('production_restart_permission',default=None)


def installation():
    value=os.getenv('NOK_DEPLOYMENT_ID','').strip()
    if not value:raise ValueError('Explicit NOK_DEPLOYMENT_ID required')
    return value


def require_backend(storage):
    if not storage.using_postgres() or storage.allow_local_fallback:
        raise ValueError('Production NOK accounts require PostgreSQL without local fallback')


def route_key(family):
    from services.simulation_restart import CAPITALS
    if family not in CAPITALS:raise ValueError('Unknown account family')
    return 'simulation_restarts/routes/'+family+'.json'


@contextmanager
def permission(period,family):
    token=_PERMISSION.set((period,family))
    try:yield
    finally:_PERMISSION.reset(token)


def permitted(period,family):return _PERMISSION.get()==(period,family)


def _certificate():
    path=Path(os.environ['NOK_APPROVAL_CERTIFICATE'])
    import hashlib
    if hashlib.sha256(path.read_bytes()).hexdigest()!=os.getenv('NOK_APPROVAL_CERT_SHA256'):
        raise ValueError('Operator certificate fingerprint mismatch')
    return path


def sign(payload,private_key):
    """Offline operator only; private key is never stored in the application DB."""
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'request';path.write_bytes(json.dumps(payload,sort_keys=True,separators=(',',':')).encode())
        result=subprocess.run(['openssl','dgst','-sha256','-sign',str(private_key),str(path)],capture_output=True,timeout=15)
        if result.returncode:raise ValueError('Operator signing failed')
        return {'payload':deepcopy(payload),'signature':base64.b64encode(result.stdout).decode()}


def verify_grant(grant):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);data=root/'request';sig=root/'signature';public=root/'public.pem'
        data.write_bytes(json.dumps(grant['payload'],sort_keys=True,separators=(',',':')).encode())
        sig.write_bytes(base64.b64decode(grant['signature'],validate=True))
        certificate=_certificate()
        result=subprocess.run(['openssl','x509','-pubkey','-noout','-in',str(certificate)],capture_output=True,timeout=15)
        if result.returncode:raise ValueError('Invalid operator certificate')
        public.write_bytes(result.stdout)
        result=subprocess.run(['openssl','dgst','-sha256','-verify',str(public),'-signature',str(sig),str(data)],capture_output=True,timeout=15)
        if result.returncode:raise ValueError('Invalid operator signature')
    p=grant['payload']
    if os.getenv('APP_ENVIRONMENT','production')!='production' or p['environment']!='production' or p['deployment_id']!=installation():
        raise ValueError('Grant is bound to another installation/environment')
    return p


def request(period,family,*,actor,approval_ref,at,restore_review,settings,cost_policy,storage=None):
    from services import simulation_restart as restart
    storage=storage or get_storage_service();bundle=storage.read_json(restart._key(period))
    restart.verify_bundle(bundle);doc=bundle['accounts'][family]
    if not actor or not approval_ref:raise ValueError('Named operator and approval reference required')
    from services.production_routing import strategy_settings
    if digest(settings)!=digest(strategy_settings(family,storage=storage)):raise ValueError('Use the existing configured strategy settings unchanged')
    stamp(at)
    if restore_review.get('status')!='RESTORED_AND_VERIFIED' or restore_review['archive']!=bundle['archive']:
        raise ValueError('Matching successful physical restore drill required')
    from services.trading_costs import validate_family
    validate_family(cost_policy,family,settings)
    return dict(schema='NOK_PRODUCTION_GRANT_V1',environment='production',deployment_id=installation(),
        period_id=period,family=family,capital_nok=restart.CAPITALS[family],opening_sha256=doc['opening_sha256'],
        start_at=bundle['start_at'],approved_at=at,approved_by=actor,approval_ref=approval_ref,
        archive=deepcopy(bundle['archive']),restore_review=deepcopy(restore_review),
        strategy_policy='EXISTING_CANONICAL_CONFIGURATION_AND_GOVERNANCE',
        settings=deepcopy(settings),cost_policy=deepcopy(cost_policy))


def _check_record(bundle,family,*,running=False):
    record=bundle.get('production_controls',{}).get(family)
    if not record:raise ValueError('No signed production authorization')
    p=verify_grant(record['grant']);doc=bundle['accounts'][family]
    if p.get('strategy_policy')!='EXISTING_CANONICAL_CONFIGURATION_AND_GOVERNANCE':raise ValueError('Unknown strategy governance policy')
    if (p['period_id']!=bundle['period_id'] or p['family']!=family or p['archive']!=bundle['archive']
        or p['opening_sha256']!=doc['opening_sha256'] or p['capital_nok']!=bundle['capitals_nok'][family]
        or p['start_at']!=bundle['start_at'] or digest(doc['approval'])!=record['approval_sha256']):
        raise ValueError('Production authorization does not match account')
    previous=None
    for i,event in enumerate(record['transitions'],1):
        if event['sequence']!=i or event['previous_hash']!=previous or event['hash']!=digest({k:v for k,v in event.items() if k!='hash'}):
            raise ValueError('Control journal integrity failure')
        previous=event['hash']
    if not record['transitions'] or record['status']!=record['transitions'][-1]['status']:raise ValueError('Missing control transition')
    if running and record['status']!='RUNNING':raise ValueError('Selected NOK account is stopped; no legacy fallback')
    return p


def _transition(record,status,actor,reason,at):
    events=record.setdefault('transitions',[])
    event=dict(sequence=len(events)+1,previous_hash=events[-1]['hash'] if events else None,
        status=status,actor=actor,reason=reason,at=at)
    event['hash']=digest(event);events.append(event);record['status']=status


def activate(grant,*,confirmation,archive_root,certificate,private_key,restore_destination,storage=None,database_dsns=None):
    """Explicit operator action; no env flag, scheduler or UI can self-approve."""
    from services import simulation_restart as restart,portfolio_accounting as ledger
    from services.simulation_archive import verify_archive, verify_restore_destination,verify_live_sources
    storage=storage or get_storage_service()
    require_backend(storage)
    p=verify_grant(grant)
    from services.trading_costs import validate_family
    validate_family(p['cost_policy'],p['family'],p['settings'])
    if confirmation!=digest(p):raise ValueError('Confirm the exact reviewed request fingerprint')
    reviewed=verify_archive(archive_root,p['archive']['archive_id'],certificate=certificate,private_key=private_key)
    if {k:reviewed[k] for k in p['archive']}!=p['archive']:raise ValueError('Archive differs from approved evidence')
    verify_restore_destination(restore_destination,p['restore_review'])
    connections={}
    try:
        names=set(reviewed['manifest'].get('database_model_fingerprints',{}))
        if database_dsns is None:
            if len(names)!=1:raise ValueError('Explicit source connections for all archived databases required')
            connections[next(iter(names))]=storage._conn()
        else:
            import psycopg2
            connections={name:psycopg2.connect(dsn,connect_timeout=10) for name,dsn in database_dsns.items()}
        verify_live_sources(reviewed,databases=connections,ignore_period=p['period_id'])
    finally:
        for connection in connections.values():connection.close()
    family=p['family'];period=p['period_id'];key=restart._key(period)
    # A route is create-only. A crash before route publication leaves an approved
    # but unselected account; retry publishes it without resetting anything.
    prior=storage.read_json(route_key(family),None)
    pointer=dict(period_id=period,family=family,deployment_id=installation(),grant_sha256=digest(grant))
    if prior is not None and prior!=pointer:raise ValueError('Account already bound to another period; no implicit switch')
    def mutation(bundle):
        restart.verify_bundle(bundle)
        if family in bundle.get('production_controls',{}):
            if bundle['production_controls'][family]['grant']!=grant:raise ValueError('Different activation already exists')
            _check_record(bundle,family);return bundle
        doc=bundle['accounts'][family]
        if doc['status']!='DRAFT':raise ValueError('Only fresh documented drafts may be activated')
        if (p['opening_sha256']!=doc['opening_sha256'] or p['start_at']!=bundle['start_at']
            or p['capital_nok']!=restart.CAPITALS[family] or p['archive']!=bundle['archive']):raise ValueError('Opening mismatch')
        # Reuse the authoritative approval validator in memory, not a second book.
        from services.restart_trading import Memory
        memory=Memory(bundle,key)
        approval={k:p[k] for k in ('approved_by','approval_ref','family','opening_sha256','start_at','approved_at')}
        approval.update(scope='production',deployment_id=p['deployment_id'],grant_sha256=digest(grant))
        with permission(period,family):ledger.approve(family,approval,storage=restart.AccountStorage(period,memory))
        result=memory.bundle
        record=dict(grant=deepcopy(grant),approval_sha256=digest(approval),transitions=[])
        _transition(record,'RUNNING',p['approved_by'],p['approval_ref'],p['approved_at'])
        result.setdefault('production_controls',{})[family]=record
        _check_record(result,family,running=True);restart.verify_bundle(result);return result
    storage.mutate_json(key,mutation)
    published=storage.write_json_immutable(route_key(family),pointer)
    if published!=pointer:raise ValueError('Concurrent route conflict; account remains unselected, no legacy fallback')
    return pointer


def selected(family,*,storage=None,require_running=True):
    from services import simulation_restart as restart
    storage=storage or get_storage_service()
    if os.getenv('APP_ENVIRONMENT','production')=='production' and os.getenv('NOK_DEPLOYMENT_ID'):
        require_backend(storage)
    pointer=storage.read_json(route_key(family),None)
    if pointer is None:return None
    if pointer['family']!=family or pointer['deployment_id']!=installation():raise ValueError('Selected account belongs to another installation')
    bundle=storage.read_json(restart._key(pointer['period_id']),None);restart.verify_bundle(bundle)
    p=_check_record(bundle,family,running=require_running)
    if pointer['grant_sha256']!=digest(bundle['production_controls'][family]['grant']):raise ValueError('Route authorization mismatch')
    return dict(pointer=pointer,bundle=bundle,approval=p)


def stop(period,family,*,actor,reason,confirmation,resume=False,storage=None):
    from services import simulation_restart as restart
    if not actor or not reason:raise ValueError('Operator identity and reason required')
    expected=dict(period_id=period,family=family,action='RESUME' if resume else 'STOP',deployment_id=installation())
    if confirmation!=digest(expected):raise ValueError('Exact stop/resume fingerprint required')
    storage=storage or get_storage_service()
    require_backend(storage)
    def mutation(bundle):
        restart.verify_bundle(bundle);_check_record(bundle,family)
        result=deepcopy(bundle)
        _transition(result['production_controls'][family],'RUNNING' if resume else 'PAUSED',actor,reason,datetime.now(timezone.utc).isoformat())
        return result
    return storage.mutate_json(restart._key(period),mutation)['production_controls'][family]['status']


def economic_event(period,family,event,*,actor,confirmation,storage=None):
    """Explicit operator booking of documented dividends/splits/capital flows."""
    from services import portfolio_accounting as ledger,simulation_restart as restart
    if not actor or confirmation!=digest(dict(period_id=period,family=family,event=event,actor=actor,deployment_id=installation())):
        raise ValueError('Review exact documented economic event and actor')
    storage=storage or get_storage_service();require_backend(storage)
    chosen=selected(family,storage=storage,require_running=False)
    if chosen is None or chosen['pointer']['period_id']!=period:raise ValueError('Wrong selected account')
    with permission(period,family):return ledger.record_event(family,event,storage=restart.AccountStorage(period,storage))
