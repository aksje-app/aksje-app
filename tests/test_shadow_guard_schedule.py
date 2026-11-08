from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from services.shadow_daily_guard import evaluate
from services.learning_progress import KEYS


def report(now, *, audit_day='2026-11-06', weekends=False):
    jobs=[dict(job_id='MI-REQUIRED-AFTERNOON',enabled=True,
        weekdays=list(range(7 if weekends else 5)),allow_weekends=weekends,
        schedules=['14:00'],timezone_name='Europe/Oslo')]
    data={KEYS['acceptance']:{'evaluated_at':now.isoformat(),'strategy_readiness':'NOT_VALIDATED'},
        KEYS['history']:{'bytes':100,'status':'COLLECTING','records':[
            {'engine':name,'status':'READY','at':now.isoformat()} for name in ('AUTONOMY','SUPER_PORTFOLIO','AUTONOMY_UNIVERSE')]},
        'autonomi_core/configuration_registry.json':{'values':{'runtime':{'scheduler':{'jobs':jobs}}}}}
    audit=[{'event':'OBSERVATIONS_REGISTERED','at':audit_day+'T21:18:28+00:00','created':0},
           {'event':'OUTCOMES_EVALUATED','at':audit_day+'T22:16:34+00:00','updated':0,'active':91,'matured':0}]
    with patch('services.shadow_daily_guard.read_json',side_effect=lambda k,p,d:data.get(k,d)),patch('services.shadow_daily_guard.read_events',return_value=audit):
        return evaluate(now)


def test_sunday_checks_real_friday_evidence_without_fabricating_24h_jobs():
    row=report(datetime(2026,11,8,0,30,tzinfo=timezone.utc))
    assert row['status']=='GUL' and not row['failures'] and row['scheduled_pause']
    assert row['registrations']==row['evaluations']==row['new_observations']==row['new_measurements']==0
    assert row['active']==91 and row['matured']==0
    assert row['last_evaluation_at']=='2026-11-06T22:16:34+00:00'
    assert row['strategy_readiness']=='NOT_VALIDATED' and not row['production_changed']


def test_weekend_does_not_hide_missing_last_workday():
    row=report(datetime(2026,11,8,0,30,tzinfo=timezone.utc),audit_day='2026-11-05')
    assert row['status']=='RØD' and len(row['failures'])==2


def test_enabled_weekend_report_still_requires_registration():
    row=report(datetime(2026,11,8,0,30,tzinfo=timezone.utc),weekends=True)
    assert row['status']=='RØD' and len(row['failures'])==1
    assert 'observasjonsregistrering' in row['failures'][0]


@pytest.mark.parametrize('hour,status',[(5,'GUL'),(9,'RØD')])
def test_monday_resumes_missing_run_detection_after_actual_due_times(hour,status):
    row=report(datetime(2026,11,9,hour,tzinfo=timezone.utc))
    assert row['status']==status
