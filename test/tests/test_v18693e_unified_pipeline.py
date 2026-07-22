from unittest.mock import patch

from market_intelligence import (
    DRAFT_JOB_ID,
    JobProfile,
    _effective_execution_job,
    job_fingerprint,
    report_identity,
)


def test_manual_morning_report_identity():
    identity = report_identity("MANUAL_FULL_CHAIN", "Morgenanalyse")
    assert identity["type"] == "MORGENRAPPORT"
    assert identity["slug"] == "Morgenrapport"


def test_manual_full_chain_uses_same_name_draft_analysis_settings():
    saved = JobProfile(
        name="Morgenanalyse",
        markets=["Alle"],
        scan_limit=100,
        deep_count=20,
        proposal_count=25,
        job_id="MIJ-SAVED",
        enabled=True,
    )
    draft = JobProfile(
        name="Morgenanalyse",
        markets=["Alle"],
        scan_limit=25,
        deep_count=20,
        proposal_count=5,
        job_id=DRAFT_JOB_ID,
        enabled=False,
    )
    with patch("market_intelligence.load_draft_job", return_value=draft):
        effective, detail = _effective_execution_job(saved, "MANUAL_FULL_CHAIN")
    assert detail["draft_merged"] is True
    assert effective.job_id == saved.job_id
    assert effective.enabled is True
    assert effective.scan_limit == 25
    assert effective.proposal_count == 5
    assert job_fingerprint(effective) == job_fingerprint(draft)
