"""
workspace_layout.py

v18.4.7 Professional Trading Workspace.
Samler AI-moduler i ett kontrollsenter og reduserer vertikal luft.

Ingen auto-trading-kobling.
"""

from __future__ import annotations

import streamlit as st

from alert_center import render_common_alert_center
from daily_ai_market_report import render_daily_ai_market_report
from market_intelligence_center import render_market_intelligence_center
from ai_heatmap_ui import render_ai_heatmaps
from forecast_backtest_ui import render_backtest_learning_panel
from market_regime_ui import render_market_regime_widget
from macro_rates_breadth_ui import render_macro_rates_breadth_panel
from forecast_ui import render_forecast_section


def inject_workspace_css() -> None:
    """CSS for compact professional workspace."""
    st.markdown(
        """
        <style>
        /* v18.4.7 professional workspace */
        .block-container {
            padding-top: 0.20rem !important;
            padding-bottom: 1.5rem !important;
            max-width: 98vw !important;
        }

        div[data-testid="stVerticalBlock"] {
            gap: 0.25rem !important;
        }

        .ptw-app-title {
            display:flex;
            align-items:center;
            gap:.55rem;
            margin:.10rem 0 .28rem 0;
            padding:.20rem .2rem .30rem .2rem;
            border-bottom:1px solid rgba(120,150,190,.28);
            font-size:1.25rem;
            line-height:1.15;
            font-weight:950;
            color:#f4f8ff;
        }

        .ptw-sticky-topbar {
            position: sticky;
            top: 0;
            z-index: 999;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: .6rem;
            padding: .55rem .75rem;
            margin: 0 0 .45rem 0;
            background: rgba(8, 16, 34, .96);
            border: 1px solid rgba(95, 122, 170, .38);
            border-radius: 14px;
            box-shadow: 0 10px 25px rgba(0,0,0,.22);
            backdrop-filter: blur(8px);
        }

        .ptw-topbar-left {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: .42rem;
        }

        .ptw-topbar-right {
            white-space: nowrap;
            opacity: .72;
            font-size: .78rem;
        }

        .ptw-pill {
            display: inline-flex;
            align-items: center;
            gap: .25rem;
            border: 1px solid rgba(120, 150, 190, .32);
            background: rgba(18, 31, 55, .82);
            color: #f3f7ff;
            border-radius: 999px;
            padding: .28rem .55rem;
            font-size: .78rem;
            font-weight: 700;
            line-height: 1.1;
        }

        .ptw-pill-ai {
            border-color: rgba(34, 197, 94, .55);
            background: rgba(16, 65, 52, .72);
        }

        .ptw-subtle {
            color: rgba(229, 237, 255, .72);
            font-weight: 700;
        }

        .ptw-control-header {
            border: 1px solid rgba(95, 122, 170, .35);
            background: linear-gradient(180deg, rgba(17, 30, 54, .95), rgba(10, 20, 38, .92));
            border-radius: 16px;
            padding: .55rem .75rem;
            margin: .2rem 0 .25rem 0;
        }

        .ptw-control-title {
            font-size: 1.05rem;
            font-weight: 900;
            margin-bottom: .2rem;
        }

        .ptw-control-caption {
            opacity: .78;
            font-size: .82rem;
        }

        .ptw-status-line {
            margin-top: .35rem;
            display:flex;
            flex-wrap:wrap;
            gap:.35rem;
        }

        div[data-testid="stExpander"] {
            border: 1px solid rgba(100, 130, 170, .32) !important;
            border-radius: 14px !important;
            background: rgba(11, 21, 39, .62) !important;
        }

        div[data-testid="stExpander"] details summary {
            padding-top: .55rem !important;
            padding-bottom: .55rem !important;
            font-weight: 850 !important;
        }

        /* Hide raw debug-like JSON blocks from earlier modules only if marked by Streamlit JSON wrapper */
        div[data-testid="stJson"] {
            max-height: 240px;
            overflow: auto;
            border-radius: 10px;
        }

        /* Make large empty top areas less dramatic */
        section.main > div {
            padding-top: .25rem !important;
        }

        /* More compact metric cards */
        div[data-testid="stMetric"] {
            background: rgba(15, 28, 52, .55);
            border: 1px solid rgba(100, 130, 170, .25);
            border-radius: 12px;
            padding: .45rem .6rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_workspace_title() -> None:
    """Render app title at the very top of the workspace."""
    st.markdown(
        """
        <div class="ptw-app-title">
          <span>📊 Market Overview – 📈 AI Aksje Analyzer Pro</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_ai_control_center() -> None:
    """One compact AI control center with tabs instead of many stacked expanders."""
    st.markdown(
        """
        <div class="ptw-control-header">
          <div class="ptw-control-title">🧠 AI Kontrollsenter</div>
          <div class="ptw-control-caption">Varsler, daglig rapport, regime, makro, heatmaps og backtest samlet i ett arbeidsområde.</div>
          <div class="ptw-status-line">
            <span class="ptw-pill ptw-pill-ai">🟢 Samlet AI workspace aktivt</span>
            <span class="ptw-pill">📌 Mindre scrolling</span>
            <span class="ptw-pill">📊 Stabile grafer</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("› Åpne AI Kontrollsenter", expanded=False):
        tab_names = [
            "🔮 Prognose",
            "🚨 Varsler",
            "📈 Daily Report",
            "🧠 Intelligence",
            "📊 Heatmaps",
            "🧪 Backtest",
            "🌍 Regime",
            "🌐 Makro/renter",
        ]

        tabs = st.tabs(tab_names)

        with tabs[0]:
            try:
                render_forecast_section()
            except TypeError:
                render_forecast_section(default_ticker="AAPL")
        with tabs[1]:
            render_common_alert_center(location="workspace")
        with tabs[2]:
            render_daily_ai_market_report()
        with tabs[3]:
            render_market_intelligence_center()
        with tabs[4]:
            render_ai_heatmaps()
        with tabs[5]:
            render_backtest_learning_panel()
        with tabs[6]:
            render_market_regime_widget()
        with tabs[7]:
            render_macro_rates_breadth_panel()
