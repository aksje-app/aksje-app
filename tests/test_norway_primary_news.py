"""Bounded verified primary disclosures; all fixtures are synthetic."""
import json
from datetime import datetime,timedelta,timezone
import pytest
from services.storage_service import StorageService
from test_revision_trade_postgres import pg

NOW=datetime(2026,11,11,1,tzinfo=timezone.utc)
ISIN='NO0005806802';MIC='XOSL';TICKER='VEI.OL'
PRODUCT=f'https://live.euronext.com/en/product/equities/{ISIN}-{MIC}'
ISSUER='https://live.euronext.com/en/listview/company-press-release/41785'

def product(**overrides):
    data=dict(name='VEIDEKKE',symbol='VEI',isin=ISIN,mic=MIC,issuer_code='41785');data.update(overrides)
    return '<link rel="canonical" href="'+PRODUCT+'"><script data-drupal-selector="drupal-settings-json" type="application/json">'+json.dumps({'custom':{'instrument':data}})+'</script><div class="regulated-news"><a href="/en/listview/company-press-release/41785">See All</a></div>'

def listing(rows=None):
    rows=rows if rows is not None else [('12921630','05 Nov 2026 09:12 CET','VEIDEKKE','Quarterly operations update'),('12918298','23 Oct 2026 08:00 CEST','VEIDEKKE','Older disclosure')]
    body=''.join(f'<tr><td>{date}</td><td>{company}</td><td><a class="standardRightCompanyPressRelease" data-node-nid="{node}" href="">{title}</a></td></tr>' for node,date,company,title in rows)
    return '<table><tbody>'+body+'</tbody></table>'

class Response:
    status_code=200
    def __init__(self,text,url):self.content=text.encode();self.url=url
    def raise_for_status(self):pass
    def iter_content(self,n):yield self.content
    def close(self):pass
class Session:
    def __init__(self,p=None,rows=None):self.p=p or product();self.rows=rows;self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append(url);return Response(self.p if url==PRODUCT else listing(self.rows),url)

@pytest.fixture
def local(tmp_path):return StorageService(tmp_path,mode='local',database_url='',allow_local_fallback=False)

def fetch(storage,session,**kwargs):
    from services.norway_primary_news import fetch_company_news
    return fetch_company_news(TICKER,ISIN,MIC,storage=storage,session=session,now=kwargs.pop('now',NOW),**kwargs)


def test_primary_news_binds_identity_datetime_and_headline_scope(local):
    s=Session();rows,meta=fetch(local,s)
    assert len(rows)==1 and s.calls==[PRODUCT,ISSUER]
    assert rows[0]['published_at']=='2026-11-05T08:12:00+00:00'
    assert rows[0]['source_observed_at']==NOW.isoformat(timespec='seconds')
    assert rows[0]['content_scope']=='HEADLINE_ONLY' and rows[0]['summary']==''
    assert rows[0]['source_role']=='PRIMARY_COMPANY' and rows[0]['isin']==ISIN
    assert meta['window_complete'] and meta['source_url']==ISSUER

@pytest.mark.parametrize('damage',[{'isin':'NO0013325506'},{'symbol':'MORLD'},{'mic':'MERK'},{'issuer_code':'777'}])
def test_wrong_instrument_or_issuer_never_yields_evidence(local,damage):
    with pytest.raises(ValueError):fetch(local,Session(product(**damage)))

@pytest.mark.parametrize('date',['12 Nov 2026 08:00 CET','05 Nov 2026','invalid','05 Nov 2026 09:12 CEST'])
def test_missing_future_or_inconsistent_dates_fail_closed(local,date):
    with pytest.raises(ValueError):fetch(local,Session(rows=[('1',date,'VEIDEKKE','Update')]))


def test_other_company_listing_never_becomes_primary_evidence(local):
    with pytest.raises(ValueError):fetch(local,Session(rows=[('1','05 Nov 2026 09:12 CET','OTHER ASA','Update')]))


