from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import controlled_parameter_learning as cpl
from autonomous_portfolio import AutonomousParameters
from decision_intelligence import (
    build_candidate_decision_diff,
    build_counter_hypothesis,
    build_historical_evaluations,
)
from report_contracts import ensure_report_document, section_payload


def _candidate(ticker: str, score: float, action: str, *, price: float, risk: float = 42.0) -> dict:
    return {
        "ticker": ticker,
        "rank": 1,
        "market": "Norge",
        "investment_score": score,
        "fundamental_score": score - 5,
        "research_score": score - 2,
        "confidence_score": 82,
        "risk_score": risk,
        "portfolio_action": action,
        "valid_for_decision": action == "BUY",
        "evidence_valid_for_decision": action == "BUY",
        "data_contract": {"validity": "VALID", "source": "LIVE"},
        "decision_readiness": {"allowed_action": action, "conflicts": 0},
        "raw": {
            "current_price": price,
            "rsi": 76,
            "distance_50d_pct": 12,
            "news_intelligence": {
                "sentiment_score": 55,
                "events": [
                    {"source": "Reuters", "title": "Resultat bekreftet"},
                    {"source": "E24", "title": "Markedskommentar"},
                ],
                "search_log": [
                    {"source": "Reuters", "status": "SUCCESS_WITH_RESULTS", "results": 1, "source_type": "PRIMARY_OR_DIRECT_RSS"},
                    {"source": "E24", "status": "SUCCESS_WITH_RESULTS", "results": 1, "source_type": "PUBLISHED_NEWS"},
                ],
            },
            "insider_intelligence": {"coverage": "AVAILABLE", "net_value": 0, "official_source": "Oslo Børs"},
        },
    }


def _contract(ticker: str, *, ready: bool, consensus: str = "STERK") -> dict:
    return {
        "ticker": ticker,
        "confidence": {
            "data_coverage": 90,
            "source_confidence": 88,
            "decision_confidence": 85 if ready else 60,
            "decision_ready": ready,
        },
        "source_consensus": {"level": consensus, "independent_sources": 3, "primary_source_present": True},
        "validity": {"valid_until": "2026-07-26T10:00:00+02:00"},
        "blockers": [] if ready else ["Score er under beslutningsterskel"],
        "change_conditions": ["Score må nå minst 78"],
    }


def _run(candidate: dict) -> dict:
    return {
        "run_id": "MI-1930-CURRENT",
        "created_at": "2026-07-25T18:30:00+00:00",
        "timezone_name": "Europe/Oslo",
        "job_name": "v19.3.0 test",
        "trigger": "SCHEDULED",
        "markets": ["Norge"],
        "summary": {"scanned": 1, "deep_analyzed": 1, "proposals": 1, "recommended": 1},
        "candidates": [candidate],
        "portfolio_decisions": {"production_threshold": 78, "actions": {candidate["portfolio_action"]: 1}},
        "report_status": {"state": "FINAL", "label": "ENDELIG"},
        "report_revision": {"revision": 1, "revision_label": "R1", "content_sha256": "abc"},
        "errors": [],
        "warnings": [],
    }


def test_decision_diff_separates_data_model_and_rule_without_mutation():
    previous = _candidate("EQNR.OL", 75, "REVIEW", price=100)
    current = _candidate("EQNR.OL", 81, "BUY", price=106)
    before = deepcopy(current)
    diff = build_candidate_decision_diff(current, previous, _contract("EQNR.OL", ready=True), _contract("EQNR.OL", ready=False), threshold=78, risk_limit=65)
    assert diff["data_diff"]
    assert diff["model_diff"]
    assert any(row["rule"] == "ACTION" for row in diff["decision_diff"])
    assert any(row["rule"] == "SCORE_THRESHOLD" for row in diff["decision_diff"])
    assert diff["net_score_delta"] == 6
    assert current == before


