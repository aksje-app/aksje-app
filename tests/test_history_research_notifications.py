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
            'finalists': [{'stop_pct': 3, 'hold_sessions': 20, 'holdout': {'trades': 5, 'total_pct': returns, 'avg_pct': -.4}},
                          {'stop_pct': 5, 'hold_sessions': 10, 'holdout': {'trades': 5, 'total_pct': 200, 'avg_pct': 24}}]}


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
    assert {k: summary['engines']['AUTONOMY'][k] for k in (
        'measured', 'positive', 'negative', 'flat', 'positive_share_pct',
        'insufficient', 'unmeasurable', 'most_selected')} == {
        'measured': 1, 'positive': 0, 'negative': 1, 'flat': 0, 'positive_share_pct': 0,
        'insufficient': 1, 'unmeasurable': 1, 'most_selected': {'stop_pct': 3, 'hold_sessions': 20, 'symbols': 1}}
    assert '0 av 1 aksjer ga samlet gevinst' in report.message(summary)


def test_new_method_cohort_keeps_older_evidence_and_resets_comparison():
    store = populated()
    old = report.run_once(service=store, now=NOW, notify=False)
    original_keys = {k: deepcopy(v) for k,v in store.data.items() if '/indexes/' in k}
    store.data[report.PROGRESS]['started_at'] = NOW.isoformat()
    new = report.run_once(service=store, now=NOW, notify=False)
    assert old['cohort'] != new['cohort']
    assert 'siden forrige melding' not in report.message(new, old)
    assert all(store.data[k] == v for k,v in original_keys.items())


def test_message_reports_progress_and_descriptive_change_with_bounded_footer():
    summary = report.run_once(service=populated(), now=NOW, notify=False)
    previous = deepcopy(summary)
    previous['processed'] = 1
    previous['engines']['AUTONOMY']['positive_share_pct'] = 50
    text = report.message(summary, previous)
    assert '2 flere aksjer er undersøkt siden forrige melding.' in text
    assert all(s in text for s in ('Autonomi:', 'Superporteføljen:', 'per testhandel', 'tap inkludert', 'Handelsreglene dine er uendret.'))
    assert not any(s in text for s in ('testdel', 'UTC', 'exit-forskning', 'testmetoden', 'umålbar'))
    assert len(text) + 120 < 1024


def test_average_comes_from_arithmetic_trade_average_not_compounded_period_total():
    from portfolio_history_optimizer import _score
    source = result()
    # Gross +10.3%, -9.7% -> net +10%, -10%: mean zero, compounded -1%.
    source['finalists'][0]['holdout'] = _score([10.3, -9.7], 1.5)
    measured = report.observation(source, 'A', 'AUTONOMY', METHOD_VERSION)
    assert measured['return_pct'] == -1
    assert measured['avg_trade_return_pct'] == 0
    assert measured['trades'] == 2


@pytest.mark.parametrize('average', [None, True, float('nan'), float('inf'), 'invalid'])
def test_invalid_trade_average_cannot_be_published(average):
    source = result()
    source['finalists'][0]['holdout']['avg_pct'] = average
    assert report.observation(source, 'A', 'AUTONOMY', METHOD_VERSION)['status'] == 'UNMEASURABLE'


def test_weighted_average_includes_losses_and_combination_sample_sizes():
    store = populated()
    for engine in report.ENGINES:
        for ticker, trades, average, total, stop, hold in (
            ('A0', 2, 10, 21, 3, 20),
            ('A1', 8, -2, -15, 3, 20),
            ('A2', 4, -1, -3.94, 2, 5),
        ):
            source = store.data[f'strategy_history/optimized/{engine}/{sha256(ticker.encode()).hexdigest()}.json']
            source['finalists'][0].update(stop_pct=stop, hold_sessions=hold,
                holdout={'trades': trades, 'avg_pct': average, 'total_pct': total})
    summary = report.run_once(service=store, now=NOW, notify=False)
    row = summary['engines']['AUTONOMY']
    assert row['avg_trade_return_pct'] == pytest.approx(0)
    assert row['trades'] == 14
    assert row['positive'] == 1
    assert row['combinations'] == [
        {'stop_pct': 3, 'hold_sessions': 20, 'symbols': 2, 'trades': 10,
         'avg_trade_return_pct': pytest.approx(.4)},
        {'stop_pct': 2, 'hold_sessions': 5, 'symbols': 1, 'trades': 4,
         'avg_trade_return_pct': pytest.approx(-1)},
    ]
    text = report.message(summary)
    assert '+0,40 % (10 handler, 2 aksjer)' in text
    assert '-1,00 % (4 handler, 1 aksje)' in text
    assert '3 % fall / 20 børsdager' in text
    assert '2 % fall / 5 børsdager' in text
    assert 'ulike aksjer' in text and 'ikke best' in text


