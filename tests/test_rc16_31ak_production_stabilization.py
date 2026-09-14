from __future__ import annotations

from pathlib import Path

import insider_intelligence
import market_intelligence as mi
import public_report_store
import short_data_sources
from report_integrity import canonical_report_view
from report_portfolio_intelligence import build_portfolio_report, ensure_portfolio_evidence
from short_intelligence import normalize_short_snapshot


def _candidate(ticker: str, action: str = "HOLD") -> dict:
    return {
        "ticker": ticker,
        "market": "USA",
        "investment_score": 75.0,
        "portfolio_action": action,
        "autonomy_outcome_code": "OVERVÅK",
        "autonomy_outcome_reason": "Kanonisk beslutning",
        "valid_for_decision": True,
        "raw": {},
    }


def test_canonical_portfolio_rows_always_carry_assessment_receipt():
    result = canonical_report_view({
        "run_id": "RUN-AK-ASSESSMENT",
        "created_at": "2026-08-25T18:00:00+00:00",
        "candidates": [_candidate("AAA"), _candidate("OWNED")],
        "portfolio_decisions": {
            "portfolio_context": {"active": True},
            "decisions": [{"ticker": "AAA", "action": "HOLD", "portfolio_assessed": True}],
        },
    })

    decisions = result["portfolio_decisions"]["decisions"]
    assert {row["ticker"] for row in decisions} == {"AAA", "OWNED"}
    assert all(row.get("portfolio_assessed") is True for row in decisions)


def test_normalized_portfolio_short_snapshot_is_not_downgraded_to_not_searched():
    canonical = {
        "ticker": "XOM",
        "market": "USA",
        "source": "FINRA",
        "as_of": "2026-08-24",
        "verification_status": "VERIFIED",
        "coverage_status": "VERIFIED",
        "short_interest_pct_float": 2.75,
        "verified": True,
        "coverage": "VERIFIED",
    }

    snapshot = normalize_short_snapshot({"ticker": "XOM", "market": "USA", "short_intelligence": canonical})

    assert snapshot["verified"] is True
    assert snapshot["coverage"] == "VERIFIED"
    assert snapshot["short_interest_pct_float"] == 2.75


def test_portfolio_table_and_short_aggregate_use_same_snapshot():
    portfolio = {
        "positions": {"XOM": {"ticker": "XOM", "quantity": 2, "average_price": 100}},
        "cash": 800,
        "initial_cash": 1000,
    }
    candidate = {
        "ticker": "XOM",
        "market": "USA",
        "raw": {"short_data": {
            "source": "FINRA",
            "as_of": "2026-08-24",
            "verification_status": "VERIFIED",
            "coverage_status": "VERIFIED",
            "short_interest_pct_float": 4.0,
        }},
    }

    report = build_portfolio_report(portfolio, [candidate])

    assert report["positions"][0]["short_intelligence"]["coverage"] == "VERIFIED"
    assert report["short_exposure"]["verified_short_coverage_pct"] == 100.0


def test_brazilian_owned_ticker_is_routed_to_brazil_not_sec(monkeypatch):
    captured: list[dict] = []

    def short_enrich(rows, *, force_refresh=False):
        captured.extend(dict(row) for row in rows)
        return [dict(row) | {"short_data": {"coverage_status": "NOT_SUPPORTED"}} for row in rows]

    def insider_enrich(rows, *, force_refresh=False):
        assert all(row.get("market") == "Brasil" for row in rows)
        return [dict(row) | {"insider_intelligence": {"coverage": "CHECKED_NO_EVENTS"}} for row in rows]

    monkeypatch.setattr(short_data_sources, "enrich_rows", short_enrich)
    monkeypatch.setattr(insider_intelligence, "enrich_rows", insider_enrich)

    result = ensure_portfolio_evidence({
        "positions": {"VBBR3.SA": {"ticker": "VBBR3.SA", "quantity": 1, "average_price": 20}},
    }, [])

    assert captured[0]["market"] == "Brasil"
    assert result[0]["market"] == "Brasil"


def test_final_artifact_pass_updates_both_pdfs_from_same_final_run(monkeypatch, tmp_path):
    main_path = tmp_path / "report.pdf"
    observed: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(mi, "ensure_report_document", lambda run, previous=None: run.setdefault("report_document", {}))
    monkeypatch.setattr(mi, "build_main_pdf", lambda run: observed.append(("main", list(run.get("errors") or []))) or b"%PDF-main")
    monkeypatch.setattr(mi, "build_technical_pdf", lambda run: observed.append(("technical", list(run.get("errors") or []))) or b"%PDF-technical")
    monkeypatch.setattr(mi, "publish_pdf", lambda run, data: run.update({"public_pdf_name": "report.pdf"}))
    monkeypatch.setattr(mi, "report_public_url", lambda run: "https://example.test/report")
    monkeypatch.setattr(public_report_store, "publish_durable_pdf", lambda run, data, **kwargs: run.update({kwargs["token_field"]: "T" * 43}) or "T" * 43)
    monkeypatch.setattr(mi, "_write", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "archive_report", lambda run: None)
    monkeypatch.setattr(mi, "verify_report_persistence", lambda run_id: {"ok": True, "run_id": run_id})
    run = {
        "run_id": "RUN-AK-FINAL",
        "pdf_path": str(main_path),
        "errors": ["dokumentert sluttfeil"],
        "full_autonomy_execution": {"status": "INCOMPLETE"},
    }

    result = mi._finalize_completed_report_artifacts(run)

    assert result == {"generated": True, "main_valid": True, "technical_valid": True}
    assert observed == [("main", ["dokumentert sluttfeil"]), ("technical", ["dokumentert sluttfeil"])]
    assert main_path.read_bytes() == b"%PDF-main"
    assert Path(run["technical_pdf_path"]).read_bytes() == b"%PDF-technical"
    assert run["pdf_delivery"]["finalized_after_execution_receipt"] is True
    assert run["technical_pdf_delivery"]["finalized_after_execution_receipt"] is True


def test_running_autonomy_without_single_ticker_has_meaningful_ui_label():
    source = Path(mi.__file__).with_name("autonomy_overview.py").read_text(encoding="utf-8")
    assert 'context = "Samlet Autonomi-steg" if stage == "AUTONOMOUS"' in source
