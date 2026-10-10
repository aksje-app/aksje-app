"""Truthful shared progress: unknown totals stay unknown; completion is explicit."""
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
import time
from functools import wraps
from contextvars import ContextVar
_active=ContextVar('work_progress_active',default=None)


def report_progress(completed,total,phase):
    row=_active.get()
    if row is None:return
    row.update(completed=completed,total=total,phase=phase,last_progress_at=datetime.now(timezone.utc).isoformat())
    if time.monotonic()-row.get('_last_write',0)>=2:
        row['_last_write']=time.monotonic();row['updated_at']=row['last_progress_at'];_save(row)


class JobBar:
    def __init__(self,st,label):
        now=datetime.now(timezone.utc).isoformat()
        self.row={'id':uuid4().hex,'label':label,'state':'RUNNING','phase':label,'percent':0,'started_at':now,'updated_at':now}
        self.bar=st.progress(0,text=label);self.last_write=0;_save(self.row)
    def progress(self,value,text=None):
        percent=int(value*100) if isinstance(value,float) and value<=1 else int(value)
        state='FAILED' if 'feilet' in str(text).lower() else 'INTERRUPTED' if 'avbrutt' in str(text).lower() else 'COMPLETED' if percent>=100 else 'RUNNING'
        self.row.update(state=state,phase=text or self.row['phase'],percent=min(99,percent) if state!='COMPLETED' else 100,
            updated_at=datetime.now(timezone.utc).isoformat(),last_progress_at=datetime.now(timezone.utc).isoformat())
        if time.monotonic()-self.last_write>=2 or state!='RUNNING':
            _save(self.row);self.last_write=time.monotonic()
        self.bar.progress(self.row['percent'],text=text);return self


def job_bar(st,text):return JobBar(st,text)


def progress_values(state, completed=None, total=None, percent=None):
    state=str(state or 'IDLE').upper()
    if state=='COMPLETED': return 100
    try:
        if percent is not None: return max(0,min(99,int(float(percent))))
        if total and float(total)>0 and completed is not None:
            return max(0,min(99,int(float(completed)/float(total)*100)))
    except (ValueError, TypeError, OverflowError): pass
    return None


def render_progress(st, status):
    state=status.get('state','IDLE');label=status.get('label') or status.get('job_name') or 'Arbeid'
    phase=status.get('phase') or status.get('active_stage') or state
    pct=progress_values(state,status.get('completed'),status.get('total'),status.get('percent'))
    text=f'{label} · {phase}'
    if status.get('total'): text+=f" · {status.get('completed',0)} av {status['total']}"
    if pct is not None: st.progress(pct,text=text)
    else: st.caption(text+' · total fremdrift er ikke kjent')
    if status.get('message'): st.caption(status['message'])
    if status.get('started_at'):
        try:
            start=datetime.fromisoformat(status['started_at']).replace(tzinfo=timezone.utc) if '+' not in status['started_at'] else datetime.fromisoformat(status['started_at'])
            end=datetime.fromisoformat(status['updated_at']) if state not in ('RUNNING','QUEUED') and status.get('updated_at') else datetime.now(timezone.utc)
            st.caption(f"Tidsbruk: {max(0,int((end-start).total_seconds()))} sekunder")
        except (ValueError, TypeError): pass
    if status.get('last_progress_at'):st.caption('Siste fremdrift: '+status['last_progress_at'])
    if status.get('checked_at'):st.caption('Siste forsøk: '+status['checked_at'])
    if status.get('error'):st.warning(status['error'])


def _save(record):
    """Status failures must never interrupt the underlying job."""
    try:
        from services.storage_service import get_storage_service
        def update(old):
            old=dict(old or {});old[record['id']]=record
            return dict(sorted(old.items(),key=lambda pair:pair[1].get('updated_at',''))[-40:])
        get_storage_service().mutate_json('work_progress/recent.json',update,{})
    except Exception: pass