def test_counter_hypothesis_is_grounded_in_named_data_source():
    candidate = _candidate("EQNR.OL", 81, "BUY", price=106)
    counter = build_counter_hypothesis(candidate, _contract("EQNR.OL", ready=True), threshold=78, risk_limit=65)
    assert counter["strongest_argument"]
    assert counter["evidence"]
    assert all(row.get("fact") and row.get("source") for row in counter["evidence"])
    assert counter["confirmation_conditions"]
    assert counter["weakening_conditions"]
    assert counter["changes_production_decision"] is False


def test_report_document_contains_complete_decision_contract_and_new_sections():
    previous_candidate = _candidate("EQNR.OL", 75, "REVIEW", price=100)
    previous = _run(previous_candidate)
    previous["run_id"] = "MI-1930-PREVIOUS"
    ensure_report_document(previous)

    current_candidate = _candidate("EQNR.OL", 81, "BUY", price=106)
    current = _run(current_candidate)
    document = ensure_report_document(current, previous)
    keys = [row["key"] for row in document["sections"]]
    for key in ("decision_diffs", "counter_hypotheses", "historical_evaluations", "controlled_learning_guard"):
        assert key in keys
    candidate = section_payload(document, "candidate_decisions", [])[0]
    contract = candidate["decision_contract"]
    for key in (
        "decision", "rationale", "validity", "critical_assumptions", "invalidating_events",
        "counter_hypothesis", "data_coverage", "source_confidence", "decision_confidence",
        "source_consensus", "next_review",
    ):
        assert key in contract
    assert candidate["counter_hypothesis"]["changes_production_decision"] is False


def test_expired_historical_decision_is_evaluated_against_current_run():
    previous_candidate = _candidate("EQNR.OL", 79, "BUY", price=100)
    current_candidate = _candidate("EQNR.OL", 74, "REVIEW", price=90)
    previous = _run(previous_candidate)
    previous["decision_report"] = {
        "candidate_contracts": [{
            **_contract("EQNR.OL", ready=True),
            "action": "BUY",
            "score": 79,
            "validity": {"valid_until": "2026-07-24T10:00:00+00:00"},
            "critical_assumptions": [{"code": "SCORE", "holds": True}],
        }]
    }
    current = _run(current_candidate)
    rows = build_historical_evaluations(current, previous, [], now="2026-07-25T18:30:00+00:00")
    assert rows
    assert rows[0]["ticker"] == "EQNR.OL"
    assert rows[0]["expired"] is True
    assert rows[0]["price_return_pct"] == -10.0
    assert rows[0]["action_changed"] is True



def test_decision_diff_survives_renderer_refresh_without_previous_argument():
    previous = _run(_candidate("EQNR.OL", 75, "REVIEW", price=100))
    previous["run_id"] = "MI-1930-PREVIOUS"
    ensure_report_document(previous)
    current = _run(_candidate("EQNR.OL", 81, "BUY", price=106))
    ensure_report_document(current, previous)
    initial = deepcopy(current["decision_diffs"])
    ensure_report_document(current)
    assert current["decision_diffs"] == initial
    row = current["decision_diffs"]["by_ticker"]["EQNR.OL"]
    assert row["has_previous"] is True
    assert row["net_score_delta"] == 6

