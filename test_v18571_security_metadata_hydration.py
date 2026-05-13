from security_metadata import resolve_security_metadata, display_label
from services.universe_service import UniverseService
from universe_engine import candidate_from_score_item
from analysis_universe_ai import _smart_result_dataframe


class DummyState:
    def __init__(self):
        self.data = {}
    def get(self, key, default=None):
        return self.data.get(key, default)
    def set(self, key, value):
        self.data[key] = value
    def get_first(self, keys, default=None):
        for key in keys:
            if key in self.data:
                return self.data[key]
        return default


class DummyStorage:
    def read_json(self, *args, **kwargs):
        return kwargs.get('default')
    def write_json(self, *args, **kwargs):
        return True


def test_stock_metadata_resolves_name_sector_risk_when_row_only_has_ticker():
    meta = resolve_security_metadata('AAPL', {'ticker': 'AAPL', 'name': 'AAPL', 'sector': 'Unknown', 'risk': 'Ukjent'})
    assert meta['name'] == 'Apple Inc.'
    assert meta['sector'] == 'Technology'
    assert meta['risk'] == 'Lav'
    assert display_label('AAPL') == 'AAPL — Apple Inc.'


def test_fund_metadata_resolves_high_yield_etf_name_not_generic_type():
    meta = resolve_security_metadata('SHYG', {'ticker': 'SHYG', 'name': 'High yield-fond'})
    assert meta['name'] == 'High yield-fond' or 'iShares' in meta['name']
    assert meta['sector'] == 'High yield credit'
    assert meta['risk'] == 'Høy'


def test_picker_rows_are_hydrated_without_running_heavy_scan():
    service = UniverseService(state_service=DummyState(), storage_service=DummyStorage())
    result = service.resolve_picker({'mode': 'Manuell liste', 'manual_list': 'AAPL, MSFT', 'max_count': 2})
    rows = result.data['result']['candidates']
    assert rows[0]['name'] == 'Apple Inc.'
    assert rows[0]['sector'] == 'Technology'
    assert rows[0]['risk'] == 'Lav'
    assert rows[1]['name'] == 'Microsoft Corporation'


def test_smart_candidate_and_dataframe_are_hydrated():
    candidate = candidate_from_score_item('AAPL', {'ticker': 'AAPL', 'score': 7, 'sector': 'Unknown', 'risk': 'Ukjent'})
    assert candidate.name == 'Apple Inc.'
    assert candidate.sector == 'Technology'
    assert candidate.risk == 'Lav'
    df = _smart_result_dataframe({'candidates': [candidate.as_dict()]})
    assert df.loc[0, 'Navn'] == 'Apple Inc.'
    assert df.loc[0, 'Sektor'] == 'Technology'
    assert df.loc[0, 'Risiko'] == 'Lav'