@contextmanager
def work_status(st, label, **kwargs):
    """Wrap synchronous waits without inventing a percentage or rerunning work."""
    now=datetime.now(timezone.utc).isoformat()
    record={'id':uuid4().hex,'label':label,'state':'RUNNING','phase':'ARBEIDER',
            'started_at':now,'updated_at':now,'last_progress_at':now}
    _save(record);started=time.monotonic()
    try:
        with st.status(label+' · arbeider',state='running',expanded=True) as box:
            st.caption('Total fremdrift er ikke kjent. Resultatet vises når dette steget er ferdig.')
            try:yield
            except BaseException:
                box.update(label=label+' · avbrutt eller feilet',state='error');raise
            else:box.update(label=label+' · steg ferdig',state='complete')
    except BaseException as exc:
        failed=isinstance(exc,Exception)
        record.update(state='FAILED' if failed else 'INTERRUPTED',phase='FEILET' if failed else 'AVBRUTT',error=type(exc).__name__)
        raise
    else:record.update(state='COMPLETED',phase='STEG FERDIG',percent=100)
    finally:
        record.update(updated_at=datetime.now(timezone.utc).isoformat(),seconds=round(time.monotonic()-started,2))
        _save(record)


def render_recent_work(st):
    from services.storage_service import get_storage_service
    rows=get_storage_service().read_json('work_progress/recent.json',{}) or {}
    if rows:
        with st.expander('Arbeid og ventestatus'):
            for row in sorted(rows.values(),key=lambda r:r.get('updated_at',''),reverse=True)[:8]:
                # Persisted RUNNING means last known state, not a claim that a
                # browser worker survived disconnect. Never silently mark it done.
                if row.get('state')=='RUNNING': row={**row,'message':'Sist registrert som aktiv. Ingen bekreftet sluttstatus ennå.'}
                render_progress(st,row)


def render_live_work(st):
    """Read status only. The fragment never starts or reconciles workers."""
    from services.storage_service import get_storage_service
    storage=get_storage_service()
    statuses=[]
    for key,label in (('super_portfolio/job_status.json','Superportefølje'),('superfund/job.json','Superfond'),('paper_trading/scanner_status.json','Paper / Autonomi-skanning')):
        row=storage.read_json(key,{}) or {}
        if row.get('state') in ('RUNNING','QUEUED','PARTIAL','PARTIAL_CHECKPOINT','PAUSED','DEFERRED_CAPACITY','DEFERRED_BUSY'):
            if label=='Superfond':
                index=storage.read_json('superfund/catalog_index.json',{}) or {}
                total=sum(max(1,(int(v)+99)//100) for v in index.get('totals',{}).values()) if len(index.get('totals',{}))==2 else None
                row={**row,'completed':len(index.get('pages',{})),'total':total}
            if label=='Paper / Autonomi-skanning':
                row={**row,'completed':row.get('tickers_processed'),'total':row.get('tickers_total'),'phase':row.get('current_ticker') or row.get('state')}
            statuses.append({**row,'label':label})
    manual=storage.read_json('manual_background_jobs/active.json',{}) or {}
    if manual.get('state') in ('QUEUED','RUNNING','STOP_REQUESTED') and manual.get('execution_id'):
        row=storage.read_json('manual_background_jobs/runs/'+manual['execution_id']+'.json',{}) or {}
        statuses.append({**row,'label':row.get('job_name','Rapport / analyse')})
    rows=storage.read_json('work_progress/recent.json',{}) or {}
    active=[r for r in rows.values() if r.get('state')=='RUNNING'][-6:]
    if statuses or active:
        with st.expander('Pågående arbeid og ventestatus',expanded=True):
            for row in statuses+active:render_progress(st,row)
    render_recent_work(st)


def tracked_job(label):
    """Background jobs publish last known activity without a second execution."""
    def decorate(fn):
        @wraps(fn)
        def call(*args,**kwargs):
            now=datetime.now(timezone.utc).isoformat()
            row={'id':uuid4().hex,'label':label,'state':'RUNNING','phase':'ARBEIDER',
                 'started_at':now,'last_progress_at':now,'updated_at':now}
            token=_active.set(row)
            _save(row)
            try:
                result=fn(*args,**kwargs)
                state=str((result.get('state') or result.get('status') or 'COMPLETED') if isinstance(result,dict) else 'COMPLETED').upper()
                if isinstance(result,dict) and result.get('interrupted'):state='INTERRUPTED'
                row.update(state=state,phase=state,
                    message=result.get('message','') if isinstance(result,dict) else '',
                    error=result.get('error','') if isinstance(result,dict) else '')
                return result
            except BaseException as exc:
                row.update(state='FAILED',phase='FEILET',error=type(exc).__name__);raise
            finally:
                row['updated_at']=datetime.now(timezone.utc).isoformat();_save(row);_active.reset(token)
        return call
    return decorate
