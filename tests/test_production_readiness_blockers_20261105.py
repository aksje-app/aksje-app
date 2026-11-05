from production_readiness import assess_production_readiness


def test_missing_release_and_live_evidence_are_explicit_blockers():
    assessment = assess_production_readiness({})
    assert assessment["production_ready"] is False
    assert assessment["status"] == "NOT_READY"
    assert "final_release_gate" in assessment["missing_local_checks"]
    assert "deployed_runtime_identity" in assessment["missing_live_checks"]
    assert "pushover" in assessment["missing_live_checks"]
    assert set(assessment["missing_local_checks"]) == {
        key for key, passed in assessment["local_checks"].items() if not passed
    }
    assert set(assessment["missing_live_checks"]) == {
        key for key, passed in assessment["live_checks"].items() if not passed
    }
