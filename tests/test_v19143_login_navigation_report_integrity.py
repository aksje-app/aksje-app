from pathlib import Path
import json

from report_integrity import canonical_report_view, validate_pdf_semantics, validate_report_integrity


def _candidate(ticker, score, outcome, evidence=True, facts=True):
    raw = {
        "insider_score": 62 if facts else 50,
        "insider_signal": "POSITIV" if facts else "KONTROLLERT – INGEN HENDELSER",
        "news_score": 65 if facts else 50,
        "news_sentiment": "POSITIV" if facts else "KONTROLLERT – INGEN HENDELSER",
        "insider_intelligence": {"verified_fact_count": 2 if facts else 0, "coverage": "AVAILABLE" if facts else "CHECKED_NO_EVENTS", "evidence": [{"x": 1}] if facts else []},
        "news_intelligence": {"verified_fact_count": 2 if facts else 0, "article_count": 2 if facts else 0, "coverage": "AVAILABLE" if facts else "CHECKED_NO_EVENTS", "events": [{"x": 1}] if facts else []},
    }
    return {
        "ticker": ticker, "market": "USA", "investment_score": score,
        "confidence_score": 80, "risk_score": 20, "data_quality": 97,
        "valid_for_decision": True, "evidence_valid_for_decision": evidence,
        "portfolio_action": "REVIEW", "status": "KREVER MANUELL VURDERING",
        "analysis_stage": "EVIDENCE_CONTROLLED", "raw": raw,
        "decision_readiness": {"news": "VERIFIED_FACTS_FOUND" if facts else "CHECKED_NO_EVENTS", "insider": "VERIFIED_FACTS_FOUND" if facts else "CHECKED_NO_EVENTS"},
    }


def test_outcomes_summary_decisions_and_evidence_are_one_truth():
    run = {
        "created_at": "2026-07-29T17:00:00+02:00",
        "summary": {"scanned": 20, "proposals": 2, "rejected": 0},
        "candidates": [_candidate("AIZ", 75.4, "WATCH"), _candidate("STB.OL", 69.0, "REJECT", evidence=False, facts=False)],
        "portfolio_decisions": {"portfolio_context": {"active": False}, "decisions": [
            {"ticker": "AIZ", "action": "REVIEW", "reason": "Ikke tilstrekkelig porteføljerom", "room": {"cash_amount": 425000}},
            {"ticker": "STB.OL", "action": "REVIEW", "reason": "Ikke tilstrekkelig porteføljerom", "room": {"cash_amount": 425000}},
        ]},
        "decision_funnel": {"production_threshold": 78, "candidates": []},
        "data_quality": {"score": 95}, "combined_data_quality": {"coverage_pct": 100},
    }
    result = canonical_report_view(run)
    by = {x["ticker"]: x for x in result["candidates"]}
    assert by["AIZ"]["autonomy_outcome_code"] == "OVERVÅKES_AUTOMATISK"
    assert by["AIZ"]["portfolio_action"] == "HOLD"
    assert by["AIZ"]["evidence_gate_status"] == "PASS"
    assert by["AIZ"]["manual_review_required"] is False
    assert by["STB.OL"]["autonomy_outcome_code"] == "AUTOMATISK_AVVIST"
    assert by["STB.OL"]["portfolio_action"] == "SKIP"
    assert by["STB.OL"]["evidence_gate_status"] == "AUTO_CLOSED"
    assert result["summary"]["rejected"] == result["report_summary"]["automatic_rejected"]
    assert len(result["autonomous_decisions"]) == 2
    assert all("Porteføljen er ikke aktiv" in x["reason"] for x in result["portfolio_decisions"]["decisions"])
    assert validate_report_integrity(result)["ok"] is True


def test_pdf_uses_canonical_candidate_details_and_full_ranking():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "proposal_rows = [candidate_lookup.get" in source
    assert 'Paragraph("Full rangering – scoretrend"' in source
    assert "for r in candidates:" in source
    assert "Rangering omfatter {len(candidates)} av {len(candidates)} kandidater" in source


def test_orchestrator_polling_never_reruns_whole_app():
    source = Path("autonomous_orchestrator_ui.py").read_text(encoding="utf-8")
    terminal = source.split('if state in {"COMPLETED", "FAILED", "CANCELLED"}', 1)[1].split('pct =', 1)[0]
    assert 'st.rerun(scope="app")' not in terminal
    assert "terminal_fragment_seen_v19143" in terminal


