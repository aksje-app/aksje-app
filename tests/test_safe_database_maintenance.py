"""Real PostgreSQL cleanup must retain valid sessions and all historical data."""
from datetime import datetime,timedelta,timezone
import pytest
from test_revision_trade_postgres import pg
from services.safe_database_maintenance import run


def test_online_maintenance_preserves_history_and_current_sessions(pg):
    now=datetime.now(timezone.utc)
    docs={'simulation_restarts/history/bundle.json':{'journal':[1,2,3]},'controlled_learning/archive.json':{'loss':-25},
          'market_intelligence/runs/old.json':{'historical_report':True},'operations/run_traces/old.json':{'audit':True}}
    for key,value in docs.items():pg.write_json(key,value)
    pg.append_jsonl('controlled_learning/outcome_audit.jsonl',{'event':'old-history','loss':-25})
    conn=pg._conn()
    with conn:
        with conn.cursor() as q:
            q.execute('CREATE TABLE app_auth_sessions(token_hash text PRIMARY KEY,expires text)')
            q.executemany('INSERT INTO app_auth_sessions VALUES (%s,%s)',[
                ('expired',(now-timedelta(days=9)).isoformat()),('recent',(now-timedelta(days=1)).isoformat()),
                ('active',(now+timedelta(days=1)).isoformat()),('malformed','0000-unknown')])
    conn.close()
    result=run(storage=pg,now=now)
    assert result['state']=='COMPLETED'
    assert result['historical_deletion_enabled'] is False
    assert result['deleted_access_tokens']=={'app_auth_sessions':1}
    assert result['vacuum']['app_kv_store']['state']=='COMPLETED'
    assert all(pg.read_json(key)==value for key,value in docs.items())
    assert pg.read_jsonl('controlled_learning/outcome_audit.jsonl')==[{'event':'old-history','loss':-25}]
    assert result['autovacuum']['app_kv_store']['state']=='CONFIGURED'
    conn=pg._conn()
    with conn.cursor() as q:
        q.execute('SELECT token_hash FROM app_auth_sessions ORDER BY token_hash')
        assert [r[0] for r in q.fetchall()]==['active','malformed','recent']
    conn.close()


def test_safe_policy_supersedes_legacy_apply_and_never_deletes_history(pg,monkeypatch):
    import storage_retention as retention
    monkeypatch.setenv('STORAGE_SAFE_MAINTENANCE_APPLY','true')
    monkeypatch.setenv('STORAGE_RETENTION_APPLY','true')
    monkeypatch.setattr(retention,'get_storage_service',lambda:pg)
    monkeypatch.setattr(retention,'_save_state',lambda state:state)
    monkeypatch.setattr(retention,'load_storage_retention_state',lambda:{})
    # Deliberately beyond the old retention count.
    for i in range(20):pg.write_json(f'investment_pipeline/runs/{i}.json',{'historical':i})
    result=retention.run_storage_retention(apply=True)
    assert result['policy']=='PRESERVE_ALL_HISTORY' and result['state']=='COMPLETED'
    assert result['apply_enabled'] is True and result['deleted_keys']=={}
    assert len([k for k in pg.list_json_names() if k.startswith('investment_pipeline/runs/')])==20


def test_safe_preview_never_changes_auth_or_vacuums(pg,monkeypatch):
    import storage_retention as retention
    monkeypatch.setenv('STORAGE_SAFE_MAINTENANCE_APPLY','true')
    monkeypatch.setattr(retention,'get_storage_service',lambda:pg)
    monkeypatch.setattr(retention,'_save_state',lambda state:state)
    monkeypatch.setattr(retention,'load_storage_retention_state',lambda:{})
    result=retention.run_storage_retention(apply=False)
    assert result['state']=='DRY_RUN' and result['safe_maintenance']['state']=='DRY_RUN'
    assert result['apply_enabled'] is False


def test_scheduled_safe_cleanup_requires_successful_maintenance_receipt():
    from scheduled_runner import _production_closure_snapshot
    state={'storage_retention':{'apply_requested':True,'apply_enabled':True,'state':'FAILED'},'paper_scanner':{}}
    result=_production_closure_snapshot(state)
    assert result['checks']['retention_effective'] is False


def test_safe_acceptance_rejects_flag_without_completed_receipt():
    from services.safe_database_maintenance import receipt_ok
    now=datetime.now(timezone.utc)
    good={'policy':'PRESERVE_ALL_HISTORY','historical_deletion_enabled':False,
        'apply_scope':'EXPIRED_ACCESS_TOKENS_AND_ONLINE_VACUUM',
        'safe_maintenance':{'state':'COMPLETED','completed_at':now.isoformat(),
            'vacuum':{'app_kv_store':{'state':'COMPLETED'},'app_jsonl_store':{'state':'COMPLETED'}}}}
    assert receipt_ok(good,now=now)
    good['safe_maintenance']['completed_at']=(now-timedelta(days=3)).isoformat()
    assert not receipt_ok(good,now=now)
    good['safe_maintenance'].pop('completed_at')
    assert not receipt_ok(good,now=now)


def test_capacity_warning_is_deduplicated_and_does_not_enable_history_deletion(monkeypatch):
    from unittest.mock import Mock
    import notifier,storage_retention as retention
    send=Mock(return_value=(True,'receipt'));monkeypatch.setattr(notifier,'send_pushover_alert',send)
    usage={'capacity_state':'WARNING','capacity_pct':72}
    first=retention._capacity_notice(usage,{},enabled=True)
    assert first['sent'] is True
    again=retention._capacity_notice(usage,{'capacity_notification':first},enabled=True)
    assert again['state']=='ALREADY_SENT' and send.call_count==1
    assert retention._capacity_notice(usage,{},enabled=False)['state']=='NOT_REQUIRED'
