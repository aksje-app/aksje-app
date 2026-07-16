from pathlib import Path

from ui_cleanup_audit import audit_ui_cleanup
from ui_library.components import status_badge
from ui_library.theme import UI_TOKENS


def test_ui_tokens_are_stable():
    data = UI_TOKENS.to_dict()
    assert data["radius_md"] >= data["radius_sm"]
    assert data["success"].startswith("#")


def test_status_badge_escapes_html():
    markup = status_badge("<script>", "danger")
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup


def test_cleanup_audit_reads_project():
    root = Path(__file__).resolve().parents[1]
    report = audit_ui_cleanup(root)
    assert report["python_files"] > 10
    assert report["shared_ui_library_present"] is True
    assert report["summary"]["parse_error_count"] == 0
