from __future__ import annotations

import report_export_audit as audit
import public_report_store as public_store
import market_intelligence as mi


def test_learning_fill_contract_uses_public_display_precision():
    run = {
        "run_id": "MI-PRECISION",
        "app_version": "v19.22.0-rc16.31w",
        "public_report_contract": {"report_id": "MI-PRECISION", "ranking": [], "decision_count": 0},
        "learning_portfolio_summary": {"learning_fills": [{
            "ticker": "cah", "side": "buy", "quantity": 141.77123456, "price": 32.4137,
        }]},
    }
    expected = audit.expected_contract(run)["learning_fills"]
    parsed = audit._text_contract(
        "Rapport-ID: MI-PRECISION\nAppversjon: v19.22.0-rc16.31w\n"
        "- CAH · BUY · antall 141.77123456 · pris 32.41 · score 76.78\n"
    )["learning_fills"]
    assert parsed == expected
    assert expected[0]["price"] == 32.41


def test_learning_fill_contract_still_detects_real_difference():
    run = {
        "learning_portfolio_summary": {"learning_fills": [{
            "ticker": "CAH", "action": "BUY", "quantity": 141.77123456, "price": 32.4137,
        }]},
    }
    parsed = audit._text_contract(
        "- CAH · BUY · antall 140.77123456 · pris 32.41 · score 76.78\n"
    )["learning_fills"]
    assert parsed != audit.expected_contract(run)["learning_fills"]


def test_text_report_preserves_eight_quantity_decimals():
    text = mi.build_text_report({
        "run_id": "MI-PRECISION", "report_id": "MI-PRECISION",
        "learning_portfolio_summary": {"learning_fills": [{
            "ticker": "CAH", "side": "BUY", "quantity": 141.77123456,
            "price": 32.4137, "score": 76.78,
        }]},
    })
    assert "antall 141,77123456 · pris 32,41" in text


def test_durable_store_supports_separate_main_and_technical_tokens(monkeypatch):
    memory = {}
    monkeypatch.setattr(public_store, "write_json", lambda key, path, value: memory.__setitem__(key, value))
    monkeypatch.setattr(public_store, "read_json", lambda key, path, default: memory.get(key, default))
    run = {
        "run_id": "MI-DUAL", "public_pdf_name": "main.pdf",
        "technical_pdf_name": "complete.pdf",
    }
    main = public_store.publish_durable_pdf(run, b"%PDF-main")
    technical = public_store.publish_durable_pdf(
        run, b"%PDF-technical", token_field="technical_report_token",
        filename_field="technical_pdf_name", document_kind="technical",
    )
    assert main != technical
    assert run["public_report_token"] == main
    assert run["technical_report_token"] == technical
    assert public_store.load_public_pdf(technical)["data"] == b"%PDF-technical"


def test_technical_delivery_prefers_durable_payload(monkeypatch):
    monkeypatch.setattr(public_store, "load_public_pdf", lambda token: {"data": b"%PDF-durable"})
    monkeypatch.setattr(mi, "_write", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "_load_report_archive", lambda: [])
    result = mi.resolve_technical_report_delivery({
        "run_id": "MI-DURABLE", "technical_report_token": "T" * 43,
        "technical_pdf_name": "complete.pdf",
    })
    assert result["ok"] is True
    assert result["data"] == b"%PDF-durable"
    assert result["regenerated"] is False


def test_archive_keeps_technical_delivery_identity(monkeypatch):
    monkeypatch.setattr(mi, "ensure_report_document", lambda run: {"metadata": {}})
    entry = mi._archive_entry({
        "run_id": "MI-ARCHIVE", "technical_pdf_path": "/tmp/full.pdf",
        "technical_pdf_name": "full.pdf", "technical_report_token": "X" * 43,
        "technical_pdf_delivery": {"durable": True},
    })
    assert entry["technical_report_token"] == "X" * 43
    assert entry["technical_pdf_name"] == "full.pdf"


def test_ui_does_not_require_local_technical_file():
    source = open("market_intelligence.py", encoding="utf-8").read()
    archive = source[source.index("delivery = resolve_report_delivery(saved_run, row)"):]
    assert "technical_path.is_file()" not in archive
    assert "resolve_technical_report_delivery(saved_run, row)" in archive
    assert "Full rapport med vedlegg" in archive
