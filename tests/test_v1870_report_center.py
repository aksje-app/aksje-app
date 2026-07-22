from pathlib import Path

import market_intelligence as mi


def test_report_archive_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, 'REPORT_ARCHIVE_PATH', tmp_path / 'archive.json')
    monkeypatch.setattr(mi, 'RUNS_DIR', tmp_path / 'runs')
    monkeypatch.setattr(mi, 'ROOT', tmp_path)
    run = {
        'run_id': 'MI-TEST', 'created_at': '2026-07-20T08:00:00+00:00',
        'job_name': 'Morgenanalyse', 'trigger': 'SCHEDULED', 'markets': ['USA'],
        'summary': {'recommended': 1},
        'candidates': [{'ticker': 'GOOG', 'investment_score': 80.0}],
    }
    mi.archive_report(run)
    rows = mi._load_report_archive()
    assert rows[0]['run_id'] == 'MI-TEST'
    assert rows[0]['top_ticker'] == 'GOOG'
    mi.set_report_favorite('MI-TEST', True)
    assert mi._load_report_archive()[0]['favorite'] is True


def test_market_column_in_pdf():
    run = {
        'run_id': 'MI-PDF', 'created_at': '2026-07-20T08:00:00+00:00',
        'job_name': 'Morgenanalyse', 'trigger': 'SCHEDULED', 'markets': ['Norge'],
        'summary': {}, 'candidates': [], 'changes': {},
        'data_refresh': {'execution_trace': [{'ticker': 'EQNR.OL', 'data_source': 'yfinance-live', 'data_fetch_status': 'OK', 'cache_bypass_applied': True}]},
    }
    pdf = mi.build_pdf(run)
    assert pdf.startswith(b'%PDF')


def test_weekday_defaults_and_notification_options():
    job = mi.JobProfile(name='Morgenanalyse')
    assert job.weekdays == [0, 1, 2, 3, 4]
    assert job.allow_weekends is False
    assert job.include_report_link is True
    assert job.include_top3_in_notification is True
