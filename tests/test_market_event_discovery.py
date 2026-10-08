import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
import market_event_discovery as ev

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def borr():
    return json.loads((Path(__file__).parent/'fixtures/market_events/borr_683610.json').read_text())['data']['message']


def test_real_borr_primary_disclosure_replay_before_finalists():
    message = borr()
    event, = ev.insider_events([message], {str(message['id']): message}, NOW)
    assert event['kind'] == 'INSIDER_PURCHASE'
    assert event['actor'] == 'Drew Holdings Ltd.'
    assert event['related_person'] == 'Mr. Trøim'
    assert event['quantity'] == 1500000 and event['price'] == 4.1314
    universe = [{'ticker': 'BORR.OL'}, {'ticker': 'TOP.OL'}]
    mapped = ev.candidate_events(universe, {'events': [event]}, NOW)
    rows = ev.prioritize_analysis([{'ticker': 'TOP.OL', 'investment_score': 99}], universe, mapped, 2)
    assert rows[0]['ticker'] == 'BORR.OL'
    assert 'investment_score' not in rows[0]  # No invented bullish score.
    assert rows[1]['investment_score'] == 99


def test_purchase_clusters_dedupe_and_separate_currency():
    message = borr()
    event, = ev.insider_events([message], {str(message['id']): message}, NOW)
    second = {**event, 'id': 'second', 'currency': 'NOK'}
    clusters = ev.purchase_clusters([event, event, second], NOW)
    assert len(clusters) == 2
    assert all(c['purchases_90d'] == 1 for c in clusters)
    assert {c['currency'] for c in clusters} == {'USD', 'NOK'}


@pytest.mark.parametrize('body', ['Drew Holdings Ltd. has exercised options.', 'Drew Holdings Ltd. has purchased 1,500,000 shares at an average price of USD 4.1314 per share. Redelivery of borrowed shares.'])
def test_options_and_borrowed_shares_not_classified_as_purchase(body):
    message = {**borr(), 'body': body}
    event, = ev.insider_events([message], {str(message['id']): message}, NOW)
    assert event['kind'] == 'INSIDER_NOTIFICATION'


def test_future_and_superseded_notifications_excluded():
    message = borr()
    assert not ev.insider_events([{**message, 'publishedTime': '2026-10-09T10:00:00Z'}], {}, NOW)
    assert not ev.insider_events([{**message, 'correctedByMessageId': 123}], {}, NOW)


def short_history():
    def position(actor, pct): return {'positionHolder': actor, 'shortPercent': pct}
    return [{'isin': 'TESTISIN', 'issuerName': 'Example', 'events': [
        {'date': '2026-10-01', 'shortPercent': 1, 'activePositions': [position('A', 1)]},
        {'date': '2026-10-02', 'shortPercent': 2, 'activePositions': [position('A', 1.5), position('B', .5)]},
        {'date': '2026-10-03', 'shortPercent': .8, 'activePositions': [position('A', .8)]}]}]


def test_short_actor_changes_and_unknown_exit_not_zero():
    events = ev.short_events(short_history(), NOW)
    assert {e['kind'] for e in events} == {'SHORT_INCREASE', 'SHORT_REDUCTION', 'SHORT_NEW_PUBLIC_POSITION', 'SHORT_BELOW_PUBLIC_THRESHOLD_OR_UNKNOWN'}
    exit_event = next(e for e in events if 'UNKNOWN' in e['kind'])
    assert exit_event['actor'] == 'B' and exit_event['current_pct'] is None
    assert all(e['metric'] == 'PUBLIC_DISCLOSED_SHORT_POSITION' for e in events)
    assert not ev.short_events([{**short_history()[0], 'events': short_history()[0]['events'][:1]}], NOW)


def test_ambiguous_names_never_route_and_isin_can_resolve():
    universe = [{'ticker': 'A.OL', 'name': 'Example', 'isin': 'TESTISIN'}, {'ticker': 'B.OL', 'name': 'Example'}]
    events = ev.short_events(short_history(), NOW)
    assert set(ev.candidate_events(universe, {'events': events}, NOW)) == {'A.OL'}
    assert ev.candidate_events(universe, {'events': [{**events[0], 'isin': ''}]}, NOW) == {}


def test_reserve_bounded_and_bearish_events_also_analyzed():
    universe = [{'ticker': f'{i}.OL'} for i in range(100)]
    mapped = {r['ticker']: [{'kind': 'SHORT_INCREASE', 'occurred_at': NOW.isoformat()}] for r in universe[50:]}
    rows = ev.prioritize_analysis(universe[:20], universe, mapped, 20, reserve=3)
    assert len(rows) == 20
    assert sum(bool(r.get('official_market_events')) for r in rows) == 3
    assert len({r['ticker'] for r in rows}) == 20


