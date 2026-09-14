from pathlib import Path
import manual_job_background as background


def test_long_running_pipeline_phases_have_real_progress_intervals():
    md_end = background.progress_percent({"phase": "MARKET_DATA", "completed": 100, "total": 100})
    ext_start = background.progress_percent({"phase": "EXTENDED_ANALYSIS", "completed": 1, "total": 100})
    ext_mid = background.progress_percent({"phase": "EXTENDED_ANALYSIS", "completed": 50, "total": 100})
    evidence = background.progress_percent({"phase": "EVIDENCE", "completed": 0, "total": 20})
    insider = background.progress_percent({"phase": "INSIDER", "completed": 10, "total": 20})
    news = background.progress_percent({"phase": "NEWS", "completed": 10, "total": 20})
    short = background.progress_percent({"phase": "SHORT", "completed": 10, "total": 20})
    insider_base = background.progress_percent({"phase": "INSIDER_BASELINE", "completed": 20, "total": 40})
    short_base = background.progress_percent({"phase": "SHORT_BASELINE", "completed": 20, "total": 40})
    scoring = background.progress_percent({"phase": "SCORING", "completed": 1, "total": 60})

    assert md_end <= ext_start <= ext_mid <= evidence <= insider <= news <= short <= insider_base <= short_base <= scoring
    assert ext_mid > md_end


def test_autonomous_progress_uses_substage_work_units():
    p0 = background.progress_percent({"phase": "AUTONOMOUS", "completed": 0, "total": 3})
    p1 = background.progress_percent({"phase": "AUTONOMOUS", "completed": 1, "total": 3})
    p2 = background.progress_percent({"phase": "AUTONOMOUS", "completed": 2, "total": 3})
    p3 = background.progress_percent({"phase": "AUTONOMOUS", "completed": 3, "total": 3})
    assert 84 == p0 < p1 < p2 < p3 <= 91


def test_existing_market_data_contract_is_preserved():
    assert background.progress_percent({"phase": "MARKET_DATA", "completed": 0, "total": 10}) == 10
    assert background.progress_percent({"phase": "COMPLETE", "completed": 1, "total": 1}) == 100


def test_ui_has_same_execution_monotonic_display_floor():
    source = Path("autonomy_overview.py").read_text(encoding="utf-8")
    assert "manual_progress_floor_v1931bz_" in source
    assert "pct = max(pct, floor)" in source
    assert "utvidet analyse, evidens, short og grunnkontroller" in source
