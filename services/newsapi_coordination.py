"""Small credential-scoped source records; never financial documents."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from services.storage_service import get_storage_service

MAX_CACHE_BYTES=512*1024
MAX_CACHE_ROWS=400

class CoordinationBusy(RuntimeError):pass
class CoordinationUnavailable(RuntimeError):pass

class PostgresCoordination:
    shared=True
    def __init__(self,conn,credential,*,read_only=False):
        self.conn=conn;self.read_only=read_only
        namespace=hashlib.sha256(credential.encode()).hexdigest()
        self.state_key='source_budgets/newsapi/'+namespace+'.json'
        self.cache_prefix='source_cache/newsapi/'+namespace+'/'
    def read(self,name):
        try:return self._read(name)
        except Exception as exc:raise CoordinationUnavailable("Source record read failed") from exc
    def _read(self,name):
        with self.conn.cursor() as cur:
            cur.execute('SELECT CASE WHEN octet_length(payload)<=%s THEN payload ELSE NULL END FROM app_kv_store WHERE name=%s',(MAX_CACHE_BYTES,name));row=cur.fetchone()
        self.conn.commit()
        if not row:return None
        if row[0] is None:raise CoordinationUnavailable("Source record exceeds read bound")
        value=json.loads(row[0])
        if not isinstance(value,dict):raise CoordinationUnavailable('Invalid source coordination record')
        return value
    def write(self,name,value):
        try:self._write(name,value)
        except Exception as exc:raise CoordinationUnavailable("Source record write failed") from exc
    def _write(self,name,value):
        payload=json.dumps(value,separators=(',',':'),ensure_ascii=True)
        if len(payload)>MAX_CACHE_BYTES:raise CoordinationUnavailable('Source record exceeds storage bound')
        with self.conn.cursor() as cur:
            cur.execute('INSERT INTO app_kv_store(name,payload,updated_at) VALUES(%s,%s,NOW()::text) ON CONFLICT(name) DO UPDATE SET payload=EXCLUDED.payload,updated_at=EXCLUDED.updated_at',(name,payload))
        self.conn.commit()
    def get_state(self):return self.read(self.state_key)
    def set_state(self,value):self.write(self.state_key,value)
    def get_cache(self,key):return self.read(self.cache_prefix+key+'.json')
    def set_cache(self,key,value):
        # Oversized results may be used by the current caller, never retained.
        if len(json.dumps(value,ensure_ascii=True))>MAX_CACHE_BYTES:return
        self.write(self.cache_prefix+key+'.json',value)
        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM app_kv_store WHERE name IN (SELECT name FROM app_kv_store WHERE name >= %s AND name < %s ORDER BY updated_at DESC,name DESC OFFSET %s LIMIT 100)',(self.cache_prefix,self.cache_prefix+'z',MAX_CACHE_ROWS))
        self.conn.commit()

@contextmanager
def coordinated(state_path,credential,*,read_only=False):
    storage=get_storage_service()
    if storage.using_postgres():
        conn=None
        try:
            try:
                storage.init_db();conn=storage._conn()
                if not read_only:
                    with conn.cursor() as cur:
                        cur.execute("SET lock_timeout='2s'")
                        cur.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))',('source:newsapi:'+hashlib.sha256(credential.encode()).hexdigest(),))
                        acquired=cur.fetchone()[0]
                    conn.commit()
                    if not acquired:raise CoordinationBusy('Another source request is active')
            except CoordinationBusy:raise
            except Exception as exc:raise CoordinationUnavailable('Source coordination setup failed') from exc
            yield PostgresCoordination(conn,credential,read_only=read_only)
        finally:
            if conn is not None:conn.close()
    else:
        if storage.database_url or storage.mode=="postgres" or not storage._local_allowed():raise CoordinationUnavailable('Authoritative source coordination is unavailable')
        state_path.parent.mkdir(parents=True,exist_ok=True)
        with state_path.with_suffix('.lock').open('a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX)
            try:yield None
            finally:fcntl.flock(handle,fcntl.LOCK_UN)
