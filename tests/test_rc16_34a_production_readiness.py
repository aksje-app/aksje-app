from __future__ import annotations

from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from pages.overview import _portfolio_summary
from public_report_ui import _return_label, _return_query, _safe_return_nav
from quality_stability_contract import is_supported_deep_link_nav
from quality_valuation_ui import (
    resolve_market_bound_manual_tickers,
    validate_result_tickers_within_requested_market,
)
from ui_library.shell import canonical_shell_route
from market_universe import production_market_scope_options

ROOT = Path(__file__).resolve().parents[1]


def test_production_market_picker_exposes_only_core_markets():
    options = production_market_scope_options(include_aggregate=True)
    assert options == ["Norge", "Sverige", "USA", "Norge + Sverige + USA"]
    assert "Brasil" not in options
    assert "Danmark" not in options
    assert "Finland" not in options


def test_all_primary_stock_entry_surfaces_use_production_market_options():
    top = (ROOT / "pages" / "top_picks.py").read_text(encoding="utf-8")
    pipeline = (ROOT / "investment_pipeline.py").read_text(encoding="utf-8")
    ai = (ROOT / "analysis_universe_ai.py").read_text(encoding="utf-8")
    assert "production_market_scope_options(include_aggregate=True)" in top
    assert "production_market_scope_options(include_aggregate=True)" in pipeline
    assert "production_market_scope_options(include_aggregate=True)" in ai
    assert "checkbox_markets = CORE_MARKET_SCOPES + [CORE_MARKET_SCOPE_LABEL]" in ai


def test_manual_quality_ticker_is_bound_to_selected_market_universe():
    resolved, errors = resolve_market_bound_manual_tickers(
        ["ALM"], ["ALM.OL", "EQNR.OL", "DNB.OL"]
    )
    assert resolved == ["ALM.OL"]
    assert errors == []


def test_manual_quality_ticker_never_falls_back_to_foreign_same_symbol():
    resolved, errors = resolve_market_bound_manual_tickers(
        ["ALM"], ["EQNR.OL", "DNB.OL"]
    )
    assert resolved == []
    assert errors == ["ALM: finnes ikke i valgt marked"]


def test_manual_quality_ticker_rejects_wrong_market_suffix():
    resolved, errors = resolve_market_bound_manual_tickers(
        ["ALM", "MSFT", "VOLV-B.ST"], ["ALM.OL", "EQNR.OL", "DNB.OL"]
    )
    assert resolved == ["ALM.OL"]
    assert "MSFT: finnes ikke i valgt marked" in errors
    assert "VOLV-B.ST: finnes ikke i valgt marked" in errors


def test_quality_result_cannot_escape_requested_market_boundary():
    result = {
        "groups": {
            "Kvalitetsselskap": [{"ticker": "ALM"}],
            "Ufullstendig / krever vurdering": [{"ticker": "EQNR.OL"}],
        }
    }
    assert validate_result_tickers_within_requested_market(result, ["ALM.OL", "EQNR.OL"]) == ["ALM"]


def test_quality_ui_persists_and_checks_selected_market():
    source = (ROOT / "quality_valuation_ui.py").read_text(encoding="utf-8")
    assert 'result["selected_market"] = str(selected_market or "")' in source
    assert 'result_market != str(selected_market).strip()' in source
    assert "MARKET_IDENTITY_MISMATCH" in source


def test_start_page_uses_authoritative_super_portfolio_nav_not_open_position_pnl():
    state = {
        "initial_cash": 1_000_000.0,
        "portfolio_value": 1_050_000.0,
        "portfolio_return_pct": 5.0,
        "positions": {
            "AAA": {"target_weight_pct": 50.0, "pnl_pct": 40.0},
            "BBB": {"target_weight_pct": 25.0, "pnl_pct": -20.0},
        },
        "history": [
            {"at": "2026-09-28T12:00:00+00:00", "portfolio_value": 1_010_000.0, "portfolio_return_pct": 1.0},
            {"at": "2026-09-29T12:00:00+00:00", "portfolio_value": 1_050_000.0, "portfolio_return_pct": 5.0},
        ],
    }
    summary = _portfolio_summary(state)
    assert summary["value"] == 1_050_000.0
    assert summary["return_pct"] == 5.0
    assert summary["history_returns"][-2:] == [1.0, 5.0]
    assert summary["cash_pct"] == 25.0


def test_super_portfolio_report_return_is_first_class():
    assert _safe_return_nav("super_portfolio") == "super_portfolio"
    assert _return_query("super_portfolio") == {"aa_nav": "super_portfolio"}
    assert _return_label("super_portfolio") == "← Tilbake til Super Portfolio"
    assert is_supported_deep_link_nav("super_portfolio")
    assert canonical_shell_route("super_portfolio") == "autonomy"


def test_market_context_is_passed_into_quality_ui():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    block_start = source.index("if view == \"Kvalitet og prising\":")
    block_end = source.index('elif view == "Rangering":', block_start)
    block = source[block_start:block_end]
    assert "selected_market=str(config.get(\"market\") or \"AI kildegrunnlag\")" in block


def test_super_portfolio_share_and_print_both_return_to_super_portfolio():
    source = (ROOT / "pages" / "super_portfolio.py").read_text(encoding="utf-8")
    assert 'returning_report_url = with_report_return(report_url, "super_portfolio")' in source
    assert 'd2.link_button("🔗 Åpne / del", returning_report_url' in source
    assert 'd3.link_button("🖨️ Print PDF", returning_report_url' in source
    assert 'st.code(returning_report_url' in source
    assert 'with_report_return(report_url, "portfolio")' not in source


def test_release_identity():
    assert APP_VERSION == "v19.22.0-rc16.34a"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.33q"