def test_previous_indexes_and_deliveries_are_preserved_while_averages_are_recollected():
    store = populated(40)
    cohort = report.digest([METHOD_VERSION, store.data[report.PROGRESS]['started_at']])
    key = report.PREFIX + 'indexes/' + cohort + '.json'
    old = {'cohort': cohort, 'records': {f'A{i}': {e: {'status': 'MEASURED',
        'return_pct': 1, 'trades': 2, 'stop_pct': 3, 'hold_sessions': 20}
        for e in report.ENGINES} for i in range(40)}}
    store.data[key] = deepcopy(old)
    receipt_key = report.PREFIX + 'deliveries/2026-11-08.json'
    store.data[receipt_key] = {'sent': True, 'message': 'old message'}
    summary = report.run_once(service=store, now=NOW, limit=32, notify=False)
    assert summary['status'] == 'BUILDING' and summary['coverage_pending'] == 8
    summary = report.run_once(service=store, now=NOW, notify=False)
    assert summary['engines']['AUTONOMY']['avg_trade_return_pct'] == pytest.approx(-.4)
    assert store.data[key] == old
    assert store.data[receipt_key] == {'sent': True, 'message': 'old message'}


def test_full_message_keeps_both_engines_rules_and_caveats_with_warning_and_footer():
    store = populated()
    for engine in report.ENGINES:
        source = store.data[f'strategy_history/optimized/{engine}/{sha256(b"A0").hexdigest()}.json']
        source['finalists'][0].update(stop_pct=11.5, hold_sessions=120)
    summary = report.run_once(service=store, now=NOW, notify=False)
    with patch('notifier.send_pushover_alert', return_value=(True, 'HTTP 200')):
        report.send_daily(service=store, summary=summary, now=NOW+timedelta(hours=9))
    receipt = store.data[report.PREFIX+'deliveries/2026-11-08.json']
    from notifier import fit_pushover_message
    text = receipt['message']
    assert len(text) + 120 < 1024
    assert fit_pushover_message(text, required_tail='x'*119) == text + '\n' + 'x'*119
    assert all(s in text for s in ('Autonomi:', 'Superporteføljen:', '11,5 % fall / 120 børsdager',
        '0,30 %', 'ulike aksjer', 'ikke årsavkastning', 'Handelsreglene dine er uendret.'))


def test_two_common_rules_fit_with_realistic_counts_progress_warning_and_footer():
    summary = report.run_once(service=populated(), now=NOW, notify=False)
    summary.update(total=1970, processed=890)
    for row in summary['engines'].values():
        row.update(measured=839, positive=628, trades=125000, avg_trade_return_pct=1,
            combinations=[
                {'stop_pct': 2, 'hold_sessions': 5, 'symbols': 113, 'trades': 12345,
                 'avg_trade_return_pct': .84},
                {'stop_pct': 11.5, 'hold_sessions': 120, 'symbols': 101, 'trades': 10000,
                 'avg_trade_return_pct': -.75}])
    text = report.message(summary, {**summary, 'processed': 850})
    warning = 'Testingen har ikke meldt ny fremdrift de siste 8 timene.\n\n'
    assert len(warning + text) + 120 <= 1024
    assert text.count('11,5 % fall / 120 børsdager: -0,75 %') == 2
    assert '40 flere aksjer' in text


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
        assert sender.call_args.args[0].startswith('Testingen har ikke meldt ny fremdrift de siste 8 timene.')


def test_notification_job_is_wired_after_real_optimizer():
    from pathlib import Path
    code = Path('scheduled_runner.py').read_text()
    assert code.index('state["portfolio_historical_optimization"] = optimize_history()') < code.index('state["historical_research_notifications"] = notify_history()')
