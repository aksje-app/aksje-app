"""Independent, bounded report-delivery observation. Never runs a report/trade."""
from contextlib import contextmanager
from datetime import datetime
import json
import os
import re
import threading
from zoneinfo import ZoneInfo

_ALERT_LOCK_ID = 19343502
_ALERT_LOCK = threading.Lock()
_RECEIPT_KEY = 'scheduler/required_report_missing_alerts.json'


def _configure(conn):
    with conn.cursor() as cur:
        cur.execute('SET statement_timeout=5000')
        cur.execute('SET lock_timeout=1000')


def read_bounded_json(key, *, connection, limit=1048576, default=None):
    with connection.cursor() as cur:
        cur.execute('SELECT CASE WHEN octet_length(payload)<=%s THEN payload END FROM app_kv_store WHERE name=%s',(limit,key))
        row=cur.fetchone()
    if row is None:return default
    if row[0] is None:raise ValueError('Operational document exceeds its read bound')
    return json.loads(row[0])


def write_operational_json(key,value,*,connection):
    if key not in {_RECEIPT_KEY,'scheduler/required_report_watchdog.json'}:raise ValueError('Explicit operational key required')
    raw=json.dumps(value,ensure_ascii=True)
    if len(raw)>1048576:raise ValueError('Operational receipt exceeds its bound')
    with connection.cursor() as cur:
        cur.execute('INSERT INTO app_kv_store(name,payload,updated_at) VALUES(%s,%s,NOW()::text) ON CONFLICT(name) DO UPDATE SET payload=EXCLUDED.payload,updated_at=EXCLUDED.updated_at',(key,raw))


def read_alert_receipts(connection):
    current=read_bounded_json(_RECEIPT_KEY,connection=connection)
    if current is not None:
        if not isinstance(current,dict):raise ValueError('Invalid alert receipt document')
        return current
    # Migrate only this small legacy projection, never read/modify/write the
    # whole configuration document outside its normal coordination lane.
    with connection.cursor() as cur:
        cur.execute("SELECT CASE WHEN octet_length(payload)<=16777216 THEN payload::json#>'{sections,legacy,scheduler,required_report_missing_alerts,json}' ELSE '\"OVERSIZED\"'::json END FROM app_kv_store WHERE name='configuration/framework.json'")
        row=cur.fetchone()
    legacy=row[0] if row and row[0] is not None else {}
    if not isinstance(legacy,dict):raise ValueError('Invalid or oversized legacy alert receipts')
    write_operational_json(_RECEIPT_KEY,legacy,connection=connection)
    return legacy


def _time(value):
    try:
        result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return result if result.tzinfo else None
    except (TypeError,ValueError):return None


def same_slot(row,owner):
    planned,scheduled=_time(row.get('planned_at')),_time(owner.get('scheduled_for'))
    return bool(row.get('job_id') and row.get('job_id')==owner.get('job_id') and planned and scheduled and planned==scheduled)


@contextmanager
def alert_lane():
    """Serialize warning deduplication independently of the heavy/financial lane."""
    conn=None;acquired=False
    try:
        if os.getenv('DATABASE_URL','').strip():
            import psycopg2
            conn=psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=5)
            conn.autocommit=True
            _configure(conn)
            with conn.cursor() as cur:
                cur.execute('SELECT pg_try_advisory_lock(%s)',(_ALERT_LOCK_ID,))
                acquired=bool(cur.fetchone()[0])
        else:acquired=_ALERT_LOCK.acquire(blocking=False)
        yield conn if acquired and conn is not None else acquired
    finally:
        if conn is not None:conn.close()
        elif acquired:_ALERT_LOCK.release()


