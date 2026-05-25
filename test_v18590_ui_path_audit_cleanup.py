from pathlib import Path

APP = Path('app.py').read_text(encoding="utf-8", errors="ignore")
REPORT = Path('V18590_UI_PATH_AUDIT_CLEANUP_BATCH_H.md').read_text(encoding="utf-8", errors="ignore")


def test_v18590_single_active_global_update_path_present():
    assert "data-ui-path='active-global-update-v18590'" in APP
    assert "top_apply_all_changes_v18590" in APP


def test_v18590_pushover_buttons_present_in_auto_safety_area():
    assert "main_auto_verify_pushover_v18590" in APP
    assert "main_auto_send_test_pushover_v18590" in APP
    assert "Pushover test / API-status" in APP


def test_v18590_audit_report_documents_runtime_mismatch():
    assert "Pushover test eksisterte i kode, men i feil synlig path" in REPORT
    assert "Global oppdatering hadde for mange legacy CSS-/layout-lag" in REPORT
