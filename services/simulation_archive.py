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
    if not root.is_dir():raise ValueError('Every declared runtime source must exist')
    files={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Declare resolved sources explicitly; symlinks are not archived')
        if path.is_dir():continue
        if not path.is_file():raise ValueError('Unsupported runtime file; quiesce and inventory source')
        files[path.relative_to(root).as_posix()]=sha(path)
    return files


def _pg_dump(connection, destination, program):
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
                shutil.copy2(source/relative,dest)
                if sha(dest)!=before[name][relative]:raise ValueError('Runtime source changed while copying')
        db_times={}
        for name,connection in databases.items():
            dest=payload/'databases'/(name+'.dump');dest.parent.mkdir(exist_ok=True)
            db_times[name]=_pg_dump(connection,dest,pg_dump_program)
        if before!={name:_inventory(path) for name,path in runtime_roots.items()}:
            raise ValueError('Runtime changed during archive; stop before restart')
        files={p.relative_to(payload).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size}
               for p in sorted(payload.rglob('*')) if p.is_file()}
        manifest=dict(schema='SIMULATION_ARCHIVE_V1',archive_id=archive_id,
            created_at=datetime.now(timezone.utc).isoformat(),coverage=coverage,
            source_quiesced=True,coverage_confirmed=True,database_snapshot_times=db_times,
            source_inventory=before,files=files,
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
