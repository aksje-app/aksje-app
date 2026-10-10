"""Bounded anonymous Nordnet public-page adapter, not a supported broker API.

No cookies, credentials or private endpoints. Schema changes fail visibly.
Published returns are screening evidence; never reconstructed daily history.
"""
from datetime import datetime, timezone
import json
import math
import re
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

ORIGIN = 'https://www.nordnet.no'
MAX_RESPONSE = 5 * 1024 * 1024


def fetch(url):
    request = Request(url, headers={'User-Agent': 'SuperfundResearch/1.0', 'Accept': 'text/html,application/xml'})
    with urlopen(request, timeout=12) as response:
        data = response.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise ValueError('Kilden overskrider svarbudsjettet')
    return data.decode('utf-8')


def embedded(text, name):
    marker = 'window.' + name + '='
    if marker not in text:
        raise ValueError('Offentlig side har endret skjema: ' + name)
    value, _ = json.JSONDecoder().raw_decode(text.split(marker, 1)[1].lstrip())
    return json.loads(value) if isinstance(value, str) else value


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def timestamp(value):
    n = number(value)
    return datetime.fromtimestamp(n / 1000, timezone.utc).isoformat() if n else None


def catalog_page(kind, page, getter=fetch):
    if kind not in ('fond', 'etf') or not 1 <= page <= 60:
        raise ValueError('Ugyldig katalogside')
    url = ORIGIN + '/' + kind + '/liste?' + urlencode({'page': page, 'sortField': 'name', 'sortOrder': 'asc'})
    state = embedded(getter(url), '__initialState__')
    data = state['Api']['/api/2/instrument_search/query/{type}']['data']
    matches = [v for k, v in data.items() if k.startswith('fundlist?' if kind == 'fond' else 'etflist?')]
    if len(matches) != 1 or not isinstance(matches[0].get('results'), list):
        raise ValueError('Ingen entydig offentlig fondsliste')
    block = matches[0]
    return {'total': int(block['total_hits']), 'rows': block['results'], 'url': url, 'page': page, 'kind': kind}


def normalize(row, kind, observed_at):
    info, fund, price = row.get('instrument_info', {}), row.get('fund_info', {}), row.get('price_info', {})
    nnx = row.get('nnx_info', {})
    isin = str(info.get('isin') or '')
    if not re.fullmatch('[A-Z]{2}[A-Z0-9]{10}', isin):
        raise ValueError('Mangler gyldig ISIN')
    name = str(info.get('long_name') or info.get('name') or isin)
    asset = str(fund.get('fund_type') or '')
    native = str(info.get('currency') or '')
    # Categories are deliberately not invented when the source is incomplete.
    row_id = isin + ':' + str(row.get('market_info', {}).get('market_id', 'fund'))
    return {'id': row_id, 'isin': isin, 'name': name, 'kind': kind,
            'currency': native, 'category': str(fund.get('fund_category') or 'UKJENT'),
            'asset': asset, 'risk': number(fund.get('fund_raw_risk')),
            'cost_pct': number(fund.get('fund_total_fee')),
            'price': number(price.get('last', {}).get('price')),
            'price_at': timestamp(price.get('tick_timestamp')), 'observed_at': observed_at,
            'bid': number(price.get('bid', {}).get('price')), 'ask': number(price.get('ask', {}).get('price')),
            'spread_pct': number(price.get('spread_pct')), 'volume': number(price.get('turnover_volume')),
            'tradable': info.get('is_tradable') is True,
            'returns': {k: number(v) for k, v in row.get('historical_returns_info', {}).items() if k.startswith('yield_')},
            'returns_currency': str(fund.get('fund_universe_currency') or native),
            'returns_currency_source': 'SOURCE' if fund.get('fund_universe_currency') else 'INSTRUMENT_CURRENCY_FALLBACK' if native else 'UNKNOWN',
            'distribution': str(fund.get('fund_dividend_strategy') or 'UKJENT'),
            'complex': bool(re.search(r'\b(inverse|leveraged|short|2x|3x|daily bull|daily bear)\b', name, re.I)),
            'url': ORIGIN + '/' + kind + '/liste/' + str(nnx.get('display_slug') or ''),
            'source': 'Nordnet offentlig produktside', 'coverage': 'PUBLIC_LIST',
            'instrument_class': str(nnx.get('instrument_class') or '')}


def details(item, getter=fetch):
    url = item['url']
    if not url.startswith(ORIGIN + '/' + item['kind'] + '/liste/'):
        raise ValueError('Ugyldig produktlenke')
    props = embedded(getter(url), '__initialProps__')['initialProps']
    data = props.get('orderBookBffData') or props.get('sharedInitialProps', {}).get('initialFundData')
    if not isinstance(data, dict):
        raise ValueError('Mangler offentlig produktdetalj')
    detail = data.get('details', {})
    exposure = data.get('exposures', {})
    return {'verified_at': datetime.now(timezone.utc).isoformat(),
            'ucits': detail.get('ucits'), 'description': detail.get('description', ''),
            'trading': detail.get('tradingInfo', {}),
            'benchmark': detail.get('morningstarValues', {}).get('benchmark', {}),
            'documents': detail.get('documents', {}), 'company': detail.get('fundCompany', {}),
            'holdings': exposure.get('holdings', [])[:30], 'exposure_at': exposure.get('updatedAt'),
            'sectors': exposure.get('sectors', [])[:30], 'regions': exposure.get('regions', [])[:30],
            'news': data.get('newsPreviews', {}).get('news', [])[:10],
            'risk_statistics': data.get('risksStatistics', {}), 'source_url': url}


def fx_history(getter=fetch):
    # ECB reference rates: units of each currency per EUR, not executable quotes.
    url = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml'
    root = ET.fromstring(getter(url))
    days = {}
    for node in root.iter():
        if 'time' in node.attrib:
            rates = {'EUR': 1.0}
            for child in node:
                n = number(child.attrib.get('rate'))
                if n and n > 0:
                    rates[child.attrib.get('currency')] = n
            if 'NOK' in rates:
                days[node.attrib['time']] = rates
    if not days:
        raise ValueError('Ingen ECB valutadata')
    return {'source': url, 'days': days}


def nok_rate(currency, price_at, fx):
    if currency == 'NOK':
        return 1.0
    day = str(price_at or '')[:10]
    dates = [d for d in fx.get('days', {}) if d <= day]
    if not dates:
        return None
    chosen = max(dates)
    if (datetime.fromisoformat(day) - datetime.fromisoformat(chosen)).days > 5:
        return None
    rates = fx['days'][chosen]
    return rates['NOK'] / rates[currency] if rates.get(currency) else None