class MemoryStorage:
    def __init__(self, value=None): self.value = value or {}
    def read_json(self, key, default): return self.value
    def mutate_json(self, key, transform, default): self.value = transform(self.value); return self.value


def test_source_failure_retains_evidence_and_does_not_mean_empty():
    message = borr()
    event, = ev.insider_events([message], {str(message['id']): message}, NOW)
    storage = MemoryStorage({'events': [event], 'sources': {'insider': {'last_success_at': '2026-10-07'}}})
    def fail(*args, **kwargs): raise TimeoutError()
    state = ev.refresh_events(now=NOW, storage=storage, request_json=fail)
    assert state['events'] == [event]
    assert state['sources']['insider']['status'] == 'UNAVAILABLE'
    assert state['sources']['insider']['last_success_at'] == '2026-10-07'
    assert ev.refresh_events(now=NOW+timedelta(minutes=1), storage=storage, request_json=fail) == state


def test_refresh_classification_not_downgraded_and_correction_replaces_original():
    message = borr()
    storage = MemoryStorage()
    def fetch(url, **kwargs):
        if url == ev.SHORT_API: return short_history()
        if '/list?' in url: return {'messages': [message], 'overflow': False}
        return {'message': message}
    first = ev.refresh_events(now=NOW, storage=storage, request_json=fetch)
    second = ev.refresh_events(now=NOW+timedelta(hours=1), storage=storage, request_json=fetch)
    assert [e for e in first['events'] if e.get('message_id')] == [e for e in second['events'] if e.get('message_id')]
    message = {**message, 'id': 999, 'messageId': 999, 'correctionForMessageId': 683610, 'body': 'Correction: transfer.'}
    state = ev.refresh_events(now=NOW+timedelta(hours=2), storage=storage, request_json=fetch)
    assert {e['message_id'] for e in state['events'] if e.get('message_id')} == {'999'}


def test_pipeline_analyzes_borr_outside_coarse_rank_without_finalist_boost(monkeypatch):
    import investment_pipeline as ip
    import super_portfolio as sp
    message = borr()
    events = ev.insider_events([message], {str(message['id']): message}, NOW)
    universe = [{'ticker': 'TOP.OL'}, {'ticker': 'BORR.OL'}]
    analyzed = []
    monkeypatch.setattr(ip, '_load_candidate_rows_from_app', lambda cfg: (universe, 'fixture'))
    monkeypatch.setattr(sp, '_coarse_rank_market_rows', lambda *a, **k: [universe[0]])
    def prepare(rows, *a, **k):
        analyzed.extend(r['ticker'] for r in rows)
        return [{**r, 'last_price': 100, 'risk_score': 20} for r in rows]
    monkeypatch.setattr(ip, '_prepare_candidate_rows', prepare)
    monkeypatch.setattr(ip, 'score_candidate', lambda row, cfg: SimpleNamespace(ticker=row['ticker'], market='Norge', investment_score=40 if row['ticker']=='BORR.OL' else 80, risk_score=20, data_quality=90, raw=row))
    monkeypatch.setattr(sp, '_bounded_insider_checks', lambda *a: {})
    monkeypatch.setattr(sp, 'write_json', lambda *a: None)
    cfg = sp.SuperPortfolioConfig(market_scopes=('Norge',), market_coarse_shortlist_per_market=2, market_deep_analysis_per_market=2, market_candidates_per_market=1)
    result = sp.build_super_portfolio_market_pipeline(cfg, now=NOW, event_state={'events': events})
    assert 'BORR.OL' in analyzed
    assert [c['ticker'] for c in result['candidates']] == ['TOP.OL']
    analysis, = result['summary']['official_event_discovery']['analysis']
    assert analysis['status'] == 'ANALYZED' and analysis['finalist'] is False


def test_new_event_invalidates_fresh_pipeline_cache(monkeypatch):
    import super_portfolio as sp
    message = borr()
    events = ev.insider_events([message], {str(message['id']): message}, NOW)
    cached = {'created_at': NOW.isoformat(), 'candidates': [{'ticker': 'TOP.OL'}], 'summary': {'event_universe': [{'ticker': 'BORR.OL'}], 'official_event_discovery': {'event_ids': []}}}
    monkeypatch.setattr(sp, 'load_latest_super_portfolio_market_pipeline', lambda: cached)
    monkeypatch.setattr(sp, '_refresh_official_events', lambda now: {'events': events})
    monkeypatch.setattr(sp, 'build_super_portfolio_market_pipeline', lambda *a, **k: {'rebuilt': True})
    assert sp.get_or_build_super_portfolio_market_pipeline(now=NOW)['rebuilt']
    cached['summary']['official_event_discovery']['event_ids'] = [events[0]['id']]
    cached['summary']['official_event_discovery']['event_revision'] = ev.event_revision({'BORR.OL': events})
    assert sp.get_or_build_super_portfolio_market_pipeline(now=NOW) is cached


