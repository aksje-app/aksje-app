from daily_user_experience import (
    ADVANCED_MODE, SIMPLE_MODE, build_attention_items, candidate_action_payload,
    get_user_mode, navigation_for_mode, set_user_mode, status_label,
)


def test_simple_mode_is_default_and_per_user():
    settings = {}
    assert get_user_mode(settings, {"username": "Per"}) == SIMPLE_MODE
    updated = set_user_mode(settings, {"username": "Per"}, "advanced")
    assert get_user_mode(updated, {"username": "Per"}) == ADVANCED_MODE
    assert get_user_mode(updated, {"username": "Other"}) == SIMPLE_MODE


def test_simple_navigation_is_four_primary_plus_more_group():
    nav = navigation_for_mode(SIMPLE_MODE)
    assert [x[1] for x in nav["primary"]] == ["Oversikt", "Rapport", "Analyse", "Portefølje"]
    assert [x[1] for x in nav["more"]] == ["Autonomi", "Paper Trading", "Godkjenninger", "Jobber", "Varsler", "Valuta", "Drift", "Innstillinger"]


def test_advanced_navigation_keeps_specialist_areas():
    labels = [x[1] for x in navigation_for_mode(ADVANCED_MODE)["primary"]]
    assert "Top Picks" in labels
    assert "Long Engine" in labels
    assert "AI-verktøy" in labels


def test_statuses_are_consistent_norwegian():
    assert status_label("review") == "Krever vurdering"
    assert status_label("READY") == "Beslutningsklar"
    assert status_label("draft") == "Foreløpig"
    assert status_label("final") == "Endelig"


def test_attention_dashboard_prioritises_errors_and_approvals():
    archive = [{
        "report_label": "Kveldsrapport", "created_at_local": "25.07.2026 18:00",
        "has_errors": True, "error_count": 2, "reserve_feed_used": True,
        "report_reliability": 55, "urgent_task_count": 1, "next_task_count": 3,
        "decision_ready_count": 2, "top3_changed": True,
    }]
    items = build_attention_items(archive, pending_approvals=2, scheduler_ok=False, max_items=10)
    assert items[0]["severity"] == "critical"
    assert {x["code"] for x in items} >= {"REPORT_ERRORS", "LOW_RELIABILITY", "PENDING_APPROVALS", "SCHEDULER_ERROR"}


def test_attention_dashboard_handles_empty_and_all_clear():
    assert build_attention_items([])[0]["code"] == "REPORT_MISSING"
    healthy = [{"report_label": "Morgenrapport", "report_reliability": 92}]
    assert build_attention_items(healthy)[0]["code"] == "ALL_CLEAR"


def test_candidate_action_payload_normalises_details():
    payload = candidate_action_payload({
        "ticker": "eqnr.ol", "candidate_state": "review", "score": 7.1,
        "previous_score": 6.8, "blockers": "Mangler primærkilde",
        "change_conditions": ["Score over 7.3"], "sources": {"name": "E24"},
    })
    assert payload["ticker"] == "EQNR.OL"
    assert payload["status"] == "Krever vurdering"
    assert payload["blockers"] == ["Mangler primærkilde"]
    assert payload["sources"][0]["name"] == "E24"
    assert '"ticker": "eqnr.ol"' in payload["export_json"]
