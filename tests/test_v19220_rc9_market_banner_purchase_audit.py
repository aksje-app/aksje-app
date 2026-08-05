from pathlib import Path
from types import SimpleNamespace

from market_universe import (
    CORE_MARKET_SCOPE_LABEL,
    EXTENDED_NORDIC_SCOPE_LABEL,
    FULL_MARKET_SCOPE_LABEL,
    MARKET_SCOPE_OPTIONS,
    NORDIC_MARKET_SCOPE_LABEL,
    expand_market_scope,
    market_profile_contract,
)
from navigation_state import AUTONOMY_PANEL, pin_autonomy_workspace_route_v19220_rc11
from autonomi_core.portfolio_decisions.decision_funnel import build_decision_funnel
from market_intelligence import build_market_coverage_v19220_rc9


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.query_params = {"aa_nav": "analysis", "aa_panel": "AI Kandidattest", "remember_token": "secret"}


def test_market_choices_name_the_exact_countries_and_keep_legacy_aliases():
    assert CORE_MARKET_SCOPE_LABEL == "Norge + Sverige + USA"
    assert EXTENDED_NORDIC_SCOPE_LABEL == "Danmark + Finland"
    assert NORDIC_MARKET_SCOPE_LABEL == "Norge + Sverige + Danmark + Finland"
    assert FULL_MARKET_SCOPE_LABEL == "Norge + Sverige + Danmark + Finland + USA + Brasil"
    assert "Utvidet Norden" not in MARKET_SCOPE_OPTIONS
    assert "Kjernemarkeder" not in MARKET_SCOPE_OPTIONS
    assert expand_market_scope("Utvidet Norden") == ["Danmark", "Finland"]
    contract = market_profile_contract("EXTENDED_NORDIC", ["Utvidet Norden"])
    assert contract["label"] == "Danmark + Finland"
    assert contract["country_text"] == "Danmark, Finland"


def test_report_action_route_pin_stays_on_reports_and_removes_tokens():
    st = FakeStreamlit()
    pin_autonomy_workspace_route_v19220_rc11(st, workspace_slug="reports", public_nav="reports")
    assert st.session_state["active_nav_target_v18674c"] == "reports"
    assert st.session_state["ai_control_center_active_panel_v1863aj"] == AUTONOMY_PANEL
    assert st.session_state["autonomy_core_workspace_slug_v1882"] == "reports"
    assert st.session_state["ai_control_center_route_lock_v19220_rc6"]["panel"] == AUTONOMY_PANEL
    assert "ai_control_center_group_radio_v1863aj" not in st.session_state
    assert "ai_control_center_panel_radio_v1863aj_Autonomi" not in st.session_state
    assert st.query_params["aa_nav"] == "autonomy"
    assert st.query_params["aa_tab"] == "reports"
    assert "remember_token" not in st.query_params


def test_banner_components_are_independent_in_runtime_source():
    source = Path("app.py").read_text(encoding="utf-8")
    start = source.index("def _special_watch_banner_css_v19220_rc9")
    end = source.index("def _special_watch_ticker_items_v18623", start)
    special = source[start:end]
    assert "special-watch-surface-v19220rc9" in special
    assert "special-watch-item-v19220rc9" in special
    assert "ticker-tape-item'" not in special
    assert "ticker-tape-wrap special-watch" not in special
    assert "if not special_banner_enabled(settings, st.session_state):\n        return" in special


def test_report_center_reruns_pin_the_reports_route():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "def _rerun_reports_v19220_rc11" in source
    quick = source[source.index('if q1.button("📄 Nytt utkast"'):source.index("unavailable = []")]
    assert "_rerun_reports_v19220_rc11(st)" in quick
    assert "st.rerun()" not in quick


def test_analytical_buy_can_be_blocked_by_autonomy_portfolio_capacity():
    params = SimpleNamespace(
        minimum_investment_score=73,
        minimum_data_quality=55,
        maximum_risk_score=65,
        maximum_open_positions=2,
        allow_additions=False,
    )
    candidate = {
        "ticker": "TEST.OL",
        "market": "Norge",
        "investment_score": 82,
        "data_quality": 95,
        "risk_score": 20,
        "price": 100,
        "mission_eligible": True,
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "technical_entry_wait": False,
        "portfolio_action": "REVIEW",
        "autonomy_outcome_code": "OVERVÅKES_AUTOMATISK",
        "final_decision_ready": False,
    }
    portfolio = {
        "status": "ACTIVE",
        "positions": {"AAA.OL": {"quantity": 1}, "BBB.OL": {"quantity": 1}},
    }
    result = build_decision_funnel([candidate], parameters=params, portfolio=portfolio)
    row = result["candidates"][0]
    assert row["analytical_recommendation"] == "BUY_RECOMMENDED"
    assert row["trade_execution_status"] == "BLOCKED_AUTONOMY_PORTFOLIO"
    assert row["portfolio_capacity_blocked"] is True
    assert row["would_be_buy_without_autonomy_portfolio_constraints"] is True
    assert result["analytical_buy_recommendations"] == 1
    assert result["trade_executable"] == 0
    assert result["capacity_blocked_buy_recommendations"] == 1
    assert result["production_threshold_changed"] is False


def test_market_coverage_reports_planned_actual_and_failed_countries():
    result = build_market_coverage_v19220_rc9({
        "markets": ["Norge", "Sverige", "Danmark", "Finland"],
        "scan_configuration": {"actual_by_market": {"Norge": 25, "Sverige": 25, "Danmark": 0, "Finland": 20}},
        "market_diagnostics": [
            {"market": "Norge", "status": "OK", "scanned": 25},
            {"market": "Sverige", "status": "OK", "scanned": 25},
            {"market": "Danmark", "status": "ERROR", "scanned": 0, "errors": 1},
            {"market": "Finland", "status": "PARTIAL", "scanned": 20, "errors": 1},
        ],
    })
    assert result["overall_status"] == "PARTIAL"
    assert result["completed_markets"] == ["Norge", "Sverige"]
    assert result["partial_markets"] == ["Finland"]
    assert result["failed_or_skipped_markets"] == ["Danmark"]


class WidgetProtectedState(dict):
    def __setitem__(self, key, value):
        if key in {
            "ai_control_center_group_radio_v1863aj",
            "ai_control_center_panel_radio_v1863aj_Autonomi",
        }:
            raise RuntimeError(f"widget key was modified after instantiation: {key}")
        super().__setitem__(key, value)


def test_report_route_pin_never_mutates_instantiated_widget_keys():
    st = FakeStreamlit()
    st.session_state = WidgetProtectedState()
    pin_autonomy_workspace_route_v19220_rc11(
        st, workspace_slug="reports", public_nav="reports",
    )
    assert st.session_state["ai_control_center_route_lock_v19220_rc6"]["tab"] == "reports"
    assert st.query_params["aa_tab"] == "reports"
