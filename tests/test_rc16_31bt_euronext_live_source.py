from __future__ import annotations

from unittest.mock import Mock
import norway_exchange_universe as neu


def test_current_euronext_product_directory_route_and_mics():
    assert '/pd_es/stocks/' in neu.EURONEXT_PRODUCT_DIRECTORY_URL
    assert 'XOSL%2CMERK%2CXOAS' in neu.EURONEXT_PRODUCT_DIRECTORY_URL
    assert neu.NORWAY_EQUITY_MICS == ('XOSL', 'MERK', 'XOAS')


def test_html_parser_extracts_all_three_oslo_markets():
    html = '''<table><tbody>
      <tr><td>Main ASA</td><td>NO0010000001</td><td>MAIN</td><td>Oslo Børs</td><td>10</td></tr>
      <tr><td>Growth AS</td><td>NO0010000002</td><td>GROW</td><td>Euronext Growth Oslo</td><td>11</td></tr>
      <tr><td>Expand ASA</td><td>NO0010000003</td><td>EXPD</td><td>Euronext Expand Oslo</td><td>12</td></tr>
    </tbody></table>'''
    rows = neu._parse_product_directory_html(html)
    assert [r['exchange_mic'] for r in rows] == ['XOSL', 'MERK', 'XOAS']
    assert [r['ticker'] for r in rows] == ['MAIN.OL', 'GROW.OL', 'EXPD.OL']


def test_html_directory_paginates_and_deduplicates(monkeypatch):
    pages = {
        0: '<table><tr><td>A ASA</td><td>NO0010000001</td><td>A</td><td>Oslo Børs</td></tr></table>',
        1: '<table><tr><td>B AS</td><td>NO0010000002</td><td>B</td><td>Euronext Growth Oslo</td></tr></table>',
        2: '<table></table>',
        3: '<table></table>',
    }
    class Resp:
        status_code = 200
        def __init__(self, page): self.text=pages.get(page, '<table></table>'); self.url='u'
        def raise_for_status(self): return None
    class Session:
        def get(self, url, params=None, **kwargs): return Resp(int((params or {}).get('page', 0)))
    rows, attempts = neu._fetch_product_directory(Session(), 1.0)
    assert [r['ticker'] for r in rows] == ['A.OL', 'B.OL']
    assert attempts[0]['strategy'] == 'PRODUCT_DIRECTORY_HTML'


def test_live_fetch_prefers_current_directory(monkeypatch):
    fake_rows=[]
    for i in range(160):
        fake_rows.append(neu._instrument_row(f'C{i}', f'NO{i:010d}'[-12:], f'T{i}', 'Oslo Børs'))
    fake_rows=[r for r in fake_rows if r]
    # use valid 12-char ISIN-like values by bypassing HTML parser contract here
    assert len(fake_rows) == 160
    monkeypatch.setattr(neu, '_fetch_product_directory', lambda session, timeout: (fake_rows, [{'strategy':'PRODUCT_DIRECTORY_HTML','rows':160}]))
    class Session:
        def get(self, *a, **k):
            class R:
                status_code=200; url='prime'
            return R()
    import requests
    monkeypatch.setattr(requests, 'Session', lambda: Session())
    out=neu.fetch_official_norway_master(timeout=1)
    assert out['status']=='OFFICIAL_LIVE'
    assert out['source']=='Euronext product directory'
    assert out['count']==160


def test_fallback_exposes_real_fetch_error(monkeypatch):
    monkeypatch.setattr(neu, '_load_durable', lambda: {})
    monkeypatch.setattr(neu, 'fetch_official_norway_master', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('HTTP 403 from product directory')))
    out=neu.get_norway_exchange_master_cached(('A.OL',), force_refresh=True)
    assert out['status']=='FALLBACK_UNVERIFIED'
    assert 'HTTP 403' in out['error']


def test_version_is_bt():
    import app_version
    assert app_version.APP_VERSION == 'v19.22.0-rc16.31bt'
