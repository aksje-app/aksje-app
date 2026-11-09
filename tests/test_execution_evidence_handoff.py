from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from services import production_routing as routing
import scanner_fresh_quote as quotes


NOW = datetime(2026, 11, 9, 13, 10, tzinfo=timezone.utc)
POLICY = {'source_ref': 'ISOLATED TEST POLICY', 'components_per_fill':
          {'brokerage_nok': 6, 'fx_cost_nok': 0, 'other_nok': 0}}


def chosen(held=None):
    return {'pointer': {'family': 'autonomy', 'period_id': 'test'},
            'approval': {'period_id': 'test', 'cost_policy': POLICY},
            'bundle': {'accounts': {'autonomy': {
                'account': {'positions': held or {}}, 'events': [], 'status': 'ACTIVE',
                'opening_sha256': 'opening', 'approval': {'scope': 'production'}}}}}


def raw_quote(at=NOW):
    return {'price': 100, 'market_data_at': at.isoformat(),
            'source': 'yfinance 1m Close', 'adjustment': 'raw'}


def no_network(monkeypatch):
    import yfinance
    monkeypatch.setattr(yfinance, 'Ticker', lambda _: (_ for _ in ()).throw(
        OSError('provider unavailable https://provider.invalid/?apikey=SECRET')))
    monkeypatch.setattr(quotes, '_intraday_history', lambda *a, **k: (_ for _ in ()).throw(
        OSError('provider unavailable')))


def test_wrapped_documented_currency_and_raw_quote_survive_metadata_provider_outage(monkeypatch):
    no_network(monkeypatch)
    rows = [{'ticker': 'MORLD.OL', 'raw': {'ticker': 'MORLD.OL', 'currency': 'NOK',
                                          'execution_quote': raw_quote()}}]
    before = deepcopy(rows)
    result = routing.context('autonomy', 'run', rows, chosen=chosen(), at=NOW.isoformat())
    assert result['evidence']['MORLD.OL']['price'] == 100
    assert result['evidence']['MORLD.OL']['currency'] == 'NOK'
    assert result['evidence_blocks'] == []
    assert rows == before


def test_nested_currency_cannot_be_inherited_from_another_instrument(monkeypatch):
    no_network(monkeypatch)
    rows = [{'ticker': 'MORLD.OL', 'execution_quote': raw_quote(),
             'raw': {'ticker': 'AAPL', 'currency': 'USD'}}]
    result = routing.context('autonomy', 'run', rows, chosen=chosen(), at=NOW.isoformat())
    assert result['evidence'] == {}
    assert result['evidence_blocks'][0]['reason_code'] == 'INSTRUMENT_IDENTITY_MISMATCH'


def test_stale_daily_mark_is_not_promoted_to_execution_evidence(monkeypatch):
    no_network(monkeypatch)
    rows = [{'ticker': 'MORLD.OL', 'raw': {'ticker': 'MORLD.OL', 'currency': 'NOK',
             'last_price': 100, 'latest_trade_timestamp': NOW.isoformat(), 'market_bar_interval': '1d'}}]
    result = routing.context('autonomy', 'run', rows, chosen=chosen(), at=NOW.isoformat())
    assert result['evidence'] == {}
    block = result['evidence_blocks'][0]
    assert block['reason_code'] == 'MISSING_EXECUTION_QUOTE'
    assert 'intradagkurs' in block['reason']
    assert 'SECRET' not in str(block)


def test_currency_lookup_failure_is_distinguished_from_missing_price(monkeypatch):
    no_network(monkeypatch)
    rows = [{'ticker': 'MORLD.OL', 'execution_quote': raw_quote()}]
    result = routing.context('autonomy', 'run', rows, chosen=chosen(), at=NOW.isoformat())
    assert result['evidence_blocks'][0]['reason_code'] == 'MISSING_INSTRUMENT_CURRENCY'
    assert 'SECRET' not in str(result)