def _learning_store(monkeypatch: pytest.MonkeyPatch):
    hypothesis = {
        "hypothesis_id": "H-TEST",
        "status": "TESTING",
        "lifecycle_status": "SIMULERT",
        "parameter": "minimum_investment_score",
        "before": 78.0,
        "after": 81.0,
        "production_applied": False,
    }
    store = {
        cpl.HYPOTHESES_PATH: [hypothesis],
        cpl.VERSIONS_PATH: [],
        cpl.APPROVALS_PATH: [],
        cpl.EXPERIMENTS_PATH: [],
        cpl.STATE_PATH: cpl.default_state(),
    }

    def read(path, default):
        return deepcopy(store.get(path, default))

    def write(path, value):
        store[path] = deepcopy(value)

    monkeypatch.setattr(cpl, "_read", read)
    monkeypatch.setattr(cpl, "_write", write)
    monkeypatch.setattr(cpl, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(cpl, "_notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(cpl, "load_parameters", lambda: AutonomousParameters())
    monkeypatch.setattr(cpl, "calculate_performance", lambda: {"profit_factor": 1.1, "drawdown_pct": 2.0})
    return store


def test_shadow_trial_never_writes_production_parameters(monkeypatch):
    store = _learning_store(monkeypatch)
    monkeypatch.setattr(cpl, "save_parameters", lambda *args, **kwargs: pytest.fail("shadow trial changed production"))
    trial = cpl.apply_trial("H-TEST")
    assert trial["mode"] == "SHADOW_READ_ONLY"
    assert trial["production_applied"] is False
    assert trial["lifecycle_status"] == "PARALLELLTESTET"
    assert store[cpl.HYPOTHESES_PATH][0]["production_applied"] is False


def test_promotion_requires_real_pending_user_approval(monkeypatch):
    store = _learning_store(monkeypatch)
    trial = cpl.apply_trial("H-TEST")
    with pytest.raises(PermissionError):
        cpl.promote_trial()
    with pytest.raises(PermissionError):
        cpl.promote_trial(explicit_user_approval=True, approval_id="PA-NOT-FOUND")
    store[cpl.APPROVALS_PATH] = [{"approval_id": "PA-OK", "version_id": trial["version_id"], "status": "PENDING"}]
    calls = []
    monkeypatch.setattr(cpl, "save_parameters", lambda params: calls.append(params))
    promoted = cpl.promote_trial(explicit_user_approval=True, approval_id="PA-OK")
    assert promoted["lifecycle_status"] == "GODKJENT"
    assert promoted["production_applied"] is True
    assert len(calls) == 1


def test_legacy_settings_cannot_reenable_automatic_production_changes(monkeypatch):
    legacy = cpl.default_state()
    legacy.update({"auto_promote": True, "auto_rollback": True, "allow_auto_promotion": True, "production_parameter_auto_change_allowed": True})
    monkeypatch.setattr(cpl, "_read", lambda path, default: deepcopy(legacy) if path == cpl.STATE_PATH else deepcopy(default))
    state = cpl.load_state()
    policy = cpl._mode_policy(state)
    assert state["auto_promote"] is False
    assert state["auto_rollback"] is False
    assert state["production_parameter_auto_change_allowed"] is False
    assert policy["auto_promote"] is False
    assert policy["auto_rollback"] is False


def test_learning_lifecycle_and_protected_rules_are_explicit():
    assert cpl.LEARNING_LIFECYCLE == (
        "HYPOTESE", "SIMULERT", "PARALLELLTESTET", "KLAR_FOR_VURDERING",
        "GODKJENT", "AVVIST", "TILBAKERULLERT",
    )
    for key in ("minimum_investment_score", "maximum_position_pct", "maximum_drawdown_pct", "stop_loss_pct", "maximum_risk_score"):
        assert key in cpl.PROTECTED_PRODUCTION_PARAMETERS


def test_public_pdf_button_and_desktop_mobile_navigation_have_stable_css_guards():
    root = Path(__file__).resolve().parents[1]
    autonomy = (root / "autonomy_overview.py").read_text(encoding="utf-8")
    app = (root / "app.py").read_text(encoding="utf-8")
    assert "right.link_button" not in autonomy
    assert "_render_report_link(delivery[\"url\"])" in autonomy
    assert "↗ Åpne offentlig PDF" in autonomy
    assert 'class="mobile-bottom-nav-v18644" aria-label="Mobilnavigasjon" style="display:none"' in app
    assert "html body .mobile-bottom-nav-v18644 {{ display:none !important" in app
    assert "@media (max-width: 760px)" in app
    assert "display:flex !important" in app
