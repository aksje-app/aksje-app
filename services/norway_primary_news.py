"""Bounded primary disclosure headlines, bound to the exchange's own identity."""
from datetime import datetime,timedelta,timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
import json,re
from bs4 import BeautifulSoup
import requests
from services.storage_service import get_storage_service

ORIGIN='https://live.euronext.com'
MAX_RESPONSE_BYTES=2*1024**2
MAX_RECORD_BYTES=256*1024
MAX_ITEMS=50
CACHE_SECONDS=3600
SCHEMA='EURONEXT_ISSUER_HEADLINES_V1'
MONTHS={name:i for i,name in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(),1)}


def _publication(text):
    m=re.fullmatch(r'(\d{1,2}) ([A-Za-z]{3}) (\d{4}) (\d{2}):(\d{2}) (CET|CEST)',' '.join(text.split()))
    if not m:raise ValueError('Missing or invalid publication timestamp')
    day,month,year,hour,minute,label=m.groups()
    offset=1 if label=='CET' else 2
    dt=datetime(int(year),MONTHS[month],int(day),int(hour),int(minute),tzinfo=timezone(timedelta(hours=offset)))
    if dt.astimezone(ZoneInfo('Europe/Oslo')).tzname()!=label:raise ValueError('Publication timezone does not match calendar')
    return dt.astimezone(timezone.utc)


def _name(text):
    return re.sub(r'[^A-Z0-9]','',' '.join(x for x in str(text).upper().split() if x not in {'ASA','AS','PLC','LTD'}))


def _html(session,url):
    response=session.get(url,timeout=12,stream=True,allow_redirects=False)
    try:
        response.raise_for_status()
        if response.status_code!=200 or response.url.rstrip('/')!=url.rstrip('/'):
            raise ValueError('Unexpected primary-source response or redirect')
        parts=[];size=0
        for chunk in response.iter_content(65536):
            size+=len(chunk)
            if size>MAX_RESPONSE_BYTES:raise ValueError('Primary-source response exceeds size limit')
            parts.append(chunk)
        return BeautifulSoup(b''.join(parts).decode('utf8'),'html.parser')
    finally:response.close()


def _identity(doc,ticker,isin,mic,product_url):
    tag=doc.select_one('script[data-drupal-selector="drupal-settings-json"]')
    canonical=doc.select_one('link[rel="canonical"]')
    if not tag or not canonical or canonical.get('href')!=product_url:
        raise ValueError('Missing verified instrument page structure')
    instrument=json.loads(tag.get_text())['custom']['instrument']
    if (instrument.get('isin'),instrument.get('mic'),instrument.get('symbol'))!=(isin,mic,ticker[:-3]):
        raise ValueError('Primary-source instrument identity mismatch')
    issuer=str(instrument.get('issuer_code') or '')
    if not re.fullmatch(r'\d{1,12}',issuer) or not instrument.get('name'):
        raise ValueError('Missing issuer identity')
    expected='/en/listview/company-press-release/'+issuer
    links=[a.get('href') for a in doc.select('.regulated-news a[href]') if '/listview/company-press-release/' in a.get('href','')]
    if links!=[expected]:raise ValueError('Instrument does not identify one matching issuer listing')
    return str(instrument['name']),urljoin(ORIGIN,expected)


def _listing(doc,ticker,isin,mic,name,source_url,now):
    links=doc.select('a.standardRightCompanyPressRelease[data-node-nid]')
    if not links:raise ValueError('Missing issuer listing structure; absence is not verified')
    if len(links)>MAX_ITEMS:raise ValueError('Issuer listing exceeds bounded row limit')
    items=[];seen=set();previous=None
    for a in links:
        tr=a.find_parent('tr');cells=tr.find_all('td') if tr else []
        if len(cells)<3 or _name(cells[1].get_text(' ',strip=True))!=_name(name):
            raise ValueError('Listing row belongs to a different issuer')
        at=_publication(cells[0].get_text(' ',strip=True));node=str(a.get('data-node-nid') or '')
        title=a.get_text(' ',strip=True)
        if at>now or (previous is not None and at>previous):raise ValueError('Future or out-of-order disclosure date')
        if not re.fullmatch(r'\d{1,12}',node) or node in seen or not title or len(title)>1000:
            raise ValueError('Invalid or duplicate disclosure identity')
        previous=at;seen.add(node)
        items.append({'title':title,'summary':'','url':source_url,'document_url':ORIGIN+'/en/node/'+node,
            'publisher':name,'original_publisher':name,'collector_source':'Euronext issuer disclosures',
            'source_id':'euronext_company_news','source_role':'PRIMARY_COMPANY',
            'verification':'VERIFIED_EXCHANGE_HEADLINE','content_scope':'HEADLINE_ONLY',
            'published_at':at.isoformat(),'publication_precision':'MINUTE','source_observed_at':now.isoformat(timespec='seconds'),
            'source_document_id':node,'isin':isin,'exchange_mic':mic,'ticker':ticker,
            'source_quality_override':1.0,'primary_source_verified':True})
    return items


