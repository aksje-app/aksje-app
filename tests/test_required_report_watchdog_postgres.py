import pytest
import psycopg2
from test_revision_trade_postgres import pg
from test_required_report_watchdog import OWNER,ROW
from services import required_report_watchdog as w
from execution_coordination import _OWNER_KEY,_REPORT_EXECUTION_LOCK_ID


def test_actual_pg_lock_protects_slow_report_then_disconnect_unblocks(pg):
    pg.write_json(_OWNER_KEY,OWNER)
    assert w.observe_owner(owner=OWNER,connect=pg._conn)['state']=='ORPHANED'
    holder=pg._conn();holder.autocommit=True
    try:
        with holder.cursor() as cur:cur.execute('SELECT pg_advisory_lock(%s)',(_REPORT_EXECUTION_LOCK_ID,))
        assert w.observe_owner(owner=OWNER,connect=pg._conn)['state']=='LIVE'
        assert pg.read_json(_OWNER_KEY)==OWNER
    finally:holder.close()
    assert w.observe_owner(owner=OWNER,connect=pg._conn)['state']=='ORPHANED'
    assert pg.read_json(_OWNER_KEY)==OWNER


def test_probe_uses_current_owner_if_new_report_replaced_stale_snapshot(pg):
    replacement={**OWNER,'job_id':'MI-REQUIRED-EVENING','scheduled_for':'2026-11-16T21:00:00+00:00'}
    pg.write_json(_OWNER_KEY,replacement)
    holder=pg._conn();holder.autocommit=True
    try:
        with holder.cursor() as cur:cur.execute('SELECT pg_advisory_lock(%s)',(_REPORT_EXECUTION_LOCK_ID,))
        probe=w.observe_owner(owner=OWNER,connect=pg._conn)
        assert probe['state']=='LIVE' and not w.same_slot(ROW,probe['owner'])
    finally:holder.close()


def test_alert_lane_deduplicates_without_waiting_for_heavy_lane(pg,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',pg.database_url)
    holder=pg._conn();holder.autocommit=True
    try:
        with holder.cursor() as cur:cur.execute('SELECT pg_advisory_lock(19343501)')
        with w.alert_lane() as acquired:
            assert acquired
            with w.alert_lane() as second:assert not second
        with w.alert_lane() as acquired:assert acquired
    finally:holder.close()


def test_database_failure_is_unknown_never_orphaned():
    def unavailable():raise psycopg2.OperationalError('controlled test failure')
    assert w.observe_owner(owner=OWNER,connect=unavailable)['state']=='UNKNOWN'


def test_oversized_owner_is_not_fetched_or_trusted(pg):
    pg.write_json(_OWNER_KEY,{**OWNER,'untrusted':'x'*20000})
    assert w.observe_owner(owner=OWNER,connect=pg._conn)['state']=='UNKNOWN'


def test_native_probe_does_not_read_legacy_owner_adapter(pg,monkeypatch):
    import execution_coordination as c
    pg.write_json(_OWNER_KEY,OWNER)
    monkeypatch.setattr(c,'report_execution_owner',lambda:pytest.fail('Legacy read must not run in native observation'))
    assert w.observe_owner(connect=pg._conn)['state']=='ORPHANED'


def test_observer_ledger_never_repairs_job_configuration(pg,monkeypatch):
    import market_intelligence as mi
    from datetime import datetime,timezone
    pg.write_json('market_intelligence/job_history.json',[])
    monkeypatch.setattr(mi,'load_jobs',lambda:pytest.fail('Watchdog cannot repair scheduled jobs'))
    conn=pg._conn()
    try:
        ledger=mi.required_report_delivery_ledger(datetime(2026,11,16,15,tzinfo=timezone.utc),observe_only=True,connection=conn)
        assert len(ledger['rows'])==3
    finally:conn.close()


def test_missing_owner_without_any_real_lock_is_inactive(pg):
    assert w.observe_owner(connect=pg._conn)['state']=='INACTIVE'


def test_native_receipt_migration_preserves_configuration_and_deduplicates(pg,monkeypatch):
    import market_intelligence as mi
    from datetime import datetime,timezone
    legacy={'2026-11-16:'+ROW['job_id']:{'sent_at':'2026-11-16T15:00:00+00:00'}}
    config={'sections':{'legacy':{'scheduler':{'required_report_missing_alerts':{'json':legacy}}}},'protected_user_setting':'UNCHANGED'}
    pg.write_json('configuration/framework.json',config)
    pg.write_json(_OWNER_KEY,OWNER)
    pg.write_json('market_intelligence/job_history.json',[])
    before=pg.json_row_versions(['configuration/framework.json'])
    monkeypatch.setenv('DATABASE_URL',pg.database_url)
    monkeypatch.setattr(mi,'load_jobs',lambda:pytest.fail('No scheduler mutation allowed'))
    import sys
    from types import SimpleNamespace
    messages=[]
    monkeypatch.setitem(sys.modules,'notifier',SimpleNamespace(send_pushover_alert=lambda *a,**kw:(messages.append(a) or (True,'LOCAL TEST ONLY')),normalize_notification_result=lambda x:x))
    now=datetime(2026,11,16,15,tzinfo=timezone.utc)
    first=mi.notify_overdue_required_reports(now)
    second=mi.notify_overdue_required_reports(now)
    assert first['alerts_sent']==['MI-REQUIRED-MORNING']
    assert second['alerts_sent']==[] and len(messages)==1
    assert pg.read_json('configuration/framework.json')==config
    assert pg.json_row_versions(['configuration/framework.json'])==before
    assert set(pg.read_json(w._RECEIPT_KEY))==set(legacy)|{'2026-11-16:MI-REQUIRED-MORNING'}
