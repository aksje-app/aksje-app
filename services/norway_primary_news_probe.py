"""One bounded source-only acceptance probe in the existing cron invocation."""
from datetime import datetime,timedelta,timezone
import os,re
from runtime_identity import current_runtime_identity
from services.norway_primary_news import fetch_company_news,SCHEMA
from services.storage_service import get_storage_service

KEY='source_probes/norway_primary_news/'+SCHEMA+'.json'
CASES=(('VEI.OL','NO0005806802','XOSL'),('MORLD.OL','NO0013325506','XOSL'),('SNTIA.OL','NO0013573014','XOSL'))


def _accepted(receipt):
    try:
        if not isinstance(receipt,dict) or receipt.get('status')!='COMPLETED' or receipt.get('collector_schema')!=SCHEMA:return False
        if receipt.get('financial_state_changed') is not False:return False
        attempted=datetime.fromisoformat(receipt['attempted_at']);completed=datetime.fromisoformat(receipt['completed_at'])
        if attempted.tzinfo is None or completed.tzinfo is None or not attempted<=completed<=datetime.now(timezone.utc):return False
        runtime=receipt['runtime']
        if runtime.get('role')!='report_scheduler' or not re.fullmatch(r'[0-9a-f]{40}',runtime.get('commit','')):return False
        records=receipt.get('records')
        if not isinstance(records,list) or len(records)!=len(CASES) or not all(isinstance(r,dict) for r in records):return False
        if [(r.get('ticker'),r.get('isin'),r.get('mic')) for r in records]!=list(CASES):return False
        for record in records:
            if record.get('source_verified') is not True or record.get('content_scope')!='HEADLINE_ONLY':return False
            observed=datetime.fromisoformat(record['observed_at'])
            if observed.tzinfo is None or not attempted-timedelta(hours=1)<=observed<=completed:return False
            if not re.fullmatch(r'https://live\.euronext\.com/en/listview/company-press-release/\d{1,12}',record['source_url']):return False
            count=record['article_count'];listed=record['listing_rows']
            if type(count) is not int or type(listed) is not int or not (0<=count<=listed and 1<=listed<=50):return False
            if not count and record.get('window_complete') is not True:return False
            if count:
                published=datetime.fromisoformat(record['latest_publication'])
                if published.tzinfo is None or not attempted-timedelta(days=14)<=published<=observed:return False
        return True
    except (TypeError,ValueError,KeyError,AttributeError):return False


def production_ready(*,storage=None):
    if os.getenv('APP_ENVIRONMENT','').strip().lower()!='production':return True
    storage=storage or get_storage_service()
    return _accepted(storage.read_json(KEY,None))


def run_once(*,storage=None,now=None):
    if os.getenv('APP_ENVIRONMENT','').strip().lower()!='production':return {'status':'SKIPPED_NON_PRODUCTION','financial_state_changed':False}
    storage=storage or get_storage_service();now=now or datetime.now(timezone.utc)
    previous=storage.read_json(KEY,None)
    if _accepted(previous):return {'status':'ALREADY_VERIFIED','financial_state_changed':False,'verified_at':previous['completed_at']}
    if isinstance(previous,dict) and previous.get('attempted_at'):
        try:
            attempted=datetime.fromisoformat(previous['attempted_at'])
            if attempted.tzinfo is not None and now<attempted+timedelta(days=1):return {**previous,'status':'FAILED','retry_deferred':True}
        except (TypeError,ValueError):pass
    receipt={'status':'COMPLETED','collector_schema':SCHEMA,'attempted_at':now.isoformat(timespec='seconds'),
             'records':[],'financial_state_changed':False,'runtime':current_runtime_identity('report_scheduler')}
    for ticker,isin,mic in CASES:
        record={'ticker':ticker,'isin':isin,'mic':mic,'source_verified':False}
        try:
            rows,meta=fetch_company_news(ticker,isin,mic,storage=storage,now=now)
            if not rows and not meta['window_complete']:raise ValueError('Requested disclosure window is not verified')
            record.update(source_verified=True,article_count=len(rows),**meta)
            if rows:record['latest_publication']=max(r['published_at'] for r in rows)
        except Exception as exc:
            receipt['status']='FAILED';record['error']=str(exc)[:240]
        receipt['records'].append(record)
    receipt['completed_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    storage.write_json(KEY,receipt)
    return receipt
