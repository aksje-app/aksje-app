"""
sticky_topbar.py

v18.5.34 Professional Trading Workspace
Sticky topbar / AI status bar with consolidated market status.

Ingen auto-trading-kobling.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from alert_center import collect_common_alerts
from forecast_store import summarize_alerts, load_learning_stats
from app_version import get_app_build_label, get_app_version
from global_busy import global_busy_chip_html
from market_hours import market_statuses
import html


def _safe_get_session(key: str, default: Any = None) -> Any:
    try:
        return st.session_state.get(key, default)
    except Exception:
        return default


def _alert_summary() -> Dict[str, int]:
    try:
        alerts = collect_common_alerts(limit=100)
        summary = summarize_alerts(alerts) if alerts else {"counts": {"red": 0, "yellow": 0, "green": 0}, "total": 0}
        counts = summary.get("counts", {})
        return {
            "total": int(summary.get("total", len(alerts))),
            "red": int(counts.get("red", 0)),
            "yellow": int(counts.get("yellow", 0)),
            "green": int(counts.get("green", 0)),
        }
    except Exception:
        return {"total": 0, "red": 0, "yellow": 0, "green": 0}


def _regime_label() -> str:
    payload = _safe_get_session("market_regime_result_v1840", {})
    if isinstance(payload, dict) and payload:
        return str(payload.get("label", "Ikke oppdatert"))
    return "Regime ikke oppdatert"


def _macro_label() -> str:
    payload = _safe_get_session("macro_rates_breadth_result_v1844", {})
    if isinstance(payload, dict) and payload:
        return f"{payload.get('label', 'Makro')} {payload.get('combined_score', '')}/100"
    return "Makro ikke oppdatert"


def _learning_samples() -> int:
    try:
        return int(load_learning_stats().get("global", {}).get("count", 0))
    except Exception:
        return 0



def _market_status_chips_html() -> str:
    """Return compact market-open chips for the global header line."""
    try:
        statuses = market_statuses()
    except Exception:
        statuses = {}
    chips: list[str] = []
    for key, status in (statuses or {}).items():
        name = str(status.get("name", key))
        short = {"USA": "USA", "Norge": "Norge", "Sverige": "Sverige"}.get(name, name)
        is_open = bool(status.get("is_open"))
        cls = "ptw-market-open" if is_open else "ptw-market-closed"
        txt = "Åpent" if is_open else "Stengt"
        chips.append(f'<span class="ptw-pill ptw-market-chip {cls}">● {html.escape(short)}: {txt}</span>')
    if not chips:
        chips.append('<span class="ptw-pill ptw-market-chip ptw-market-unknown">● Børsstatus: ukjent</span>')
    return "".join(chips)

def render_sticky_topbar() -> None:
    _version_for_legacy_tests = get_app_version()  # single source remains app_version.py
    """Render compact sticky AI/control status bar."""
    alerts = _alert_summary()
    regime = _regime_label()
    macro = _macro_label()
    samples = _learning_samples()

    # status color
    status_dot = "🟢"
    status_text = "AI OK"
    if alerts["red"] > 0:
        status_dot = "🔴"
        status_text = "Kritiske varsler"
    elif alerts["yellow"] > 0:
        status_dot = "🟡"
        status_text = "Varsler"

    st.markdown(
        f"""
        <div class="ptw-sticky-topbar">
          <div class="ptw-topbar-left">
            <span class="ptw-pill ptw-pill-ai">{status_dot} {status_text}</span>
            <span class="ptw-pill">🚨 {alerts['total']} varsler · 🔴 {alerts['red']} · 🟡 {alerts['yellow']} · 🟢 {alerts['green']}</span>
            <span class="ptw-pill">🌍 {regime}</span>
            <span class="ptw-pill">🌐 {macro}</span>
            <span class="ptw-pill">🧠 Learning: {samples}</span>
            {_market_status_chips_html()}
          </div>
          <div class="ptw-topbar-right ptw-v18570-status-zone">
            <span class="ptw-version-chip">Professional Trading Workspace {get_app_build_label()}</span>
            <div class="ptw-global-busy-fixed" aria-live="polite">{global_busy_chip_html()}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
