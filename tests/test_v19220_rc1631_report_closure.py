from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from report_integrity import audit_learning_report_consistency
from report_replay_export import build_single_report_package


FIXTURE = Path("/tmp/rc1631_report_audit.t2cfit/report/report.json")


def _fixture_run():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_actual_rc1631_learning_fill_is_the_authoritative_final_result():
    run = _fixture_run()
    audit = audit_learning_report_consistency(run)
    assert audit["ok"] is True
    assert audit["learning_buy_tickers"] == ["ABNB", "APH", "BWLPG.OL"]
    assert audit["conflicting_decision_tickers"] == []


def test_actual_rc1631_export_contains_portfolio_snapshot_and_completed_replay():
    payload, manifest = build_single_report_package(_fixture_run())
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "report/portfolio_snapshot.json" in names
        snapshot = json.loads(archive.read("report/portfolio_snapshot.json"))
        replay = json.loads(archive.read("report/replay_result_rc16.json"))
    assert snapshot.get("limits")
    assert manifest["missing"] in ([], ["FULL_REPLAY_SNAPSHOT_MISSING"])
    assert replay["status"] == "COMPLETED"
    assert len(replay["results"]) == 10


def test_actual_rc1631_pdf_lists_every_learning_fill_with_price_and_quantity():
    payload, _ = build_single_report_package(_fixture_run())
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        pdf = archive.read("report/report.pdf")
    from pypdf import PdfReader
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Kanoniske læringshandler i denne kjøringen" in text
    for ticker in ("ABNB", "APH", "BWLPG.OL"):
        assert ticker in text
    assert "178,07" in text
    assert "169,18" in text
    assert "205,00" in text


def test_summary_numbers_use_compact_consistent_typography_and_norwegian_decimals():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "def _format_summary_value" in source
    assert "SUMMARY_VALUE_FONT_SIZE = 8" in source
    assert "padding=2" in source


def test_report_notification_contract_separates_report_and_learning_channels():
    run = _fixture_run()
    payload, _ = build_single_report_package(run)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        exported = json.loads(archive.read("report/report.json"))
    contract = exported["notification_channels"]
    assert contract["report"]["sent"] is False
    assert contract["learning"]["activity_count"] == 3
    assert contract["learning"]["sent_count"] == 0
    assert contract["learning"]["status_label"] == "Ikke dokumentert"
    assert contract["learning"]["tickers"] == ["ABNB", "APH", "BWLPG.OL"]


def test_report_consistency_audit_covers_learning_fills_across_json_txt_pdf():
    payload, _ = build_single_report_package(_fixture_run())
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        audit = json.loads(archive.read("REPORT_CONSISTENCY_AUDIT.json"))
    assert audit["ok"] is True
    assert [row["ticker"] for row in audit["expected"]["learning_fills"]] == ["ABNB", "APH", "BWLPG.OL"]
