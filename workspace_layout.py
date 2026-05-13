"""
workspace_layout.py

v18.5.35 Professional Trading Workspace.
Samler AI-moduler i ett kontrollsenter og reduserer vertikal luft.

Ingen auto-trading-kobling.
"""

from __future__ import annotations

import streamlit as st
from typing import Callable, Iterable, Optional, Sequence, Tuple
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
            opacity: .98;
            font-size: .76rem;
            display:flex;
            align-items:center;
            justify-content:flex-end;
            gap:.55rem;
            min-width: fit-content;
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



        /* v18.5.48: Global update lives high in the app and must never dim the workspace on normal edits. */
        .v18548-global-update-wrap {
            border: 1px solid rgba(56,189,248,.30);
            background: linear-gradient(180deg, rgba(8,16,34,.96), rgba(10,20,38,.88));
            border-radius: 14px;
            padding: .48rem .62rem .34rem .62rem;
            margin: .10rem 0 .45rem 0;
            box-shadow: 0 8px 20px rgba(0,0,0,.20);
        }
        .v18548-global-note {
            margin: .06rem 0 .18rem 0 !important;
            line-height: 1.28 !important;
        }
        .stApp, .main, section.main, div[data-testid="stAppViewContainer"], div[data-testid="stVerticalBlock"] {
            opacity: 1 !important;
            filter: none !important;
        }
        div[data-testid="stSpinner"] {
            background: rgba(8,16,34,.88) !important;
            border: 1px solid rgba(56,189,248,.24) !important;
            border-radius: 12px !important;
            padding: .45rem .65rem !important;
        }
        /* v18.5.68: never let Streamlit's script-run overlay dim or block the whole app on normal widget changes. */
        [data-testid="stAppViewBlockContainer"],
        [data-testid="stAppViewContainer"],
        [data-testid="stApp"],
        .stApp,
        .main,
        section.main {
            opacity: 1 !important;
            filter: none !important;
        }
        [data-testid="stStatusWidget"] {
            visibility: visible !important;
            opacity: 1 !important;
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

        /* v18.5.35: lazy control center panel selector. */
        .ptw-lazy-panel-note {
            font-size: .78rem;
            color: rgba(226,232,240,.78);
            margin: .10rem 0 .35rem 0;
        }
        .ptw-control-panel-shell {
            border: 1px solid rgba(56,189,248,.18);
            background: rgba(8,16,34,.52);
            border-radius: 14px;
            padding: .46rem .54rem .55rem .54rem;
            margin-top: .38rem;
        }
        .ptw-control-panel-title {
            font-size: .86rem;
            font-weight: 950;
            color: #f8fafc;
            margin-bottom: .25rem;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] {
            gap: .36rem .42rem !important;
        }
        div[data-testid="stRadio"] label {
            border: 1px solid rgba(56,189,248,.35) !important;
            background: linear-gradient(180deg, rgba(14,165,233,.26), rgba(2,132,199,.18)) !important;
            border-radius: 999px !important;
            padding: .23rem .58rem !important;
            margin: 0 .10rem .18rem 0 !important;
            color: #e0f2fe !important;
            font-weight: 900 !important;
        }
        div[data-testid="stRadio"] label:has(input:checked) {
            border-color: rgba(34,197,94,.72) !important;
            background: linear-gradient(180deg, rgba(22,163,74,.45), rgba(21,128,61,.26)) !important;
            box-shadow: 0 0 16px rgba(34,197,94,.16) !important;
        }



        /* v18.5.34: explicit busy slot in the top-right header, no overlap. */
        .ptw-global-busy-fixed {
            position: static;
            display: inline-flex;
            align-items:center;
            z-index: 2500;
            pointer-events: none;
        }
        .ptw-global-busy-fixed .ptw-pill {
            font-size: .82rem;
            padding: .34rem .66rem;
            box-shadow: 0 0 18px rgba(14, 165, 233, .18), 0 8px 18px rgba(0,0,0,.22);
        }
        .ptw-market-chip {
            font-weight: 850;
        }
        .ptw-market-open {
            border-color: rgba(34,197,94,.54) !important;
            background: rgba(16,65,52,.62) !important;
            color: #dcfce7 !important;
        }
        .ptw-market-closed {
            border-color: rgba(239,68,68,.52) !important;
            background: rgba(86,22,36,.55) !important;
            color: #fecaca !important;
        }
        .ptw-market-unknown {
            border-color: rgba(245,158,11,.48) !important;
            background: rgba(120,53,15,.35) !important;
            color: #fde68a !important;
        }
        .v18532-header-status {
            border: 1px solid rgba(95, 122, 170, .30);
            background: rgba(8, 16, 34, .78);
            border-radius: 14px;
            padding: .42rem .58rem;
            margin: .06rem 0 .30rem 0;
        }
        .v18532-status-row {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: .25rem .42rem;
        }
        .v18532-status-label {
            color: rgba(226,232,240,.78);
            font-size: .72rem;
            font-weight: 950;
            letter-spacing: .03em;
            text-transform: uppercase;
            margin-right: .15rem;
        }
        .v18532-trading-control-note {
            font-size: .76rem;
            color: rgba(226,232,240,.82);
            margin: .18rem 0 .18rem 0;
            font-weight: 750;
        }
        .v18532-top-controls {
            border: 1px solid rgba(95, 122, 170, .28);
            background: rgba(10, 20, 38, .68);
            border-radius: 14px;
            padding: .38rem .56rem .30rem .56rem;
            margin: .06rem 0 .38rem 0;
        }
        .v18532-top-controls .v153-control-note {
            max-width: none !important;
            min-width: 0 !important;
            margin: .28rem 0 .20rem 0 !important;
        }
        .v18532-top-controls + .v153-control-note,
        .v153-control-note.warning {
            font-size: .72rem !important;
            line-height: 1.18 !important;
            padding: .30rem .55rem !important;
            margin: .16rem 0 .16rem 0 !important;
            max-width: 68rem !important;
        }
        .v153-control-note.warning b { font-weight: 950 !important; }
        section[data-testid="stSidebar"] {
            font-size: .82rem !important;
        }
        section[data-testid="stSidebar"] .block-container {
            padding-top: .65rem !important;
            padding-left: .75rem !important;
            padding-right: .75rem !important;
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            font-size: .92rem !important;
            line-height: 1.1 !important;
            margin: .28rem 0 .32rem 0 !important;
        }
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] .stMarkdown {
            font-size: .76rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stExpander"] details {
            border-radius: 12px !important;
            background: rgba(8,16,34,.70) !important;
        }
        section[data-testid="stSidebar"] [data-testid="stTextInput"] input,
        section[data-testid="stSidebar"] [data-testid="stSelectbox"] input,
        section[data-testid="stSidebar"] [data-baseweb="select"] > div {
            min-height: 32px !important;
            font-size: .76rem !important;
        }
        .auth-sidebar-card {
            border: 1px solid rgba(95,122,170,.34);
            background: rgba(8,16,34,.70);
            border-radius: 12px;
            padding: .48rem .55rem;
            margin: .20rem 0 .42rem 0;
        }
        .auth-sidebar-title { font-size:.80rem; font-weight:950; color:#f8fafc; margin-bottom:.25rem; }
        .auth-sidebar-user { display:flex; justify-content:space-between; gap:.35rem; font-size:.78rem; color:#e2e8f0; }
        .auth-sidebar-user span { color:#94a3b8; font-size:.70rem; font-weight:850; }
        .auth-remember-chip {
            display:inline-flex; align-items:center; gap:.25rem;
            border-radius:999px; padding:.18rem .42rem; margin-top:.35rem;
            font-size:.72rem; font-weight:900;
            border:1px solid rgba(148,163,184,.28);
        }
        .auth-remember-chip.on { color:#bbf7d0; background:rgba(22,101,52,.22); border-color:rgba(34,197,94,.45); }
        .auth-remember-chip.off { color:#fecaca; background:rgba(127,29,29,.22); border-color:rgba(239,68,68,.45); }
        .auth-mini-heading { font-size:.74rem; color:#cbd5e1; font-weight:950; margin:.55rem 0 .18rem 0; }
        .auth-user-list { display:flex; flex-direction:column; gap:.20rem; margin:.18rem 0 .35rem 0; }
        .auth-user-row { display:flex; justify-content:space-between; align-items:center; gap:.35rem; padding:.24rem .38rem; border:1px solid rgba(148,163,184,.18); border-radius:9px; background:rgba(15,23,42,.66); font-size:.70rem; }
        .auth-dot { width:.52rem; height:.52rem; border-radius:999px; display:inline-block; background:#ef4444; box-shadow:0 0 8px rgba(239,68,68,.35); }
        .auth-dot.on { background:#22c55e; box-shadow:0 0 8px rgba(34,197,94,.35); }



        /* v18.5.34: hard header layout and real busy spinner visibility. */
        .ptw-sticky-topbar {
            display: grid !important;
            grid-template-columns: minmax(0, 1fr) auto !important;
            align-items: center !important;
            column-gap: .85rem !important;
            overflow: visible !important;
        }
        .ptw-topbar-left {
            min-width: 0 !important;
            overflow: hidden !important;
            padding-right: .25rem !important;
        }
        .ptw-topbar-right {
            flex: 0 0 auto !important;
            min-width: 310px !important;
            max-width: 45vw !important;
            justify-content: flex-end !important;
            gap: .45rem !important;
            overflow: visible !important;
        }
        .ptw-version-chip {
            display: inline-flex;
            align-items: center;
            min-width: 0;
            color: rgba(229,237,255,.70);
            font-size: .74rem;
            font-weight: 850;
            white-space: nowrap;
        }
        .ptw-global-busy-fixed {
            position: relative !important;
            flex: 0 0 auto !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: flex-end !important;
            z-index: 3200 !important;
            pointer-events: none !important;
        }
        .ptw-global-busy-fixed .ptw-pill {
            min-width: 96px !important;
            justify-content: center !important;
            font-size: .82rem !important;
            padding: .36rem .70rem !important;
            line-height: 1 !important;
            color: #f8fafc !important;
        }
        .ptw-busy-running {
            min-width: 164px !important;
            animation: ptw-busy-glow 1.25s ease-in-out infinite alternate;
        }
        .ptw-busy-copy { color:#f8fafc !important; font-weight:900 !important; }
        .ptw-pill-ready { color:#dcfce7 !important; font-weight:900 !important; }
        .ptw-busy-spinner {
            width: .86rem !important;
            height: .86rem !important;
            border: 2px solid rgba(226,232,240,.35) !important;
            border-top-color: #67e8f9 !important;
            border-right-color: #22d3ee !important;
            border-radius: 999px !important;
            display:inline-block !important;
            flex: 0 0 auto !important;
            animation: ptw-spin .65s linear infinite !important;
        }
        @keyframes ptw-busy-glow {
            from { box-shadow: 0 0 8px rgba(56,189,248,.20), 0 8px 18px rgba(0,0,0,.22); }
            to { box-shadow: 0 0 20px rgba(56,189,248,.42), 0 8px 18px rgba(0,0,0,.22); }
        }
        .v18534-trading-control-stack {
            border: 1px solid rgba(95, 122, 170, .28);
            background: rgba(10, 20, 38, .68);
            border-radius: 14px;
            padding: .36rem .52rem .42rem .52rem;
            margin: .06rem 0 .24rem 0;
        }
        .v18534-trading-help {
            font-size: .70rem !important;
            line-height: 1.15 !important;
            color: rgba(226,232,240,.76) !important;
            font-weight: 750 !important;
            margin: 0 0 .18rem 0 !important;
        }
        .v18534-trading-warning {
            display:block !important;
            width: min(100%, 78rem) !important;
            max-width: 78rem !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
            font-size: .68rem !important;
            line-height: 1.18 !important;
            font-weight: 850 !important;
            padding: .26rem .48rem !important;
            margin: .16rem 0 .48rem 0 !important;
            border-radius: 9px !important;
            background: rgba(255, 193, 7, 0.13) !important;
            border: 1px solid rgba(255, 193, 7, 0.38) !important;
            color: #ffe08a !important;
            white-space: normal !important;
            word-break: normal !important;
            overflow-wrap: normal !important;
        }
        .v18534-control-button-gap {
            height: .16rem !important;
        }
        @media (max-width: 1100px) {
            .ptw-sticky-topbar { grid-template-columns: 1fr !important; row-gap: .35rem !important; }
            .ptw-topbar-right { width:100% !important; max-width:100% !important; min-width:0 !important; justify-content:space-between !important; }
            .ptw-version-chip { font-size:.70rem !important; }
        }

        @media (max-width: 900px) {
            .ptw-sticky-topbar { align-items:flex-start; flex-direction:column; }
            .ptw-topbar-right { width:100%; justify-content:space-between; }
            .ptw-global-busy-fixed .ptw-pill { font-size: .74rem; padding: .30rem .50rem; }
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
            font-size: 1.34rem;
            font-weight: 950;
            letter-spacing: -0.01em;
            margin-bottom: .18rem;
        }

        .ptw-control-caption {
            opacity: .72;
            font-size: .76rem;
            line-height: 1.22;
            font-weight: 650;
        }

        .ptw-status-line {
            margin-top: .30rem;
            display:flex;
            flex-wrap:wrap;
            gap:.25rem;
        }
        .ptw-status-line .ptw-pill {
            font-size: .68rem !important;
            padding: .18rem .42rem !important;
            line-height: 1.05 !important;
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



def _run_control_panel(label: str, renderer: Callable[[], None]) -> None:
    """Render exactly one control-center panel and keep failures local."""
    st.markdown(
        f"<div class='ptw-control-panel-shell'><div class='ptw-control-panel-title'>{label}</div>",
        unsafe_allow_html=True,
    )
    try:
        renderer()
    except Exception as exc:
        st.warning(f"Panelet kunne ikke vises: {exc}")
    finally:
        st.markdown("</div>", unsafe_allow_html=True)


def render_ai_control_center(extra_panels: Optional[Sequence[Tuple[str, Callable[[], None]]]] = None) -> None:
    """Lazy AI control center. Only the selected panel is rendered/executed."""
    st.markdown(
        """
        <div class="ptw-control-header">
          <div class="ptw-control-title">🧠 AI Kontrollsenter</div>
          <div class="ptw-control-caption">Analyseunivers, prognose, varsler, nyheter, analyse, system/admin og tjenester samlet i ett arbeidsområde.</div>
          <div class="ptw-status-line">
            <span class="ptw-pill ptw-pill-ai">🟢 Samlet AI workspace aktivt</span>
            <span class="ptw-pill">🧩 Lazy panels</span>
            <span class="ptw-pill">Ingen skjulte analyser</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("› Åpne AI Kontrollsenter", expanded=False):
        base_panels: list[Tuple[str, Callable[[], None]]] = [
            ("🎯 Analyseunivers", lambda: render_ai_analysis_universe_workspace(expanded=True)),
            ("🔮 Prognose", _render_forecast_workspace_tab),
            ("🚨 Varsler", lambda: render_common_alert_center(location="workspace")),
            ("📈 Daily Report", render_daily_ai_market_report),
            ("🧠 Intelligence", render_market_intelligence_center),
            ("📊 Heatmaps", render_ai_heatmaps),
            ("🧪 Testing & Learning", lambda: (
                st.info("Strategi-test, Strategi-test Pro, prognose-vs-faktisk, scoreforklaring og backtest-læring er samlet her."),
                render_strategy_testing_workspace(),
                render_backtest_learning_panel(),
            )),
            ("🌍 Regime", render_market_regime_widget),
            ("🌐 Makro/renter", render_macro_rates_breadth_panel),
            ("🧩 Services", _render_storage_services_status),
        ]
        panels = base_panels + list(extra_panels or [])
        labels = [label for label, _renderer in panels]
        active_label = st.radio(
            "Velg Kontrollsenter-panel",
            labels,
            index=0,
            horizontal=True,
            key="ai_control_center_active_panel_v18535",
            help="Kun valgt panel rendres. Skjulte paneler starter ikke tunge analyser.",
        )
        st.markdown(
            "<div class='ptw-lazy-panel-note'>Kun valgt panel åpnes og kjøres. Bytt panel når du trenger funksjonen.</div>",
            unsafe_allow_html=True,
        )
        renderer = dict(panels).get(active_label)
        if renderer:
            _run_control_panel(active_label, renderer)

