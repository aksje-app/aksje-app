from __future__ import annotations

from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from pages.overview import _portfolio_summary
from ui_library.shell import canonical_shell_route

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_identity_rc16_34b():
    assert APP_VERSION in {"v19.22.0-rc16.34b", "v19.22.0-rc16.34c", "v19.22.0-rc16.34d", "v19.22.0-rc16.34e", "v19.22.0-rc16.34f", "v19.22.0-rc16.34g", "v19.22.0-rc16.34h"}
    if APP_VERSION == "v19.22.0-rc16.34b":
        assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.34a"
    elif APP_VERSION == "v19.22.0-rc16.34c":
        assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.34b"
    elif APP_VERSION == "v19.22.0-rc16.34d":
        assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.34c"
    elif APP_VERSION == "v19.22.0-rc16.34e":
        assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.34d"
    elif APP_VERSION == "v19.22.0-rc16.34f":
        assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.34e"
    elif APP_VERSION == "v19.22.0-rc16.34g":
        assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.34f"
    else:
        assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.34g"


def test_super_portfolio_is_canonical_market_route():
    assert canonical_shell_route("super_portfolio") == "market"
    navigation = _source("navigation_state.py")
    assert '"🌍 Super Portfolio": "market"' in navigation


def test_active_control_center_registers_super_portfolio_renderer():
    source = _source("workspace_layout.py")
    start = source.index("def _render_ai_control_center_v1863aj")
    block = source[start:]
    assert '("🌍 Super Portfolio", _render_super_portfolio_market_panel_v1934b)' in block
    assert '"Marked og signaler": _matching_panel_labels("super portfolio"' in block


def test_direct_super_portfolio_route_renders_before_legacy_dashboard():
    source = _source("app.py")
    direct = source.index("# RC16.34b: Super Portfolio is a true first-class Market page.")
    legacy = source.index("# A+B Overview is a true replacement page.")
    assert direct < legacy
    block = source[direct:legacy]
    assert '_direct_sp_panel_v1934b == "🌍 Super Portfolio"' in block
    assert "render_super_portfolio as _render_super_portfolio_direct_v1934b" in block
    assert "_render_super_portfolio_direct_v1934b(" in block
    assert "st.stop()" in block


def test_start_page_summary_contains_real_position_rows():
    state = {
        "initial_cash": 500_000.0,
        "portfolio_value": 510_000.0,
        "portfolio_return_pct": 2.0,
        "positions": {
            "AAA": {
                "ticker": "AAA",
                "target_weight_pct": 20.0,
                "pnl_pct": 5.0,
                "distance_to_hard_stop_pct": 4.2,
                "stop_pressure": "MEDIUM",
            },
            "BBB": {
                "ticker": "BBB",
                "target_weight_pct": 10.0,
                "pnl_pct": -2.0,
                "distance_to_hard_stop_pct": 0.8,
                "stop_pressure": "CRITICAL",
            },
        },
    }
    summary = _portfolio_summary(state)
    assert summary["positions"] == 2
    assert len(summary["position_rows"]) == 2
    aaa = next(row for row in summary["position_rows"] if row["ticker"] == "AAA")
    bbb = next(row for row in summary["position_rows"] if row["ticker"] == "BBB")
    assert aaa["value_nok"] == 102_000.0
    assert aaa["pnl_nok"] == 5_100.0
    assert aaa["distance_to_stop_pct"] == 4.2
    assert bbb["status"] == "CRITICAL"


def test_start_page_visibly_renders_holdings_and_primary_open_button():
    source = _source("pages/overview.py")
    assert 'st_module.markdown("### Porteføljen nå")' in source
    assert '"Verdi NOK": row.get("value_nok")' in source
    assert '"P/L NOK": row.get("pnl_nok")' in source
    assert '"Til stop %": distance if distance is not None else None' in source
    assert 'st_module.button("🌍 Åpne hele Super Portfolio"' in source
    assert 'navigate("super_portfolio")' in source


def test_super_portfolio_page_starts_with_decision_and_visual_overview():
    source = _source("pages/super_portfolio.py")
    assert 'st.markdown("### 🚦 Hva skjer nå?")' in source
    assert '"Verdi NOK": round(position_value,0)' in source
    assert '"P/L NOK": round(position_pnl_nok,0)' in source
    assert 'st.markdown("### 📈 Utvikling – totalt")' in source
    assert 'st.markdown("### 📉 Utvikling – alle aksjer")' in source
    assert 'st.markdown("### 🧮 Hvem skaper resultatet?")' in source
    assert 'with st.expander("🧾 Innsiderkontroll – lesbar visning"' in source


def test_compact_market_card_does_not_stack_raw_event_markdown():
    source = _source("app.py")
    start = source.index("def render_super_portfolio_front_window_v1932c")
    end = source.index("def cached_auto_rank_market", start)
    block = source[start:end]
    assert "event_lines" not in block
    assert 'st.markdown("**Hva krever oppmerksomhet?**")' in block
    assert "st.error(" in block
    assert "st.warning(" in block
    assert "Porteføljeverdi NOK" in block
