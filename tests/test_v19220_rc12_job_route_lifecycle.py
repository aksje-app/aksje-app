from __future__ import annotations

import json
from pathlib import Path

import manual_job_background as background
import market_intelligence as mi
from navigation_state import (
    AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12,
    consume_autonomy_workspace_route_lease_v19220_rc12,
    queue_autonomy_workspace_route_lease_v19220_rc12,
)


def _memory_storage(monkeypatch):
    memory = {}

    def write_json(key, path, value):
        memory[key] = json.loads(json.dumps(value, default=str))

    def read_json(key, path, default):
        return json.loads(json.dumps(memory.get(key, default)))

    monkeypatch.setattr(background, "write_json", write_json)
    monkeypatch.setattr(background, "read_json", read_json)
    background._THREADS.clear()
    return memory


def test_report_workspace_lease_stays_until_bound_execution_is_terminal():
    state = {}
    queue_autonomy_workspace_route_lease_v19220_rc12(
        state, workspace_slug="reports", execution_id="MBJ-1",
    )
    assert consume_autonomy_workspace_route_lease_v19220_rc12(
        state, {"execution_id": "MBJ-1", "state": "RUNNING"},
    )
    assert state["autonomy_core_workspace_v1880"] == "Rapporter"
    assert AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12 in state

    assert consume_autonomy_workspace_route_lease_v19220_rc12(
        state, {"execution_id": "MBJ-1", "state": "COMPLETED"},
    )
    assert state["autonomy_core_workspace_v1880"] == "Rapporter"
    assert AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12 not in state


def test_old_route_lease_cannot_override_a_new_active_execution():
    state = {}
    queue_autonomy_workspace_route_lease_v19220_rc12(
        state, workspace_slug="reports", execution_id="OLD",
    )
    consume_autonomy_workspace_route_lease_v19220_rc12(
        state, {"execution_id": "NEW", "state": "RUNNING"},
    )
    assert AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12 not in state


def test_manual_job_acceptance_records_process_identity_and_explicit_name(monkeypatch):
    _memory_storage(monkeypatch)

    class DormantThread:
        def __init__(self, *args, name="", **kwargs):
            self.name = name
        def start(self):
            return None
        def is_alive(self):
            return False

    monkeypatch.setattr(background.threading, "Thread", DormantThread)
    job = mi.JobProfile(name="Uten navn", markets=["Danmark + Finland"])
    accepted = background.start_manual_job(job, trigger="MANUAL_DRAFT_TEST")
    assert accepted["job_name"].startswith("Utkast –")
    assert accepted["worker_process_identity"] == background._PROCESS_IDENTITY
    assert accepted["heartbeat_at"] == accepted["accepted_at"]


def test_same_process_missing_worker_is_not_called_server_restart(monkeypatch):
    _memory_storage(monkeypatch)
    status = {
        "execution_id": "MBJ-STALE", "state": "RUNNING", "active_stage": "MARKET_DATA",
        "worker_process_identity": background._PROCESS_IDENTITY,
        "updated_at": "2020-01-01T00:00:00+00:00", "heartbeat_at": "2020-01-01T00:00:00+00:00",
    }
    background._write_status(status)
    reconciled = background.reconcile_orphaned_status(
        status, same_process_stale_seconds=60, force=True,
    )
    assert reconciled["state"] == "FAILED"
    assert reconciled["error_code"] == "WORKER_LOST_SAME_PROCESS"
    assert "serverrestart" not in reconciled["message"].casefold()


def test_different_process_identity_is_positive_restart_evidence(monkeypatch):
    _memory_storage(monkeypatch)
    status = {
        "execution_id": "MBJ-OLD", "state": "RUNNING",
        "worker_process_identity": "999:old",
        "updated_at": "2020-01-01T00:00:00+00:00",
    }
    reconciled = background.reconcile_orphaned_status(status)
    assert reconciled["state"] == "CANCELLED"
    assert reconciled["orphan_reason_code"] == "SERVER_PROCESS_RESTART"


