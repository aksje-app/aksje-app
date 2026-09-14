from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_version_is_bl_and_builds_on_bk():
    src = read("app_version.py")
    assert 'APP_VERSION = "v19.22.0-rc16.31bl"' in src
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.31bk"' in src


def test_progress_snapshot_chooses_freshest_runtime_or_atomic_mirror():
    src = read("manual_job_background.py")
    assert "def freshness(value: Mapping[str, Any])" in src
    assert "max(candidates, key=freshness)" in src
    assert '"LOCAL_ATOMIC_MIRROR" if local_status' in src
    assert 'release_process_memory("manual_worker_after_terminal_status")' in src


def test_autonomy_progress_poll_is_two_seconds_and_phase_is_explicit():
    src = read("autonomy_overview.py")
    assert 'fragment(run_every="2s")' in src
    assert 't3.metric("Fasefremdrift"' in src
    assert "Hovedprosenten er samlet fremdrift" in src


def test_report_detail_state_survives_browser_refresh_and_is_lazy():
    src = read("market_intelligence.py")
    assert 'detail_query_key_v19220_rc1631bl = "report_detail"' in src
    assert 'st.query_params[detail_query_key_v19220_rc1631bl] = archive_run_id' in src
    assert 'expanded=(archive_run_id == detail_query_run_id_v19220_rc1631bl)' in src
    assert 'Klargjør rapportfiler' in src
    assert 'Rapportsammendraget er klart. PDF/JSON/tekst lastes separat' in src
    assert 'release_process_memory("report_detail_closed")' in src


def test_trend_chart_uses_tight_normalized_plotly_and_rsi_reference_lines():
    src = read("market_intelligence.py")
    assert "import plotly.graph_objects as go" in src
    assert '"Indeks (start = 100)"' in src
    assert '"range": [lo - pad, hi + pad]' in src
    assert 'rfig.add_hline(y=70' in src
    assert 'rfig.add_hline(y=30' in src
    assert '"Først oppdaget"' in src
    assert '"Valgt kandidat"' in src


def test_final_export_buffers_are_released_before_complete():
    src = read("market_intelligence.py")
    cleanup = src.index('release_process_memory("after_final_export_validation")')
    complete = src.index('emit(\n        "COMPLETE"', cleanup)
    assert cleanup < complete
    assert 'mark_breadcrumb(\n        "report:memory_cleanup:after_final_gate"' in src
    assert 'release_process_memory("after_parallel_validation")' in src
