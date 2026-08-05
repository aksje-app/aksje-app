from __future__ import annotations

from evidence_contract import SECONDARY_FACTS_FOUND, VERIFIED_FACTS_FOUND, canonical_status
from insider_intelligence import score_transactions
from market_intelligence import JobProfile
from market_universe import CORE_MARKET_SCOPES, market_profile_contract
from news_intelligence import score_articles
from report_integrity import canonical_report_view, validate_report_integrity


def _candidate(ticker: str = "AAPL", *, market: str = "USA") -> dict:
    return {
        "ticker": ticker,
        "name": "Apple Inc." if ticker == "AAPL" else ticker,
        "market": market,
        "investment_score": 74.0,
        "confidence_score": 57.0,
        "confidence_before_evidence_policy": 87.0,
        "confidence_profile": {
            "model_confidence": 87.0,
            "calibrated_confidence": 57.0,
            "data_coverage": 40.0,
        },
        "risk_score": 25.0,
        "data_quality": 96.0,
        "valid_for_decision": True,
        "evidence_valid_for_decision": False,
        "portfolio_action": "REVIEW",
        "analysis_stage": "EVIDENCE_CONTROLLED",
        "decision_readiness": {
            "news": "VERIFIED_FACTS_FOUND",
            "insider": "CHECKED_NO_EVENTS",
            "allowed_action": "REVIEW",
        },
        "evidence_coverage": {
            "news": {"status": "VERIFIED_FACTS_FOUND"},
            "insider": {"status": "CHECKED_NO_EVENTS"},
        },
        "raw": {
            "news_score": 65,
            "news_sentiment": "POSITIV",
            "news_intelligence": {
                "coverage": "AVAILABLE",
                "verified_fact_count": 1,
                "article_count": 1,
                "relevance_policy": "EXPLICIT_COMPANY_OR_TICKER_MATCH_OR_PRIMARY_COMPANY_SOURCE",
                "events": [{
                    "title": "Apple reports quarterly results",
                    "company_relevant": True,
                    "relevance_score": 1.0,
                    "url": "https://example.com/apple-results",
                }],
            },
            "insider_signal": "KONTROLLERT – INGEN HENDELSER",
            "insider_intelligence": {
                "coverage": "CHECKED_NO_EVENTS",
                "verified_fact_count": 0,
                "evidence": [],
            },
        },
    }


def _run(markets=None, job_name="Normalanalyse – Kjernemarkeder") -> dict:
    return {
        "run_id": "MI-V19150-TEST",
        "created_at": "2026-07-30T08:00:00+02:00",
        "job_name": job_name,
        "markets": list(markets or CORE_MARKET_SCOPES),
        "investment_mission": {"markets": list(markets or CORE_MARKET_SCOPES)},
        "summary": {"scanned": 30, "proposals": 1},
        "candidates": [_candidate()],
        "portfolio_decisions": {
            "portfolio_context": {"portfolio_status": "PAUSED"},
            "decisions": [{
                "ticker": "AAPL",
                "action": "REVIEW",
                "reason": "Ikke tilstrekkelig porteføljerom eller disponibel kontantandel",
            }],
        },
        "data_quality": {"score": 100},
        "combined_data_quality": {"coverage_pct": 100},
    }


def test_legacy_core_job_repairs_stale_six_market_list():
    job = JobProfile.from_dict({
        "name": "Normalanalyse – Kjernemarkeder",
        "markets": ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"],
    })
    assert job.market_profile == "CORE"
    assert job.markets == ["Norge + Sverige + USA"]
    contract = market_profile_contract(job.market_profile, job.markets, name=job.name)
    assert contract["expanded_markets"] == ["Norge", "Sverige", "USA"]


def test_market_profile_mismatch_is_a_blocking_semantic_error():
    report = canonical_report_view(_run(["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"]))
    assert report["report_integrity"]["ok"] is False
    assert any("Markedsprofilen Norge + Sverige + USA" in error for error in report["report_integrity"]["errors"])


def test_news_relevance_rejects_other_companies_and_general_big_tech():
    rows = [
        {"title": "Apple reports quarterly results", "url": "https://example.com/apple"},
        {"title": "Qualcomm Q3 earnings miss", "summary": "Apple is mentioned once", "url": "https://example.com/qcom"},
        {"title": "Big Tech earnings: what to watch", "summary": "AAPL and MSFT", "url": "https://example.com/big-tech"},
        {"title": "Nvidia targets a $5 trillion valuation", "url": "https://example.com/nvda"},
    ]
    result = score_articles("AAPL", rows, company_name="Apple Inc.")
    assert result["relevant_article_count"] == 1
    assert result["rejected_irrelevant_count"] == 3
    assert result["events"][0]["company_relevant"] is True
    fallback = score_articles("AAPL", rows, company_name="AAPL")
    assert fallback["relevant_article_count"] == 1


