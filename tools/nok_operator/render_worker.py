"""Private operator process over SSH. Never schedules, resets, archives or restores a DB."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import socketserver
import subprocess
import sys
import tarfile
import tempfile
import threading

from wire import emit, line, send_file, receive_file, sha
import operator_common as shared

OUT = None
IN = None
LOCK = threading.Lock()
ROOT = None
ORIGINAL_PGOPTIONS = None


def event(kind, **values):
    with LOCK: emit(OUT, dict(kind=kind, **values))


def upload(name, path, expected_sha256=None):
    part=path.with_name(path.name+'.part')
    offset=part.stat().st_size if name=='archive.cms' and part.is_file() and not part.is_symlink() else 0
    with LOCK:
        emit(OUT,dict(kind='upload',name=name,offset=offset,prefix_sha256=sha(part) if offset else None))
        return receive_file(IN,path,offset=offset,expected_sha256=expected_sha256)


def download(name, path):
    with LOCK: send_file(OUT, path, kind='download', name=name)


def store(path, value):
    shared.save(path, value)


def original_review(value):
    if (value.get('status') != 'RESTORED_AND_VERIFIED'
        or value.get('review_sha256') != shared.REVIEW_SHA):
        raise ValueError('Original verified restore receipt required')
    from services.economic_opening import digest
    if digest({k:v for k,v in value.items() if k!='review_sha256'}) != shared.REVIEW_SHA:
        raise ValueError('Original restore receipt checksum mismatch')
    if value['archive']['archive_id'] != shared.ARCHIVE:
        raise ValueError('Wrong original archive')
    return value


class DecryptHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            args = json.loads(self.rfile.readline(8192))
            expected = ['cms','-decrypt','-binary','-inform','DER','-in',None,'-recip',None,'-inkey',None,'-out',None]
            if len(args)!=len(expected) or any(e is not None and a!=e for a,e in zip(args,expected)):
                raise ValueError('Only original archive CMS decrypt is delegated')
            cipher, cert, key, target = map(Path, (args[6],args[8],args[10],args[12]))
            if (sha(cipher)!=self.server.cipher_sha or sha(cert)!=self.server.cert_sha
                or key.resolve()!=self.server.token.resolve()
                or not target.resolve().is_relative_to(ROOT.resolve()) or target.exists()):
                raise ValueError('Private decrypt binding mismatch')
            with LOCK:
                emit(OUT,dict(kind='decrypt',cipher_sha256=self.server.cipher_sha,certificate_sha256=self.server.cert_sha))
                receive_file(IN,target)
            target.chmod(0o600)
            # Keep the same inode core.verify_archive is about to verify, so
            # rehydration does not require a second plaintext network transfer.
            cache=ROOT/'decrypted-transport-cache.tar'
            if not cache.exists():os.link(target,cache)
            self.wfile.write(b'{"ok":true}\n')
        except Exception:
            self.wfile.write(b'{"ok":false}\n')


def delegate(root, receipt):
    """Transport adapter, not an archive-verifier override. Core remains unchanged."""
    actual = shutil.which('openssl')
    if not actual: raise ValueError('Installed OpenSSL missing')
    binary = root/'crypto-bin'; binary.mkdir(mode=0o700,exist_ok=True)
    code = Path(__file__).with_name('openssl_delegate.py').read_text()
    expected_code='#!'+sys.executable+'\n'+code.split('\n',1)[1]
    if (binary/'openssl').exists() and (binary/'openssl').read_text()!=expected_code:raise ValueError('Existing crypto transport code changed')
    if not (binary/'openssl').exists():(binary/'openssl').write_text(expected_code)
    (binary/'openssl').chmod(0o700)
    token = root/'PC_ARCHIVE_KEY_HANDLE'
    if not token.exists():token.write_text('NONSECRET PC CRYPTO HANDLE; NOT A PRIVATE KEY\n')
    token.chmod(0o600)
    import fcntl,stat
    handle=(root/'operator-process.lock').open('a+b')
    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise ValueError('An existing operator process still owns this context; no concurrent retry')
    sock = str(root/'decrypt.sock')
    if os.path.lexists(sock):
        info=os.lstat(sock)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.geteuid():raise ValueError('Unexpected previous crypto socket')
        os.unlink(sock)  # stale socket only; exclusive process lock proves no live owner.
    server = socketserver.UnixStreamServer(sock, DecryptHandler)
    server.operator_lock=handle
    os.chmod(sock,0o600)
    server.cipher_sha = receipt['cipher_sha256']; server.cert_sha = sha(root/'archive-certificate.pem'); server.token = token
    threading.Thread(target=server.serve_forever,daemon=True).start()
    if (root/'decrypt.sock').is_symlink():raise ValueError('Unexpected crypto socket symlink')
    os.environ.update(NOK_SYSTEM_OPENSSL=actual,NOK_DECRYPT_SOCKET=sock,PATH=str(binary)+os.pathsep+os.environ['PATH'])
    return server, token


def recover_payload(root, receipt, review, token):
    from services import simulation_archive as archive
    destination = root/'verification-files'
    if destination.exists():
        # Safe preparation reuse: SAME pinned ciphertext, original restore
        # receipt, manifest bytes and every payload file are checked again.
        # activate() still runs its complete real verify_archive/decrypt barrier.
        archive.verify_restore_destination(destination,review)
        if sha(root/'archives'/shared.ARCHIVE/'archive.cms')!=receipt['cipher_sha256']:
            raise ValueError('Retained original ciphertext changed')
        manifest_path=destination/'payload'/'manifest.json'
        if manifest_path.stat().st_size>32*1024**2 or sha(manifest_path)!=receipt['manifest_sha256']:
            raise ValueError('Retained original manifest changed')
        sealed=dict(receipt,manifest=shared.load(manifest_path),
            verification_method='PINNED_CIPHERTEXT_AND_ORIGINAL_RESTORE_FILES_RECHECKED')
        (root/'decrypted-transport-cache.tar').unlink(missing_ok=True)
        return sealed,destination
    sealed = archive.verify_archive(root/'archives',shared.ARCHIVE,certificate=root/'archive-certificate.pem',private_key=token)
    # Rehydrate ONLY the original receipt's file inventory. No DB CREATE/restore.
    packed = root/'decrypted-transport-cache.tar'
    if not packed.is_file():raise ValueError('Verified plaintext transport inode missing')
    destination.mkdir(mode=0o700)
    with tarfile.open(packed) as original:
        names = [m.name for m in original.getmembers()]
        if len(names)!=len(set(names)) or set(names)!=set(review['files']):
            raise ValueError('Restored payload inventory differs from ORIGINAL receipt')
        if any(not m.isfile() or m.name.startswith('/') or '..' in Path(m.name).parts for m in original.getmembers()):
            raise ValueError('Unsafe restored file tree')
        original.extractall(destination/'payload',filter='data')
    store(destination/'restore-review.json',review)
    archive.verify_restore_destination(destination,review)
    packed.unlink()  # only our temporary decrypted tar, never original evidence.
    store(root/'verification-files-receipt.json',dict(status='ORIGINAL_RESTORE_FILE_TREE_REHYDRATED_AND_VERIFIED',
        original_review_sha256=shared.REVIEW_SHA,archive=review['archive'],new_database_restore_performed=False,
        source='EXISTING_SEALED_ARCHIVE',files=len(review['files'])))
    return sealed,destination


def source_check(sealed, config, storage, destination):
    from services.simulation_archive import verify_live_sources
    import psycopg2
    connections={}
    try:
        mapping=config['database_environment_variables']
        if set(mapping)!=set(sealed['manifest']['database_model_fingerprints']):
            raise ValueError('Original full database coverage differs')
        for name,variable in mapping.items():
            connections[name]=psycopg2.connect(os.environ[variable],connect_timeout=10)
        from services.simulation_archive import runtime_source_evidence
        runtime_evidence=runtime_source_evidence(sealed,destination/'payload')
        verify_live_sources(sealed,databases=connections,ignore_period=shared.PERIOD,
            restored_payload=destination/'payload',runtime_evidence=runtime_evidence)
        return runtime_evidence
    finally:
        for connection in connections.values():connection.close()


def strategy_inputs(storage):
    """Read actual persisted producer outputs, not scanner workers/default signals."""
    from services.economic_opening import digest
    values={}; sources={}; blockers=[]
    # Use complete immutable scanner inputs and the EXISTING production strategy.
    # The bridge contains parallel/shadow decisions and must not replace it.
    index=storage.read_json('repositories/market_snapshots_index.json',[])
    snapshots=[r for r in index if r.get('source')=='paper_scanner'] if isinstance(index,list) else []
    if snapshots:
        entry=max(snapshots,key=lambda r:str(r.get('captured_at') or ''))
        snapshot=storage.read_json(entry.get('item_key',''),None)
        if isinstance(snapshot,dict):
            from domain.market_snapshot import validate_market_snapshot
            from repositories.application import RepositoryRegistry
            from services.strategy_registry_service import StrategyRegistryService
            from services.production_strategy_service import ProductionStrategyService
            from signal_engine import build_trading_decision
            if not validate_market_snapshot(snapshot)['ok']:
                blockers.append('Paper: lagret immutable scanner-snapshot har ugyldig integritet')
            else:
                registry=StrategyRegistryService(RepositoryRegistry(storage))
                selected=registry.production_for_family('technical')
                if not selected:
                    blockers.append('Paper: lagret produksjonsstrategi mangler; ingen kode-default valgt')
                else:
                    from services.market_snapshot_service import MarketSnapshotService
                    from services.technical_signal_service import TechnicalSignalService
                    from services.technical_quality_service import TechnicalQualityService
                    quality=TechnicalQualityService(TechnicalSignalService(MarketSnapshotService(RepositoryRegistry(storage))))
                    service=ProductionStrategyService(registry=registry,quality_service=quality)
                    from services import simulation_restart as restart
                    # Existing strategy router only reads portfolio positions/cash.
                    bundle=storage.read_json(restart._key(shared.PERIOD))
                    account=bundle['accounts']['paper']['account']
                    portfolio_state=dict(cash=account['cash'],initial_cash=account['initial_cash'],positions=account['positions'])
                    signals=[]
                    for row in snapshot.get('candidates',[]):
                        technical=row.get('technical')
                        if not isinstance(technical,dict) or not technical:
                            blockers.append('Paper: lagrede tekniske input mangler for '+row['ticker']);continue
                        decision=service.evaluate_technical(row,build_trading_decision(row,technical),
                            run_id=snapshot['run_id'],portfolio_state=portfolio_state)
                        if decision.get('production_router_error'):
                            blockers.append('Paper: eksisterende produksjonsstrategi kunne ikke evalueres for '+row['ticker']);continue
                        signals.append(dict(ticker=row['ticker'],operation='AUTO',signal=decision['decision'],
                            confidence=decision['confidence'],rsi=technical.get('rsi'),prev_rsi=technical.get('prev_rsi'),
                            currency=row.get('currency'),trade_context=dict(candidate_snapshot=row,
                                decision_source='technical_production_strategy',source_run_id=snapshot['run_id'],
                                source_snapshot_sha256=digest(snapshot),production_decision=decision)))
                    if signals:
                        values['paper']=signals
                        sources['paper']=dict(key=entry['item_key'],run_id=snapshot['run_id'],sha256=digest(snapshot),
                            production_strategy_sha256=digest(selected))
    if 'paper' not in values:blockers.append('Paper: fullstendig faktisk scanner-input/produksjonsbinding mangler; ingen standardsignaler valgt')
    run=storage.read_json('market_intelligence/latest_run.json',None)
    if isinstance(run,dict) and run.get('run_id') and isinstance(run.get('candidates'),list):
        status=str(run.get('completion_status') or run.get('status') or '').upper()
        if status not in ('FULLFØRT','COMPLETED','COMPLETE','SUCCESS','SUCCEEDED'):
            blockers.append('Autonomi: siste lagrede MI-kjøring er ikke bekreftet fullført: '+status)
        else:
            # Exact existing runtime/orchestrator.py handoff filtering, no learning writes.
            observed=run['candidates'];valid=[r for r in observed if r.get('valid_for_decision',True)]
            selected=valid if valid else observed
            values['autonomy']=[dict(r,autonomy_learning_probe=bool(observed and not valid)) for r in selected
                if not r.get('portfolio_action') or str(r['portfolio_action']).upper() in {'BUY','HOLD','SELL','REVIEW','SKIP'}]
            sources['autonomy']=dict(key='market_intelligence/latest_run.json',run_id=run['run_id'],sha256=digest(run),
                governance='autonomi_core/runtime/orchestrator.py existing handoff')
    if 'autonomy' not in values:blockers.append('Autonomi: fullført faktisk MI-input mangler')
    pipeline=storage.read_json('super_portfolio/market_pipeline.json',None)
    if isinstance(pipeline,dict) and pipeline.get('run_id') and isinstance(pipeline.get('candidates'),list):
        if any(r.get('source')!='Super Portfolio independent market universe' for r in pipeline['candidates']):
            blockers.append('Superporteføljen: uavhengig univers/opprinnelse kan ikke bekreftes')
        else:
            values['super_portfolio']=pipeline
            sources['super_portfolio']=dict(key='super_portfolio/market_pipeline.json',run_id=pipeline['run_id'],sha256=digest(pipeline))
    if 'super_portfolio' not in values:blockers.append('Superporteføljen: faktisk uavhengig pipeline mangler')
    return values,sources,blockers


def activation_preflights(inputs,costs,review,storage,runtime_evidence):
    from services import activation_preflight as preflight,production_routing as routing
    result={}
    for family in shared.FAMILIES:
        result[family]=preflight.inspect(shared.PERIOD,family,
            settings=routing.strategy_settings(family,storage=storage,require_stored=True),
            cost_policy=costs[family],restore_review=review,strategy_input=inputs[family],
            storage=storage,runtime_evidence=runtime_evidence)
    return result


def build_requests(root, review, actor, storage, preflights):
    from services import production_restart as control,production_routing as routing
    from services.economic_opening import digest
    requests={};costs=shared.policies();settings={}
    at=datetime.now(timezone.utc).isoformat()
    for family in shared.FAMILIES:
        settings[family]=routing.strategy_settings(family,storage=storage,require_stored=True)
        requests[family]=control.request(shared.PERIOD,family,actor=actor,approval_ref='PERSONAL-B-REQUIRED:'+root.name,
            at=at,restore_review=review,settings=settings[family],cost_policy=costs[family],storage=storage,
            activation_preflight=preflights[family])
    cert=control._certificate()
    catalog=dict(environment='production',deployment_id=shared.DEPLOYMENT,period_id=shared.PERIOD,
        archive=review['archive'],restore_review_sha256=shared.REVIEW_SHA,
        operator_certificate_file_sha256=sha(cert),requests={f:digest(requests[f]) for f in shared.FAMILIES})
    return requests,settings,costs,catalog,cert


def prepare(root, receipt, review, config, token, actor):
    from services import simulation_restart as restart
    from services.economic_opening import digest
    event('progress',message='Verifiserer eksisterende arkiv og gjenskaper bare manglende originalt filtre.')
    sealed,destination=recover_payload(root,receipt,review,token)
    storage=shared.ReadOnlyStorage()
    event('progress',message='Kontrollerer fullstendige eksisterende arkivfingeravtrykk med deployet native UTF-8-adapter.')
    runtime_evidence=source_check(sealed,config,storage,destination)
    inputs,sources,blockers=strategy_inputs(storage)
    if blockers:raise ValueError('; '.join(blockers))
    actual=activation_preflights(inputs,shared.policies(),review,storage,runtime_evidence)
    requests,settings,costs,catalog,cert=build_requests(root,review,actor,storage,actual)
    catalog['strategy_input_sources']=sources
    catalog['preflight_evidence_sha256']={family:digest(p) for family,p in actual.items()}
    out=root/('requests-'+os.urandom(8).hex());out.mkdir(mode=0o700)
    for f,payload in requests.items():store(out/(f+'-request.json'),payload)
    (out/'operator-certificate.PUBLIC.pem').write_bytes(cert.read_bytes())
    store(out/'catalog.json',catalog);store(out/'input-sources.json',sources);store(out/'settings.json',settings)
    store(out/'cost-policies.json',costs)
    before=digest(storage.read_json(restart._key(shared.PERIOD)))
    store(out/'private-context.json',dict(work=str(root),source_bundle_sha256=before,catalog_sha256=digest(catalog),
        restore_destination=str(destination),config=config,input_sources=sources))
    preview_dir=out/'activation-preflights';preview_dir.mkdir(mode=0o700)
    for family,p in actual.items():store(preview_dir/(family+'.json'),p)
    ready=not blockers and set(actual)==set(shared.FAMILIES)
    # Readiness is explicitly order-free. No live_preview receipt is manufactured.
    status=dict(status='READY_FOR_PERSONAL_B' if ready else 'WAITING_FOR_ACTIVATION_INPUT',
        approval_B_ready=ready,blockers=blockers,accounts_activated=False,scheduler_started=False,
        catalog_sha256=digest(catalog),remote_package=str(out),period_id=shared.PERIOD,
        archive_sha256=receipt['cipher_sha256'],restore_review_sha256=shared.REVIEW_SHA)
    store(out/'status.json',status)
    for family,p in actual.items():
        store(out/(family+'-activation-preflight.json'),p)
    for p in sorted(out.iterdir()):
        if p.is_file() and p.name!='private-context.json':download(p.name,p)
    event('complete',**status)


def activate(root,receipt,review,config,token,header):
    from services import production_restart as control,production_routing as routing,simulation_restart as restart
    from services.economic_opening import digest
    # A redeploy may remove all /tmp files. The exact locally reviewed requests
    # are restored from PC; no server-side replacement grant or signature is made.
    out=root/('approved-'+header['approval_b'])
    out.mkdir(mode=0o700,exist_ok=True)
    for name in ['catalog.json','status.json']+[f+'-request.json' for f in shared.FAMILIES]:
        target=out/name
        if not target.exists():upload(name,target)
    catalog=shared.load(out/'catalog.json');status=shared.load(out/'status.json')
    if (status.get('approval_B_ready') is not True or header.get('approval_b')!=digest(catalog)
        or status.get('catalog_sha256')!=digest(catalog)):
        raise ValueError('Exact personal B and complete prerequisites required')
    signed=root/('signed-'+os.urandom(8).hex()+'.json');upload('signed-grants.json',signed)
    grants=shared.load(signed)
    if grants.get('personal_B_catalog_sha256')!=digest(catalog) or set(grants.get('grants',{}))!=set(shared.FAMILIES):raise ValueError('B package mismatch')
    storage=shared.ReadOnlyStorage();requests={}
    from services.activation_preflight import validate
    for family in shared.FAMILIES:
        payload=control.verify_grant(grants['grants'][family]);requests[family]=payload
        if (payload!=shared.load(out/(family+'-request.json')) or digest(payload)!=catalog['requests'][family]
            or payload.get('schema')!='NOK_PRODUCTION_GRANT_V2'):
            raise ValueError('Signed activation request changed')
        validate(payload.get('activation_preflight'),shared.PERIOD,family,settings=payload['settings'],
            cost_policy=payload['cost_policy'],restore_review=review,storage=storage)
    if sha(control._certificate())!=catalog['operator_certificate_file_sha256']:raise ValueError('Public signing pin changed')
    # Restore the original verification files after redeploy, never a new DB or account.
    recover_payload(root,receipt,review,token)
    if ORIGINAL_PGOPTIONS is None:os.environ.pop('PGOPTIONS',None)
    else:os.environ['PGOPTIONS']=ORIGINAL_PGOPTIONS
    from services.storage_service import get_storage_service
    writable=get_storage_service();control.require_backend(writable)
    activated=[]
    try:
        for family in shared.FAMILIES:
            pointer=control.activate(grants['grants'][family],confirmation=catalog['requests'][family],
                archive_root=root/'archives',certificate=root/'archive-certificate.pem',private_key=token,
                restore_destination=root/'verification-files',storage=writable,
                database_dsns={name:os.environ[var] for name,var in config['database_environment_variables'].items()})
            activated.append(family)
            path=out/(family+'-activation-receipt.json')
            if path.exists():
                if shared.load(path)!=pointer:raise ValueError('Existing activation receipt differs')
            else:store(path,pointer)
            download(path.name,path)
        bundle=storage.read_json(restart._key(shared.PERIOD));proof={}
        for family in shared.FAMILIES:
            control._check_record(bundle,family,running=True)
            route=storage.read_json(control.route_key(family))
            if route['period_id']!=shared.PERIOD or route['grant_sha256']!=digest(grants['grants'][family]):raise ValueError('PostgreSQL route mismatch')
            doc=bundle['accounts'][family];account=doc['account']
            proof[family]=dict(status=doc['status'],control_status=bundle['production_controls'][family]['status'],
                cash_nok=account['cash'],positions=len(account['positions']),trades=len(account['trades']),route=route)
        path=out/('postgres-activation-confirmation-'+os.urandom(4).hex()+'.json');store(path,proof);download('postgres-activation-confirmation.json',path)
        event('complete',status='ACTIVATED_AND_CONFIRMED_IN_POSTGRESQL',accounts=proof,scheduler_started=False)
    except Exception:
        event('partial',activated=activated,message='Ingen automatisk gjentakelse eller rollback. Behold kvitteringene.')
        raise


def main():
    global ROOT,ORIGINAL_PGOPTIONS,OUT,IN
    OUT=sys.stdout.buffer;IN=sys.stdin.buffer
    # Third-party stdout must never corrupt the framed channel.
    sys.stdout=sys.stderr
    os.umask(0o077)
    header=line(IN)
    if (os.getenv('RENDER_SERVICE_ID')!=shared.SERVICE or os.getenv('APP_ENVIRONMENT')!='production'
        or os.getenv('NOK_DEPLOYMENT_ID')!=shared.DEPLOYMENT or os.getenv('STORAGE_MODE')!='postgres'
        or os.getenv('ALLOW_LOCAL_STORAGE_FALLBACK','false').lower() not in ('false','0','no')):
        raise ValueError('Wrong production installation; no action')
    sys.path.insert(0,'/opt/render/project/src')
    ORIGINAL_PGOPTIONS=os.getenv('PGOPTIONS');os.environ['PGOPTIONS']=(ORIGINAL_PGOPTIONS or '')+' -c default_transaction_read_only=on'
    os.environ['APP_RUNTIME_ROOT']=tempfile.mkdtemp(prefix='nok-isolated-runtime-')
    from services.economic_opening import digest
    try:
        from services.activation_preflight import inspect as activation_capability
    except ImportError:
        raise ValueError('Deploy the tested unified activation-preflight release before running this versioned operator')
    retained=header.get('remote_work')
    if retained:
        candidate=Path(retained).resolve()
        if candidate.parent!=Path('/tmp') or not candidate.name.startswith('nok-verify-existing-'):
            raise ValueError('Unexpected retained verification environment')
        if candidate.exists() and (candidate.is_symlink() or candidate.stat().st_mode & 0o077):
            raise ValueError('Retained verification context is not private')
    else:candidate=None
    if header['action'] in {'prepare','activate'}:
        ROOT=candidate if candidate is not None and candidate.is_dir() else Path(tempfile.mkdtemp(prefix='nok-verify-existing-'))
        event('context',remote_work=str(ROOT))
        if not (ROOT/'archive-receipt.json').exists():
            for name in ('config.json','restore-result.json','archive-certificate.pem','archive-receipt.json'):
                upload(name,ROOT/name)
        config=shared.load(ROOT/'config.json');review=original_review(shared.load(ROOT/'restore-result.json'));receipt=shared.load(ROOT/'archive-receipt.json')
        if {k:receipt[k] for k in review['archive']}!=review['archive']:raise ValueError('Archive receipt differs from original restore')
        target=ROOT/'archives'/shared.ARCHIVE;target.mkdir(parents=True,mode=0o700,exist_ok=True);target.parent.chmod(0o700)
        if not (target/'receipt.json').exists():store(target/'receipt.json',receipt)
        if not (target/'archive.cms').exists():upload('archive.cms',target/'archive.cms',expected_sha256=receipt['cipher_sha256'])
        if sha(target/'archive.cms')!=receipt['cipher_sha256']:raise ValueError('Incomplete previous ciphertext transfer; preserved, never reused')
    else:raise ValueError('Unknown action')
    if receipt.get('archive_id')!=shared.ARCHIVE or receipt.get('cipher_sha256')!=shared.CIPHER_SHA:raise ValueError('Unexpected original cipher identity')
    server,token=delegate(ROOT,receipt)
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(30):event('progress',message='Operatorprosessen arbeider fortsatt; ikke start en parallell kjoring.')
    threading.Thread(target=heartbeat,daemon=True).start()
    try:
        if header['action']=='prepare':prepare(ROOT,receipt,review,config,token,header['actor'])
        else:activate(ROOT,receipt,review,config,token,header)
    finally:
        stop.set()
        server.shutdown();server.server_close();(ROOT/'decrypt.sock').unlink(missing_ok=True)
        (ROOT/'decrypted-transport-cache.tar').unlink(missing_ok=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        event('error',error_type=type(error).__name__,message=str(error) if isinstance(error,ValueError) else 'Kontrollen stoppet; private nøkler/tilkoblingsstrenger er ikke skrevet ut.')
        raise SystemExit(1)
