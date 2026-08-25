from datetime import datetime, timedelta, timezone

import pandas as pd

import analysis
import market_intelligence as mi
import paper_scanner_runtime as psr
import ticker_health


def test_history_cache_is_strictly_bounded(monkeypatch):
    analysis.release_score_caches(history=True, info=True, insider=True)
    monkeypatch.setattr(analysis, "HISTORY_CACHE_MAX_ITEMS", 2)
    frame = pd.DataFrame({"Close": range(150), "Volume": range(150)})

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, **_kwargs):
            return frame.copy()

    monkeypatch.setattr(analysis.yf, "Ticker", FakeTicker)
    for ticker in ("A", "B", "C", "D"):
        assert not analysis.get_history(ticker).empty
    assert len(analysis._HISTORY_CACHE) == 2
    assert set(key[0] for key in analysis._HISTORY_CACHE) == {"C", "D"}


def test_scanner_checkpoint_roundtrip(monkeypatch):
    stored = {}
    monkeypatch.setattr(psr, "write_json", lambda key, path, value: stored.update({key: value}))
    monkeypatch.setattr(psr, "read_json", lambda key, path, default: stored.get(key, default))
    psr.save_scanner_checkpoint({"scan_run_id": "SCAN-1", "next_index": 7})
    assert psr.load_scanner_checkpoint()["next_index"] == 7
    psr.clear_scanner_checkpoint()
    assert psr.load_scanner_checkpoint() == {}


def test_ticker_quarantine_expires_and_never_deletes(monkeypatch):
    stored = {}
    monkeypatch.setattr(ticker_health, "write_json", lambda key, path, value: stored.update({key: value}))
    monkeypatch.setattr(ticker_health, "read_json", lambda key, path, default: stored.get(key, default))
    ticker_health.record_ticker_failure(" test.ol ", "empty")
    row = ticker_health.record_ticker_failure("TEST.OL", "empty again")
    assert row["quarantined_until"]
    assert ticker_health.quarantine_status("TEST.OL")["active"] is True
    stored[ticker_health.KEY]["TEST.OL"]["quarantined_until"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).isoformat()
    assert ticker_health.quarantine_status("TEST.OL")["active"] is False
    assert "TEST.OL" in stored[ticker_health.KEY]


def test_final_revalidation_sends_revised_report_notification(monkeypatch):
    now = datetime.now(timezone.utc)
    job = mi.JobProfile(job_id="JOB-1", name="Morgenrapport")
    parent = {
        "run_id": "RUN-R1", "job_id": "JOB-1", "created_at": (now - timedelta(hours=2)).isoformat(),
        "report_status": {"state": "PROVISIONAL"}, "revalidation": {"attempt": 0},
    }
    monkeypatch.setenv("REPORT_REVALIDATION_HOURS", "1")
    monkeypatch.setattr(mi, "load_jobs", lambda: [job])
    monkeypatch.setattr(mi, "_load_report_archive", lambda: [{
        "run_id": "RUN-R1", "report_series_id": "SERIES-1", "revalidation_required": True,
    }])
    monkeypatch.setattr(mi, "load_archived_run", lambda _entry: parent)
    monkeypatch.setattr(mi, "run_job", lambda *_args, **_kwargs: {
        "run_id": "RUN-R2", "report_status": {"state": "FINAL"},
        "report_revision": {"revision_label": "R2"}, "change_since_previous": {"material_change": True},
    })
    monkeypatch.setattr(mi, "_notification", lambda *_args: (True, "sent"))
    result = mi.revalidate_provisional_reports(now=now)
    assert result["runs"][0]["notification_sent"] is True
    assert result["runs"][0]["state"] == "FINAL"


def test_learning_notice_no_longer_claims_real_buy():
    source = open("autonomous_portfolio.py", encoding="utf-8").read()
    assert "AUTONOMY LEARNING BUY" not in source
    assert "SIMULERT LÆRINGSOBSERVASJON" in source
