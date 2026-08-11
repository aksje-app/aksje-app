from pathlib import Path
import io
import threading
import zipfile

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from local_time import browser_header_clock_document
import replay_export_background as background

ROOT = Path(__file__).resolve().parents[1]

def test_version_chain_rc165():
    assert APP_VERSION == "v19.22.0-rc16.7"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.4"

def test_header_clock_is_browser_local_and_before_version():
    doc = browser_header_clock_document(APP_VERSION)
    assert "new Date()" in doc
    assert "Intl.DateTimeFormat('nb-NO'" in doc
    assert doc.index('id="pc-clock"') < doc.index('id="app-version"')
    assert APP_VERSION in doc

def test_replay_worker_is_non_daemon_and_fragment_uses_defined_streamlit_alias():
    source = (ROOT / "replay_export_background.py").read_text(encoding="utf-8")
    ui = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    assert "daemon=False" in source
    assert "_st_fragment_rc161.fragment" in ui
    assert "_st_fragment_rc16.fragment" not in ui

def test_zip_validation_and_atomic_roundtrip(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ok.txt", b"ok")
    payload = buffer.getvalue()
    assert background._valid_zip_bytes(payload)
    target = tmp_path / "verified.zip"
    background._atomic_write_bytes(target, payload)
    assert target.read_bytes() == payload
    assert background._valid_zip_bytes(target.read_bytes())
    assert not background._valid_zip_bytes(b"not-a-zip")
