from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import sys
import types

from pypdf import PdfReader

streamlit_stub = sys.modules.get("streamlit")
if streamlit_stub is None:
    streamlit_stub = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit_stub
components_stub = sys.modules.get("streamlit.components")
if components_stub is None:
    components_stub = types.ModuleType("streamlit.components")
    sys.modules["streamlit.components"] = components_stub
components_v1_stub = sys.modules.get("streamlit.components.v1")
if components_v1_stub is None:
    components_v1_stub = types.ModuleType("streamlit.components.v1")
    sys.modules["streamlit.components.v1"] = components_v1_stub
if not hasattr(components_v1_stub, "html"):
    components_v1_stub.html = lambda *args, **kwargs: None
setattr(streamlit_stub, "components", components_stub)
setattr(components_stub, "v1", components_v1_stub)

import auth
import market_intelligence as mi
import navigation_state
import ui_sidebar_stable
from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from report_contracts import ensure_report_document


ROOT = Path(__file__).resolve().parents[1]


def _candidate(ticker: str, rank: int, score: float) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "market": "Norge",
        "rank": rank,
        "investment_score": score,
        "final_score": score,
        "confidence_score": 82,
        "risk_score": 28 + rank,
        "data_quality": 96,
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "portfolio_action": "REVIEW",
        "status": "ANBEFALT FOR VURDERING",
        "confidence_profile": {
            "model_confidence": 82,
            "market_data_coverage": 96,
            "documentation_coverage": 88,
            "data_coverage": 88,
            "source_confidence": 74,
            "calibrated_confidence": 74,
            "decision_confidence": 70,
        },
        "decision_readiness": {
            "status": "KOMPLETT",
            "market_data": "GYLDIG",
            "news": "CHECKED_NO_EVENTS",
            "insider": "CHECKED_NO_EVENTS",
            "allowed_action": "REVIEW",
        },
        "raw": {
            "technical": {"rsi": 51.25},
            "fundamental": {"roe": 17.5},
            "insider_intelligence": {
                "coverage": "CHECKED_NO_EVENTS",
                "evidence": [],
                "search_log": [{"attempted": True, "status": "SUCCESS_NO_RESULTS", "source": "Primærkilde"}],
            },
            "news_intelligence": {
                "coverage": "CHECKED_NO_EVENTS",
                "events": [],
                "search_log": [{"attempted": True, "status": "SUCCESS_NO_RESULTS", "source": "Utgiver"}],
            },
        },
    }


def _run() -> dict:
    rows = [
        _candidate("AAA.OL", 1, 81.25),
        _candidate("BBB.OL", 2, 78.5),
        _candidate("CCC.OL", 3, 76.75),
    ]
    return {
        "run_id": "MI-RC4-FRONT-PAGE",
        "created_at": "2026-08-04T11:30:00+00:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "JOB-MORNING",
        "job_name": "Morgenanalyse",
        "trigger": "SCHEDULED",
        "markets": ["Norge"],
        "summary": {"scanned": 3, "deep_analyzed": 3, "proposals": 3},
        "data_quality": {"score": 96},
        "combined_data_quality": {"evaluated": 3, "market_data_valid": 3, "overall_valid": 3},
        "candidates": rows,
        "proposals": [dict(row) for row in rows],
        "portfolio_decisions": {"production_threshold": 73, "actions": {"BUY": 0, "REVIEW": 3, "SKIP": 0}},
        "report_revision": {"revision": 2, "revision_label": "R2", "supersedes_run_id": "MI-RC4-PREV"},
        "changes": {},
    }


def test_rc4_version_identity_is_current() -> None:
    assert APP_VERSION == "v19.22.0-rc16.1"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16"


def test_rc4_pdf_page_one_contains_decision_information_and_top3() -> None:
    run = _run()
    document = ensure_report_document(run)
    metadata = document["metadata"]
    assert metadata["analysis_id"].startswith("AN-")
    assert metadata["analysis_id"] != run["run_id"]
    assert len(metadata["content_sha256"]) == 64

    reader = PdfReader(BytesIO(mi.build_pdf(run)))
    pages = [page.extract_text() or "" for page in reader.pages]
    first = pages[0]
    for label in (
        "Hovedkonklusjon",
        "Beslutningsjustert",
        "Teknisk dokumentasjon",
        "Kandidatenes evidens",
        "Uavhengige kilder",
        "Beslutningsstyrke rapport",
        "Top 1-3 - investeringsrangering",
        "Rapport-ID",
        "Analyse-ID",
        "SHA-256",
        "MI-RC4-PREV",
        "AAA.OL",
        "BBB.OL",
        "CCC.OL",
    ):
        assert label in first
    assert "Rapportpålitelighet" not in first
    assert "Samlet rapportgrunnlag" not in first
    assert "Top 1-3 - investeringsrangering" not in "\n".join(pages[1:])
    assert "Teknisk vedlegg" in "\n".join(pages[1:])
    full_text = "\n".join(pages)
    assert "[########" not in full_text
    assert "Læringskjøp" not in full_text