def test_cache_reuses_original_observation_and_rechecks_window(local):
    rows,meta=fetch(local,Session());s=Session()
    cached,hit=fetch(local,s,now=NOW+timedelta(minutes=30))
    assert s.calls==[] and hit['cache_status']=='HIT' and cached==rows
    assert cached[0]['source_observed_at']==rows[0]['source_observed_at']


def test_recent_only_listing_does_not_claim_complete_history(local):
    rows,meta=fetch(local,Session(rows=[('1','10 Nov 2026 09:00 CET','VEIDEKKE','Update')]))
    assert rows and not meta['window_complete']


def test_source_without_listing_structure_never_claims_no_events(local):
    s=Session();s.get=lambda url,**kw:Response(product() if url==PRODUCT else '<html>Maintenance</html>',url)
    with pytest.raises(ValueError):fetch(local,s)


def test_oversized_response_is_rejected_before_parsing(local):
    s=Session();s.p='x'*(2*1024**2+1)
    with pytest.raises(ValueError):fetch(local,s)


def test_primary_rows_remain_company_relevant_without_name_in_headline(local):
    from news_intelligence import score_articles
    rows,_=fetch(local,Session());result=score_articles(TICKER,rows,company_name='Veidekke ASA')
    assert result['events'] and result['events'][0]['content_scope']=='HEADLINE_ONLY'
    assert result['events'][0]['retrieved_at']==NOW.isoformat(timespec='seconds')


def test_production_developer_plan_never_enters_coordinator_or_http(monkeypatch):
    import newsapi_budget as api
    monkeypatch.setenv('APP_ENVIRONMENT','production');monkeypatch.setenv('NEWSAPI_PLAN','Developer');monkeypatch.setenv('NEWSAPI_KEY','synthetic-key')
    monkeypatch.setattr(api,'_coordinator',lambda **kw:pytest.fail('Production Developer must stop before coordination or transport'))
    with pytest.raises(api.NewsApiSourceError) as exc:api.fetch_articles('Veidekke',purpose='NEWS')
    assert not exc.value.attempted and exc.value.reason_code=='PLAN_NOT_SUPPORTED_IN_PRODUCTION'


def test_corrupt_cached_publisher_is_refetched_instead_of_credited(local):
    fetch(local,Session());key=f'source_cache/euronext_company_news/{ISIN}-{MIC}.json'
    record=local.read_json(key);record['items'][0]['publisher']='OTHER ASA';local.write_json(key,record)
    s=Session();rows,_=fetch(local,s)
    assert len(s.calls)==2 and rows[0]['publisher']=='VEIDEKKE'


def test_cache_cannot_claim_publication_after_its_observation(local):
    fetch(local,Session());key=f'source_cache/euronext_company_news/{ISIN}-{MIC}.json'
    record=local.read_json(key);record['items'][0]['published_at']=(NOW+timedelta(minutes=10)).isoformat();local.write_json(key,record)
    s=Session();rows,_=fetch(local,s,now=NOW+timedelta(minutes=30))
    assert len(s.calls)==2 and rows[0]['published_at']=='2026-11-05T08:12:00+00:00'


def test_enrichment_forwards_verified_identity_and_retains_primary_news(local,monkeypatch,tmp_path):
    import news_intelligence as news
    import services.norway_primary_news as source
    monkeypatch.setattr(news,'CACHE_PATH',tmp_path/'news.json');monkeypatch.setattr(news,'source_specs',lambda *a:[])
    real_fetch=source.fetch_company_news
    def primary(ticker,isin,mic,**kw):
        assert (ticker,isin,mic)==(TICKER,ISIN,MIC)
        return real_fetch(ticker,isin,mic,storage=local,session=Session(),now=NOW,**kw)
    monkeypatch.setattr(source,'fetch_company_news',primary)
    monkeypatch.setattr(news,'_fetch_yfinance',lambda *a:pytest.fail('Verified primary coverage should avoid broken secondary request'))
    monkeypatch.setattr(news,'_fetch_newsapi',lambda *a:pytest.fail('Verified primary coverage should avoid spending API quota'))
    result=news.enrich_rows([{'ticker':TICKER,'isin':ISIN,'exchange_mic':MIC,'market':'Norge','longName':'Veidekke ASA'}],force_refresh=True)[0]['news_intelligence']
    assert result['events'][0]['isin']==ISIN and result['events'][0]['content_scope']=='HEADLINE_ONLY'
    assert result['canonical_evidence_status']=='VERIFIED_FACTS_FOUND'


