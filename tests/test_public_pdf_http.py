"""HTTP PDF delivery must open the native viewer, without a Streamlit session."""
import base64
from datetime import datetime,timedelta,timezone
import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route
from starlette.responses import PlainTextResponse
from urllib.parse import urlsplit
import requests,socket,threading,time
import uvicorn

TOKEN='T'*43
DATA=b'%PDF-1.4\noriginal durable PDF bytes\n%%EOF'

@pytest.fixture
def client(monkeypatch):
    import public_report_store as store
    from public_pdf_http import pdf_response,ReportEntryMiddleware
    payload={'token':TOKEN,'filename':'Rapport æøå.pdf','expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'pdf_base64':base64.b64encode(DATA).decode()}
    monkeypatch.setattr(store,'read_json',lambda key,path,default:payload if key==store._document_key(TOKEN) else default)
    async def page(request):return PlainTextResponse('HTML reserve page')
    app=Starlette(routes=[Route('/reports/{token}.pdf',pdf_response,methods=['GET','HEAD']),Route('/',page)],middleware=[Middleware(ReportEntryMiddleware)])
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        deadline=time.monotonic()+5
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.01)
        assert server.started
        session=requests.Session();session.trust_env=False
        class Client:
            def get(self,path,**kw):return session.get('http://127.0.0.1:'+str(port)+path,timeout=5,**kw)
            def head(self,path,**kw):return session.head('http://127.0.0.1:'+str(port)+path,timeout=5,**kw)
            def post(self,path,**kw):return session.post('http://127.0.0.1:'+str(port)+path,timeout=5,**kw)
        try:yield Client(),payload
        finally:
            session.close();server.should_exit=True;thread.join(timeout=5)



def test_existing_pushover_root_link_opens_inline_pdf_without_app_page(client):
    c,_=client;r=c.get('/?public_report_token='+TOKEN)
    assert r.history[0].status_code==307 and urlsplit(r.url).path=='/reports/'+TOKEN+'.pdf'
    assert r.content==DATA and r.headers['content-type']=='application/pdf'
    assert r.headers['content-disposition'].startswith('inline;') and 'filename*=UTF-8' in r.headers['content-disposition']
    assert r.headers['x-content-type-options']=='nosniff'


def test_explicit_page_and_unrelated_root_stay_in_the_app(client):
    c,_=client
    for query in ('','?aa_nav=reports','?public_report_token='+TOKEN+'&report_view=page','?public_file_token='+TOKEN+'&public_report_token='+TOKEN):
        assert c.get('/'+query).text=='HTML reserve page'


@pytest.mark.parametrize('token',['short','BAD.'+'a'*40,'X'*43])
def test_invalid_or_unknown_token_never_returns_pdf(client,token):
    c,_=client;assert c.get('/reports/'+token+'.pdf').status_code==404


