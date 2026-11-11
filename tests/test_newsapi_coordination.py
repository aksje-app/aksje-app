"""Source requests are coordinated; no real provider calls in these tests."""
from datetime import datetime,timezone
import types
import pytest
import newsapi_budget as api
from test_revision_trade_postgres import pg

class Response:
    def __init__(self,status=200,retry='30'):
        self.status_code=status;self.headers={'Retry-After':retry}
    def json(self):return {'code':'rateLimited'} if self.status_code==429 else {'articles':[{'title':'A','url':'https://example.test/a','source':{'name':'Source'}}]}
    def raise_for_status(self):
        if self.status_code>=400:raise RuntimeError('provider status')

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(api,'STATE_PATH',tmp_path/'state.json');monkeypatch.setattr(api,'CACHE_PATH',tmp_path/'cache.json')
    monkeypatch.setenv('NEWSAPI_KEY','synthetic-key');monkeypatch.setenv('NEWSAPI_DAILY_BUDGET','5')
    clock=[1780000000.0];calls=[];responses=[Response()]
    monkeypatch.setattr(api.time,'time',lambda:clock[0]);monkeypatch.setattr(api,'_now',lambda:datetime.fromtimestamp(clock[0],timezone.utc))
    def get(*a,**kw):
        calls.append(kw);r=responses.pop(0) if len(responses)>1 else responses[0]
        if isinstance(r,Exception):raise r
        return r
    monkeypatch.setitem(__import__('sys').modules,'requests',types.SimpleNamespace(get=get))
    return clock,calls,responses

@pytest.mark.parametrize('retry',['30','Wed, 28 May 2026 20:27:10 GMT','invalid'])
def test_cooldown_persists_between_queries(client,retry):
    clock,calls,responses=client
    # HTTP-date is generated from the same clock so the test has no wall-clock dependency.
    if retry.startswith('Wed'):
        from email.utils import format_datetime
        retry=format_datetime(datetime.fromtimestamp(clock[0]+30,timezone.utc),usegmt=True)
    responses[:]=[Response(429,retry),Response()]
    with pytest.raises(api.NewsApiRateLimited):api.fetch_articles('A',purpose='NEWS')
    with pytest.raises(api.NewsApiRateLimited) as exc:api.fetch_articles('B',purpose='INSIDER')
    assert len(calls)==1 and exc.value.attempted is False
    clock[0]+=61
    assert api.fetch_articles('B',purpose='INSIDER') and len(calls)==2


def test_identical_queries_share_cache_across_purposes_and_credentials_do_not(client,monkeypatch):
    clock,calls,_=client
    first=api.fetch_articles('A',purpose='NEWS')
    assert api.fetch_articles('A',purpose='INSIDER')==first and len(calls)==1
    monkeypatch.setenv('NEWSAPI_KEY','other-synthetic-key');clock[0]+=2
    api.fetch_articles('A',purpose='NEWS');assert len(calls)==2


def test_uncertain_http_is_charged_before_transport(client,monkeypatch):
    clock,calls,responses=client;monkeypatch.setenv('NEWSAPI_DAILY_BUDGET','1')
    responses[:]=[TimeoutError('uncertain response'),Response()]
    with pytest.raises(TimeoutError):api.fetch_articles('A',purpose='NEWS')
    clock[0]+=2
    with pytest.raises(api.NewsApiDailyQuotaExceeded):api.fetch_articles('B',purpose='NEWS')
    assert len(calls)==1


def test_cooldown_survives_utc_rollover(client):
    clock,calls,responses=client
    clock[0]=datetime(2026,5,28,23,59,50,tzinfo=timezone.utc).timestamp()
    responses[:]=[Response(429,'60'),Response()]
    with pytest.raises(api.NewsApiRateLimited):api.fetch_articles('A',purpose='NEWS')
    clock[0]+=20
    with pytest.raises(api.NewsApiRateLimited):api.fetch_articles('B',purpose='NEWS')
    assert len(calls)==1


def test_shared_bootstrap_preserves_unknown_prior_quota(pg,client,monkeypatch):
    from services import newsapi_coordination as coord
    monkeypatch.setattr(coord,'get_storage_service',lambda:pg)
    with pytest.raises(api.NewsApiDailyQuotaExceeded):api.fetch_articles('A',purpose='NEWS')
    assert client[1]==[] and api.health_snapshot()['coordination']=='POSTGRES'
    client[0][0]+=86400
    assert api.fetch_articles('A',purpose='NEWS') and len(client[1])==1