def test_primary_and_secondary_insider_provenance_are_not_equivalent():
    secondary = score_transactions("AAPL", [{
        "date": "2026-07-29", "transaction": "Sale", "shares": 100,
        "price": 200, "insider": "Example Person", "source_type": "SECONDARY_STRUCTURED",
    }])
    assert secondary["secondary_fact_count"] == 1
    assert secondary["primary_verified_fact_count"] == 0
    assert canonical_status(secondary, secondary["evidence"]) == SECONDARY_FACTS_FOUND
    assert canonical_status({}, [{"verification": "STRUCTURED_PROVIDER"}]) == SECONDARY_FACTS_FOUND

    primary = score_transactions("AAPL", [{
        "date": "2026-07-29", "transaction": "Purchase", "shares": 100,
        "price": 200, "insider": "Example Person", "source_type": "OFFICIAL_PRIMARY",
        "source_url": "https://www.sec.gov/Archives/example", "document_id": "0001",
        "form_type": "4", "verification": "PRIMARY_DOCUMENT",
    }])
    assert primary["primary_verified_fact_count"] == 1
    assert canonical_status(primary, primary["evidence"]) == VERIFIED_FACTS_FOUND


def test_canonical_report_has_one_confidence_truth_and_correct_quality_metric():
    report = canonical_report_view(_run())
    candidate = report["candidates"][0]
    profile = candidate["confidence_profile"]
    assert candidate["model_confidence"] == profile["model_confidence"] == 87.0
    assert candidate["evidence_adjusted_model_confidence"] == profile["evidence_adjusted_model_confidence"] == 57.0
    assert candidate["decision_confidence"] == profile["decision_confidence"]
    assert report["priority_top3"][0]["decision_confidence"] == candidate["decision_confidence"]
    assert report["quality_metrics"]["candidate_evidence_coverage_average"] == 40.0
    assert report["quality_metrics"]["labels"]["overall_report_quality"] == "Teknisk rapportfullstendighet"


def test_candidate_portfolio_reason_is_synchronised_with_canonical_decision():
    report = canonical_report_view(_run())
    candidate = report["candidates"][0]
    assert "Porteføljen er ikke aktiv" in candidate["portfolio_decision"]["reason"]
    assert candidate["portfolio_decision"] == report["portfolio_decisions"]["decisions"][0]
    assert validate_report_integrity(report)["ok"] is True


def test_semantic_integrity_rejects_irrelevant_news_and_stale_candidate_reason():
    report = canonical_report_view(_run())
    report["candidates"][0]["raw"]["news_intelligence"]["events"][0]["company_relevant"] = False
    report["candidates"][0]["portfolio_decision"]["reason"] = "Ikke tilstrekkelig porteføljerom"
    validation = validate_report_integrity(report)
    assert validation["ok"] is False
    assert any("selskapsrelevans" in error for error in validation["errors"])
    assert any("porteføljebegrunnelse" in error for error in validation["errors"])



def test_notification_failures_are_not_misclassified_as_success(monkeypatch, tmp_path):
    import autonomous_portfolio as portfolio
    import controlled_parameter_learning as learning
    import notifier

    assert notifier.normalize_notification_result((False, "blocked")) == (False, "blocked")
    assert notifier.normalize_notification_result((True, None)) == (True, "")
    assert notifier.normalize_notification_result(False) == (False, "")

    monkeypatch.setattr(notifier, "send_pushover_alert", lambda *args, **kwargs: (False, "blocked"))

    notification_path = tmp_path / "portfolio_notifications.json"
    monkeypatch.setattr(portfolio, "NOTIFICATIONS_PATH", notification_path)
    portfolio._notification("TEST", "Tittel", "Melding", {"run_id": "RUN-1"})
    rows = portfolio._read(notification_path, [])
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["delivery"] == "PUSHOVER_FAILED"
    assert rows[0].get("sent_at") in (None, "")

    learning_path = tmp_path / "learning_notifications.json"
    monkeypatch.setattr(learning, "NOTIFICATIONS_PATH", learning_path)
    learning._notify("Tittel", "Melding", {"run_id": "RUN-2"})
    learning_rows = learning._read(learning_path, [])
    assert learning_rows[0]["delivery"] == "PUSHOVER_FAILED"


def test_full_system_release_audit_is_clean():
    from tools.audit_full_system_v19150 import audit
    result = audit()
    assert result["ok"] is True, result["errors"]
