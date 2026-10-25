"""Resume only transfer/finalization after a genuine completed Windows restore."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import runpy
import sys
import threading
import uuid
import zipfile

os.umask(0o077)
WORK=Path('/tmp/nok-job-20261024T165039Z')
ACTIVE_WORKER=None


def load(path):
    if path.is_symlink() or path.stat().st_size>4*1024**2:raise ValueError('Unexpected private metadata')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024**2),b''):h.update(chunk)
    return h.hexdigest()


def no_running_job(work):
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name)==os.getpid():continue
        try:
            if entry.stat().st_uid!=os.geteuid():continue
            args=(entry/'cmdline').read_bytes().split(b'\0')
            if any(a==str(work).encode() or a.startswith((str(work)+'/').encode()) for a in args):
                raise ValueError('Another private job process may be running; no replay')
        except (FileNotFoundError,ProcessLookupError):continue


def private_directory(path):
    if not path.is_dir() or path.is_symlink() or path.stat().st_uid!=os.geteuid() or path.stat().st_mode & 0o077:
        raise ValueError('Expected private operator directory')


def target_valid(target,receipt):
    if not target.is_dir() or target.is_symlink():return False
    if set(p.name for p in target.iterdir())!={'archive.cms','receipt.json'}:return False
    cipher=target/'archive.cms';proof=target/'receipt.json'
    return (not cipher.is_symlink() and not proof.is_symlink() and load(proof)==receipt
            and sha(cipher)==receipt['cipher_sha256'])


def payload_valid(path,expected):
    return path.is_file() and not path.is_symlink() and sha(path)==expected


def promote(staging,work,receipt,payload_sha):
    """Reuse exact copies; preserve incomplete previous transfers, never overwrite."""
    private_directory(staging)
    allowed={'archive.cms','windows-decrypted-payload.tar','archive-receipt.json'}
    if not set(p.name for p in staging.iterdir())<=allowed:raise ValueError('Unexpected staged file; preserve for review')
    for path in staging.iterdir():
        if not path.is_file() or path.is_symlink() or path.stat().st_uid!=os.geteuid():raise ValueError('Private regular staged files required')
        path.chmod(0o600)
    if load(staging/'archive-receipt.json')!=receipt:raise ValueError('Staged receipt differs from original archive')
    root=work/'archives'
    if root.exists():private_directory(root)
    else:root.mkdir(mode=0o700)
    target=root/receipt['archive_id']
    if not target_valid(target,receipt):
        source=staging/'archive.cms'
        if not source.is_file() or sha(source)!=receipt['cipher_sha256']:raise ValueError('Complete verified ciphertext transfer required')
        if target.exists():
            if target.is_symlink() or not target.is_dir() or target.stat().st_uid!=os.geteuid():raise ValueError('Unexpected archive destination')
            if not set(p.name for p in target.iterdir())<={'archive.cms','receipt.json'}:raise ValueError('Unreviewed archive directory; do not move it')
            target.rename(root/('preserved-incomplete-transfer-'+uuid.uuid4().hex))
        target.mkdir(mode=0o700)
        source.rename(target/'archive.cms')
        (staging/'archive-receipt.json').rename(target/'receipt.json')
        for p in target.iterdir():p.chmod(0o400)
        target.chmod(0o500)
    cache=work/'windows-decrypted-payload.tar'
    if not payload_valid(cache,payload_sha):
        source=staging/'windows-decrypted-payload.tar'
        if not source.is_file() or sha(source)!=payload_sha:raise ValueError('Complete verified plaintext transfer required')
        if cache.exists() or cache.is_symlink():
            if not cache.is_file() or cache.is_symlink() or cache.stat().st_uid!=os.geteuid():raise ValueError('Unexpected previous plaintext transfer')
            cache.rename(work/('preserved-incomplete-payload-'+uuid.uuid4().hex+'.tar'))
        source.rename(cache)
    cache.chmod(0o600)


def main(args):
    global ACTIVE_WORKER
    work=Path(args.work)
    if work!=WORK:raise ValueError('Only original bounded operator job accepted')
    private_directory(work);no_running_job(work)
    if not re.fullmatch(r'prepare-from-pc-[a-f0-9]{32}\.py',args.worker):raise ValueError('Expected existing PC-restore worker')
    if not re.fullmatch(r'resume-transfer-[a-f0-9]{32}',args.stage):raise ValueError('Dedicated transfer staging directory required')
    for value in (args.worker_sha,args.review_sha,args.payload_sha):
        if not re.fullmatch(r'[a-f0-9]{64}',value):raise ValueError('Invalid expected checksum')
    worker=work/args.worker
    if worker.is_symlink() or sha(worker)!=args.worker_sha:raise ValueError('Existing final worker does not match reviewed source')
    receipt=load(work/'archive-receipt.json');review=load(work/'local-restore-review.json');proof=load(work/'windows-decryption-proof.json')
    if (review.get('review_sha256')!=args.review_sha or proof.get('payload_tar_sha256')!=args.payload_sha
        or proof.get('archive_id')!=receipt.get('archive_id') or proof.get('cipher_sha256')!=receipt.get('cipher_sha256')
        or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}',receipt.get('archive_id',''))):raise ValueError('Original Windows restore context changed')
    for name in ('restore','restore-result.json','preparation-attempt.json','prepared.json','final-result.json','transfer-final-claim.json'):
        if (work/name).exists() or (work/name).is_symlink():raise ValueError('Later or claimed preparation state exists; never replay')
    module=runpy.run_path(str(worker),run_name='verified_transfer_worker')
    ACTIVE_WORKER=module
    module['main'](argparse.Namespace(action='check-context',work=str(work)))
    staging=work/args.stage
    if args.mode=='stage':
        staging.mkdir(mode=0o700)  # exclusive: never overwrite an uncertain transfer
        result=dict(status='VERIFIED_RESTORE_TRANSFER_READY',cipher_copy_verified=target_valid(work/'archives'/receipt['archive_id'],receipt),
                    payload_copy_verified=payload_valid(work/'windows-decrypted-payload.tar',args.payload_sha),accounts_activated=False)
        print(json.dumps(result),flush=True);return
    promote(staging,work,receipt,args.payload_sha)
    # Atomic claim prevents concurrent finalization and any later blind rerun.
    with (work/'transfer-final-claim.json').open('x',encoding='utf-8') as f:
        json.dump(dict(stage=args.stage,review_sha256=args.review_sha),f)
    module['main'](argparse.Namespace(action='prepare',work=str(work)))
    names=('final-result.json','restore-result.json','prepared.json','account-settings-for-review.json','inventory.json','config.json')
    bundle=work/(args.stage+'-receipts.zip')
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_STORED) as z:
        for name in names:
            path=work/name
            if path.is_symlink() or not path.is_file() or path.stat().st_size>4*1024**2:raise ValueError('Unexpected final receipt')
            z.write(path,arcname=name)
    module['main'](argparse.Namespace(action='cleanup-transfer',work=str(work)))
    for p in staging.iterdir():p.unlink()  # only our validated transfer cache, never a sealed archive
    staging.rmdir()
    print(json.dumps(dict(status='THREE_INACTIVE_DRAFTS_PREPARED_RECEIPTS_READY',receipt_bundle=bundle.name,accounts_activated=False)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('mode','work','worker','stage','worker-sha','review-sha','payload-sha'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    if args.mode not in ('stage','finalize'):raise SystemExit('Invalid transfer mode')
    resource.setrlimit(resource.RLIMIT_AS,(1152*1024**2,)*2)
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(30):print('Arbeider fortsatt med verifisering/klargjoring; ikke start en ny kjoring.',flush=True)
    threading.Thread(target=heartbeat,daemon=True).start()
    try:main(args);stop.set()
    except Exception as error:
        stop.set()
        details=(ACTIVE_WORKER['sanitized_failure'](error) if ACTIVE_WORKER else dict(error_type=type(error).__name__,
            reason=str(error) if type(error) is ValueError else 'Transfer/finalization stopped; inspect private status before any replay'))
        result=dict(status='TRANSFER_RESUME_STOPPED',mode=args.mode,accounts_activated=False,**details)
        try:
            if WORK.is_dir():
                private_directory(WORK)
                with (WORK/('STOPPED-transfer-resume-'+uuid.uuid4().hex+'.json')).open('x') as f:json.dump(result,f)
        except Exception:pass
        print(json.dumps(result),flush=True);raise SystemExit(1)
