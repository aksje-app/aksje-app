"""Read-only reconciliation after lost SSH. No restart, cleanup or account write."""
import json
import os
from pathlib import Path
import sys

WORK = Path('/tmp/nok-job-20261024T165039Z')
CHECKPOINTS = ('archive-receipt.json','windows-copy-proof.json','windows-decryption-proof.json',
    'windows-decrypted-payload.tar','restore/restore-review.json','restore-result.json',
    'preparation-attempt.json','prepared.json','final-result.json','isolated-pg/postmaster.pid')


def read_json(path):
    if path.is_symlink() or path.stat().st_size > 2*1024**2:
        raise ValueError('Unexpected metadata file')
    with path.open(encoding='utf-8-sig') as stream:
        return json.load(stream)


def processes(work):
    found = []
    complete = True
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.geteuid():
                continue
            arguments = (entry / 'cmdline').read_bytes().split(b'\0')
            scoped = [arg.decode('utf-8','replace') for arg in arguments
                      if arg == str(work).encode() or arg.startswith((str(work)+'/').encode())]
            if scoped:
                action = next((a.decode() for a in arguments if a in
                    (b'restore-drafts',b'fingerprint-readonly',b'cleanup')), None)
                found.append(dict(pid=int(entry.name),kind=action or 'private_job_process'))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            complete = False
    return found, complete


def account_metadata(dsn):
    import psycopg2
    connection = psycopg2.connect(dsn,connect_timeout=10,
        options='-c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=2000',
        application_name='aksje_readonly_restore_reconciliation')
    try:
        connection.set_session(readonly=True,isolation_level='REPEATABLE READ',autocommit=False)
        with connection.cursor() as q:
            q.execute("SELECT current_setting('transaction_read_only'),pg_postmaster_start_time()::text")
            mode, started = q.fetchone()
            if mode != 'on':raise ValueError('Read-only connection required')
            q.execute("SELECT name FROM public.app_kv_store WHERE name LIKE %s ORDER BY name DESC LIMIT 21",
                      ('simulation_restarts/nok-%/bundle.json',))
            names = [row[0] for row in q.fetchall()]
            result = dict(server_started_at=started,periods=[],more_than_20_periods=len(names)>20,routes=[])
            for name in names[:20]:
                q.execute('SELECT payload FROM public.app_kv_store WHERE name=%s AND octet_length(payload)<=524288 LIMIT 1',(name,))
                row=q.fetchone()
                if row is None:
                    result['periods'].append(dict(key=name,metadata_not_loaded=True));continue
                bundle=json.loads(row[0])
                result['periods'].append(dict(period_id=bundle.get('period_id'),status=bundle.get('status'),
                    account_statuses={family:account.get('status') for family,account in bundle.get('accounts',{}).items()}))
            for family in ('paper','autonomy','super_portfolio'):
                q.execute('SELECT payload FROM public.app_kv_store WHERE name=%s AND octet_length(payload)<=8192 LIMIT 1',
                          ('simulation_restarts/routes/'+family+'.json',))
                row=q.fetchone()
                if row:
                    route=json.loads(row[0])
                    result['routes'].append(dict(family=family,period_id=route.get('period_id'),status=route.get('status')))
            return result
    finally:
        try:connection.rollback()
        finally:connection.close()


def inspect(work=WORK):
    result=dict(status='READ_ONLY_RESTORE_STATUS',job_exists=work.is_dir(),
                remote_actions_performed=False,account_mutations_performed=False)
    active, complete = processes(work)
    result.update(job_processes=active,process_scan_complete=complete)
    group=Path('/sys/fs/cgroup')
    result['container_memory']={}
    for name in ('memory.max','memory.current','memory.events'):
        try:result['container_memory'][name]=(group/name).read_text().strip()
        except OSError:pass
    result['container_memory_note']='Current-container counters only; do not prove the cause of the prior SSH closure'
    if work.exists():
        if work.is_symlink() or work.stat().st_uid != os.geteuid() or work.stat().st_mode & 0o077:
            raise ValueError('Expected private operator job required')
        result['checkpoints']={name:(work/name).exists() for name in CHECKPOINTS}
        for filename in ('final-result.json','restore-result.json','prepared.json','preparation-attempt.json'):
            path=work/filename
            if path.is_file():
                doc=read_json(path)
                result[filename]={key:doc[key] for key in ('status','period_id','accounts_activated','approval_B_ready') if key in doc}
                if filename=='prepared.json':
                    result[filename]['account_statuses']={family:a.get('status') for family,a in doc.get('accounts',{}).items()}
        failed=sorted(work.glob('STOPPED-restore-drafts*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        if failed:
            doc=read_json(failed[0]);result['latest_failure']={k:doc.get(k) for k in ('stage','error_type','sqlstate')}
        log=work/'isolated-pg.log'
        if log.is_file() and not log.is_symlink():
            with log.open('rb') as stream:
                stream.seek(max(0,log.stat().st_size-262144));tail=stream.read().lower()
            result['isolated_pg_log_flags']={key:pattern in tail for key,pattern in
                (('out_of_memory',b'out of memory'),('signal9',b'terminated by signal 9'),('system_shut_down',b'database system is shut down'))}
    if active or not complete:
        result['source_metadata']='Not queried while private job may still be running'
    elif os.getenv('DATABASE_URL'):
        try:result['source_metadata']=account_metadata(os.environ['DATABASE_URL'])
        except Exception as error:
            result['source_metadata']=dict(error_type=type(error).__name__,sqlstate=getattr(error,'pgcode',None))
    else:
        result['source_metadata']='DATABASE_URL not available; no fallback attempted'
    return result


if __name__=='__main__':
    try:print(json.dumps(inspect(),indent=2))
    except Exception as error:
        print(json.dumps(dict(status='READ_ONLY_STATUS_FAILED',error_type=type(error).__name__,remote_actions_performed=False)))
        raise SystemExit(1)