def test_checked_no_events_is_valid_and_has_zero_penalty() -> None:
    candidate = _candidate("NOEVENT.OL", 1, 80)
    candidate["confidence_score"] = 88
    summary = mi.apply_evidence_coverage_policy([candidate])
    assert candidate["confidence_score"] == 88
    assert candidate["evidence_confidence_penalty"] == 0
    assert candidate["evidence_review_required"] is False
    assert candidate["evidence_valid_for_decision"] is True
    assert candidate["decision_readiness"]["news"] == "CHECKED_NO_EVENTS"
    assert candidate["decision_readiness"]["insider"] == "CHECKED_NO_EVENTS"
    assert summary["reduced"] == 0
    coverage = mi.insider_coverage_by_market([candidate])[0]
    assert coverage["no_events"] == 1
    assert coverage["missing"] == 0
    assert coverage["source_errors"] == 0


def test_report_center_uses_background_progress_and_non_persisting_health_reads() -> None:
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    action = source[source.index('##### 2. Handlinger'):source.index('##### 3. Siste rapporter')]
    assert "st.progress(percent" in source
    assert "_live_report_progress_fragment_v19220_rc161()" in action
    assert "@st.fragment(run_every=\"3s\")" not in action
    assert action.count("start_manual_job(") >= 4
    status = source[source.index('##### 1. Status for planlagte rapporter'):source.index('##### 2. Handlinger')]
    assert "start_manual_job(" in status
    assert 'trigger="MISSED_SCHEDULE_CATCHUP"' in status
    assert "scheduled_for=" in status
    assert "with st.spinner" not in status
    assert "scheduler_health_snapshot(persist=False, jobs=quick_jobs)" in source
    assert '>= 60.0' in source


def test_scheduler_health_ui_read_does_not_write(monkeypatch) -> None:
    writes: list[object] = []
    monkeypatch.setattr(mi, "_write", lambda *args, **kwargs: writes.append((args, kwargs)))
    monkeypatch.setattr(mi, "load_job_history", lambda limit=50: [])
    result = mi.scheduler_health_snapshot(now=datetime(2026, 8, 4), persist=False, jobs=[])
    assert result["active_jobs"] == 0
    assert writes == []


def test_remember_login_uses_revocable_server_validated_cookie(monkeypatch) -> None:
    token = "a" * 64
    fake_st = SimpleNamespace(session_state={}, query_params={})
    monkeypatch.setattr(auth, "st", fake_st)
    monkeypatch.setattr(auth, "_remember_cookie_token_v19143", lambda: token)
    monkeypatch.setattr(auth, "_db_get_remember_item", lambda value: {
        "username": "per",
        "session_version": 7,
        "expires": (datetime.now() + timedelta(days=1)).isoformat(timespec="seconds"),
    })
    monkeypatch.setattr(auth, "get_user", lambda username: {
        "username": username,
        "active": True,
        "session_version": 7,
    })
    restored = auth._restore_from_remember_token()
    assert restored["username"] == "per"
    assert fake_st.session_state["auth_remember_me"] is True
    assert fake_st.session_state["remember_token"] == token
    assert auth._remember_token_hash_v19144(token) != token

    source = (ROOT / "auth.py").read_text(encoding="utf-8")
    for marker in ("SameSite=Strict", "Max-Age=", "Secure", "session_version", "_db_delete_remember_item"):
        assert marker in source
    assert 'searchParams.set("remember_token"' not in source
    assert "window.parent.location.reload" not in source
    assert "localStorage.setItem" not in source


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {
            "ai_control_center_active_panel_v1863aj": "Long Engine",
            "ai_control_center_group_v1863aj": "Long Engine",
            "autonomy_core_workspace_slug_v1882": "operations",
        }
        self.query_params = {
            "remember_token": "secret",
            "remember_bootstrap": "1",
            "panel": "long_engine",
        }

    def rerun(self):
        raise RuntimeError("test rerun")


def test_explicit_menu_click_wins_and_sensitive_url_state_is_removed(monkeypatch) -> None:
    st = _FakeStreamlit()
    monkeypatch.setattr(ui_sidebar_stable, "_sidebar_persist_nav_v18658", lambda *args, **kwargs: None)
    ui_sidebar_stable._sidebar_nav_set_v18650(st, "reports")
    assert st.session_state["active_nav_target_v18674c"] == "reports"
    assert st.session_state["autonomy_core_workspace_slug_v1882"] == "reports"
    assert st.query_params["aa_nav"] == "reports"
    assert "remember_token" not in st.query_params
    assert "remember_bootstrap" not in st.query_params

    ui_sidebar_stable._sidebar_nav_set_v18650(st, "analysis")
    assert st.session_state["active_nav_target_v18674c"] == "analysis"
    assert st.session_state["ai_control_center_active_panel_v1863aj"] == "AI Kandidattest"
    assert st.query_params["aa_nav"] == "analysis"


def test_global_navigation_removes_legacy_sensitive_query_keys() -> None:
    st = SimpleNamespace(
        query_params={"remember_token": "secret", "remember_bootstrap": "1", "aa_nav": "reports"},
    )
    navigation_state.set_global_navigation_state(st, nav="analysis", group="AI Kandidattest", panel="AI Kandidattest")
    assert "remember_token" not in st.query_params
    assert "remember_bootstrap" not in st.query_params
    assert st.query_params["aa_nav"] == "analysis"


def test_sidebar_fallback_copy_is_identical() -> None:
    assert (ROOT / "ui_sidebar_stable.py").read_bytes() == (ROOT / "tools" / "ui_sidebar_stable.py").read_bytes()