def test_shared_clients_reuse_results_and_enforce_one_budget(pg,client,monkeypatch):
    from services import newsapi_coordination as coord
    monkeypatch.setattr(coord,'get_storage_service',lambda:pg)
    with pytest.raises(api.NewsApiDailyQuotaExceeded):api.fetch_articles('A',purpose='NEWS')
    client[0][0]+=86400;monkeypatch.setenv('NEWSAPI_DAILY_BUDGET','1')
    first=api.fetch_articles('A',purpose='NEWS')
    assert api.fetch_articles('A',purpose='INSIDER')==first
    with pytest.raises(api.NewsApiDailyQuotaExceeded):api.fetch_articles('B',purpose='NEWS')
    assert len(client[1])==1


def test_corporate_parse_error_is_not_a_rate_limit():
    from evidence_search_status import infer_reason_code
    assert infer_reason_code('SOURCE_ERROR',attempted=True,error='Unable to parse corporate filing')=='SOURCE_ERROR'


def test_source_coordination_failure_never_sends_untracked_http(client,monkeypatch):
    from services import newsapi_coordination as coord
    class Broken:
        database_url='configured';mode='postgres'
        def using_postgres(self):return True
        def init_db(self):raise RuntimeError('database unavailable')
    monkeypatch.setattr(coord,'get_storage_service',lambda:Broken())
    with pytest.raises(api.NewsApiError) as exc:api.fetch_articles('A',purpose='NEWS')
    assert exc.value.status=='SOURCE_ERROR' and not exc.value.attempted and client[1]==[]


def test_shared_lock_survives_commits_and_health_remains_readable(pg,client,monkeypatch):
    from services import newsapi_coordination as coord
    monkeypatch.setattr(coord,'get_storage_service',lambda:pg)
    with pytest.raises(api.NewsApiDailyQuotaExceeded):api.fetch_articles('A',purpose='NEWS')
    client[0][0]+=86400
    with coord.coordinated(api.STATE_PATH,'synthetic-key') as owner:
        owner.set_state({'utc_date':api._now().date().isoformat(),'requests':0})
        assert api.health_snapshot()['coordination']=='POSTGRES'
        with pytest.raises(api.NewsApiRateLimited) as exc:api.fetch_articles('A',purpose='NEWS')
        assert not exc.value.attempted and client[1]==[]
    assert api.fetch_articles('A',purpose='NEWS') and len(client[1])==1


def test_postgres_cache_has_bounded_row_count(pg,client,monkeypatch):
    from services import newsapi_coordination as coord
    monkeypatch.setattr(coord,'get_storage_service',lambda:pg);monkeypatch.setattr(coord,'MAX_CACHE_ROWS',2)
    with coord.coordinated(api.STATE_PATH,'synthetic-key') as backend:
        for i in range(3):backend.set_cache(str(i),{'articles':[],'cached_at':client[0][0]})
        with backend.conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM app_kv_store WHERE name >= %s AND name < %s',(backend.cache_prefix,backend.cache_prefix+'z'))
            assert cur.fetchone()[0]==2


def test_discovery_storage_failure_is_not_missing_configuration(client,monkeypatch):
    import international_insider_sources as sources
    monkeypatch.setattr(sources,'_NEWS_CACHE',{})
    def fail(*a,**kw):raise api.NewsApiSourceError('Source coordination unavailable')
    monkeypatch.setattr(sources,'fetch_newsapi_articles',fail)
    result=sources.discover_with_newsapi('STB.OL','Storebrand','Norge')
    assert result['status']=='SOURCE_ERROR' and result['attempted'] is False


def test_cooldown_is_reported_as_not_searched(client,monkeypatch,tmp_path):
    import news_intelligence as news
    monkeypatch.setattr(news,'CACHE_PATH',tmp_path/'news.json');monkeypatch.setattr(news,'source_specs',lambda *a:[])
    monkeypatch.setattr(news,'_fetch_yfinance',lambda *a:[])
    monkeypatch.setattr(news,'record_source_attempt',lambda **kw:None)
    def fail(*a,**kw):raise api.NewsApiRateLimited(30,attempted=False)
    monkeypatch.setattr(news,'_fetch_newsapi',fail)
    result=news.fetch_news_intelligence('TEST',force_refresh=True)
    row=next(x for x in result['search_log'] if x['source'].startswith('NewsAPI'))
    assert row['attempted'] is False and row['search_status']=='NOT_SEARCHED_POLICY'


