from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from unittest.mock import patch
import pytest
from portfolio_history_optimizer import METHOD_VERSION
from services import history_research_notifications as report

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


class Store:
    def __init__(self):
        self.data, self.reads, self.writes = {}, [], []

    def read_json(self, key, default=None):
        self.reads.append(key)
        return deepcopy(self.data.get(key, default))

    def write_json(self, key, value):
        assert key.startswith(report.PREFIX), 'Only notification evidence may be written'
        self.writes.append(key)
        self.data[key] = deepcopy(value)

    def mutate_json(self, key, fn):
        value = fn(deepcopy(self.data.get(key)))
        self.write_json(key, value)
        return value


def result(ticker='A', engine='AUTONOMY', returns=-2):
    return {'ticker': ticker, 'portfolio': engine, 'method_version': METHOD_VERSION,
            'status': 'COMPLETE_RESEARCH', 'cost_round_trip_pct': .3, 'purge_sessions': 120,
            'scope': 'UNCONDITIONAL_ENTRY_EXIT_GRID_NOT_PORTFOLIO_REPLAY',
            'train_end': '2023-01-01', 'validation_start': '2023-07-01', 'holdout_start': '2025-01-01',
            'finalists': [{'stop_pct': 3, 'hold_sessions': 20, 'holdout': {'trades': 5, 'total_pct': returns}},
                          {'stop_pct': 5, 'hold_sessions': 10, 'holdout': {'trades': 5, 'total_pct': 200}}]}


def populated(count=3):
    store = Store()
    tickers = [f'A{i}' for i in range(count)]
    store.data[report.PROGRESS] = {'method_version': METHOD_VERSION, 'started_at': '2026-10-24T00:00:00+00:00',
        'completed_tickers': tickers, 'processed': count, 'total': count+10, 'status': 'RUNNING', 'updated_at': NOW.isoformat()}
    for ticker in tickers:
        for engine in report.ENGINES:
            store.data[f'strategy_history/optimized/{engine}/{sha256(ticker.encode()).hexdigest()}.json'] = result(ticker, engine)
    return store


def test_holdout_never_selects_the_winning_finalist_after_the_fact():
    source = result()
    measured = report.observation(source, 'A', 'AUTONOMY', METHOD_VERSION)
    assert measured['return_pct'] == -2 and measured['hold_sessions'] == 20
    assert measured['source_sha256'] == report.digest(source)


@pytest.mark.parametrize('change', [
    {'method_version': 'old'}, {'ticker': 'OTHER'}, {'portfolio': 'SUPER_PORTFOLIO'},
    {'scope': 'PORTFOLIO'}, {'cost_round_trip_pct': 0}, {'purge_sessions': 0},
    {'holdout_start': '2022-01-01'}, {'finalists': []},
    {'finalists': [{'stop_pct': 3, 'hold_sessions': 20, 'holdout': {'total_pct': float('nan'), 'trades': 2}}]},
    {'finalists': [{'stop_pct': 3, 'hold_sessions': 20, 'holdout': {'total_pct': 10, 'trades': 0}}]},
])
def test_invalid_or_unrelated_evidence_is_not_positive(change):
    assert report.observation({**result(), **change}, 'A', 'AUTONOMY', METHOD_VERSION)['status'] == 'UNMEASURABLE'


def test_bounded_resume_preserves_source_documents_and_reuses_measurements():
    store = populated(40)
    original = deepcopy(store.data)
    first = report.run_once(service=store, now=NOW, limit=999, notify=False)
    assert first['coverage_processed'] == 32 and first['coverage_pending'] == 8
    assert first['status'] == 'BUILDING' and first['engines']['AUTONOMY']['positive'] == 0
    second = report.run_once(service=store, now=NOW, notify=False)
    assert second['engines']['AUTONOMY']['measured'] == 40 and second['coverage_pending'] == 0
    store.reads.clear()
    third = report.run_once(service=store, now=NOW, notify=False)
    assert third['collected_in_batch'] == 0
    assert not any('/optimized/' in k for k in store.reads)
    assert all(store.data[k] == v for k,v in original.items())
    assert all(k.startswith(report.PREFIX) for k in store.writes)


