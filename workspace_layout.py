"""
workspace_layout.py

v18.5.31 Professional Trading Workspace.
Samler AI-moduler i ett kontrollsenter og reduserer vertikal luft.

Ingen auto-trading-kobling.
"""

from __future__ import annotations

import streamlit as st
from ai_service_bridge import render_service_workspace

from alert_center import render_common_alert_center
from daily_ai_market_report import render_daily_ai_market_report
from market_intelligence_center import render_market_intelligence_center
from ai_heatmap_ui import render_ai_heatmaps
from forecast_backtest_ui import render_backtest_learning_panel
from strategy_testing_workspace import render_strategy_testing_workspace
from market_regime_ui import render_market_regime_widget
from macro_rates_breadth_ui import render_macro_rates_breadth_panel
from forecast_ui import render_forecast_section
from analysis_universe_ai import render_ai_analysis_universe_workspace
from persistent_storage_status import compact_storage_status_rows, storage_status_snapshot


def inject_workspace_css() -> None:
    """CSS for compact professional workspace."""
    st.markdown(
        """
        <style>
        /* v18.5.21 professional workspace */
        .block-container {
            padding-top: 0.15rem !important;
            padding-bottom: 1.5rem !important;
            max-width: 98vw !important;
        }

        div[data-testid="stVerticalBlock"] {
            gap: 0.18rem !important;
        }

        .ptw-app-title {
            display:flex;
            align-items:center;
            gap:.55rem;
            margin:.06rem 0 .18rem 0;
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
            padding: .50rem .70rem;
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
            opacity: .95;
            font-size: .78rem;
            display:flex;
            align-items:center;
            gap:.42rem;
        }

        .ptw-pill-busy {
            border-color: rgba(56, 189, 248, .72) !important;
            background: rgba(7, 89, 133, .72) !important;
            box-shadow: 0 0 18px rgba(56, 189, 248, .24);
        }

        .ptw-pill-ready {
            border-color: rgba(34, 197, 94, .52) !important;
            background: rgba(16, 65, 52, .55) !important;
        }

        .ptw-busy-spinner {
            width: .72rem;
            height: .72rem;
            border: 2px solid rgba(226, 232, 240, .35);
            border-top-color: #67e8f9;
            border-radius: 999px;
            display:inline-block;
            animation: ptw-spin .8s linear infinite;
        }

        @keyframes ptw-spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        .ptw-main-panel-nav {
            border: 1px solid rgba(95, 122, 170, .34);
            background: rgba(8, 16, 34, .80);
            border-radius: 14px;
            padding: .45rem .65rem .18rem .65rem;
            margin: .05rem 0 .42rem 0;
        }

        .ptw-main-panel-nav-title {
            font-size: .72rem;
            font-weight: 900;
            color: rgba(226, 232, 240, .78);
            text-transform: uppercase;
            letter-spacing: .04em;
            margin-bottom: .12rem;
        }

        .ptw-main-panel-nav div[role="radiogroup"] {
            display:flex;
            flex-wrap:wrap;
            gap:.38rem .55rem;
            align-items:center;
        }

        .ptw-main-panel-nav label {
            border: 1px solid rgba(120,150,190,.34) !important;
            background: rgba(15, 23, 42, .82) !important;
            border-radius: 999px !important;
            padding: .22rem .52rem !important;
            margin: 0 !important;
        }

        .ptw-main-panel-nav label:has(input:checked) {
            border-color: rgba(34,197,94,.72) !important;
            background: rgba(16, 65, 52, .74) !important;
            box-shadow: 0 0 14px rgba(34,197,94,.14);
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
            padding: .50rem .70rem;
            margin: .10rem 0 .16rem 0;
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


        /* v18.5.21: keep Streamlit inputs/selects dark, including focus/active states. */
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea {
            background-color: rgba(15, 23, 42, .92) !important;
            color: #f8fafc !important;
            caret-color: #7dd3fc !important;
            border-color: rgba(125, 211, 252, .42) !important;
            box-shadow: none !important;
        }

        div[data-testid="stTextInput"] input:focus,
        div[data-testid="stNumberInput"] input:focus,
        div[data-testid="stTextArea"] textarea:focus,
        div[data-baseweb="input"] input:focus,
        div[data-baseweb="textarea"] textarea:focus {
            background-color: rgba(15, 23, 42, .98) !important;
            color: #ffffff !important;
            border-color: rgba(56, 189, 248, .85) !important;
            box-shadow: 0 0 0 1px rgba(56, 189, 248, .38) !important;
        }

        div[data-baseweb="select"] > div,
        div[data-baseweb="select"] div[role="button"],
        div[data-baseweb="select"] input {
            background-color: rgba(15, 23, 42, .92) !important;
            color: #f8fafc !important;
            border-color: rgba(125, 211, 252, .34) !important;
        }

        div[data-baseweb="popover"],
        div[data-baseweb="menu"],
        ul[role="listbox"] {
            background-color: #0f172a !important;
            color: #f8fafc !important;
        }

        div[data-baseweb="menu"] li,
        ul[role="listbox"] li {
            background-color: #0f172a !important;
            color: #f8fafc !important;
        }

        div[data-baseweb="menu"] li:hover,
        ul[role="listbox"] li:hover {
            background-color: rgba(14, 165, 233, .28) !important;
        }


        /* v18.5.21: Chrome/Edge autofill can force white boxes over dark inputs. */
        input:-webkit-autofill,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:focus,
        textarea:-webkit-autofill,
        textarea:-webkit-autofill:hover,
        textarea:-webkit-autofill:focus,
        select:-webkit-autofill,
        select:-webkit-autofill:hover,
        select:-webkit-autofill:focus {
            -webkit-text-fill-color: #f8fafc !important;
            -webkit-box-shadow: 0 0 0px 1000px #0f172a inset !important;
            box-shadow: 0 0 0px 1000px #0f172a inset !important;
            caret-color: #7dd3fc !important;
            border-color: rgba(56, 189, 248, .85) !important;
        }



        /* v18.5.26: hard input visibility guard for Chrome/Edge autofill and Streamlit BaseWeb wrappers. */
        div[data-testid="stTextInput"],
        div[data-testid="stTextInput"] > div,
        div[data-testid="stTextInput"] > div > div,
        div[data-baseweb="input"],
        div[data-baseweb="input"] > div,
        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"],
        div[data-baseweb="base-input"] > div,
        div[data-baseweb="base-input"] input {
            background: #0f172a !important;
            background-color: #0f172a !important;
            color: #f8fafc !important;
            -webkit-text-fill-color: #f8fafc !important;
            opacity: 1 !important;
            border-color: rgba(125, 211, 252, .50) !important;
            box-shadow: none !important;
        }

        div[data-testid="stTextInput"]:focus-within,
        div[data-testid="stTextInput"]:focus-within > div,
        div[data-testid="stTextInput"]:focus-within > div > div,
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="input"]:focus-within > div,
        div[data-baseweb="base-input"]:focus-within,
        div[data-baseweb="base-input"]:focus-within > div {
            background: #0b1220 !important;
            background-color: #0b1220 !important;
            border-color: rgba(56, 189, 248, .96) !important;
            box-shadow: 0 0 0 1px rgba(56, 189, 248, .45) !important;
        }

        div[data-testid="stTextInput"] input,
        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"] input {
            background: transparent !important;
            background-color: transparent !important;
            color: #f8fafc !important;
            -webkit-text-fill-color: #f8fafc !important;
            caret-color: #7dd3fc !important;
            font-weight: 900 !important;
            text-shadow: none !important;
        }

        div[data-testid="stTextInput"] input::placeholder,
        div[data-baseweb="input"] input::placeholder,
        div[data-baseweb="base-input"] input::placeholder {
            color: rgba(203, 213, 225, .72) !important;
            -webkit-text-fill-color: rgba(203, 213, 225, .72) !important;
            opacity: 1 !important;
        }

        input:-webkit-autofill,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:focus,
        input:-webkit-autofill:active {
            -webkit-text-fill-color: #f8fafc !important;
            caret-color: #7dd3fc !important;
            box-shadow: 0 0 0 1000px #0f172a inset !important;
            -webkit-box-shadow: 0 0 0 1000px #0f172a inset !important;
            transition: background-color 999999s ease-in-out 0s, color 999999s ease-in-out 0s !important;
        }

        /* v18.5.21: safety net for old Streamlit dataframe boxes that still render in some tabs. */
        div[data-testid="stDataFrame"],
        div[data-testid="stDataFrame"] > div,
        div[data-testid="stDataFrame"] iframe {
            background: #020617 !important;
            border-color: rgba(56, 189, 248, .22) !important;
            border-radius: 12px !important;
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


def _render_forecast_workspace_tab() -> None:
    """Render forecast inside AI Control Center only."""
    try:
        st.session_state["forecast_render_context_v1849"] = "ai_control_center"
        render_forecast_section()
    except TypeError:
        render_forecast_section(default_ticker="AAPL")
    except Exception as exc:
        st.warning(f"Prognosemodul kunne ikke vises i AI Kontrollsenter: {exc}")
    finally:
        st.session_state["forecast_render_context_v1849"] = "normal"


def _render_storage_services_status() -> None:
    """Render service/storage health inside AI Kontrollsenter."""
    st.subheader("🧩 Services / persistent storage")
    snap = storage_status_snapshot()
    backend = str(snap.get("backend", "unknown"))
    persistent = bool(snap.get("persistent"))
    ok = bool(snap.get("ok", True))
    if persistent and ok:
        st.success("Storage: Postgres aktiv ✅ Runtime-data lagres robust utenfor Render-filsystemet.")
    elif ok:
        st.warning("Storage: lokal fallback ⚠️ OK for dev/test. På Render bør DATABASE_URL/Postgres være aktiv.")
    else:
        st.error(str(snap.get("message", "Storage-feil")))
    st.caption(str(snap.get("message", "")))
    st.caption(f"Backend: {backend} · Persistent: {'ja' if persistent else 'nei/fallback'}")
    rows = compact_storage_status_rows()
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True, height=min(420, 42 + len(rows) * 34))
    try:
        render_service_workspace()
    except Exception as exc:
        st.caption(f"Service workspace kunne ikke vises: {exc}")



def render_ai_control_center() -> None:
    """One compact AI control center with tabs instead of many stacked expanders."""
    st.markdown(
        """
        <div class="ptw-control-header">
          <div class="ptw-control-title">🧠 AI Kontrollsenter</div>
          <div class="ptw-control-caption">Analyseunivers, varsler, daglig rapport, regime, makro, heatmaps og backtest samlet i ett arbeidsområde.</div>
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
            "🎯 Analyseunivers",
            "🔮 Prognose",
            "🚨 Varsler",
            "📈 Daily Report",
            "🧠 Intelligence",
            "📊 Heatmaps",
            "🧪 Testing & Learning",
            "🌍 Regime",
            "🌐 Makro/renter",
            "🧩 Services",
        ]

        tabs = st.tabs(tab_names)

        with tabs[0]:
            render_ai_analysis_universe_workspace(expanded=True)
        with tabs[1]:
            _render_forecast_workspace_tab()
        with tabs[2]:
            render_common_alert_center(location="workspace")
        with tabs[3]:
            render_daily_ai_market_report()
        with tabs[4]:
            render_market_intelligence_center()
        with tabs[5]:
            render_ai_heatmaps()
        with tabs[6]:
            st.info("Strategi-test, Strategi-test Pro, prognose-vs-faktisk, scoreforklaring og backtest-læring er samlet her. Legacy backtesting/strategi-knapper er ryddet ut av hovedvisningen.")
            render_strategy_testing_workspace()
            render_backtest_learning_panel()
        with tabs[7]:
            render_market_regime_widget()
        with tabs[8]:
            render_macro_rates_breadth_panel()
        with tabs[9]:
            _render_storage_services_status()