def test_legacy_unnamed_profiles_are_normalized_without_changing_schedule():
    profile = mi.JobProfile.from_dict({
        "name": "Uten navn", "markets": ["Danmark + Finland"],
        "schedules": ["08:00", "22:00"], "job_id": "MIJ-OLD",
    })
    assert profile.name == "Analyse – Danmark + Finland"
    assert profile.schedules == ["08:00", "22:00"]


def test_rc12_scheduler_contract_migration_preserves_schedule_and_timezone():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    block = source[source.index("mission_missing ="):source.index("from evidence_integrity import")]
    assert "JOB_CONFIGURATION_CONTRACT_MIGRATED_RC12" in block
    assert '"schedules_preserved": list(persisted_job.schedules or [])' in block
    assert '"timezone_preserved": persisted_job.timezone_name' in block
    assert "Opprett oppdraget på nytt" not in block


def test_stale_scheduler_contract_is_regenerated_and_persisted(monkeypatch):
    from types import SimpleNamespace
    import autonomi_core.configuration.policy as policy_module
    import autonomi_core.configuration.registry as registry_module
    import autonomi_core.missions.investment_mission as mission_module
    import autonomi_core.missions.user_mission as user_mission_module
    import autonomi_core.portfolio_decisions as portfolio_module
    import evidence_integrity

    stale = {
        "mission_id": "IM-OLD", "configuration_version": "CFG-OLD",
        "search_for": "Kvalitet", "markets": ["Norge", "Sverige", "USA"],
        "sectors": [], "strategy": "Kvalitet til rimelig pris",
        "horizon": "3–12 måneder", "risk": "Balansert", "risk_ceiling": 65,
        "portfolio_need": "Beste enkeltkandidater", "minimum_data_quality": 45,
        "candidate_count": 10, "exclusions": [], "objective": "Kvalitet",
    }
    generated_payload = {**stale, "mission_id": "IM-NEW", "configuration_version": "CFG-NEW"}
    generated = SimpleNamespace(
        mission_id="IM-NEW", configuration_version="CFG-NEW",
        to_dict=lambda: dict(generated_payload),
    )
    persisted = []

    monkeypatch.setattr(mi, "apply_execution_settings", lambda job: (job, {}))
    monkeypatch.setattr(mi, "_effective_execution_job", lambda job, trigger: (job, {}))
    monkeypatch.setattr(portfolio_module, "read_portfolio_needs", lambda: {"summary": "Beste enkeltkandidater"})
    monkeypatch.setattr(mission_module, "load_investment_mission", lambda mission_id="": dict(stale))
    monkeypatch.setattr(mission_module, "create_investment_mission", lambda **kwargs: generated)
    monkeypatch.setattr(registry_module, "status", lambda: {"config_version": "CFG-NEW"})
    monkeypatch.setattr(policy_module, "load_policy", lambda: SimpleNamespace(minimum_data_quality=45.0))
    monkeypatch.setattr(user_mission_module, "load_user_mission", lambda: {})
    monkeypatch.setattr(mi, "upsert_job", lambda job: persisted.append(job))

    def stop_after_migration(job):
        assert job.investment_mission_id == "IM-NEW"
        assert job.configuration_version == "CFG-NEW"
        raise RuntimeError("STOP_AFTER_MIGRATION")

    monkeypatch.setattr(evidence_integrity, "build_integrity_preflight", stop_after_migration)
    job = mi.JobProfile(
        name="Morgenanalyse", markets=["Norge + Sverige + USA"],
        schedules=["08:00", "22:00"], job_id="MIJ-STALE",
        investment_mission_id="IM-OLD", configuration_version="CFG-OLD",
    )
    try:
        mi._run_job_impl(job, trigger="SCHEDULED")
    except RuntimeError as exc:
        assert str(exc) == "STOP_AFTER_MIGRATION"
    else:
        raise AssertionError("Testen skulle stoppe etter kontraktsmigreringen")

    assert len(persisted) == 1
    assert persisted[0].investment_mission_id == "IM-NEW"
    assert persisted[0].configuration_version == "CFG-NEW"
    assert persisted[0].schedules == ["08:00", "22:00"]
    assert persisted[0].timezone_name == "Europe/Oslo"
