"""
ai_control_center.py

v18.4.6 AI Kontrollsenter / Layout Cleanup.
Samler AI-modulene i én ryddig toppseksjon.
Ingen auto-trading-kobling.
"""
from __future__ import annotations

import streamlit as st

from alert_center import collect_common_alerts, render_common_alert_center
from daily_ai_market_report import render_daily_ai_market_report
from market_intelligence_center import render_market_intelligence_center
from ai_heatmap_ui import render_ai_heatmaps
from forecast_backtest_ui import render_backtest_learning_panel
from market_regime_ui import render_market_regime_widget
from macro_rates_breadth_ui import render_macro_rates_breadth_panel


def _compact_alert_status() -> str:
    try:
        alerts = collect_common_alerts(limit=100)
    except Exception:
        alerts = []
    red = sum(1 for a in alerts if a.get("level") == "red")
    yellow = sum(1 for a in alerts if a.get("level") == "yellow")
    green = sum(1 for a in alerts if a.get("level") == "green")
    if not alerts:
        return "🟢 Varselsenter: ingen aktive prognose-/porteføljevarsler."
    return f"🚨 Varsler: 🔴 {red} · 🟡 {yellow} · 🟢 {green}"


def render_ai_control_center() -> None:
    status = _compact_alert_status()

    st.markdown(
        f"""
        <div style="
            border:1px solid rgba(148,163,184,.30);
            border-radius:14px;
            padding:.55rem .8rem;
            margin:.25rem 0 .45rem 0;
            background:rgba(15,23,42,.55);
        ">
            <div style="font-weight:900;font-size:1.05rem;">🧠 AI Kontrollsenter</div>
            <div style="opacity:.9;font-size:.88rem;">{status}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("▸ Åpne AI Kontrollsenter", expanded=False):
        st.caption(
            "Samlet kontrollpanel for AI-rapport, varsler, regime, heatmaps og backtest-læring. "
            "Dette er beslutningsstøtte, ikke auto-trading."
        )

        tabs = st.tabs([
            "🚨 Varsler",
            "📈 Daily Report",
            "🧠 Intelligence",
            "📊 Heatmaps",
            "🧪 Backtest",
            "🌍 Regime",
            "🌐 Makro",
        ])

        with tabs[0]:
            render_common_alert_center(location="control_center")
        with tabs[1]:
            render_daily_ai_market_report()
        with tabs[2]:
            render_market_intelligence_center()
        with tabs[3]:
            render_ai_heatmaps()
        with tabs[4]:
            render_backtest_learning_panel()
        with tabs[5]:
            render_market_regime_widget()
        with tabs[6]:
            render_macro_rates_breadth_panel()
