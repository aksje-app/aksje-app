from autonomous_decision_reduction import apply_decision_reduction
from report_contracts import build_report_document, section_payload


def _row(ticker, score, action, outcome=None):
    row = {
        "ticker": ticker, "market": "Norge", "investment_score": score,
        "risk_score": 20, "portfolio_action": action,
        "valid_for_decision": True, "evidence_valid_for_decision": True,
        "mission_eligible": True,
    }
    if outcome:
        row["autonomy_outcome_code"] = outcome
    return row


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json


def test_report_document_ranks_only_buys_and_rejects_are_appendix_only():
    rows = [
        {**_row("BUY.OL", 90, "BUY", "KJØPSKANDIDAT"), "final_decision_ready": True, "autonomy_outcome_label": "Kjøpskandidat"},
        {**_row("NO.OL", 85, "SKIP", "AUTOMATISK_AVVIST"), "final_decision_ready": False, "autonomy_outcome_label": "Automatisk avvist", "autonomy_outcome_reason": "Risikoport avviste"},
    ]
    run = {"run_id":"R1", "job_id":"J1", "created_at":"2026-08-05T20:00:00Z", "timezone_name":"Europe/Oslo", "candidates":rows, "summary":{}, "report_identity":{"type":"MORNING","label":"Morgenrapport","slug":"morgenrapport"}}
    doc = build_report_document(run)
    ranked = section_payload(doc, "candidate_decisions", [])
    rejected = section_payload(doc, "rejected_control_appendix", [])
    assert [x["ticker"] for x in ranked] == ["BUY.OL"]
    assert [x["ticker"] for x in rejected] == ["NO.OL"]
