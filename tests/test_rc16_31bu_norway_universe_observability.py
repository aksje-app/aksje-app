import json
import zipfile
from io import BytesIO
import norway_exchange_universe as neu

class Resp:
    def __init__(self, status=200, text='', url='https://example.test/final', ctype='text/html'):
        self.status_code=status; self.text=text; self.url=url; self.headers={'content-type':ctype,'content-length':str(len(text))}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')
    def json(self):
        raise ValueError('not json')

class FailSession:
    def get(self,*a,**k): return Resp(403,'blocked',ctype='text/html')
    def post(self,*a,**k): return Resp(503,'unavailable',ctype='text/plain')

def test_fetch_error_keeps_attempt_details(monkeypatch):
    import requests
    monkeypatch.setattr(requests, 'Session', lambda: FailSession())
    captured={}
    monkeypatch.setattr(neu, 'write_json', lambda key,path,value: captured.update(value))
    try:
        neu.fetch_official_norway_master(timeout=0.1)
        assert False, 'expected failure'
    except neu.NorwayUniverseFetchError as exc:
        assert exc.attempts
    assert captured['status']=='FAILED'
    assert captured['attempts']
    assert any(a.get('http_status') in (403,503) for a in captured['attempts'])
    assert all('observed_at' in a for a in captured['attempts'])

def test_fallback_embeds_fetch_diagnostics():
    out=neu._fallback_master(('A.OL',),'boom',{'status':'FAILED','parsed_count':0})
    assert out['status']=='FALLBACK_UNVERIFIED'
    assert out['fetch_diagnostics']['status']=='FAILED'

def test_safe_response_meta_contains_http_and_content_type():
    meta=neu._safe_response_meta(Resp(200,'abc',ctype='text/html; charset=UTF-8'))
    assert meta['http_status']==200
    assert 'text/html' in meta['content_type']
    assert meta['response_chars']==3
