from __future__ import annotations

from pathlib import Path


def test_reports_and_overview_use_one_progress_implementation():
    overview = Path("autonomy_overview.py").read_text(encoding="utf-8")
    reports = Path("market_intelligence.py").read_text(encoding="utf-8")

    assert "def render_shared_manual_job_progress" in overview
    assert 'fragment(run_every="5s")(_live_progress_panel)' in overview
    assert "from autonomy_overview import render_shared_manual_job_progress" in reports

    action = reports[reports.index("##### 2. Handlinger"):reports.index("##### 3. Siste rapporter")]
    assert action.count("render_shared_manual_job_progress(") == 1
    assert "_live_report_progress_fragment_v19220_rc161()" not in action
    assert "get_active_status_snapshot" not in action


def test_reports_do_not_force_terminal_full_app_rerun():
    reports = Path("market_intelligence.py").read_text(encoding="utf-8")
    action = reports[reports.index("##### 2. Handlinger"):reports.index("##### 3. Siste rapporter")]
    assert "refresh_app_on_terminal=False" in action


def test_rc162_version_scope_is_progress_only():
    version = Path("app_version.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v19.22.0-rc16.7"' in version
    assert "samme dynamiske Streamlit-fragment" in version
    assert "Ingen endring i rapportmotor, ZIP, tidssone, meny, score, scheduler, porteføljer eller handel" in version
