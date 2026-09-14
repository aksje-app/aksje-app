from __future__ import annotations

import norway_exchange_universe as neu


def _csv(rows: int = 160) -> str:
    header = 'Name;ISIN;Symbol;Market;Last;Date/Time\n'
    body = []
    markets = ('Oslo Børs', 'Euronext Growth Oslo', 'Euronext Expand Oslo')
    for i in range(rows):
        market = markets[i % 3]
        body.append(f'Company {i};NO{i:010d};T{i:03d};{market};10.0;08/09/2026')
    return header + '\n'.join(body)


def test_current_official_csv_endpoint_is_pd_es_download():
    assert neu.EURONEXT_STOCKS_DOWNLOAD_ENDPOINT.endswith('/en/pd_es/data/stocks/download')
    assert neu.NORWAY_EQUITY_MICS == ('XOSL', 'MERK', 'XOAS')


def test_csv_parser_extracts_all_three_oslo_markets():
    text = '''Name;ISIN;Symbol;Market\nMain ASA;NO0010000001;MAIN;Oslo Børs\nGrowth AS;NO0010000002;GROW;Euronext Growth Oslo\nExpand ASA;NO0010000003;EXPD;Euronext Expand Oslo\n'''
    rows = neu._parse_euronext_csv(text)
    assert [r['exchange_mic'] for r in rows] == ['XOSL', 'MERK', 'XOAS']
    assert [r['ticker'] for r in rows] == ['MAIN.OL', 'GROW.OL', 'EXPD.OL']


def test_csv_parser_handles_norwegian_headers_and_metadata_prefix():
    text = '''Euronext Oslo equity export\nGenerated;08/09/2026\nNavn;ISIN;Ticker;Marked\nAlpha ASA;NO0010000001;ALPHA;Oslo Børs\nBeta AS;NO0010000002;BETA;Euronext Growth Oslo\n'''
    rows = neu._parse_euronext_csv(text)
    assert [r['ticker'] for r in rows] == ['ALPHA.OL', 'BETA.OL']
    assert rows[1]['exchange_name'] == 'Euronext Growth Oslo'


def test_csv_parser_can_filter_all_stock_export_using_mic_column():
    text = '''Name,ISIN,Symbol,Market,MIC\nOslo Co,NO0010000001,OSLO,Something,XOSL\nGrowth Co,NO0010000002,GROW,Something,MERK\nParis Co,FR0010000003,PAR,Something,XPAR\nExpand Co,NO0010000004,EXP,Something,XOAS\n'''
    rows = neu._parse_euronext_csv(text)
    assert [r['ticker'] for r in rows] == ['OSLO.OL', 'GROW.OL', 'EXP.OL']


def test_official_csv_fetch_prefers_oslo_specific_variant():
    class Resp:
        status_code = 200
        headers = {'content-type': 'text/csv; charset=utf-8'}
        url = neu.EURONEXT_STOCKS_DOWNLOAD_ENDPOINT
        def __init__(self, text):
            self.text = text
            self.content = text.encode('utf-8')
        def raise_for_status(self):
            return None
    class Session:
        def get(self, url, params=None, **kwargs):
            assert params['mics'] == 'XOSL,MERK,XOAS'
            return Resp(_csv(160))
    rows, attempts = neu._fetch_official_csv(Session(), 1.0)
    assert len(rows) == 160
    assert attempts[0]['strategy'] == 'OFFICIAL_CSV_EXPORT'
    assert attempts[0]['variant'] == 'OSLO_MICS'
    assert attempts[0]['rows'] == 160


