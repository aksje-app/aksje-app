"""
sticky_topbar.py

v18.6.36 compact status topbar
Sticky topbar / AI status bar with consolidated market status.

Ingen auto-trading-kobling.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from alert_center import collect_common_alerts
from forecast_store import summarize_alerts, load_learning_stats
from topbar_status_store import load_status, compact_time
from app_version import get_app_version
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
    if not isinstance(payload, dict) or not payload:
        payload = load_status("market_regime")
    if isinstance(payload, dict) and payload:
        label = str(payload.get("label") or payload.get("market_regime") or "Regime")
        stamp = compact_time(payload.get("updated_at"))
        return f"{label} · {stamp}" if stamp else label
    return "Regime ikke oppdatert"


def _macro_label() -> str:
    payload = _safe_get_session("macro_rates_breadth_result_v1844", {})
    if not isinstance(payload, dict) or not payload:
        payload = load_status("macro_rates_breadth")
    if isinstance(payload, dict) and payload:
        score = payload.get("combined_score")
        label = str(payload.get("label") or "Makro")
        score_text = f" {score}/100" if score not in (None, "") else ""
        stamp = compact_time(payload.get("updated_at"))
        suffix = f" · {stamp}" if stamp else ""
        return f"{label}{score_text}{suffix}"
    return "Makro ikke oppdatert"


def _learning_label() -> str:
    """Return canonical controlled-learning status, not only forecast samples."""
    try:
        from learning_observation_engine import load_engine_state
        state = load_engine_state()
        daily = state.get("daily") if isinstance(state, dict) else {}
        if isinstance(daily, dict) and daily:
            active = int(daily.get("active") or 0)
            updated = int(daily.get("updated") or 0)
            stamp = compact_time(daily.get("completed_at"))
            status = str(daily.get("status") or "AKTIV").upper()
            core = f"{status} · {active} aktive"
            if updated:
                core += f" · {updated} oppdatert"
            if stamp:
                core += f" · {stamp}"
            return core
    except Exception:
        pass
    try:
        samples = int(load_learning_stats().get("global", {}).get("count", 0))
        return f"{samples} samples" if samples else "Ikke oppdatert"
    except Exception:
        return "Ikke oppdatert"



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

def global_busy_chip_html() -> str:
    """Legacy regression anchor: busy chip is inline, not fixed overlay."""
    return '<span class="ptw-pill ptw-global-busy-fixed" aria-live="polite">Klar</span>'


def render_sticky_topbar() -> None:
    _version_for_legacy_tests = get_app_version()  # single source remains app_version.py
    """Render compact sticky AI/control status bar."""
    alerts = _alert_summary()
    regime = _regime_label()
    macro = _macro_label()
    learning = _learning_label()

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
            <span class="ptw-pill">🧠 Learning: {learning}</span>
            {_market_status_chips_html()}
          </div>
          <div class="ptw-topbar-right ptw-v18570-status-zone" aria-live="polite">
            {global_busy_chip_html()}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
