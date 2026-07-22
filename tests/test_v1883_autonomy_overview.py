from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import types


ROOT = Path(__file__).resolve().parents[1]


def test_next_run_uses_each_jobs_local_timezone_and_earliest_utc():
    sys.modules.setdefault("streamlit", types.ModuleType("streamlit"))
    from autonomy_overview import _next_scheduled_run

    jobs = [
        SimpleNamespace(enabled=True, name="Oslo", timezone_name="Europe/Oslo", weekdays=[2], schedules=["10:00"]),
        SimpleNamespace(enabled=True, name="New York", timezone_name="America/New_York", weekdays=[2], schedules=["08:00"]),
    ]
    result = _next_scheduled_run(jobs, datetime(2026, 7, 22, 6, 0, tzinfo=timezone.utc))
    assert result["job_name"] == "Oslo"
    assert result["at"].hour == 10
    assert result["timezone_name"] == "Europe/Oslo"


def test_overview_contains_all_daily_monitoring_areas():
    source = (ROOT / "autonomy_overview.py").read_text(encoding="utf-8")
    for label in (
        "Aktivt oppdrag", "Produksjonskjede", "Neste kjøring",
        "Pågående kjøring, fremdrift og avbryt", "Siste kandidater",
        "Siste beslutninger", "Portefølje og risiko", "Datakvalitet",
        "Pushover og drift", "Ventende godkjenninger", "Siste rapport",
    ):
        assert label in source


def test_overview_uses_existing_durable_services_and_safe_cancel():
    source = (ROOT / "autonomy_overview.py").read_text(encoding="utf-8")
    assert "get_active_status" in source
    assert "request_cancel" in source
    assert "_load_report_archive" in source
    assert "load_portfolio" in source
    assert "pushover_audit" in source
    assert "promotion_approvals.json" in source
    assert "AUTONOMY_OVERVIEW" in source
    assert "resolve_promotion_approval(approval_id, True)" in source
    assert "resolve_promotion_approval(approval_id, False)" in source


def test_overview_is_default_workspace_and_detail_engines_remain_lazy():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def render_autonomy_core_control_center_v1880")
    block = source[start:start + 5000]
    assert '"overview": "Oversikt"' in block
    assert 'if workspace == "Oversikt"' in block
    assert "render_autonomy_overview()" in block
    assert 'elif workspace == "Orchestrator og tidsplan"' in block
    assert 'elif workspace == "Learning Portfolio"' in block


def test_release_metadata_v1883():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")
    assert '"v18.8.3: Autonomi Oversikt:' in version