def test_official_csv_fetch_uses_all_stock_variant_when_specific_export_empty():
    class Resp:
        status_code = 200
        headers = {'content-type': 'text/csv'}
        url = neu.EURONEXT_STOCKS_DOWNLOAD_ENDPOINT
        def __init__(self, text):
            self.text = text
            self.content = text.encode('utf-8')
        def raise_for_status(self): return None
    calls=[]
    class Session:
        def get(self, url, params=None, **kwargs):
            calls.append(params['mics'])
            if params['mics'] == 'XOSL,MERK,XOAS':
                return Resp('Name;ISIN;Symbol;Market\n')
            return Resp(_csv(160))
    rows, attempts = neu._fetch_official_csv(Session(), 1.0)
    assert len(rows) == 160
    assert calls == ['XOSL,MERK,XOAS', 'dm_all_stock']
    assert attempts[-1]['variant'] == 'ALL_STOCKS'


def test_live_master_prefers_official_csv_without_touching_html_or_legacy(monkeypatch):
    fake = [neu._instrument_row(f'C{i}', f'NO{i:010d}', f'T{i}', 'Oslo Børs') for i in range(160)]
    fake = [x for x in fake if x]
    monkeypatch.setattr(neu, '_fetch_official_csv', lambda session, timeout: (fake, [{'strategy':'OFFICIAL_CSV_EXPORT','rows':160}]))
    monkeypatch.setattr(neu, '_fetch_product_directory', lambda *a, **k: (_ for _ in ()).throw(AssertionError('HTML fallback should not run')))
    monkeypatch.setattr(neu, '_fetch_legacy_json', lambda *a, **k: (_ for _ in ()).throw(AssertionError('legacy fallback should not run')))
    class PrimeResp:
        status_code=200; url='prime'; headers={'content-type':'text/html'}; text='ok'
    class Session:
        def get(self, *a, **k): return PrimeResp()
    import requests
    monkeypatch.setattr(requests, 'Session', lambda: Session())
    monkeypatch.setattr(neu, '_persist_fetch_diagnostics', lambda **kwargs: kwargs)
    out = neu.fetch_official_norway_master(timeout=1)
    assert out['status'] == 'OFFICIAL_LIVE'
    assert out['source'] == 'Euronext official CSV export'
    assert out['source_url'] == neu.EURONEXT_STOCKS_DOWNLOAD_ENDPOINT
    assert out['count'] == 160


def test_version_is_bv():
    import app_version
    assert app_version.APP_VERSION == 'v19.22.0-rc16.31bv'

def test_current_json_contract_matches_pd_es_oslo_table_route():
    params, data = neu._request_payload_current()
    assert neu.EURONEXT_STOCKS_ENDPOINT_CURRENT.endswith('/en/pd_es/data/stocks')
    assert params['mics'] == 'XOSL,MERK,XOAS'
    assert params['display_datapoints'] == 'dp_stocks'
    assert params['display_filters'] == 'df_stocks2'
    assert params['display_table'] == 'dt_stocks_osl'
    assert data['iDisplayLength'] == '2000'


def test_current_json_parser_accepts_datatables_payload():
    payload = {'recordsFiltered': 3, 'aaData': [
        ['Main ASA','NO0010000001','MAIN','Oslo Børs','','',''],
        ['Growth AS','NO0010000002','GROW','Euronext Growth Oslo','','',''],
        ['Expand ASA','NO0010000003','EXPD','Euronext Expand Oslo','','',''],
    ]}
    class Resp:
        status_code=200; headers={'content-type':'application/json'}; url=neu.EURONEXT_STOCKS_ENDPOINT_CURRENT; text='{}'
        def raise_for_status(self): return None
        def json(self): return payload
    class Session:
        def post(self, url, params=None, data=None, headers=None, timeout=None):
            assert url == neu.EURONEXT_STOCKS_ENDPOINT_CURRENT
            assert headers['X-Requested-With'] == 'XMLHttpRequest'
            return Resp()
    rows, out, attempts = neu._fetch_current_json(Session(), 1.0)
    assert len(rows) == 3
    assert out['recordsFiltered'] == 3
    assert attempts[0]['strategy'] == 'CURRENT_JSON_POST'
