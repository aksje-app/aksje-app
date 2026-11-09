from datetime import datetime, timezone
from services.learning_progress import snapshot, KEYS


def test_streams_and_maturity_are_separate_and_stale_pass_is_visible():
    data = {
        KEYS['baseline']: {'signal_count': 1382, 'analysis': {'matured_count': 0, 'horizons': [
            {'horizon_days': 5, 'return': {'count': 1382, 'average': -1.1}, 'excess_return': {'average': -1.0}}]}},
        KEYS['acceptance']: {'evaluated_at': '2026-11-02T07:16:13Z', 'operational_verdict': 'PASS',
                             'strategy_readiness': 'NOT_VALIDATED', 'strategy_quality_gate': {'mature_closed_positions': 0}},
        KEYS['history']: {'gaps': 3, 'records': [
            {'status': 'READY', 'engine': 'AUTONOMY', 'at': '2026-10-29', 'complete_universe': False},
            {'status': 'MISSING', 'engine': 'SUPER_PORTFOLIO', 'at': '2026-10-30'}]},
    }
    report = snapshot(lambda key: data.get(key), now=datetime(2026, 11, 5, tzinfo=timezone.utc))
    assert report['historical_reference_horizons'][0]['measured_count'] == 1382
    assert report['current_mature_positions'] == 0
    assert report['acceptance_fresh'] is False
    assert report['replay_streams']['AUTONOMY']['frames'] == 1
    assert report['replay_streams']['SUPER_PORTFOLIO']['frames'] == 0
    assert report['reported_archive_gaps'] == 3
    assert report['can_authorize_buy'] is False


def test_missing_documents_do_not_create_zero_performance_evidence():
    report = snapshot(lambda key: None)
    assert report['historical_signal_count'] is None
    assert report['acceptance_fresh'] is False
    assert report['strategy_readiness'] == 'UNKNOWN'
