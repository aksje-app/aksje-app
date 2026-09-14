from __future__ import annotations

import norway_exchange_universe as neu


def _csv_for(mic: str, count: int, *, blank_market: bool = True) -> str:
    lines = ['Name;ISIN;Symbol;Market;Currency']
    for i in range(count):
        market = '' if blank_market else neu.MIC_TO_MARKET[mic]
        lines.append(f'Company {mic} {i};NO{i:010d};{mic}{i:03d};{market};NOK')
    return '\n'.join(lines)


def test_csv_parser_accepts_authoritative_mic_hint_when_market_display_is_blank():
    rows = neu._parse_euronext_csv(_csv_for('MERK', 3), mic_hint='MERK')
    assert len(rows) == 3
    assert {r['exchange_mic'] for r in rows} == {'MERK'}
    assert {r['exchange_name'] for r in rows} == {'Euronext Growth Oslo'}


def test_official_csv_fetches_all_three_mics_separately_and_combines_them():
    counts = {'XOSL': 110, 'MERK': 70, 'XOAS': 20}
    calls = []

    class Resp:
        status_code = 200
        headers = {'content-type': 'text/csv;charset=UTF-8'}
        url = neu.EURONEXT_STOCKS_DOWNLOAD_ENDPOINT
        def __init__(self, text):
            self.text = text
            self.content = text.encode('utf-8')
        def raise_for_status(self): return None

    class Session:
        def get(self, url, params=None, **kwargs):
            mic = params['mics']
            calls.append(mic)
            return Resp(_csv_for(mic, counts[mic]))

    rows, attempts = neu._fetch_official_csv(Session(), 1.0)
    assert len(rows) == sum(counts.values())
    assert calls == ['XOSL', 'MERK', 'XOAS']
    assert [a['variant'] for a in attempts] == ['MIC_XOSL', 'MIC_MERK', 'MIC_XOAS']
    split = {mic: sum(r['exchange_mic'] == mic for r in rows) for mic in neu.NORWAY_EQUITY_MICS}
    assert split == counts


def test_real_euronext_datatables_html_cells_are_parsed():
    payload = {
        'recordsFiltered': 3,
        'aaData': [
            [
                '<a href="/en/product/equities/NO0010345853-XOSL/aker-bp/akr/quotes" data-title-hover="AKER BP">AKER BP</a>',
                '<span>NO0010345853</span>',
                '<span data-order="AKRBP">AKRBP</span>',
                '<span>Oslo Børs</span>', '', '', ''
            ],
            [
                '<a href="/en/product/equities/NO0010000002-MERK/growth/grow/quotes" data-title-hover="Growth AS">Growth AS</a>',
                '<span>NO0010000002</span>',
                '<span data-order="GROW">GROW</span>',
                '<span>Euronext Growth Oslo</span>', '', '', ''
            ],
            [
                '<a href="/en/product/equities/NO0010000003-XOAS/expand/expd/quotes" data-title-hover="Expand ASA">Expand ASA</a>',
                '<span>NO0010000003</span>',
                '<span data-order="EXPD">EXPD</span>',
                '<span>Euronext Expand Oslo</span>', '', '', ''
            ],
        ],
    }
    rows = neu._parse_rows(payload)
    assert [r['ticker'] for r in rows] == ['AKRBP.OL', 'GROW.OL', 'EXPD.OL']
    assert [r['exchange_mic'] for r in rows] == ['XOSL', 'MERK', 'XOAS']


def test_json_parser_accepts_mapping_rows_and_embedded_mic():
    payload = {'aaData': [
        {'Name': '<b>Alpha ASA</b>', 'ISIN': 'NO0010000001', 'Symbol': 'ALPHA', 'Market': '<span data-mic="XOSL">Oslo</span>'},
        {'name': 'Beta AS', 'isin': 'NO0010000002', 'ticker': 'BETA', 'marketMic': 'MERK'},
    ]}
    rows = neu._parse_rows(payload)
    assert [r['ticker'] for r in rows] == ['ALPHA.OL', 'BETA.OL']
    assert [r['exchange_mic'] for r in rows] == ['XOSL', 'MERK']


def test_version_is_bw():
    import app_version
    assert app_version.APP_VERSION == 'v19.22.0-rc16.31bw'


def test_per_mic_parser_rejects_rows_that_explicitly_belong_to_other_market():
    mixed = '''Name;ISIN;Symbol;Market\nMain;NO0010000001;MAIN;Oslo Børs\nGrowth;NO0010000002;GROW;Euronext Growth Oslo\n'''
    rows = neu._parse_euronext_csv(mixed, mic_hint='XOSL')
    assert [r['ticker'] for r in rows] == ['MAIN.OL']
    assert rows[0]['exchange_mic'] == 'XOSL'


def test_live_master_closes_observed_render_case_294_json_rows_after_empty_csv(monkeypatch):
    html_rows = []
    markets = [('XOSL', 'Oslo Børs'), ('MERK', 'Euronext Growth Oslo'), ('XOAS', 'Euronext Expand Oslo')]
    for i in range(294):
        mic, market = markets[i % 3]
        isin = f'NO{i:010d}'
        symbol = f'T{i:03d}'
        html_rows.append([
            f'<a href="/en/product/equities/{isin}-{mic}/company/{symbol.lower()}/quotes">Company {i}</a>',
            f'<span>{isin}</span>',
            f'<span data-order="{symbol}">{symbol}</span>',
            f'<span>{market}</span>', '', '', ''
        ])
    payload = {'recordsFiltered': 294, 'aaData': html_rows}

    monkeypatch.setattr(neu, '_fetch_official_csv', lambda *a, **k: ([], [{'strategy': 'OFFICIAL_CSV_EXPORT', 'rows': 0}]))
    monkeypatch.setattr(neu, '_fetch_product_directory', lambda *a, **k: ([], [{'strategy': 'PRODUCT_DIRECTORY_HTML', 'rows': 0}]))
    monkeypatch.setattr(neu, '_fetch_current_json', lambda *a, **k: (neu._parse_rows(payload), payload, [{'strategy': 'CURRENT_JSON_POST', 'rows': 294, 'records_filtered': 294}]))
    monkeypatch.setattr(neu, '_persist_fetch_diagnostics', lambda **kwargs: kwargs)

    class PrimeResp:
        status_code = 200
        url = 'prime'
        headers = {'content-type': 'text/html'}
        text = 'ok'
    class Session:
        def get(self, *a, **k): return PrimeResp()
    import requests
    monkeypatch.setattr(requests, 'Session', lambda: Session())

    out = neu.fetch_official_norway_master(timeout=1)
    assert out['status'] == 'OFFICIAL_LIVE'
    assert out['count'] == 294
    assert out['source'] == 'Euronext current stocks endpoint'
    assert {row['exchange_mic'] for row in out['instruments']} == {'XOSL', 'MERK', 'XOAS'}
