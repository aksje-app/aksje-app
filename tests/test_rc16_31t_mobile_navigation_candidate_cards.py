from __future__ import annotations

from pathlib import Path

import market_intelligence as mi
from navigation_state import (
    apply_route_tab_to_session_state_v19220_rc7,
    current_route_tab_from_session_v19220_rc7,
)


ROOT = Path(__file__).resolve().parents[1]


class _MarkupCapture:
    def __init__(self):
        self.value = ""

    def markdown(self, value, **kwargs):
        assert kwargs.get("unsafe_allow_html") is True
        self.value = str(value)


def test_priority_candidates_render_as_safe_responsive_cards_not_columns():
    st = _MarkupCapture()
    mi._render_priority_candidate_cards_v19220_rc1631t(st, [{
        "ticker": 'SAFE<"', "name": "Selskap <test>", "market": "Norge",
        "investment_score": 76.95, "decision_confidence": 88,
        "risk_score": 41.9, "proposed_position_pct": 4.32,
        "validation_score": 96, "autonomy_outcome_label": "Overvåkes automatisk",
        "automatic_next_action": "Følg kandidaten og vurder den på nytt.",
    }])

    assert "mi-priority-grid-v19220rc1631t" in st.value
    assert "PRIORITET 1" in st.value
    assert "Beslutningskonfidens" in st.value
    assert "Neste handling" in st.value
    assert "Selskap &lt;test&gt;" in st.value
    assert 'SAFE&lt;&quot;' in st.value


def test_mobile_css_stacks_candidates_and_keeps_contract_metrics_two_by_two():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")

    assert ".mi-priority-grid-v19220rc1631t {grid-template-columns:1fr" in source
    assert ".mi-contract-grid-v19220rc1631t {grid-template-columns:repeat(2" in source
    candidate_block = source[source.index("heading = f\"#### Prioritert"):source.index("if latest.get(\"errors\")")]
    assert "_render_priority_candidate_cards_v19220_rc1631t" in candidate_block
    assert "st.columns(min(3" not in candidate_block


def test_report_subsurface_roundtrips_through_route_state():
    state = {}
    changed = apply_route_tab_to_session_state_v19220_rc7(
        state, nav="autonomy", tab="reports", subtab="report_history",
    )

    assert changed is True
    assert state["autonomy_core_workspace_slug_v1882"] == "reports"
    assert state["mi_report_surface_v19220_rc1631t"] == "Rapporter, historikk og avansert"
    state["autonomy_core_workspace_active_slug_v19220_rc7"] = "reports"
    assert current_route_tab_from_session_v19220_rc7(state, nav="autonomy") == (
        "reports", "report_history",
    )


def test_autonomy_has_one_tap_report_shortcuts_and_collapsed_full_menu():
    source = (ROOT / "pages" / "autonomy.py").read_text(encoding="utf-8")

    assert "📚 Rapporter og historikk" in source
    assert "▶️ Kjøring og status" in source
    assert 'with st.expander("Alle arbeidsflater", expanded=False)' in source
    assert 'args=("reports", "Rapporter, historikk og avansert")' in source


def test_report_center_uses_one_selector_instead_of_two_nested_selectors():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    block = source[source.index("def render_market_intelligence()"):]

    assert '"Rapportområde"' in block
    assert 'key=report_surface_key' in block
    assert '"Del av fullt rapportsenter"' not in block
    assert '"Arbeidsområde",\n        ["Hurtigarkiv og komplett ZIP", "Fullt rapportsenter"]' not in block