def test_batch_does_not_treat_a_later_fresh_quote_as_future(monkeypatch):
    clock = SimpleNamespace(at=NOW)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.at
    monkeypatch.setattr(routing, 'datetime', Clock)
    def fetch(ticker, interval='5m'):
        at = clock.at
        if ticker == 'A.OL':
            clock.at = NOW + timedelta(minutes=2)
        return pd.DataFrame({'Close': [100.]}, index=pd.DatetimeIndex([at]))
    monkeypatch.setattr(quotes, '_intraday_history', fetch)
    rows = [{'ticker': t, 'currency': 'NOK'} for t in ('A.OL', 'B.OL')]
    result = routing.context('autonomy', 'run', rows, chosen=chosen())
    assert set(result['evidence']) == {'A.OL', 'B.OL'}
    assert result['at'] == '2026-11-09T13:12:00+00:00'
    assert result['evidence_blocks'] == []


def test_first_quote_cannot_expire_while_later_quotes_are_collected(monkeypatch):
    clock = SimpleNamespace(at=NOW)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.at
    monkeypatch.setattr(routing, 'datetime', Clock)
    def fetch(ticker, interval='5m'):
        if ticker == 'B.OL':
            clock.at = NOW + timedelta(minutes=16)
        return pd.DataFrame({'Close': [100.]}, index=pd.DatetimeIndex([clock.at]))
    monkeypatch.setattr(quotes, '_intraday_history', fetch)
    rows = [{'ticker': t, 'currency': 'NOK'} for t in ('A.OL', 'B.OL')]
    result = routing.context('autonomy', 'run', rows, chosen=chosen())
    assert set(result['evidence']) == {'B.OL'}
    assert result['evidence_blocks'][0]['ticker'] == 'A.OL'
    assert result['evidence_blocks'][0]['reason_code'] == 'EXPIRED_EXECUTION_QUOTE'


def test_live_clock_advances_during_the_first_provider_request(monkeypatch):
    clock = SimpleNamespace(at=NOW)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.at
    monkeypatch.setattr(routing, 'datetime', Clock)
    def fetch(ticker, interval='5m'):
        clock.at = NOW + timedelta(minutes=6)
        return pd.DataFrame({'Close': [100.]}, index=pd.DatetimeIndex([clock.at]))
    monkeypatch.setattr(quotes, '_intraday_history', fetch)
    result = routing.context('autonomy', 'run', [{'ticker': 'A.OL', 'currency': 'NOK'}], chosen=chosen())
    assert result['evidence_blocks'] == []
    assert result['evidence']['A.OL']['observed_at'] == '2026-11-09T13:16:00+00:00'
    assert result['at'] == '2026-11-09T13:16:00+00:00'


def test_missing_quote_for_an_existing_holding_still_fails_closed(monkeypatch):
    no_network(monkeypatch)
    with pytest.raises(ValueError):
        routing.context('autonomy', 'run', [], chosen=chosen({'MORLD.OL': {'currency': 'NOK'}}),
                        at=NOW.isoformat())


def test_live_preview_uses_the_same_documented_wrapper_fields(monkeypatch):
    from services import simulation_restart, restart_trading, trading_costs
    no_network(monkeypatch)
    current = datetime.now(timezone.utc)
    class Store:
        def read_json(self, key):
            return chosen()['bundle']
    monkeypatch.setattr(simulation_restart, 'verify_bundle', lambda value: None)
    monkeypatch.setattr(routing, 'strategy_settings', lambda *a, **kw: {})
    monkeypatch.setattr(trading_costs, 'validate_family', lambda *a: None)
    monkeypatch.setattr(restart_trading, 'preview', lambda **kw: {'evidence': kw['evidence']})
    result = routing.live_preview('test', 'autonomy', cost_policy=POLICY, storage=Store(),
        strategy_input=[{'ticker': 'MORLD.OL', 'raw': {'ticker': 'MORLD.OL', 'currency': 'NOK',
                                                    'execution_quote': raw_quote(current)}}])
    assert result['evidence']['MORLD.OL']['price'] == 100
    assert result['preflight_excluded_candidates'] == []


