from pathlib import Path
import io
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def test_reports_and_overview_share_the_exact_draft_starter():
    overview = (ROOT / 'autonomy_overview.py').read_text(encoding='utf-8')
    reports = (ROOT / 'market_intelligence.py').read_text(encoding='utf-8')
    assert 'def start_shared_manual_draft_job' in overview
    assert 'start_manual_job(\n        load_draft_job(),' in overview
    action = reports[reports.index('if q1.button("📄 Nytt utkast"'):reports.index('if q2.button("🌅 Kjør morgenanalyse"')]
    assert 'from autonomy_overview import start_shared_manual_draft_job' in action
    assert 'start_shared_manual_draft_job(trigger="MANUAL_DRAFT_TEST")' in action
    assert '_rerun_reports_v19220_rc11' not in action
    assert 'load_draft_job()' not in action


def test_replay_ui_is_fragment_only_and_shows_real_work_units():
    reports = (ROOT / 'market_intelligence.py').read_text(encoding='utf-8')
    block = reports[reports.index('def _render_replay_export_status_v19220_rc16'):reports.index('def render_market_intelligence')]
    assert 'st.progress(percent' in block
    assert 'arbeidsenheter {completed}/{total}' in block
    assert 'automatisk oppdatering hvert 3. sekund' in block
    assert '_replay_export_status_fragment_v19220_rc16' in reports
    assert 'run_every="3s"' in reports


def test_replay_worker_publishes_snapshot_and_stage_progress():
    source = (ROOT / 'replay_export_background.py').read_text(encoding='utf-8')
    assert '_STATUS_SNAPSHOT' in source
    assert '"stage": stage' in source
    assert '"current_file": current_file' in source
    assert 'daemon=False' in source
    assert '_valid_zip_bytes(persisted)' in source


def test_finalize_zip_reports_each_file_and_verifies_integrity():
    import report_replay_export as export
    events = []
    payload = export._finalize_zip(
        {'a.txt': b'a', 'b.txt': b'b'},
        progress_callback=lambda done, total, message: events.append((done, total, message)),
        progress_offset=2,
        progress_total=10,
    )
    with zipfile.ZipFile(io.BytesIO(payload), 'r') as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) >= {'a.txt', 'b.txt', 'SHA256SUMS.txt'}
    assert any(message.startswith('Komprimerer:') for _, _, message in events)
    assert any(message == 'Kontrollerer ZIP-integritet' for _, _, message in events)
