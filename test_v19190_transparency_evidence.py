from analysis_transparency import build_candidate_transparency, build_claim_ledger


def _candidate():
    return {
        "ticker": "TEST.OL", "investment_score": 74.2, "data_quality": 95,
        "confidence_score": 78, "evidence_valid_for_decision": False,
        "evidence_passport": {"areas": {
            "news": {"status": "VERIFIED_FACTS_FOUND", "facts": [
                {"title": "Resultatvekst", "publisher": "Reuters", "source_url": "https://news.yahoo.com/x", "verification": "VERIFIED"},
                {"title": "Marginpress", "publisher": "Reuters", "source_url": "https://reuters.com/y", "verification": "VERIFIED"},
                {"title": "Usikker påstand", "publisher": "Blogg", "source_url": "https://blog.example/z", "verification": "REJECTED", "reason": "Ingen dokumentasjon"},
            ], "sources": [{"attempted": True, "status": "SUCCESS_WITH_RESULTS"}]},
            "insider": {"status": "CHECKED_NO_EVENTS", "facts": [], "sources": [
                {"attempted": True, "status": "CHECKED_NO_EVENTS", "source_type": "PRIMARY_REGULATORY"}
            ]},
            "filings": {"status": "NOT_SEARCHED", "facts": [], "sources": []},
        }}
    }


def test_original_publisher_drives_source_independence():
    ledger = build_claim_ledger(_candidate())
    assert ledger["independent_source_count"] == 1
    assert ledger["independent_sources"] == ["publisher:reuters"]
    assert ledger["rejected_claim_count"] == 1


def test_statuses_are_not_collapsed():
    data = build_candidate_transparency(_candidate())
    classes = {row["area"]: row["status_class"] for row in data["evidence_matrix"]}
    assert classes["insider"] == "CHECKED_NO_FINDINGS"
    assert classes["filings"] == "NOT_SEARCHED"
    assert data["claim_ledger"]["primary_source_attempted_areas"] == ["insider"]
    assert data["schema_version"] == "19.19.0-rc1"


def test_transparency_does_not_modify_candidate():
    candidate = _candidate()
    before = dict(candidate)
    build_candidate_transparency(candidate)
    assert candidate == before
