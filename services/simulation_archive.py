"""Encrypted, create-only restart archives outside application and Git storage.

Snapshot ALL configured database/runtime sources, not a shortlist of trades.
Callers must inventory external report/model stores and quiesce writers first.
No reset, source write, schema migration or live restore exists in this module.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid

REPO=Path(__file__).resolve().parents[1]
CATEGORIES={'portfolios','trades','decisions_and_signals','reports','nav_and_results',
            'learning_models_and_observations','strategy_parameters','audit_and_diagnostics'}


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def _private_root(root, sources):
    root=Path(root).resolve()
    if root==REPO or REPO in root.parents:raise ValueError('Archive must remain outside Git')
    sources=list(sources)
    if os.getenv('APP_RUNTIME_ROOT'):sources.append(os.environ['APP_RUNTIME_ROOT'])
    for source in sources:
        source=Path(source).resolve()
        if source==root or source in root.parents or root in source.parents:
            raise ValueError('Archive and model runtime must be separate trees')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if stat.S_IMODE(root.stat().st_mode)&0o077:raise ValueError('Archive root must have private 0700 permissions')
    return root


def _inventory(root):
    root=Path(root).resolve()
    if root.is_file():return {root.name:sha(root)}
    if not root.is_dir():raise ValueError('Every declared runtime source must exist')
    files={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Declare resolved sources explicitly; symlinks are not archived')
        if path.is_dir():continue
        if not path.is_file():raise ValueError('Unsupported runtime file; quiesce and inventory source')
        files[path.relative_to(root).as_posix()]=sha(path)
    return files


def _pg_dump(connection, destination, program, *, fingerprints=None, name=None):
    """Full custom-format pg_dump, pinned to an exported read-only snapshot."""
    import psycopg2.extensions
    connection.set_session(readonly=True,isolation_level='REPEATABLE READ',autocommit=False)
    params=connection.get_dsn_parameters()
    env={**os.environ}
    # Credentials stay in child environment, never command arguments or receipts.
    for key,value in params.items():env['PGDATABASE' if key=='dbname' else 'PG'+key.upper()]=value
    if connection.info.password:env['PGPASSWORD']=connection.info.password
    with connection.cursor() as cur:
        cur.execute('SHOW transaction_read_only')
        if cur.fetchone()[0]!='on':raise ValueError('Read-only source transaction required')
        cur.execute('SELECT pg_export_snapshot(), transaction_timestamp()::text')
        snapshot,at=cur.fetchone()
        if fingerprints is not None and hasattr(connection,'server_version'):
            fingerprints[name]=database_fingerprint(connection)
        with Path(destination).open('xb') as stream:
            result=subprocess.run([str(program),'--format=custom','--snapshot='+snapshot],
                stdout=stream,stderr=subprocess.PIPE,env=env,timeout=1800)
        if result.returncode:raise ValueError('Database archive failed; no sealed archive created')
    connection.rollback()
    if Path(destination).stat().st_size==0:raise ValueError('Empty database dump')
    return at


def _openssl(args):
    result=subprocess.run(['openssl',*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1800)
    if result.returncode:raise ValueError('Archive encryption/decryption failed; check key and certificate privately')
    return result.stdout


def create_archive(root, *, runtime_roots, databases, certificate, coverage,
                   source_quiesced, coverage_confirmed, pg_dump_program='pg_dump'):
    """Create and seal a new encrypted archive. No overwrite or silent omissions.

    databases maps source names to already configured connections. Full dumps
    preserve all tables, reports, decisions, learning and audit, including unknown
    namespaces. Runtime roots include binary models and external report folders.
    """
    if not source_quiesced or not coverage_confirmed:raise ValueError('Quiesced sources and complete source inventory required')
    if set(coverage)!=CATEGORIES or not runtime_roots or not databases:
        raise ValueError('All archive categories, database and runtime sources must be declared')
    identifiers=set(runtime_roots)|set(databases)
    if len(identifiers)!=len(runtime_roots)+len(databases):raise ValueError('Source IDs must be unique')
    if any(not refs or not set(refs)<=identifiers for refs in coverage.values()):raise ValueError('Every category needs included source references')
    if any(not name or not name.replace('_','').isalnum() for name in identifiers):raise ValueError('Safe source IDs required')
    runtime_roots={name:Path(path).resolve() for name,path in runtime_roots.items()}
    root=_private_root(root,runtime_roots.values())
    archive_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex
    target=root/archive_id
    target.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix='.building-',dir=root) as working:
        work=Path(working);payload=work/'payload';payload.mkdir(mode=0o700)
        before={name:_inventory(path) for name,path in runtime_roots.items()}
        for name,source in runtime_roots.items():
            for relative in before[name]:
                dest=payload/'runtime'/name/relative;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source if source.is_file() else source/relative,dest)
                if sha(dest)!=before[name][relative]:raise ValueError('Runtime source changed while copying')
        db_times={};db_fingerprints={}
        for name,connection in databases.items():
            dest=payload/'databases'/(name+'.dump');dest.parent.mkdir(exist_ok=True)
            db_times[name]=_pg_dump(connection,dest,pg_dump_program,fingerprints=db_fingerprints,name=name)
        if before!={name:_inventory(path) for name,path in runtime_roots.items()}:
            raise ValueError('Runtime changed during archive; stop before restart')
        files={p.relative_to(payload).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size}
               for p in sorted(payload.rglob('*')) if p.is_file()}
        manifest=dict(schema='SIMULATION_ARCHIVE_V1',archive_id=archive_id,
            created_at=datetime.now(timezone.utc).isoformat(),coverage=coverage,
            source_quiesced=True,coverage_confirmed=True,database_snapshot_times=db_times,
            source_inventory=before,source_roots={k:str(v) for k,v in runtime_roots.items()},
            database_model_fingerprints=db_fingerprints,files=files,
            classification='PRIVATE_FULL_MODEL_HISTORY_NOT_VERIFIED_ECONOMIC_RETURNS')
        (payload/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,ensure_ascii=False))
        packed=work/'payload.tar'
        with tarfile.open(packed,'w') as archive:
            for p in sorted(payload.rglob('*')):
                if p.is_file():archive.add(p,arcname=p.relative_to(payload).as_posix(),recursive=False)
        encrypted=work/'archive.cms'
        _openssl(['cms','-encrypt','-binary','-aes-256-cbc','-outform','DER','-in',packed,'-out',encrypted,'-recip',certificate])
        receipt=dict(schema='SIMULATION_ARCHIVE_RECEIPT_V1',archive_id=archive_id,
            created_at=manifest['created_at'],cipher_sha256=sha(encrypted),
            manifest_sha256=sha(payload/'manifest.json'),file_count=len(files),
            coverage=sorted(coverage),status='SEALED_RESTORE_REVIEW_REQUIRED')
        # Exclusive creation; failed/incomplete directories are never restart evidence.
        with (target/'archive.cms').open('xb') as output,encrypted.open('rb') as source:
            shutil.copyfileobj(source,output)
            output.flush();os.fsync(output.fileno())
        with (target/'receipt.json').open('x') as output:
            json.dump(receipt,output,sort_keys=True)
            output.flush();os.fsync(output.fileno())
        for p in target.iterdir():p.chmod(0o400)
        target.chmod(0o500)
        for directory in (target,root):
            descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
    return receipt


def verify_archive(root, archive_id, *, certificate, private_key):
    """Offline restore drill: decrypt, verify every byte, never restore production."""
    if not archive_id or '/' in archive_id or '..' in archive_id:raise ValueError('Archive ID required')
    root=_private_root(root,[]);target=root/archive_id
    receipt=json.loads((target/'receipt.json').read_text())
    if receipt.get('archive_id')!=archive_id or receipt.get('status')!='SEALED_RESTORE_REVIEW_REQUIRED':
        raise ValueError('Incomplete or mismatched archive receipt')
    if sha(target/'archive.cms')!=receipt['cipher_sha256']:raise ValueError('Archive checksum mismatch')
    with tempfile.TemporaryDirectory(prefix='.review-',dir=root) as work:
        packed=Path(work)/'payload.tar'
        _openssl(['cms','-decrypt','-binary','-inform','DER','-in',target/'archive.cms',
                  '-recip',certificate,'-inkey',private_key,'-out',packed])
        with tarfile.open(packed) as archive:
            members=archive.getmembers();names=[m.name for m in members]
            if len(names)!=len(set(names)) or any(not m.isfile() or m.name.startswith('/') or '..' in Path(m.name).parts for m in members):
                raise ValueError('Unsafe archive structure')
            raw=archive.extractfile('manifest.json').read()
            if hashlib.sha256(raw).hexdigest()!=receipt['manifest_sha256']:raise ValueError('Manifest checksum mismatch')
            manifest=json.loads(raw)
            if manifest['archive_id']!=archive_id or set(manifest['coverage'])!=CATEGORIES:
                raise ValueError('Archive scope/identity mismatch')
            if set(names)!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Missing or unexpected archived files')
            for name,entry in manifest['files'].items():
                content_hash=hashlib.sha256()
                with archive.extractfile(name) as stream:
                    for block in iter(lambda:stream.read(1024*1024),b''):content_hash.update(block)
                if archive.getmember(name).size!=entry['bytes'] or content_hash.hexdigest()!=entry['sha256']:
                    raise ValueError('Archived file checksum mismatch')
    return {**receipt,'status':'VERIFIED_RESTORE_REVIEW','verified_at':datetime.now(timezone.utc).isoformat(),
            'manifest':manifest}


def restore_drill(root,archive_id,*,certificate,private_key,destination,database_targets,pg_restore_program='pg_restore'):
    """Restore to NEW private files and NEW EMPTY databases named nok_restore_*.

    Never uses --clean, DROP, overwrite, or any configured production database.
    Targets are caller-supplied DSNs kept out of receipts and process arguments.
    A failed restore leaves no successful receipt and cannot authorize activation.
    """
    import psycopg2
    from psycopg2.extensions import parse_dsn
    reviewed=verify_archive(root,archive_id,certificate=certificate,private_key=private_key)
    destination=Path(destination).resolve()
    _private_root(destination.parent,[])
    if destination.exists():raise ValueError('Restore destination must be new; never overwrite')
    destination.mkdir(mode=0o700)
    required=set(reviewed['manifest']['database_snapshot_times'])
    if set(database_targets)!=required:raise ValueError('Every archived database needs its own empty restore target')
    identities=set();results={}
    for name,dsn in database_targets.items():
        params=parse_dsn(dsn);dbname=params.get('dbname','')
        if not dbname.startswith('nok_restore_'):raise ValueError('Only explicitly isolated nok_restore_* databases may be restored')
        identity=(params.get('host',''),params.get('port','5432'),dbname)
        if identity in identities:raise ValueError('Restore targets must be distinct')
        identities.add(identity)
        for variable in ('DATABASE_URL','AUTH_DATABASE_URL'):
            source=os.getenv(variable)
            if source:
                original=parse_dsn(source)
                if identity==(original.get('host',''),original.get('port','5432'),original.get('dbname','')):
                    raise ValueError('Active application/auth database is not a restore target')
        connection=psycopg2.connect(dsn,connect_timeout=10)
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f')")
                if cur.fetchone()[0]:raise ValueError('Restore target is not empty')
        finally:connection.close()
    packed=destination/'payload.tar'
    _openssl(['cms','-decrypt','-binary','-inform','DER','-in',Path(root)/archive_id/'archive.cms',
        '-recip',certificate,'-inkey',private_key,'-out',packed])
    # verify_archive already checked structure/checksums. Repeat extraction checks
    # through tarfile's data filter rather than trusting filesystem paths.
    with tarfile.open(packed) as archive:archive.extractall(destination/'payload',filter='data')
    packed.unlink()
    for name,dsn in database_targets.items():
        params=parse_dsn(dsn);env={**os.environ}
        for k,v in params.items():env['PGDATABASE' if k=='dbname' else 'PG'+k.upper()]=v
        with (destination/'payload'/'databases'/(name+'.dump')).open('rb') as stream:
            result=subprocess.run([str(pg_restore_program),'--exit-on-error','--no-owner','--no-privileges','--dbname='+params['dbname']],
                stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=1800)
        if result.returncode:raise ValueError('Physical PostgreSQL restore failed; activation remains blocked')
        connection=psycopg2.connect(dsn,connect_timeout=10)
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
                tables=cur.fetchall();counts={}
                from psycopg2 import sql
                for schema,table in tables:
                    cur.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table)))
                    counts[schema+'.'+table]=cur.fetchone()[0]
                results[name]=dict(status='RESTORED',tables=counts)
            fingerprint=database_fingerprint(connection)
            if fingerprint!=reviewed['manifest'].get('database_model_fingerprints',{}).get(name):
                raise ValueError('Restored database differs from archived snapshot')
            from services.economic_opening import digest
            results[name]['model_fingerprint_sha256']=digest(fingerprint)
        finally:connection.close()
    proof={k:reviewed[k] for k in ('archive_id','cipher_sha256','manifest_sha256','file_count')}
    receipt=dict(status='RESTORED_AND_VERIFIED',archive=proof,databases=results,
        restored_at=datetime.now(timezone.utc).isoformat(),files=_inventory(destination/'payload'))
    from services.economic_opening import digest
    receipt['review_sha256']=digest(receipt)
    (destination/'restore-review.json').write_text(json.dumps(receipt,sort_keys=True))
    return receipt


def verify_restore_destination(destination,receipt):
    from services.economic_opening import digest
    destination=Path(destination).resolve()
    _private_root(destination.parent,[])
    if (receipt.get('status')!='RESTORED_AND_VERIFIED' or
        receipt.get('review_sha256')!=digest({k:v for k,v in receipt.items() if k!='review_sha256'}) or
        not receipt.get('databases') or any(v.get('status')!='RESTORED' for v in receipt['databases'].values()) or
        json.loads((destination/'restore-review.json').read_text())!=receipt or
        _inventory(destination/'payload')!=receipt['files']):
        raise ValueError('Missing, incomplete or changed physical restore evidence')
    return receipt


def database_fingerprint(connection,*,ignore_period=None):
    """Read-only multiset fingerprints, streamed; no financial values in receipt.

    Activation may exclude only its newly prepared period and matching routes.
    All pre-existing periods, legacy tables, losses, learning and unknown tables
    remain protected.
    Called inside pg_dump's exported repeatable-read snapshot.
    """
    from psycopg2 import sql
    result={}
    with connection.cursor() as cur:
        cur.execute("SET LOCAL TIME ZONE 'UTC'")
        cur.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
        tables=cur.fetchall()
    for schema,table in tables:
        query=sql.SQL('SELECT row_to_json(t)::text FROM {}.{} AS t').format(sql.Identifier(schema),sql.Identifier(table))
        count=0;total=0
        with connection.cursor(name='archive_'+uuid.uuid4().hex) as rows:
            rows.itersize=1000;rows.execute(query)
            for (raw,) in rows:
                # Canonical JSON removes representation differences on restore.
                from decimal import Decimal
                value=json.loads(raw,parse_float=Decimal)
                if table=='app_kv_store' and ignore_period:
                    key=value.get('name','')
                    if key=='simulation_restarts/'+ignore_period+'/bundle.json':continue
                    if key.startswith('simulation_restarts/routes/'):
                        payload=value.get('payload');payload=json.loads(payload) if isinstance(payload,str) else payload
                        if payload.get('period_id')==ignore_period:continue
                content=json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()
                total=(total+int.from_bytes(hashlib.sha256(content).digest(),'big'))%(1<<256);count+=1
        result[schema+'.'+table]=dict(rows=count,multiset_sha256_sum=f'{total:064x}')
    return result


def verify_live_sources(reviewed,*,databases,ignore_period=None):
    """Activation barrier: archive still matches quiesced legacy/model sources."""
    manifest=reviewed['manifest']
    if not manifest.get('source_roots') or set(manifest.get('database_model_fingerprints',{}))!=set(databases):
        raise ValueError('Archive lacks full live-source fingerprint coverage')
    for name,path in manifest['source_roots'].items():
        if _inventory(path)!=manifest['source_inventory'][name]:raise ValueError('Runtime changed after archive; stop activation')
    for name,connection in databases.items():
        connection.set_session(readonly=True,isolation_level='REPEATABLE READ',autocommit=False)
        try:
            if database_fingerprint(connection,ignore_period=ignore_period)!=manifest['database_model_fingerprints'][name]:
                raise ValueError('Database model/history changed after archive; stop activation')
        finally:connection.rollback()