def test_read_only_probe_runs_once_and_is_required_in_production(local,monkeypatch):
    from services import norway_primary_news_probe as probe
    calls=[]
    def source(ticker,isin,mic,**kw):
        calls.append(ticker)
        return [{'published_at':'2026-11-10T08:00:00+00:00'}],{'source_url':ISSUER,'observed_at':NOW.isoformat(),'window_complete':True,'listing_rows':50}
    monkeypatch.setattr(probe,'fetch_company_news',source)
    monkeypatch.setenv('APP_ENVIRONMENT','production')
    assert not probe.production_ready(storage=local)
    result=probe.run_once(storage=local,now=NOW)
    assert result['status']=='COMPLETED' and result['financial_state_changed'] is False and len(calls)==3
    assert probe.production_ready(storage=local)
    assert probe.run_once(storage=local,now=NOW)['status']=='ALREADY_VERIFIED' and len(calls)==3


def test_probe_failure_does_not_enable_primary_source_or_retry_immediately(local,monkeypatch):
    from services import norway_primary_news_probe as probe
    def broken(*a,**kw):raise ValueError('Unexpected issuer identity')
    monkeypatch.setattr(probe,'fetch_company_news',broken);monkeypatch.setenv('APP_ENVIRONMENT','production')
    assert probe.run_once(storage=local,now=NOW)['status']=='FAILED'
    assert not probe.production_ready(storage=local)
    result=probe.run_once(storage=local,now=NOW+timedelta(minutes=15))
    assert result['status']=='FAILED' and result['retry_deferred'] is True


def test_cron_probe_skips_nonproduction_without_fetching_or_writing(local,monkeypatch):
    from services import norway_primary_news_probe as probe
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    monkeypatch.setattr(probe,'fetch_company_news',lambda *a,**kw:pytest.fail('No external source probe in test/development'))
    assert probe.run_once(storage=local,now=NOW)['status']=='SKIPPED_NON_PRODUCTION'
    assert local.read_json(probe.KEY,None) is None


@pytest.mark.parametrize('records',[None,{},['invalid']])
def test_malformed_probe_receipt_cannot_enable_or_crash_primary_gate(local,monkeypatch,records):
    from services import norway_primary_news_probe as probe
    from services.norway_primary_news import SCHEMA
    monkeypatch.setenv('APP_ENVIRONMENT','production')
    local.write_json(probe.KEY,{'status':'COMPLETED','collector_schema':SCHEMA,'records':records})
    assert probe.production_ready(storage=local) is False


def test_primary_cache_is_shared_between_independent_database_clients(pg):
    first,_=fetch(pg,Session())
    other=StorageService(pg.base_dir/'second-service',database_url=pg.database_url,mode='postgres',allow_local_fallback=False)
    session=Session();second,meta=fetch(other,session)
    assert second==first and meta['cache_status']=='HIT' and session.calls==[]
    conn=pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT octet_length(payload) FROM app_kv_store WHERE name=%s',(f'source_cache/euronext_company_news/{ISIN}-{MIC}.json',))
            assert cur.fetchone()[0]<256*1024
    finally:conn.close()


def test_failed_source_probe_keeps_cron_warning_visible():
    from scheduled_runner import _derive_overall_state
    state={'state':'RUNNING','paper_scanner':{'state':'MARKET_CLOSED'},'norway_primary_news_probe':{'status':'FAILED'}}
    assert _derive_overall_state(state)=='COMPLETED_WITH_WARNINGS'
    assert 'norway_primary_news_probe:FAILED' in state['degraded_components']
