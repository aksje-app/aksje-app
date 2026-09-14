from pathlib import Path

import analysis
from report_integrity import canonical_report_view, validate_report_integrity
from tools.build_safe_distribution import required_runtime_delta_file


def _candidate(ticker: str, action: str) -> dict:
    return {
        "ticker": ticker,
        "market": "USA",
        "investment_score": 75.0,
        "confidence_score": 80.0,
        "portfolio_action": action,
        "autonomy_outcome_code": "KJØPSKANDIDAT" if action == "BUY" else "OVERVÅK",
        "autonomy_outcome_reason": "Kanonisk beslutning",
        "valid_for_decision": action == "BUY",
        "raw": {},
    }


def test_partial_portfolio_decisions_are_completed_from_canonical_candidates():
    candidates = [_candidate("AAA", "BUY"), _candidate("BBB", "HOLD"), _candidate("CCC", "SKIP")]
    run = {
        "run_id": "RUN-AJ-PARTIAL",
        "created_at": "2026-08-25T15:00:00+00:00",
        "candidates": candidates,
        "portfolio_decisions": {
            "portfolio_context": {"active": True},
            "decisions": [{"ticker": "AAA", "action": "REVIEW", "custom": "preserved"}],
            "actions": {"REVIEW": 1},
        },
    }

    result = canonical_report_view(run)
    decisions = result["portfolio_decisions"]["decisions"]

    assert [row["ticker"] for row in decisions] == ["AAA", "BBB", "CCC"]
    expected_actions = [row["portfolio_action"] for row in result["candidates"]]
    assert [row["action"] for row in decisions] == expected_actions
    assert decisions[0]["custom"] == "preserved"
    assert sum(result["portfolio_decisions"]["actions"].values()) == len(result["candidates"])
    assert validate_report_integrity(result)["ok"] is True


def test_quarantined_ticker_never_reaches_yfinance(monkeypatch):
    analysis._HISTORY_CACHE.clear()
    monkeypatch.setattr(analysis, "quarantine_status", lambda _ticker: {"active": True})
    monkeypatch.setattr(analysis.yf, "Ticker", lambda _ticker: (_ for _ in ()).throw(AssertionError("network call")))

    assert analysis.get_history("BAD.OL").empty
    assert analysis.get_info("BAD.OL") == {}


def test_minimal_delta_excludes_repository_growth_artifacts():
    assert required_runtime_delta_file("app_version.py") is True
    assert required_runtime_delta_file("report_integrity.py") is True
    assert required_runtime_delta_file("tests/test_release.py") is False
    assert required_runtime_delta_file("tools/validate_distribution.py") is False
    assert required_runtime_delta_file("RELEASE_NOTES_v19.md") is False
    assert required_runtime_delta_file("DISTRIBUTION_MANIFEST.json") is False


def test_production_code_no_longer_uses_removed_components_html_api():
    root = Path(__file__).resolve().parents[1]
    for relative in ("auth.py", "ui_clock.py", "workspace_layout.py"):
        assert "streamlit.components.v1" not in (root / relative).read_text(encoding="utf-8")