def test_missing_insufficient_and_unmeasured_are_not_made_up_wins():
    store = populated()
    for engine in report.ENGINES:
        prefix = f'strategy_history/optimized/{engine}/'
        store.data[prefix+sha256(b'A0').hexdigest()+'.json'] = {'ticker': 'A0', 'status': 'INSUFFICIENT_PURGED_PERIODS'}
        del store.data[prefix+sha256(b'A1').hexdigest()+'.json']
    summary = report.run_once(service=store, now=NOW, notify=False)
    assert summary['engines']['AUTONOMY'] == {
        'measured': 1, 'positive': 0, 'negative': 1, 'flat': 0, 'positive_share_pct': 0,
        'insufficient': 1, 'unmeasurable': 1, 'most_selected': {'stop_pct': 3, 'hold_sessions': 20, 'symbols': 1}}
    assert 'For kort/umålbar historikk: 1/1' in report.message(summary)


def test_new_method_cohort_keeps_older_evidence_and_resets_comparison():
    store = populated()
    old = report.run_once(service=store, now=NOW, notify=False)
    original_keys = {k: deepcopy(v) for k,v in store.data.items() if '/indexes/' in k}
    store.data[report.PROGRESS]['started_at'] = NOW.isoformat()
    new = report.run_once(service=store, now=NOW, notify=False)
    assert old['cohort'] != new['cohort']
    assert 'Første tendensmåling' in report.message(new, old)
    assert all(store.data[k] == v for k,v in original_keys.items())


def test_message_reports_progress_and_descriptive_change_with_bounded_footer():
    summary = report.run_once(service=populated(), now=NOW, notify=False)
    previous = deepcopy(summary)
    previous['processed'] = 1
    previous['engines']['AUTONOMY']['positive_share_pct'] = 50
    text = report.message(summary, previous)
    assert '+2 behandlet' in text and 'endring -50.0 pp' in text
    assert all(s in text for s in ('Autonomi:', 'Superporteføljen:', 'ikke portefølje/prognose', '0,30 %', 'Ingen regelendring'))
    assert len(text) + 120 < 1024


def test_delivered_receipt_is_retained_and_duplicate_or_failure_is_not_delivery():
    store = populated()
    summary = report.run_once(service=store, now=NOW, notify=False)
    with patch('notifier.send_pushover_alert', return_value=(True, 'HTTP 200')) as sender:
        assert report.send_daily(service=store, summary=summary, now=NOW)['sent']
        before = deepcopy(store.data)
        assert report.send_daily(service=store, summary=summary, now=NOW)['status'] == 'ALREADY_SENT'
        assert sender.call_count == 1 and before == store.data
    later = NOW+timedelta(days=1)
    with patch('notifier.send_pushover_alert', return_value=(True, 'duplicate suppressed')) as sender:
        assert not report.send_daily(service=store, summary=summary, now=later)['sent']
        assert report.send_daily(service=store, summary=summary, now=later)['status'] == 'RETRY_DEFERRED'
        assert sender.call_count == 1
    with patch('notifier.send_pushover_alert', return_value=(False, 'HTTP 500')):
        assert not report.send_daily(service=store, summary=summary, now=later+timedelta(hours=1))['sent']
    with patch('notifier.send_pushover_alert', return_value=(True, 'HTTP 200')):
        assert report.send_daily(service=store, summary=summary, now=later+timedelta(hours=2))['sent']
    receipt = store.data[report.PREFIX+'deliveries/'+later.date().isoformat()+'.json']
    assert len(receipt['attempts']) == 3 and receipt['attempts'][0]['sent'] is False


def test_oslo_clock_summary_backlog_and_stale_data_are_explicit():
    store = populated()
    summary = report.run_once(service=store, now=NOW, notify=False)
    with patch('notifier.send_pushover_alert', return_value=(True,'HTTP 200')) as sender:
        assert report.send_daily(service=store, summary=summary, now=NOW.replace(hour=6))['status'] == 'NOT_DUE_YET'
        assert report.send_daily(service=store, summary={**summary,'status':'BUILDING'}, now=NOW)['status'] == 'WAITING_FOR_SUMMARY'
        assert not sender.called
        assert report.send_daily(service=store, summary=summary, now=NOW+timedelta(hours=9))['sent']
        assert sender.call_args.args[0].startswith('OBS: Ingen fersk forskningsfremdrift')


def test_notification_job_is_wired_after_real_optimizer():
    from pathlib import Path
    code = Path('scheduled_runner.py').read_text()
    assert code.index('state["portfolio_historical_optimization"] = optimize_history()') < code.index('state["historical_research_notifications"] = notify_history()')