def _cached(record,ticker,isin,mic,now):
    try:
        if not isinstance(record,dict) or record.get('schema')!=SCHEMA:return False
        if (record['ticker'],record['isin'],record['mic'])!=(ticker,isin,mic):return False
        age=(now-datetime.fromisoformat(record['observed_at'])).total_seconds()
        if not 0<=age<CACHE_SECONDS or len(json.dumps(record,ensure_ascii=True))>MAX_RECORD_BYTES:return False
        if not re.fullmatch(re.escape(ORIGIN)+r'/en/listview/company-press-release/\d{1,12}',record['source_url']):return False
        items=record['items']
        if not isinstance(items,list) or not 1<=len(items)<=MAX_ITEMS:return False
        observed=datetime.fromisoformat(record['observed_at'])
        for row in items:
            if row['publisher']!=record['issuer_name'] or row['source_role']!='PRIMARY_COMPANY' or row['verification']!='VERIFIED_EXCHANGE_HEADLINE' or row.get('primary_source_verified') is not True:return False
            if (row['ticker'],row['isin'],row['exchange_mic'])!=(ticker,isin,mic):return False
            if row['url']!=record['source_url'] or row['source_observed_at']!=record['observed_at']:return False
            at=datetime.fromisoformat(row['published_at'])
            if at.tzinfo is None or at>observed or row['content_scope']!='HEADLINE_ONLY':return False
        return True
    except (ValueError,TypeError,KeyError):return False


def fetch_company_news(ticker,isin,mic,*,lookback_days=14,storage=None,session=None,now=None):
    ticker=str(ticker).upper().strip();isin=str(isin).upper().strip();mic=str(mic).upper().strip()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{0,18}\.OL',ticker) or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}\d',isin) or mic not in {'XOSL','XOAS','MERK'}:
        raise ValueError('Verified Norwegian ticker, ISIN and MIC are required')
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('Timezone-aware observation required')
    days=int(lookback_days)
    if not 1<=days<=365:raise ValueError('Invalid disclosure time window')
    storage=storage or get_storage_service();key=f'source_cache/euronext_company_news/{isin}-{mic}.json'
    record=storage.read_json(key,None);cache_hit=_cached(record,ticker,isin,mic,now)
    if not cache_hit:
        owned=session is None;session=session or requests.Session()
        try:
            product_url=f'{ORIGIN}/en/product/equities/{isin}-{mic}'
            product=_html(session,product_url);name,source_url=_identity(product,ticker,isin,mic,product_url)
            del product
            listing=_html(session,source_url)
            items=_listing(listing,ticker,isin,mic,name,source_url,now);del listing
            record={'schema':SCHEMA,'ticker':ticker,'isin':isin,'mic':mic,'observed_at':now.isoformat(timespec='seconds'),
                'source_url':source_url,'issuer_name':name,'items':items}
            if len(json.dumps(record,ensure_ascii=True))>MAX_RECORD_BYTES:raise ValueError('Primary-source cache exceeds size limit')
            storage.write_json(key,record)
        finally:
            if owned:session.close()
    cutoff=now-timedelta(days=days)
    rows=[dict(row) for row in record['items'] if cutoff<=datetime.fromisoformat(row['published_at'])<=now]
    complete=min(datetime.fromisoformat(x['published_at']) for x in record['items'])<=cutoff
    return rows,{'source_url':record['source_url'],'issuer_name':record['issuer_name'],'observed_at':record['observed_at'],'cache_status':'HIT' if cache_hit else 'MISS',
        'listing_rows':len(record['items']),'window_complete':complete,'content_scope':'HEADLINE_ONLY','source_id':'euronext_company_news'}
