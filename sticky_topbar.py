"""
sticky_topbar.py

v18.5.21 Professional Trading Workspace
Sticky topbar / AI status bar.

Ingen auto-trading-kobling.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from alert_center import collect_common_alerts
from forecast_store import summarize_alerts, load_learning_stats
from app_version import get_app_version
from global_busy import global_busy_chip_html


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


def render_sticky_topbar() -> None:
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
          </div>
          <div class="ptw-topbar-right">
            {global_busy_chip_html()}
            <span class="ptw-subtle">Professional Trading Workspace {get_app_version()}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