def test_partial_feed_and_detail_budget_are_reported():
    message = borr()
    messages = [{**message, 'id': i, 'messageId': i} for i in range(100, 120)]
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        if url == ev.SHORT_API: return []
        if '/list?' in url: return {'messages': messages, 'overflow': True}
        mid = int(url.rsplit('=', 1)[1])
        return {'message': {**message, 'id': mid, 'messageId': mid}}
    state = ev.refresh_events(now=NOW, storage=MemoryStorage(), request_json=fetch)
    assert len(calls) == ev.MAX_DETAILS + 2
    assert state['sources']['insider']['status'] == 'PARTIAL'
    assert len(state['events']) == 20
    assert state['sources']['insider']['remaining_details'] == 14


def test_events_do_not_override_real_entry_persistence_gate():
    import super_portfolio as sp
    row = {'ticker': 'BORR.OL', 'price': 100, 'investment_score': 90,
           'quality_score': 95, 'risk_score': 20, 'market': 'Norge', 'sector': 'Energy',
           'raw': {'volatility_pct': 20, 'return_5d': 3},
           'official_market_events': [{'kind': 'INSIDER_PURCHASE'}]}
    state = {'risk_reentry_confirmation': {'OLD.OL': {}}, 'candidate_persistence': {}}
    allowed, gates, _ = sp._candidate_entry_gates(state=state, proposed_rows=[row], ranked=[row], previous={},
        pipeline={'run_id': 'NEW', 'created_at': NOW.isoformat()}, config=sp.SuperPortfolioConfig(),
        now=NOW, regime_policy={})
    assert not allowed
    assert 'PERSISTENCE_GATE_BLOCKED' in gates['BORR.OL']['reason_codes']


def test_observation_after_replay_time_cannot_leak_future_evidence():
    event = ev.short_events(short_history(), NOW)[0]
    assert not ev.candidate_events([{'ticker': 'A.OL', 'isin': 'TESTISIN'}], {'events': [event]}, NOW-timedelta(hours=1))


def test_short_correction_has_stable_identity_for_actor_and_event_date():
    event = ev.short_events(short_history(), NOW)[0]
    assert ev.event_id(event) == ev.event_id({**event, 'current_pct': 1.9, 'kind': 'SHORT_REDUCTION'})


def test_invalidated_original_removed_when_replacement_not_in_feed():
    message = borr()
    event, = ev.insider_events([message], {str(message['id']): message}, NOW)
    def fetch(url, **kwargs):
        if url == ev.SHORT_API: return []
        return {'messages': [{**message, 'correctedByMessageId': 999}], 'overflow': False}
    state = ev.refresh_events(now=NOW, storage=MemoryStorage({'events': [event]}), request_json=fetch)
    assert not state['events']


def test_failed_details_rotate_so_other_notifications_are_not_starved():
    message = borr()
    messages = [{**message, 'id': i, 'messageId': i} for i in range(100, 112)]
    details = []
    def fetch(url, **kwargs):
        if url == ev.SHORT_API: return []
        if '/list?' in url: return {'messages': messages, 'overflow': False}
        details.append(int(url.rsplit('=', 1)[1])); raise TimeoutError()
    storage = MemoryStorage()
    ev.refresh_events(now=NOW, storage=storage, request_json=fetch)
    ev.refresh_events(now=NOW+timedelta(hours=1), storage=storage, request_json=fetch)
    assert len(set(details)) == 12


def test_same_day_short_change_invalidates_cache_without_new_event_identity(monkeypatch):
    import super_portfolio as sp
    event = ev.short_events(short_history(), NOW)[0]
    old = {'A.OL': [event]}
    cached = {'created_at': NOW.isoformat(), 'candidates': [{'ticker': 'A.OL'}],
              'summary': {'event_universe': [{'ticker': 'A.OL', 'isin': 'TESTISIN'}],
                          'official_event_discovery': {'event_ids': [event['id']], 'event_revision': ev.event_revision(old)}}}
    updated = {**event, 'current_pct': 1.9}
    assert ev.event_id(event) == ev.event_id(updated)
    monkeypatch.setattr(sp, 'load_latest_super_portfolio_market_pipeline', lambda: cached)
    monkeypatch.setattr(sp, '_refresh_official_events', lambda now: {'events': [updated]})
    monkeypatch.setattr(sp, 'build_super_portfolio_market_pipeline', lambda *a, **k: {'rebuilt': True})
    assert sp.get_or_build_super_portfolio_market_pipeline(now=NOW)['rebuilt']
    assert ev.event_revision(old) == ev.event_revision({'A.OL': [{**event, 'observed_at': '2026-10-08T11:59:00Z'}]})
