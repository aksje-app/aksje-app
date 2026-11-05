"""A normal long cron must not make an accepted manual request fail at 10 min."""
from contextlib import contextmanager
from unittest.mock import Mock
import manual_job_background as jobs
import resource_coordinator


def test_manual_waits_for_twenty_minute_cron_without_repeated_submission(monkeypatch):
    clock=[0.0];status={'state':'QUEUED'}
    monkeypatch.setattr('time.monotonic',lambda:clock[0])
    monkeypatch.setattr('time.sleep',lambda delay:clock.__setitem__(0,clock[0]+delay))
    monkeypatch.setattr(jobs,'get_status',lambda _:dict(status))
    monkeypatch.setattr(jobs,'_write_status',lambda value:status.update(value))
    @contextmanager
    def lane(_):yield clock[0]>=1200
    monkeypatch.setattr(resource_coordinator,'execution_lane',lane)
    worker=Mock();monkeypatch.setattr(jobs,'_worker_impl',worker)
    jobs._worker('fixture',{},'MANUAL_REPORT_CENTER',False)
    worker.assert_called_once()
    assert status['state']=='QUEUED'
    assert status['phase']=='WAITING_FOR_REPORT_LOCK'