def test_expiry_checked_on_every_request(client):
    c,payload=client;assert c.get('/reports/'+TOKEN+'.pdf').content==DATA
    payload['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    assert c.get('/reports/'+TOKEN+'.pdf').status_code==404


def test_storage_outage_is_503_not_html_or_old_cache(client,monkeypatch):
    import public_report_store as store
    def unavailable(*a,**kw):raise ConnectionError('private database details')
    monkeypatch.setattr(store,'load_public_pdf',unavailable)
    r=client[0].get('/reports/'+TOKEN+'.pdf')
    assert r.status_code==503 and 'private database details' not in r.text


@pytest.mark.parametrize('header,expected',[('bytes=0-4',DATA[:5]),('bytes=5-',DATA[5:]),('bytes=-5',DATA[-5:]),('bytes=0-9999',DATA)])
def test_single_ranges_preserve_pdf_bytes(client,header,expected):
    r=client[0].get('/reports/'+TOKEN+'.pdf',headers={'Range':header})
    assert r.status_code==206 and r.content==expected and r.headers['content-range'].endswith('/'+str(len(DATA)))


@pytest.mark.parametrize('header',['bytes=99999-','bytes=9-2','bytes=-0','bytes=abc'])
def test_unsatisfiable_ranges_fail_without_a_full_copy(client,header):
    r=client[0].get('/reports/'+TOKEN+'.pdf',headers={'Range':header})
    assert r.status_code==416 and r.headers['content-range']=='bytes */'+str(len(DATA))


def test_head_and_conditional_requests_keep_expiry_and_length(client):
    c,_=client;r=c.head('/reports/'+TOKEN+'.pdf')
    assert r.status_code==200 and not r.content and int(r.headers['content-length'])==len(DATA)
    assert c.get('/reports/'+TOKEN+'.pdf',headers={'If-None-Match':r.headers['etag']}).status_code==304
    assert c.post('/reports/'+TOKEN+'.pdf').status_code==405


def test_ui_urls_opt_into_page_and_notifier_urls_open_the_pdf(monkeypatch):
    from public_report_ui import with_report_return
    from report_delivery import pushover_pdf_url
    monkeypatch.setenv('RENDER_EXTERNAL_URL','https://aksje-app.onrender.com')
    root='https://aksje-app.onrender.com/?public_report_token='+TOKEN
    page=with_report_return(root,'reports')
    assert 'report_view=page' in page
    assert pushover_pdf_url(page)=='https://aksje-app.onrender.com/reports/'+TOKEN+'.pdf'
    for other in ('https://external.invalid/?public_report_token='+TOKEN,'https://aksje-app.onrender.com/?aa_nav=reports',root+'&public_report_token=other'):
        assert pushover_pdf_url(other)==other


def test_pushover_transport_sends_the_direct_pdf_link(monkeypatch):
    import notifier
    monkeypatch.setenv('RENDER_EXTERNAL_URL','https://aksje-app.onrender.com')
    monkeypatch.setattr(notifier,'notifications_allowed',lambda:(True,''))
    monkeypatch.setattr(notifier,'load_settings',lambda:{'pushover_enabled':True})
    monkeypatch.setattr(notifier,'pushover_enabled',lambda:True)
    fingerprints=[]
    monkeypatch.setattr(notifier,'_recent_duplicate',lambda *a,**k:fingerprints.append(a[2]) or False)
    monkeypatch.setattr(notifier,'_record_notification_fingerprint',lambda *a,**k:fingerprints.append(a[2]))
    monkeypatch.setattr(notifier,'_log_delivery',lambda *a,**k:None)
    sent=[]
    class Result:status_code=200
    def transport(url,**kw):sent.append(kw['data']);return Result()
    monkeypatch.setattr(notifier.requests,'post',transport)
    assert notifier.send_pushover_alert('Test',url='https://aksje-app.onrender.com/?public_report_token='+TOKEN+'&report_view=page')[0]
    assert sent[0]['url']=='https://aksje-app.onrender.com/reports/'+TOKEN+'.pdf'
    original='https://aksje-app.onrender.com/?public_report_token='+TOKEN+'&report_view=page'
    assert fingerprints==[original,original]


def test_secondary_download_page_remains_a_page_after_pdf_default_changes():
    from mobile_file_delivery import render_mobile_file_delivery
    from types import SimpleNamespace
    from bs4 import BeautifulSoup
    from urllib.parse import parse_qs
    html=[]
    st=SimpleNamespace(markdown=lambda value,**kw:html.append(value),caption=lambda *a:None,code=lambda *a,**kw:None)
    source='https://aksje-app.onrender.com/?public_report_token='+TOKEN
    render_mobile_file_delivery(st,url=source,filename='report.pdf',label='Åpne PDF',mime='application/pdf',key='probe',show_return=False)
    links=BeautifulSoup(html[0],'html.parser').find_all('a')
    assert links[0]['href']==source
    query=parse_qs(urlsplit(next(a['href'] for a in links if a.get_text()=='Åpne nedlastingsside')).query)
    assert query['public_report_token']==[TOKEN] and query['report_view']==['page']
