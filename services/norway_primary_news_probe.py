"""One bounded source-only acceptance probe in the existing cron invocation."""
from datetime import datetime,timedelta,timezone
import os
from services.norway_primary_news import fetch_company_news,SCHEMA
from services.storage_service import get_storage_service

KEY='source_probes/norway_primary_news/'+SCHEMA+'.json'
CASES=(('VEI.OL','NO0005806802','XOSL'),('MORLD.OL','NO0013325506','XOSL'),('SNTIA.OL','NO0013573014','XOSL'))


def _accepted(receipt):
    if not isinstance(receipt,dict) or receipt.get('status')!='COMPLETED' or receipt.get('collector_schema')!=SCHEMA:return False
    records=receipt.get('records')
    return (isinstance(records,list) and len(records)==len(CASES) and all(isinstance(r,dict) for r in records)
        and [(r.get('ticker'),r.get('isin'),r.get('mic')) for r in records]==list(CASES)
        and all(r.get('source_verified') is True for r in records))


def production_ready(*,storage=None):
    if os.getenv('APP_ENVIRONMENT','').strip().lower()!='production':return True
    storage=storage or get_storage_service()
    return _accepted(storage.read_json(KEY,None))


def run_once(*,storage=None,now=None):
    if os.getenv('APP_ENVIRONMENT','').strip().lower()!='production':return {'status':'SKIPPED_NON_PRODUCTION','financial_state_changed':False}
    storage=storage or get_storage_service();now=now or datetime.now(timezone.utc)
    previous=storage.read_json(KEY,None)
    if _accepted(previous):return {'status':'ALREADY_VERIFIED','financial_state_changed':False,'verified_at':previous['completed_at']}
    if previous and previous.get('attempted_at'):
        attempted=datetime.fromisoformat(previous['attempted_at'])
        if now<attempted+timedelta(days=1):return {**previous,'retry_deferred':True}
    receipt={'status':'COMPLETED','collector_schema':SCHEMA,'attempted_at':now.isoformat(timespec='seconds'),
             'records':[],'financial_state_changed':False}
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
