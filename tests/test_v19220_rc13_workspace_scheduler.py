from __future__ import annotations

from datetime import datetime, timezone

import market_intelligence as mi
from navigation_state import (
    AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12,
    consume_autonomy_workspace_route_lease_v19220_rc12,
    pin_autonomy_workspace_route_v19220_rc13,
)


class FakeStreamlit:
    def __init__(self):
        self.session_state = {"autonomy_core_workspace_v1880": "Oversikt"}
        self.query_params = {"aa_nav": "autonomy", "aa_tab": "overview"}


def test_rc13_report_action_never_mutates_instantiated_workspace_widget_key():
    st = FakeStreamlit()
    pin_autonomy_workspace_route_v19220_rc13(
        st, workspace_slug="reports", public_nav="reports", execution_id="MBJ-RC13",
    )
    # The current render already owns this widget key. It must remain untouched.
    assert st.session_state["autonomy_core_workspace_v1880"] == "Oversikt"
    assert st.session_state["autonomy_core_workspace_slug_v1882"] == "reports"
    assert st.session_state[AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12]["execution_id"] == "MBJ-RC13"
    assert st.query_params["aa_tab"] == "reports"


def test_rc13_pending_workspace_is_applied_before_widget_on_following_render():
    st = FakeStreamlit()
    pin_autonomy_workspace_route_v19220_rc13(st, execution_id="MBJ-RC13")
    assert consume_autonomy_workspace_route_lease_v19220_rc12(
        st.session_state, {"execution_id": "MBJ-RC13", "state": "RUNNING"},
    )
    assert st.session_state["autonomy_core_workspace_v1880"] == "Rapporter"


def test_rc13_pre_start_slot_is_unobserved_not_missed_or_due(monkeypatch):
    monkeypatch.setattr(mi, "SCHEDULER_OBSERVATION_STARTED_AT_UTC_V19220_RC13", datetime(2026, 8, 5, 10, 2, tzinfo=timezone.utc))
    monkeypatch.setattr(mi, "load_job_history", lambda limit=1000: [])
    job = mi.JobProfile(
        name="Morgenanalyse", schedules=["10:00"], weekdays=[0, 1, 2, 3, 4, 5, 6],
        timezone_name="Europe/Oslo", enabled=True, last_run_at="",
    )
    now = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)  # 12:30 Oslo; slot 10:00 Oslo predates process.
    timeline = mi.schedule_timeline(job, now)
    assert timeline["unobserved_after_restart"] is True
    assert timeline["missed"] is False
    assert timeline["last_planned_status"] == "Ikke vurdert etter omstart"
    assert timeline["scheduler_status_reason_code"] == "SCHEDULER_PROCESS_STARTED_AFTER_SLOT"
    assert mi._due_slot_info(job, now)["due"] is False


def test_rc13_durable_completed_history_wins_over_restart_boundary(monkeypatch):
    monkeypatch.setattr(mi, "SCHEDULER_OBSERVATION_STARTED_AT_UTC_V19220_RC13", datetime(2026, 8, 5, 10, 2, tzinfo=timezone.utc))
    job = mi.JobProfile(
        name="Morgenanalyse", schedules=["10:00"], weekdays=[0, 1, 2, 3, 4, 5, 6],
        timezone_name="Europe/Oslo", enabled=True, last_run_at="", job_id="MIJ-RC13",
    )
    monkeypatch.setattr(mi, "load_job_history", lambda limit=1000: [{
        "job_id": "MIJ-RC13", "planned_at": "2026-08-05T08:00:00+00:00", "status": "Fullført",
    }])
    now = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
    timeline = mi.schedule_timeline(job, now)
    assert timeline["last_planned_status"] == "Fullført"
    assert timeline["unobserved_after_restart"] is False
    assert timeline["missed"] is False


def test_rc13_report_center_exposes_restart_aware_scheduler_status():
    source = open("market_intelligence.py", encoding="utf-8").read()
    assert 'status_unobserved.metric("Ikke vurdert"' in source
    assert "De er ikke merket som mistet og startes ikke automatisk i ettertid." in source
    assert 'and not timeline.get("unobserved_after_restart")' in source
