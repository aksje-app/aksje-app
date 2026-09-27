from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from quality_valuation import add_peer_context, evaluate_company
from quality_valuation_ui import build_screen_pdf
from quality_extended_report import build_extended_analysis_pdf


NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def _base(**changes):
    row = {
        "ticker": "TEST.OL",
        "name": "Test ASA",
        "country": "Norway",
        "currency": "NOK",
        "sector": "Industrials",
        "industry": "Engineering & Construction",
        "price": 100,
        "trailing_eps": 8,
        "forward_eps": 9,
        "annual_eps": [8, 7, 6, 5],
        "financial_date": "2025-12-31",
        "fiscal_periods": ["2025-12-31", "2024-12-31", "2023-12-31"],
        "roce": .18,
        "roce_history": [.18, .17, .16, .15],
        "free_cash_flow": 100,
        "free_cash_flow_history": [100, 90, 80, 70],
        "debt_history": [200, 210, 220],
        "operating_margin_history": [.12, .11, .10],
    }
    row.update(changes)
    return row


def test_active_financial_policy_uses_roe_and_not_industrial_roce():
    raw = _base(
        ticker="PROT.OL",
        name="Protector-like Insurance",
        sector="Financial Services",
        industry="Insurance - Property & Casualty",
        is_financial=True,
        financial_date=None,
        roce=None,
        roce_history=[],
        roe_history=[.367, .333, .272, .345],
        free_cash_flow=None,
        free_cash_flow_history=[],
    )
    row = evaluate_company(raw, as_of=NOW)
    assert row["sector_policy"] == "FINANCIAL"
    assert row["financial_date"] == "2025-12-31"
    assert row["roe_pct"] is not None
    assert row["quality_evidence_ready"] is True
    assert row["group"] == "Kvalitetsselskap"
    assert not any("ROCE/ROACE" in warning for warning in row["warnings"])


def test_cyclical_policy_does_not_auto_use_peer_pe():
    rows = [
        evaluate_company(_base(
            ticker=f"SHIP{i}.OL",
            sector="Industrials",
            industry="Marine Shipping",
            roce_history=[.11, .10, .09, .08],
            roce=.11,
        ), as_of=NOW)
        for i in range(4)
    ]
    add_peer_context(rows)
    assert all(row["sector_policy"] == "CYCLICAL" for row in rows)
    assert all(row.get("entry_range_scenario") is None for row in rows)
    assert all(any("peer-P/E" in warning for warning in row["warnings"]) for row in rows)


def test_real_estate_requires_sector_metrics_instead_of_plain_pe():
    row = evaluate_company(_base(
        ticker="PROP.OL",
        sector="Real Estate",
        industry="Real Estate Services",
        roce_history=[],
        roce=None,
    ), assumed_pe=15, as_of=NOW)
    assert row["sector_policy"] == "REAL_ESTATE"
    assert row["quality_state"] == "SECTOR_METRIC_REQUIRED"
    assert row["entry_range_scenario"] is None
    assert row["review_reason_category"] == "SECTOR_METRIC_REQUIRED"


def test_peer_basis_is_explicit_and_scenario_is_not_called_target():
    rows = [evaluate_company(_base(ticker=f"X{i}.OL", price=90 + i), as_of=NOW) for i in range(4)]
    add_peer_context(rows)
    assert all(row.get("peer_count") == 3 for row in rows)
    assert all(len(row.get("peer_tickers") or []) == 3 for row in rows)
    assert all(row.get("fair_price_scenario") for row in rows)


def test_short_and_extended_pdfs_label_today_pe_and_nonprinting_return():
    row = evaluate_company(_base(), as_of=NOW)
    result = {
        "state": "COMPLETED",
        "generated_at": NOW.isoformat(),
        "run_key": "quality/test",
        "groups": {"Kvalitetsselskap": [row]},
        "quality_v2_shadow": {"rows": [], "evaluated": 0},
    }
    short = build_screen_pdf(result)
    extended = build_extended_analysis_pdf(result)
    assert b"%PDF" in short[:10] and b"%PDF" in extended[:10]
    short_reader = PdfReader(BytesIO(short))
    ext_reader = PdfReader(BytesIO(extended))
    assert "P/E ved dagens kurs" in "\n".join(page.extract_text() or "" for page in short_reader.pages)
    assert "P/E ved dagens kurs" in "\n".join(page.extract_text() or "" for page in ext_reader.pages)
    for reader in (short_reader, ext_reader):
        annots = reader.pages[0].get("/Annots") or []
        assert annots
        assert all(int(item.get_object().get("/F", 0)) & 4 == 0 for item in annots)


def test_ui_uses_durable_mobile_delivery_instead_of_raw_download_as_primary():
    src = Path("quality_valuation_ui.py").read_text(encoding="utf-8")
    assert "publish_durable_pdf" in src
    assert "publish_durable_file" in src
    assert ("Åpne / del kort PDF" in src or '"Kort rapport"' in src)
    assert ("Åpne / del komplett kontrollpakke" in src or '"Last ned alt"' in src)
    assert ("PDF-returknappen er skjerm-only" in src or "quality_reports" in src)