def test_fx_failure_stays_blocked_with_a_specific_reason(monkeypatch):
    no_network(monkeypatch)
    result = routing.context('autonomy', 'run', [{'ticker': 'AAPL', 'currency': 'USD',
        'execution_quote': raw_quote()}], chosen=chosen(), at=NOW.isoformat())
    assert result['evidence'] == {}
    assert result['evidence_blocks'][0]['reason_code'] == 'MISSING_FX_QUOTE'


def test_unknown_provider_error_cannot_leak_credentials_into_a_receipt(monkeypatch):
    monkeypatch.setattr(routing, 'market_evidence', lambda *a, **kw: (_ for _ in ()).throw(
        OSError('https://provider.invalid?apikey=SECRET')))
    result = routing.context('autonomy', 'run', [{'ticker': 'AAPL'}],
                             chosen=chosen(), at=NOW.isoformat())
    assert result['evidence'] == {}
    assert result['evidence_blocks'][0]['reason_code'] == 'EXECUTION_EVIDENCE_ERROR'
    assert 'OSError' in result['evidence_blocks'][0]['reason']
    assert 'SECRET' not in str(result)


def test_nested_documented_fx_survives_provider_outage(monkeypatch):
    no_network(monkeypatch)
    rows = [{'ticker': 'AAPL', 'raw': {'ticker': 'AAPL', 'currency': 'USD',
        'execution_quote': raw_quote(), 'fx_quote': {'currency': 'USD', 'base_currency': 'NOK',
        'rate': 10, 'observed_at': NOW.isoformat(), 'source': 'ISOLATED FX'}}}]
    result = routing.context('autonomy', 'run', rows, chosen=chosen(), at=NOW.isoformat())
    assert result['evidence']['AAPL']['fx_quote']['rate'] == 10
    assert result['evidence_blocks'] == []


def test_fx_can_expire_even_when_the_stock_quote_is_still_fresh(monkeypatch):
    clock = SimpleNamespace(at=NOW)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.at
    monkeypatch.setattr(routing, 'datetime', Clock)
    def fetch(ticker, interval='5m'):
        clock.at = NOW + timedelta(minutes=6)
        return pd.DataFrame({'Close': [100.]}, index=pd.DatetimeIndex([clock.at]))
    monkeypatch.setattr(quotes, '_intraday_history', fetch)
    rows = [{'ticker': 'AAPL', 'currency': 'USD', 'execution_quote': raw_quote(),
             'fx_quote': {'currency': 'USD', 'base_currency': 'NOK', 'rate': 10,
                          'observed_at': (NOW-timedelta(minutes=10)).isoformat(), 'source': 'ISOLATED FX'}},
            {'ticker': 'B.OL', 'currency': 'NOK'}]
    result = routing.context('autonomy', 'run', rows, chosen=chosen())
    assert set(result['evidence']) == {'B.OL'}
    assert result['evidence_blocks'][0]['reason_code'] == 'INVALID_FX_QUOTE'


def test_paper_batch_does_not_skip_a_quote_that_expires_before_execution(monkeypatch):
    clock = SimpleNamespace(at=NOW)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.at
    monkeypatch.setattr(routing, 'datetime', Clock)
    def fetch(ticker, interval='5m'):
        clock.at = NOW + timedelta(minutes=16)
        return pd.DataFrame({'Close': [100.]}, index=pd.DatetimeIndex([clock.at]))
    monkeypatch.setattr(quotes, '_intraday_history', fetch)
    selected = chosen()
    selected['pointer']['family'] = 'paper'
    selected['bundle']['accounts']['paper'] = selected['bundle']['accounts'].pop('autonomy')
    rows = [{'ticker': 'A.OL', 'currency': 'NOK', 'execution_quote': raw_quote()},
            {'ticker': 'B.OL', 'currency': 'NOK'}]
    with pytest.raises(routing.ExecutionEvidenceError) as error:
        routing.context('paper', 'run', rows, chosen=selected)
    assert error.value.code == 'EXPIRED_EXECUTION_QUOTE'