def test_login_uses_cookie_without_secret_url_roundtrip_and_one_submit():
    source = Path("auth.py").read_text(encoding="utf-8")
    assert "midlertidig deaktivert" in source
    assert "window.parent.location.reload" not in source
    assert "st.rerun()" in source

def test_autonomy_overview_uses_report_decisions_fallback():
    source = Path("autonomy_overview.py").read_text(encoding="utf-8")
    assert 'latest_run.get("autonomous_decisions")' in source


def test_paper_ui_uses_central_gate_and_one_canonical_status():
    source = Path("pages/paper_trading.py").read_text(encoding="utf-8")
    assert "paper_gate_v19143 = paper_trading_decision()" in source
    assert "Modellsignal" in source
    assert "Handelstillatelse" in source
    assert "Endelig handling" in source
    assert "INGEN HANDEL" in source
    assert "disabled=buy_stock_disabled_v19143" in source
    assert source.count('key="paper_stock_sell_v1871"') == 1


def test_disabled_paper_buy_does_not_mutate_persistent_portfolio(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("APP_RUNTIME_ROOT", str(tmp_path / "runtime"))
    import trading_engine
    before = trading_engine.load_portfolio()
    before_json = json.dumps(before, sort_keys=True, default=str)
    ok, message = trading_engine.paper_buy("STB.OL", 200.0, 90, "v19.17.0-rc6 blocked persistence test", amount_override=10000)
    after = trading_engine.load_portfolio()
    assert ok is False
    assert "deaktivert" in message.lower() or "blokkert" in message.lower()
    assert json.dumps(after, sort_keys=True, default=str) == before_json


def test_draft_status_and_quality_metrics_are_canonical():
    payload = {
        "report_identity": {"type": "UTKAST", "label": "Utkast – Kveldsrapport"},
        "report_status": {"state": "FINAL", "label": "ENDELIG"},
        "data_quality": {"score": 100},
        "combined_data_quality": {"evaluated": 20, "market_data_valid": 20},
        "candidates": [_candidate("AIZ", 75.4, "WATCH")],
        "summary": {"scanned": 20, "proposals": 1},
    }
    result = canonical_report_view(payload)
    assert result["report_status"]["state"] == "DRAFT"
    assert result["report_status"]["label"] == "UTKAST – IKKE ENDELIG"
    assert result["quality_metrics"]["overall_report_quality"] == 100
    assert result["quality_metrics"]["data_coverage"] == 100
    assert validate_report_integrity(result)["ok"] is True


def test_pdf_semantic_gate_rejects_missing_stamp():
    result = canonical_report_view({
        "report_identity": {"type": "UTKAST", "label": "Utkast"},
        "candidates": [_candidate("AIZ", 75.4, "WATCH")],
        "summary": {"scanned": 1, "proposals": 1},
    })
    validation = validate_pdf_semantics(b"not a pdf", result)
    assert validation["ok"] is False


def test_reprocessed_report_stamps_one_current_version_in_json_and_pdf():
    from app_version import APP_VERSION, REPORT_SCHEMA_VERSION
    from market_intelligence import build_pdf
    payload = {
        "version": "v19.14.2",
        "version_contract": {"app_version": "v19.14.2", "report_schema_version": "1.4"},
        "report_identity": {"type": "UTKAST", "label": "Utkast – Kveldsrapport"},
        "created_at": "2026-07-29T17:00:00+02:00",
        "run_id": "MI-VERSION-CONSISTENCY",
        "job_id": "MI-DRAFT-AUTOSAVE",
        "summary": {"scanned": 1, "proposals": 1},
        "candidates": [_candidate("AIZ", 75.4, "WATCH")],
    }
    result = canonical_report_view(payload)
    assert result["version"] == APP_VERSION
    assert result["version_contract"]["app_version"] == APP_VERSION
    assert result["version_contract"]["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert result["report_document"]["metadata"]["app_version"] == APP_VERSION
    assert result["report_document"]["schema_version"] == REPORT_SCHEMA_VERSION
    assert result["source_version_contract"]["app_version"] == "v19.14.2"
    assert validate_report_integrity(result)["ok"] is True
    assert validate_pdf_semantics(build_pdf(result), result)["ok"] is True
