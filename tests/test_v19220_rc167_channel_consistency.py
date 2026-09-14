from report_contracts import ensure_report_document
from report_channel_consistency import projection_from_run, validate_channel_projection


def _run():
    return {
        "run_id": "RUN-167", "report_id": "REPORT-167", "job_id": "JOB-1",
        "created_at": "2026-08-05T20:00:00+00:00", "timezone_name": "Europe/Oslo",
        "report_identity": {"type": "MORGENRAPPORT", "label": "Morgenrapport", "slug": "Morgenrapport"},
        "summary": {}, "markets": ["Norge"],
        "candidates": [
            {"ticker":"AAA", "market":"Norge", "investment_score":91, "rank":1, "autonomy_outcome_code":"KJØPSKANDIDAT", "autonomy_outcome_label":"Kjøpskandidat", "portfolio_action":"BUY", "final_decision_ready": True},
            {"ticker":"BBB", "market":"Norge", "investment_score":84, "rank":2, "autonomy_outcome_code":"KJØPSKANDIDAT", "autonomy_outcome_label":"Kjøpskandidat", "portfolio_action":"BUY", "final_decision_ready": True},
            {"ticker":"CCC", "market":"Norge", "investment_score":99, "rank":3, "status":"AUTOMATISK_AVVIST", "portfolio_action":"SKIP"},
        ],
    }


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json
