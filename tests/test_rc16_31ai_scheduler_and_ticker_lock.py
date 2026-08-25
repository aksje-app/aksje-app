from pathlib import Path


def test_report_scheduler_lock_does_not_cover_paper_scan():
    source = Path("scheduled_runner.py").read_text(encoding="utf-8")
    run_once = source[source.index("def run_once()") : source.index("def main()")]
    assert "global_scheduler_lock" not in run_once
    assert "return _run_once_locked()" in run_once
    assert "already_coordinated=False" in source


def test_report_market_fetch_honours_shared_ticker_quarantine():
    source = Path("candidate_market_data.py").read_text(encoding="utf-8")
    assert "from ticker_health import" in source
    assert '"data_fetch_status": "QUARANTINED"' in source
    assert "record_ticker_failure" in source
    assert "record_ticker_success" in source
