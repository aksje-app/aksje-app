"""Preserve application history; reclaim obsolete MVCC space and expired access tokens.

No financial, report, learning, repository, JSONL or archive row is deleted.
VACUUM makes old PostgreSQL row versions reusable; it is not VACUUM FULL.
"""
from datetime import datetime,timedelta,timezone
import time
from services.storage_service import get_storage_service

POLICY='PRESERVE_ALL_HISTORY'
LOCK_ID=19343502
TABLES=('app_kv_store','app_jsonl_store','app_auth_sessions','app_remember_tokens')


def run(*,storage=None,now=None):
    storage=storage or get_storage_service()
    if not storage.using_postgres() or storage.allow_local_fallback:
        raise ValueError('Safe production maintenance requires authoritative PostgreSQL')
    now=now or datetime.now(timezone.utc);started=time.monotonic()
    result={'policy':POLICY,'historical_deletion_enabled':False,'state':'RUNNING',
        'started_at':now.isoformat(timespec='seconds'),'deleted_access_tokens':{},'vacuum':{},'autovacuum':{},
        'access_token_batch_limit':500,'statement_timeout_seconds':90,'maintenance_memory_mb':16}
    conn=storage._conn();conn.autocommit=True
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(%s)',(LOCK_ID,))
            if not cur.fetchone()[0]:
                return {**result,'state':'DEFERRED_BUSY','completed_at':datetime.now(timezone.utc).isoformat()}
            cur.execute("SET lock_timeout='2s'")
            cur.execute("SET statement_timeout='90s'")
            cur.execute("SET maintenance_work_mem='16MB'")
            cur.execute("SET vacuum_cost_delay='5ms'")
            cur.execute('SET vacuum_cost_limit=1000')
            cutoff=now-timedelta(days=7)
            for table,identity in (('app_auth_sessions','token_hash'),('app_remember_tokens','token')):
                cur.execute('SELECT to_regclass(%s)',(table,))
                if cur.fetchone()[0] is None:continue
                # Expiry strings are legacy ISO timestamps, sometimes naive.
                # Validate each bounded candidate before removal; malformed and
                # currently valid tokens are retained. Never log token values.
                cur.execute(f'SELECT {identity},expires FROM {table} WHERE expires<%s ORDER BY expires LIMIT 500',
                    (cutoff.isoformat(timespec='seconds'),))
                expired=[]
                for token,raw in cur.fetchall():
                    try:
                        at=datetime.fromisoformat(str(raw).replace('Z','+00:00'))
                        if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)
                        if at<cutoff:expired.append((token,raw))
                    except (ValueError,TypeError):continue
                deleted=0
                for token,raw in expired:
                    # Compare original expiry too: a concurrently renewed token survives.
                    cur.execute(f'DELETE FROM {table} WHERE {identity}=%s AND expires=%s',(token,raw))
                    deleted+=cur.rowcount
                result['deleted_access_tokens'][table]=deleted
            for table in TABLES:
                cur.execute('SELECT to_regclass(%s)',(table,))
                if cur.fetchone()[0] is None:continue
                try:
                    if table in ('app_kv_store','app_jsonl_store'):
                        cur.execute('SELECT reloptions FROM pg_class WHERE oid=%s::regclass',(table,))
                        before=cur.fetchone()[0]
                        cur.execute(f'ALTER TABLE {table} SET (autovacuum_vacuum_scale_factor=0.02, autovacuum_vacuum_threshold=200, autovacuum_analyze_scale_factor=0.02, autovacuum_analyze_threshold=200, toast.autovacuum_vacuum_scale_factor=0.02, toast.autovacuum_vacuum_threshold=1000)')
                        result['autovacuum'][table]={'state':'CONFIGURED','previous_options':before,
                            'scale_factor':0.02,'toast_threshold':1000}
                    cur.execute(f'VACUUM (ANALYZE, TRUNCATE FALSE) {table}')
                    result['vacuum'][table]={'state':'COMPLETED'}
                except Exception as exc:
                    result['vacuum'][table]={'state':'FAILED','error_type':type(exc).__name__}
            result['state']='PARTIAL' if any(v['state']=='FAILED' for v in result['vacuum'].values()) else 'COMPLETED'
            cur.execute("SELECT relname,n_live_tup,n_dead_tup,last_vacuum,last_analyze FROM pg_stat_user_tables WHERE relname=ANY(%s)",(list(TABLES),))
            result['relations']=[dict(table=r[0],estimated_live_rows=r[1],estimated_dead_rows=r[2],last_vacuum=str(r[3]),last_analyze=str(r[4])) for r in cur.fetchall()]
    finally:
        conn.close()  # releases advisory lock on every exit
    result.update(completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),seconds=round(time.monotonic()-started,3))
    return result


def receipt_ok(retention,*,now=None):
    """An enabled flag alone is never evidence that housekeeping completed."""
    safe=retention.get('safe_maintenance') or {}
    if (safe.get('state')!='COMPLETED' or retention.get('historical_deletion_enabled') is not False
            or retention.get('apply_scope')!='EXPIRED_ACCESS_TOKENS_AND_ONLINE_VACUUM'):
        return False
    if any((safe.get('vacuum',{}).get(t) or {}).get('state')!='COMPLETED' for t in TABLES[:2]):
        return False
    try:
        completed=datetime.fromisoformat(safe['completed_at'].replace('Z','+00:00'))
        age=((now or datetime.now(timezone.utc))-completed).total_seconds()
        return 0<=age<=48*3600
    except (KeyError,TypeError,ValueError):
        return False