def test_notification_explains_searches_without_claiming_buy_readiness(monkeypatch):
    import market_intelligence as mi
    from test_v19220_rc1631_test_series_delivery import _notification_run
    import sys
    captured={}
    monkeypatch.setattr(mi,'_read',lambda *a,**k:{});monkeypatch.setattr(mi,'_write',lambda *a,**k:None);monkeypatch.setattr(mi,'_audit',lambda *a,**k:None)
    monkeypatch.setitem(sys.modules,'notifier',types.SimpleNamespace(send_pushover_alert=lambda message,**kw:(captured.update(message=message) or True,None)))
    run=_notification_run(automatic=False)
    run['evidence_search_summary']={'source_budget':{'planned':10,'attempted':6,'successful':4,'with_results':1,'failed':2,'not_searched':4}}
    ok,_=mi._notification(mi.JobProfile(name='Source test',notification_mode='ALWAYS',notify_only_changes=False),run)
    assert ok and 'Kildesøk: treff 1 · uten treff 3 · feil 2 · ikke undersøkt 4' in captured['message']
    assert 'Kjøpsklare nå: 0' in captured['message']


@pytest.mark.parametrize('used',[-1,'invalid',True])
def test_corrupt_shared_counter_never_resets_or_sends_http(pg,client,monkeypatch,used):
    from services import newsapi_coordination as coord
    monkeypatch.setattr(coord,'get_storage_service',lambda:pg)
    with coord.coordinated(api.STATE_PATH,'synthetic-key') as backend:
        backend.set_state({'utc_date':api._now().date().isoformat(),'requests':used})
    with pytest.raises(api.NewsApiSourceError):api.fetch_articles('A',purpose='NEWS')
    assert client[1]==[]


def test_provider_error_is_classified_and_charged(client):
    client[2][:]=[Response(403)]
    with pytest.raises(api.NewsApiSourceError) as exc:api.fetch_articles('A',purpose='NEWS')
    assert exc.value.attempted is True and api.health_snapshot()['used_today']==1
    assert api.health_snapshot()['last_http_status']==403


def test_future_shared_counter_cannot_reset_today_quota(pg,client,monkeypatch):
    from services import newsapi_coordination as coord
    monkeypatch.setattr(coord,'get_storage_service',lambda:pg)
    tomorrow=datetime.fromtimestamp(client[0][0]+86400,timezone.utc).date().isoformat()
    with coord.coordinated(api.STATE_PATH,'synthetic-key') as backend:
        backend.set_state({'utc_date':tomorrow,'requests':50})
    with pytest.raises(api.NewsApiSourceError):api.fetch_articles('A',purpose='NEWS')
    assert client[1]==[]


def test_handoff_cannot_be_bypassed_by_raising_configured_budget(pg,client,monkeypatch):
    from services import newsapi_coordination as coord
    monkeypatch.setattr(coord,'get_storage_service',lambda:pg)
    with pytest.raises(api.NewsApiDailyQuotaExceeded):api.fetch_articles('A',purpose='NEWS')
    monkeypatch.setenv('NEWSAPI_DAILY_BUDGET','50')
    with pytest.raises(api.NewsApiDailyQuotaExceeded):api.fetch_articles('B',purpose='NEWS')
    assert client[1]==[]


def test_coordination_busy_is_not_reported_as_provider_429(pg,client,monkeypatch):
    from services import newsapi_coordination as coord
    monkeypatch.setattr(coord,'get_storage_service',lambda:pg)
    with coord.coordinated(api.STATE_PATH,'synthetic-key'):
        with pytest.raises(api.NewsApiRateLimited) as exc:api.fetch_articles('A',purpose='NEWS')
    assert not exc.value.attempted and '429' not in str(exc.value)
    assert exc.value.reason_code=='SOURCE_BUSY' and client[1]==[]


@pytest.mark.parametrize('exc,reason',[(api.NewsApiReportQuotaExceeded(),'REPORT_QUOTA_EXCEEDED'),(api.NewsApiQuotaHandoffPending(),'UNKNOWN_PRIOR_QUOTA_USAGE')])
def test_quota_reason_reaches_report_without_false_daily_exhaustion(client,monkeypatch,tmp_path,exc,reason):
    import news_intelligence as news
    monkeypatch.setattr(news,'CACHE_PATH',tmp_path/'news.json');monkeypatch.setattr(news,'source_specs',lambda *a:[])
    monkeypatch.setattr(news,'_fetch_yfinance',lambda *a:[]);monkeypatch.setattr(news,'record_source_attempt',lambda **kw:None)
    def fail(*a,**kw):raise exc
    monkeypatch.setattr(news,'_fetch_newsapi',fail)
    result=news.fetch_news_intelligence('TEST',force_refresh=True)
    row=next(x for x in result['search_log'] if x['source'].startswith('NewsAPI'))
    assert row['reason_code']==reason and not row['attempted']
    assert result['source_budget']['daily_quota_exceeded']==0
