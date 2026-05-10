from services.storage_service import StorageService
from score_explanation_store import capture_score_explanations, score_explanations_for_ui

storage = StorageService(base_dir="/tmp/score_explanation_store_test", database_url="")
rows = [
    {
        "ticker": "TEST",
        "score": 72,
        "smart_score": 81,
        "strength": 66,
        "risk": "Lav",
        "reason": "Sterk trend og lav risiko.",
    }
]
saved = capture_score_explanations(rows, source="unit-test", storage=storage)
assert saved and saved[0]["ticker"] == "TEST"
ui_rows = score_explanations_for_ui("TEST", storage=storage)
assert ui_rows
assert ui_rows[0]["Ticker"] == "TEST"
assert ui_rows[0]["AI-score"] == 72.0
print("score_explanation_store smoke test OK")
