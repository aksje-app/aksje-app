from datetime import datetime, timezone
from pathlib import Path

from market_intelligence import build_market_status
from report_contracts import build_report_identity


def test_closed_norway_market_shows_next_open_same_day():
    rows = build_market_status(["Norge"], now=datetime(2026, 9, 9, 0, 10, tzinfo=timezone.utc))
    row = rows[0]
    assert row["status"] == "STENGT"
    assert row["local_time"] == "02:10"
    assert row["next_open_display"] == "Åpner 09:00"
    assert row["next_open_local"].startswith("2026-09-09T09:00")


def test_closed_after_market_shows_next_weekday_open():
    rows = build_market_status(["Norge"], now=datetime(2026, 9, 9, 18, 30, tzinfo=timezone.utc))
    row = rows[0]
    assert row["status"] == "STENGT"
    assert row["next_open_display"] == "Åpner tor 09:00"


def test_draft_night_mission_no_longer_hardcodes_usa():
    identity = build_report_identity(
        "MANUAL_DRAFT_TEST", "Utkast – Norge", "MI-DRAFT-AUTOSAVE",
        created_at="2026-09-09T00:10:25+00:00", timezone_name="Europe/Oslo",
    )
    assert identity["type"] == "UTKAST"
    assert identity["period_type"] == "NATTRAPPORT"
    assert "USA" not in identity["mission_label"]
    assert "USA" not in identity["mission_objective"]
    assert "norske handelsdag" in identity["mission_objective"]


def test_pdf_source_uses_evidence_control_semantics_and_funnel():
    src = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "Evidenskontroll: {evidence_ready}/{evidence_controlled}" in src
    assert "Analyseflyt for komplett Norge-univers" in src
    assert "Neste ordinære åpning" in src
    assert "Rapportkandidater totalt" in src


def test_report_integrity_rehydrates_exchange_metadata():
    src = Path("report_integrity.py").read_text(encoding="utf-8")
    assert "norway_exchange_by_ticker" in src
    assert '"exchange_name", "market_segment", "exchange_mic", "exchange_symbol", "isin", "listing_status"' in src


def test_final_export_memory_guard_ignores_reclaimable_file_cache(monkeypatch):
    import runtime_memory
    monkeypatch.setattr(runtime_memory, "memory_snapshot", lambda: {
        "process_rss_mb": 871.0,
        "cgroup_memory_current_mb": 1860.9,
        "cgroup_memory_limit_mb": 2048.0,
        "cgroup_anon_mb": 789.8,
        "cgroup_file_mb": 1024.3,
        "cgroup_shmem_mb": 0.0,
        "cgroup_kernel_mb": 46.4,
    })
    guard = runtime_memory.memory_guard(
        "manual_report_before_final_export",
        soft_limit_mb=1450.0,
        raise_on_pressure=False,
        ignore_reclaimable_file_cache=True,
    )
    assert guard["pressure"] is False
    assert guard["observed_mb"] == 871.0
    assert guard["total_observed_mb"] == 1860.9
    assert guard["reclaimable_file_cache_mb"] == 1024.3


def test_final_export_memory_guard_still_fails_near_hard_limit(monkeypatch):
    import runtime_memory
    monkeypatch.setattr(runtime_memory, "memory_snapshot", lambda: {
        "process_rss_mb": 900.0,
        "cgroup_memory_current_mb": 2015.0,
        "cgroup_memory_limit_mb": 2048.0,
        "cgroup_anon_mb": 820.0,
        "cgroup_file_mb": 1100.0,
        "cgroup_shmem_mb": 0.0,
        "cgroup_kernel_mb": 50.0,
    })
    guard = runtime_memory.memory_guard(
        "manual_report_before_final_export",
        soft_limit_mb=1450.0,
        raise_on_pressure=False,
        ignore_reclaimable_file_cache=True,
    )
    assert guard["pressure"] is True
    assert guard["hard_limit_pressure"] is True