def observe_owner(*,owner=None,connect=None,connection=None):
    """A persisted ACTIVE flag is diagnostic data, never proof of a live worker.

    One native query observes the small owner row and actual report lock. A
    database error is UNKNOWN, not proof that a real report process has died.
    No lock is acquired/released and no financial or owner row is written.
    """
    from execution_coordination import _LOCAL_LOCK,_OWNER_KEY,_OWNER_PATH,_REPORT_EXECUTION_LOCK_ID
    previous=dict(owner or {})
    if not connect and connection is None and not os.getenv('DATABASE_URL','').strip():
        try:
            if owner is None and _OWNER_PATH.is_file():
                if _OWNER_PATH.stat().st_size>16384:raise ValueError('Oversized local owner')
                previous=json.loads(_OWNER_PATH.read_text())
            return {'state':'LIVE' if _LOCAL_LOCK.locked() else 'ORPHANED' if previous.get('state')=='ACTIVE' else 'INACTIVE','owner':previous}
        except Exception as exc:return {'state':'UNKNOWN','owner':{},'error_type':type(exc).__name__}
    conn=None
    try:
        if connection is not None:conn=connection
        elif connect:conn=connect()
        else:
            import psycopg2
            conn=psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=5)
        if connection is None:conn.set_session(readonly=True)
        _configure(conn)
        with conn.cursor() as cur:
            cur.execute("""SELECT (SELECT CASE WHEN octet_length(payload)<=16384 THEN payload END
                    FROM app_kv_store WHERE name=%s),
                (SELECT octet_length(payload) FROM app_kv_store WHERE name=%s),
                EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND granted
                  AND classid=0 AND objid=%s AND objsubid=1
                  AND database=(SELECT oid FROM pg_database WHERE datname=current_database()))
                """,(_OWNER_KEY,_OWNER_KEY,_REPORT_EXECUTION_LOCK_ID))
            row=cur.fetchone()
        if row[1] is None:
            return {'state':'UNKNOWN' if row[2] else 'INACTIVE','owner':{}}
        if row[0] is None:raise ValueError('Oversized report owner')
        current=json.loads(row[0])
        if not isinstance(current,dict):raise ValueError('Invalid report owner')
        state='LIVE' if row[2] else 'ORPHANED' if current.get('state')=='ACTIVE' else 'INACTIVE'
        return {'state':state,'owner':current}
    except Exception as exc:
        return {'state':'UNKNOWN','owner':previous,'error_type':type(exc).__name__}
    finally:
        if conn is not None and connection is None:conn.close()


def _read_trace(trace_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,96}',str(trace_id)):return {}
    key='operations/run_traces/'+trace_id+'.json'
    if os.getenv('DATABASE_URL','').strip():
        import psycopg2
        conn=psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=5)
        try:
            conn.set_session(readonly=True);_configure(conn)
            return read_bounded_json(key,connection=conn,limit=65536,default={})
        finally:conn.close()
    from operational_telemetry import _trace_path
    path=_trace_path(trace_id)
    return json.loads(path.read_text()) if path.is_file() and path.stat().st_size<=65536 else {}



def failure_detail(row,observation,*,read_trace=None):
    from runtime_env import redact_secrets
    if row.get('error'):return redact_secrets(str(row['error']))[:450]
    owner=observation.get('owner') or {}
    match=same_slot(row,owner)
    trace={}
    if match and owner.get('trace_id'):
        try:trace=(read_trace or _read_trace)(owner['trace_id']) or {}
        except Exception:trace={}
    if not isinstance(trace,dict) or not isinstance(trace.get('metadata'),dict) or trace.get('job_id')!=row.get('job_id') or not same_slot(row,{'job_id':trace.get('job_id'),'scheduled_for':(trace.get('metadata') or {}).get('scheduled_for')}):trace={}
    if trace.get('error'):return redact_secrets(str(trace['error']))[:450]
    if match and observation.get('state')=='ORPHANED':
        message='Rapportens registrerte kjørelås er ikke lenger holdt. Ingen ferdigkvittering.'
    else:message='Rapporten mangler ferdig- og leveringskvittering.'
    stage=trace.get('current_stage') or (owner.get('stage') if match else None)
    if stage:message+=' Siste fase: '+str(stage)[:80]+'.'
    heartbeat=_time(owner.get('heartbeat_at')) if match else None
    if heartbeat:message+=' Siste livstegn: '+heartbeat.astimezone(ZoneInfo('Europe/Oslo')).strftime('%d.%m.%Y %H:%M:%S')+' (Europe/Oslo).'
    message+=' Stoppårsaken er ikke lagret; kontroller Render-loggen.'
    return redact_secrets(message)[:450]


def run_startup_check():
    """Runs before the heavy execution lane, including DEFERRED_BUSY cycles."""
    from datetime import timezone
    if os.getenv('APP_ENVIRONMENT','production').lower()=='production' and not os.getenv('DATABASE_URL','').strip():
        return {'state':'DEFERRED_DATABASE','financial_state_changed':False}
    try:
        from market_intelligence import notify_overdue_required_reports
        result=notify_overdue_required_reports()
        small={'state':result.get('state','COMPLETED'),'checked_at':datetime.now(timezone.utc).isoformat(),
               'overdue':result.get('overdue',0),'alerts_sent':result.get('alerts_sent',[]),
               'owner_observation':result.get('owner_observation',{}).get('state','UNKNOWN'),
               'financial_state_changed':False, 'deployed_commit':os.getenv('RENDER_GIT_COMMIT','unknown')}
    except Exception as exc:
        small={'state':'UNAVAILABLE','checked_at':datetime.now(timezone.utc).isoformat(),
               'error_type':type(exc).__name__,'financial_state_changed':False}
    try:
        if os.getenv('DATABASE_URL','').strip():
            import psycopg2
            conn=psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=5)
            try:
                conn.autocommit=True;_configure(conn)
                write_operational_json('scheduler/required_report_watchdog.json',small,connection=conn)
            finally:conn.close()
    except Exception:pass
    return small
