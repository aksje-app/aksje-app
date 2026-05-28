"""
workspace_layout.py

v18.5.35 Professional Trading Workspace.
Samler AI-moduler i ett kontrollsenter og reduserer vertikal luft.

Ingen auto-trading-kobling.
"""

from __future__ import annotations

import html
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
            white-space: normal;
            opacity: 1;
            font-size: .78rem;
            display:flex;
            align-items:center;
            justify-content:flex-end;
            gap:.55rem;
            min-width: 0;
            max-width: 70vw;
            overflow: visible;
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
        .ptw-control-hero {
            border: 1px solid rgba(56,189,248,.55);
            background: linear-gradient(135deg, rgba(8,47,73,.84), rgba(15,23,42,.94) 58%, rgba(20,83,45,.38));
            border-radius: 16px;
            padding: .86rem .95rem .74rem .95rem;
            margin: .34rem 0 .58rem 0;
            box-shadow: 0 14px 32px rgba(0,0,0,.24), 0 0 0 1px rgba(125,211,252,.10) inset;
        }
        .ptw-control-hero-top {
            display:flex;
            justify-content:space-between;
            align-items:flex-start;
            gap:.85rem;
            flex-wrap:wrap;
        }
        .ptw-control-eyebrow {
            color:#67e8f9;
            font-size:.76rem;
            font-weight:950;
            text-transform:uppercase;
            letter-spacing:.06em;
            margin-bottom:.12rem;
        }
        .ptw-control-title {
            font-size:1.62rem;
            line-height:1.08;
            font-weight:950;
            color:#f8fafc;
        }
        .ptw-control-caption {
            color:#dbeafe;
            font-size:.90rem;
            line-height:1.34;
            margin-top:.20rem;
            max-width:74rem;
        }
        .ptw-control-active-chip {
            border:1px solid rgba(34,197,94,.55);
            background:rgba(16,65,52,.70);
            color:#dcfce7;
            border-radius:999px;
            padding:.34rem .62rem;
            font-size:.78rem;
            font-weight:950;
            white-space:nowrap;
            box-shadow:0 0 18px rgba(34,197,94,.15);
        }
        .ptw-control-selector-shell {
            border:1px solid rgba(125,211,252,.70);
            background:linear-gradient(135deg, rgba(8,47,73,.88), rgba(12,74,110,.66) 48%, rgba(15,23,42,.92));
            border-radius:16px;
            padding:.82rem .82rem .68rem .82rem;
            margin:.62rem 0 .34rem 0;
            box-shadow:0 14px 34px rgba(14,165,233,.18), 0 0 0 1px rgba(125,211,252,.12) inset;
        }
        .ptw-control-selector-title {
            display:inline-flex;
            align-items:center;
            border:1px solid rgba(125,211,252,.72);
            background:linear-gradient(180deg, rgba(14,165,233,.38), rgba(2,132,199,.22));
            color:#e0f2fe;
            border-radius:999px;
            padding:.26rem .64rem;
            font-size:.98rem;
            font-weight:950;
            text-transform:uppercase;
            letter-spacing:.04em;
            margin:0 0 .68rem 0;
            text-shadow:0 0 12px rgba(56,189,248,.26);
        }
        .ptw-control-selector-shell div[data-testid="stSelectbox"] label,
        .ptw-control-hero div[data-testid="stSelectbox"] label {
            display:inline-flex !important;
            width:auto !important;
            border:1px solid rgba(125,211,252,.58) !important;
            background:rgba(14,165,233,.18) !important;
            color:#dff6ff !important;
            font-size:1rem !important;
            font-weight:950 !important;
            border-radius:999px !important;
            padding:.16rem .54rem !important;
            margin-bottom:.36rem !important;
            line-height:1.15 !important;
        }
        .ptw-control-selector-shell div[data-testid="stSelectbox"] {
            display:none !important;
        }
        .ptw-control-selector-shell div[data-baseweb="select"] > div,
        .ptw-control-hero div[data-baseweb="select"] > div {
            min-height:52px !important;
            border-color:rgba(125,211,252,.88) !important;
            background:linear-gradient(180deg, rgba(15,23,42,.96), rgba(8,47,73,.84)) !important;
            box-shadow:0 0 0 1px rgba(56,189,248,.16) inset, 0 8px 18px rgba(0,0,0,.18) !important;
        }
        .ptw-control-selector-shell div[data-baseweb="select"] span,
        .ptw-control-hero div[data-baseweb="select"] span {
            font-weight:900 !important;
            color:#f8fafc !important;
            font-size:1rem !important;
        }
        .ptw-control-note-strong {
            border:1px solid rgba(34,197,94,.34);
            background:rgba(6,78,59,.30);
            color:#d1fae5;
            border-radius:12px;
            padding:.48rem .60rem;
            margin:.42rem 0 .40rem 0;
            font-size:.84rem;
            font-weight:850;
        }
        .ptw-control-selector-shell div[data-testid="stButton"] button {
            min-height: 34px !important;
            border-radius: 10px !important;
            padding: .30rem .62rem !important;
            border: 1px solid rgba(125,211,252,.70) !important;
            background: linear-gradient(180deg, rgba(14,165,233,.38), rgba(8,47,73,.92)) !important;
            color: #e0f2fe !important;
            font-weight: 950 !important;
            font-size: .82rem !important;
            line-height: 1.14 !important;
            overflow-wrap: anywhere !important;
            box-shadow: 0 8px 20px rgba(14,165,233,.14), 0 0 0 1px rgba(125,211,252,.10) inset !important;
        }
        .ptw-control-selector-shell div[data-testid="stButton"] button[kind="primary"] {
            border-color: rgba(248,113,113,.86) !important;
            background: linear-gradient(180deg, rgba(239,68,68,.72), rgba(127,29,29,.88)) !important;
            color: #fff7f7 !important;
            box-shadow: 0 0 22px rgba(248,113,113,.28), 0 0 0 1px rgba(254,202,202,.14) inset !important;
        }
        .ptw-control-selector-shell div[data-testid="stButton"] button[data-testid="baseButton-primary"] {
            border-color: rgba(248,113,113,.86) !important;
            background: linear-gradient(180deg, rgba(239,68,68,.76), rgba(127,29,29,.90)) !important;
            color: #fff7f7 !important;
            box-shadow: 0 0 22px rgba(248,113,113,.32), 0 0 0 1px rgba(254,202,202,.16) inset !important;
        }
        .ptw-control-home-button div[data-testid="stButton"] button {
            border-color: rgba(125,211,252,.84) !important;
            background: linear-gradient(180deg, rgba(14,165,233,.55), rgba(8,47,73,.96)) !important;
            color:#f0f9ff !important;
            min-height:34px !important;
            padding:.30rem .62rem !important;
            font-weight:950 !important;
        }
        .ptw-control-submenu {
            border:1px solid rgba(125,211,252,.46);
            background:rgba(2,6,23,.38);
            border-radius:14px;
            padding:.58rem .62rem .32rem .62rem;
            margin:.42rem 0 .32rem 0;
        }
        .ptw-control-submenu-title {
            color:#bae6fd;
            font-size:.84rem;
            font-weight:950;
            text-transform:uppercase;
            letter-spacing:.04em;
            margin-bottom:.32rem;
        }
        .ptw-control-mini-title {
            color:#bae6fd;
            font-size:.78rem;
            font-weight:950;
            margin:.26rem 0 .20rem 0;
            text-transform:uppercase;
            letter-spacing:.04em;
        }
        .ptw-control-mode-note {
            color:#cbd5e1;
            font-size:.80rem;
            margin:.15rem 0 .30rem 0;
        }
        .ptw-ai-control-open-hint {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:.75rem;
            flex-wrap:wrap;
            border:1px solid rgba(56,189,248,.42);
            background:linear-gradient(135deg, rgba(14,165,233,.22), rgba(15,23,42,.78));
            border-radius:14px;
            padding:.54rem .68rem;
            margin:.34rem 0 .20rem 0;
        }
        .ptw-ai-control-open-hint b {
            color:#f8fafc;
            font-size:1.02rem;
        }
        .ptw-ai-control-open-hint span {
            color:#bae6fd;
            font-size:.82rem;
            font-weight:850;
        }
        html body .stApp div[data-testid="stExpander"] details summary {
            min-height:48px !important;
            border:1px solid rgba(56,189,248,.42) !important;
            background:linear-gradient(180deg, rgba(8,47,73,.76), rgba(15,23,42,.94)) !important;
            border-radius:13px !important;
            padding:.55rem .72rem !important;
            box-shadow:0 10px 22px rgba(0,0,0,.18), 0 0 0 1px rgba(125,211,252,.08) inset !important;
        }
        html body .stApp div[data-testid="stExpander"] details summary p {
            color:#f8fafc !important;
            font-size:.98rem !important;
            font-weight:950 !important;
        }
        html body .stApp div[data-testid="stExpander"] details[open] summary {
            border-color:rgba(34,197,94,.42) !important;
            background:linear-gradient(180deg, rgba(6,78,59,.60), rgba(15,23,42,.94)) !important;
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
            flex: 0 1 auto !important;
            min-width: 0 !important;
            max-width: 70vw !important;
            justify-content: flex-end !important;
            gap: .45rem !important;
            overflow: visible !important;
            white-space: normal !important;
        }
        .ptw-version-chip {
            display: inline-flex;
            align-items: center;
            gap: .28rem;
            min-width: 0;
            max-width: min(62vw, 780px);
            padding: .34rem .64rem;
            border: 1px solid rgba(125,211,252,.70);
            border-radius: 999px;
            background: rgba(8,47,73,.74);
            color: #f8fafc;
            font-size: .82rem;
            font-weight: 950;
            line-height: 1.12;
            white-space: normal;
            overflow: visible;
            box-shadow: 0 0 0 1px rgba(255,255,255,.08), 0 6px 18px rgba(14,165,233,.16);
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
        
        /* v18.5.69: user-requested polish: readable AI Kontrollsenter and stable header indicators. */
        .ptw-control-title { font-size: 1.26rem !important; line-height:1.15 !important; font-weight: 950 !important; }
        .ptw-control-caption { font-size: .78rem !important; line-height:1.24 !important; color: rgba(203,213,225,.88) !important; }
        .ptw-status-line .ptw-pill, .ptw-control-header .ptw-pill { font-size: .68rem !important; padding: .18rem .38rem !important; }
        .ptw-control-hero .ptw-control-title { font-size: 1.62rem !important; line-height:1.08 !important; }
        .ptw-control-hero .ptw-control-caption { font-size: .90rem !important; line-height:1.34 !important; color:#dbeafe !important; }
        .ptw-control-hero .ptw-status-line .ptw-pill { font-size: .76rem !important; padding: .26rem .52rem !important; }
        .ptw-global-busy-fixed .ptw-pill { min-height: 30px !important; opacity:1 !important; }
        .ptw-global-busy-fixed .ptw-busy-running { min-width: 178px !important; }
        .ptw-busy-spinner { opacity:1 !important; visibility:visible !important; }
        .ptw-sticky-topbar { overflow: visible !important; padding-top:.58rem !important; }

        /* v18.5.95: top-right status must remain readable, not force a 480px desktop-only width. */
        .ptw-v18570-status-zone, .ptw-topbar-right { min-width: 0 !important; max-width:70vw !important; opacity:1 !important; overflow:visible !important; }
        .ptw-version-chip { color:#f8fafc !important; opacity:1 !important; font-size:.82rem !important; }
        .ptw-global-busy-fixed { opacity:1 !important; visibility:visible !important; min-width:112px !important; }
        .ptw-global-busy-fixed .ptw-pill { opacity:1 !important; visibility:visible !important; min-height:32px !important; }
        .ptw-busy-running { min-width:184px !important; border-color:rgba(56,189,248,.85) !important; background:rgba(8,89,133,.82) !important; }
        .ptw-busy-spinner { display:inline-block !important; opacity:1 !important; visibility:visible !important; }
        html body .stApp, html body .main, html body section.main,
        html body div[data-testid="stAppViewContainer"], html body div[data-testid="stAppViewBlockContainer"] {
            opacity:1 !important; filter:none !important; transition:none !important;
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
        render_forecast_section(default_ticker="")
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


AI_CONTROL_CENTER_MAIN_PANEL_LABEL_V18598 = "↩️ Hovedpanel / normal visning"


def render_ai_control_center(extra_panels: Optional[Sequence[Tuple[str, Callable[[], None]]]] = None) -> Optional[str]:
    """Lazy AI control center. Only the selected panel is rendered/executed.

    Returns the selected control-center panel label when a real panel is active.
    Returns None when the user wants the normal main dashboard below.
    """
    return _render_ai_control_center_v1863aj(extra_panels)

    with st.expander("🧠  ÅPNE AI KONTROLLSENTER  ·  samlet arbeidsflate", expanded=True):
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
        panel_map = dict(panels)
        group_map = {
            "Analyse og prognose": [
                "🎯 Analyseunivers",
                "🔮 Prognose",
                "📈 Daily Report",
                "📊 Interaktiv analyse",
            ],
            "Marked og signaler": [
                "🚨 Varsler",
                "🧠 Intelligence",
                "📊 Heatmaps",
                "🌍 Regime",
                "🌐 Makro/renter",
                "📰 Nyheter",
                "🏆 Marked/rangering",
                "🔔 Watchlist/signaler",
            ],
            "Testing og portefølje": [
                "🧪 Testing & Learning",
                "🔬 Auto Test Lab",
                "🏦 Fond / ETF",
                "📊 Porteføljeanalyse",
            ],
            "System": [
                "🧩 Services",
                "🛠 System/admin",
            ],
        }
        def _matching_panel_labels(*needles: str) -> list[str]:
            out: list[str] = []
            wanted = [str(n or "").lower() for n in needles if str(n or "").strip()]
            for label, _renderer in panels:
                text = str(label or "").lower()
                if any(n in text for n in wanted):
                    out.append(label)
            return out

        # Build groups from the actual panel labels. This avoids the mobile/encoding
        # fallback where "Marked og signaler" only showed normal hovedpanel.
        group_map = {
            "Analyse og prognose": _matching_panel_labels("ai kandidattest", "kandidattest", "analyseunivers", "prognose", "daily report", "interaktiv analyse"),
            "Marked og signaler": _matching_panel_labels("top picks", "alpha", "aktor", "aktør", "oljefond", "nbim", "finansavisen", "bjellesau", "beslut", "muligheter", "ipo", "varsler", "intelligence", "heatmaps", "regime", "makro", "nyheter", "marked", "marked/rangering", "watchlist"),
            "Testing og portefølje": _matching_panel_labels("testing", "auto test lab", "fond / etf", "portef", "paper"),
            "System": _matching_panel_labels("services", "system/admin"),
        }
        group_map["Marked og signaler"] = list(dict.fromkeys(
            group_map["Marked og signaler"] + _matching_panel_labels("finansavisen", "bjellesauer")
        ))

        known_labels = {label for labels_in_group in group_map.values() for label in labels_in_group}
        extra_labels = [label for label, _renderer in panels if label not in known_labels]
        if extra_labels:
            group_map["Andre paneler"] = extra_labels
        active_stage_hint = str(st.session_state.get("analysis_pipeline_active_stage_v1863bz") or "")
        stage_relevant_labels = _pipeline_relevant_panel_labels_v1864j(active_stage_hint, panels)
        stage_group_name = ""
        if stage_relevant_labels:
            stage_label = active_stage_hint
            try:
                from services.analysis_pipeline_service import stage_wizard_info

                stage_label = str(stage_wizard_info(active_stage_hint).get("label") or active_stage_hint)
            except Exception:
                pass
            stage_group_name = f"Analyseflyt: {stage_label}"
            group_map = {stage_group_name: stage_relevant_labels, **group_map}

        first_real_panel = next((labels[0] for labels in group_map.values() if labels), None)
        previous_label = st.session_state.get("ai_control_center_active_real_panel_v18598") or first_real_panel or AI_CONTROL_CENTER_MAIN_PANEL_LABEL_V18598
        default_group = next((name for name, labels in group_map.items() if labels), "Analyse og prognose")
        for group_name, group_labels in group_map.items():
            if previous_label in group_labels:
                default_group = group_name
                break

        try:
            from services.analysis_pipeline_service import STAGE_PANEL_LABELS

            active_panel_for_sync = st.session_state.get("ai_control_center_active_panel_v1863aj") or ""
            for stage_id, panel_label in STAGE_PANEL_LABELS.items():
                if str(panel_label) == str(active_panel_for_sync):
                    st.session_state["analysis_pipeline_active_stage_v1863bz"] = stage_id
                    break
        except Exception:
            pass

        st.markdown(
            f"""
            <div class="ptw-control-hero">
              <div class="ptw-control-hero-top">
                <div>
                  <div class="ptw-control-eyebrow">Samlet arbeidsflate</div>
                  <div class="ptw-control-title">🧠 AI Kontrollsenter</div>
                  <div class="ptw-control-caption">Analyseunivers, prognose, varsler, nyheter, marked, testing og system er samlet her. Velg ett område og ett panel, så kjøres bare det panelet.</div>
                </div>
                <div class="ptw-control-active-chip">Aktivt panel: {html.escape(str(previous_label or first_real_panel or "-"))}</div>
              </div>
              <div class="ptw-status-line" style="margin-top:.55rem;">
                <span class="ptw-pill ptw-pill-ai">🟢 Samlet AI workspace aktivt</span>
                <span class="ptw-pill">Kun valgt panel kjøres</span>
                <span class="ptw-pill">Ingen skjulte analyser</span>
              </div>
            </div>
            <div class="ptw-control-selector-shell">
              <div class="ptw-control-selector-title">Velg oppgave</div>
            """,
            unsafe_allow_html=True,
        )

        # v18.6.3ag: quick navigation replaces the two selectboxes below.
        c_group, c_panel = st.columns([0.9, 1.35])
        with c_group:
            active_group = st.selectbox(
                "Velg arbeidsområde",
                list(group_map.keys()),
                index=list(group_map.keys()).index(default_group),
                key="ai_control_center_group_v1863m",
                help="Grupperer Kontrollsenteret så menyen er ryddig på mobil og PC.",
            )
        panel_options = [label for label in group_map.get(active_group, []) if label in panel_map]
        if not panel_options:
            panel_options = [first_real_panel] if first_real_panel else []
        group_suffix = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(active_group))[:48]
        panel_key = f"ai_control_center_active_panel_v1863m_{group_suffix}"
        remembered_panel = st.session_state.get(panel_key) or previous_label
        default_panel_index = panel_options.index(remembered_panel) if remembered_panel in panel_options else 0
        with c_panel:
            active_label = st.selectbox(
                "Velg panel",
                panel_options,
                index=default_panel_index,
                key=panel_key,
                help="Kun valgt panel rendres. Skjulte paneler starter ikke tunge analyser.",
            )
        st.session_state["ai_control_center_active_panel_v1863m"] = active_label
        groups = list(group_map.keys())
        menu_open = bool(st.session_state.get("ai_control_center_menu_open_v1863ag", True))

        mode_map = {
            "Finne kjop": "Marked og signaler",
            "Overvake portefolje": "Testing og portefÃ¸lje",
            "Teste strategi": "Testing og portefÃ¸lje",
            "Administrere": "System",
        }
        mode_options = list(mode_map.keys())
        current_mode = st.session_state.get("ai_control_center_work_mode_v1863ag") or mode_options[0]
        st.markdown("<div class='ptw-control-mini-title'>Arbeidsmodus</div>", unsafe_allow_html=True)
        mode_cols = st.columns(len(mode_options))
        for idx, mode in enumerate(mode_options):
            with mode_cols[idx]:
                if st.button(mode, key=f"ai_cc_mode_v1863ag_{idx}", type="primary" if mode == current_mode else "secondary", use_container_width=True):
                    st.session_state["ai_control_center_work_mode_v1863ag"] = mode
                    st.session_state["ai_control_center_group_v1863m"] = mode_map[mode]
                    st.session_state["ai_control_center_menu_open_v1863ag"] = True
                    st.rerun()

        st.markdown("<div class='ptw-control-mini-title'>HovedomrÃ¥der</div>", unsafe_allow_html=True)
        group_cols = st.columns(len(groups))
        for idx, group_name in enumerate(groups):
            labels = [label for label in group_map.get(group_name, []) if label in panel_map]
            active = group_name == active_group
            prefix = "🔴" if active else "🔵"
            with group_cols[idx]:
                if st.button(f"{prefix} {group_name} · {len(labels)}", key=f"ai_cc_group_v1863ag_{idx}", type="primary" if active else "secondary", use_container_width=True):
                    st.session_state["ai_control_center_group_v1863m"] = group_name
                    st.session_state["ai_control_center_menu_open_v1863ag"] = True
                    st.rerun()

        favorite_needles = ["top picks", "paper trading", "paper-portef", "regime", "valutavarsler"]
        favorites: list[str] = []
        for needle in favorite_needles:
            match = next((label for label, _renderer in panels if needle in str(label).lower()), None)
            if match and match not in favorites:
                favorites.append(match)
        if favorites:
            st.markdown("<div class='ptw-control-mini-title'>Favoritter</div>", unsafe_allow_html=True)
            fav_cols = st.columns(min(len(favorites), 5))
            for idx, label in enumerate(favorites[:5]):
                with fav_cols[idx]:
                    if st.button(label, key=f"ai_cc_fav_v1863ag_{idx}", type="primary" if label == active_label else "secondary", use_container_width=True):
                        st.session_state["ai_control_center_active_panel_v1863m"] = label
                        st.session_state["ai_control_center_active_real_panel_v18598"] = label
                        st.session_state["ai_control_center_menu_open_v1863ag"] = False
                        for g_name, g_labels in group_map.items():
                            if label in g_labels:
                                st.session_state["ai_control_center_group_v1863m"] = g_name
                                break
                        st.rerun()

        recent = [x for x in st.session_state.get("ai_control_center_recent_panels_v1863ag", []) if x in panel_map]
        if recent:
            st.markdown("<div class='ptw-control-mini-title'>Sist brukt</div>", unsafe_allow_html=True)
            recent_cols = st.columns(min(len(recent), 4))
            for idx, label in enumerate(recent[:4]):
                with recent_cols[idx]:
                    if st.button(label, key=f"ai_cc_recent_v1863ag_{idx}", type="primary" if label == active_label else "secondary", use_container_width=True):
                        st.session_state["ai_control_center_active_panel_v1863m"] = label
                        st.session_state["ai_control_center_active_real_panel_v18598"] = label
                        st.session_state["ai_control_center_menu_open_v1863ag"] = False
                        for g_name, g_labels in group_map.items():
                            if label in g_labels:
                                st.session_state["ai_control_center_group_v1863m"] = g_name
                                break
                        st.rerun()

        search_query = st.text_input("SÃ¸k i funksjoner", value="", key="ai_control_center_search_v1863ag", placeholder="Skriv f.eks. paper, valuta, regime, heatmap")
        quick_panel_options = [label for label in group_map.get(active_group, []) if label in panel_map]
        if search_query.strip():
            q = search_query.strip().lower()
            quick_panel_options = [label for label, _renderer in panels if q in str(label).lower()]
            menu_open = True
            submenu_title = f"SÃ¸keresultat: {len(quick_panel_options)} treff"
        else:
            submenu_title = f"Undermeny for {active_group}"
        if not quick_panel_options:
            quick_panel_options = panel_options

        if menu_open and quick_panel_options:
            st.markdown(f"<div class='ptw-control-submenu'><div class='ptw-control-submenu-title'>{html.escape(submenu_title)}</div>", unsafe_allow_html=True)
            for start in range(0, len(quick_panel_options), 4):
                row = quick_panel_options[start:start + 4]
                cols = st.columns(len(row))
                for idx, label in enumerate(row):
                    with cols[idx]:
                        if st.button(label, key=f"ai_cc_panel_v1863ag_{start}_{idx}", type="primary" if label == active_label else "secondary", use_container_width=True):
                            st.session_state["ai_control_center_active_panel_v1863m"] = label
                            st.session_state["ai_control_center_active_real_panel_v18598"] = label
                            st.session_state["ai_control_center_menu_open_v1863ag"] = False
                            recent_next = [label] + [x for x in recent if x != label]
                            st.session_state["ai_control_center_recent_panels_v1863ag"] = recent_next[:4]
                            for g_name, g_labels in group_map.items():
                                if label in g_labels:
                                    st.session_state["ai_control_center_group_v1863m"] = g_name
                                    break
                            st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        elif not menu_open:
            if st.button("Ã…pne undermeny", key="ai_cc_open_submenu_v1863ag", use_container_width=True):
                st.session_state["ai_control_center_menu_open_v1863ag"] = True
                st.rerun()

        active_label = st.session_state.get("ai_control_center_active_panel_v1863m") or active_label
        st.markdown("</div>", unsafe_allow_html=True)
        if active_label == AI_CONTROL_CENTER_MAIN_PANEL_LABEL_V18598:
            st.markdown(
                "<div class='ptw-control-note-strong'>Normal hovedvisning er aktiv. Velg et Kontrollsenter-panel når du vil kjøre én samlet oppgave.</div>",
                unsafe_allow_html=True,
            )
            st.session_state["ai_control_center_active_real_panel_v18598"] = ""
            return None

        st.markdown(
            f"<div class='ptw-control-note-strong'>Du jobber nå i: <b>{html.escape(str(active_label))}</b>. Kun dette panelet åpnes og kjøres.</div>",
            unsafe_allow_html=True,
        )
        renderer = panel_map.get(active_label)
        if renderer:
            st.session_state["ai_control_center_active_real_panel_v18598"] = active_label
            _run_control_panel(active_label, renderer)
            return active_label
        st.session_state["ai_control_center_active_real_panel_v18598"] = ""
        return None
    return None


def _render_ai_control_center_v1863ah(extra_panels: Optional[Sequence[Tuple[str, Callable[[], None]]]] = None) -> Optional[str]:
    """Clean quick-navigation control center without hidden selectbox widgets."""
    with st.expander("AI KONTROLLSENTER - samlet arbeidsflate", expanded=True):
        base_panels: list[Tuple[str, Callable[[], None]]] = [
            ("Analyseunivers", lambda: render_ai_analysis_universe_workspace(expanded=True)),
            ("Prognose", _render_forecast_workspace_tab),
            ("Varsler", lambda: render_common_alert_center(location="workspace")),
            ("Daily Report", render_daily_ai_market_report),
            ("Intelligence", render_market_intelligence_center),
            ("Heatmaps", render_ai_heatmaps),
            ("Testing & Learning", lambda: (
                st.info("Strategi-test, Strategi-test Pro, prognose-vs-faktisk, scoreforklaring og backtest-laering er samlet her."),
                render_strategy_testing_workspace(),
                render_backtest_learning_panel(),
            )),
            ("Regime", render_market_regime_widget),
            ("Makro/renter", render_macro_rates_breadth_panel),
            ("Services", _render_storage_services_status),
        ]
        panels = base_panels + list(extra_panels or [])
        panel_map = dict(panels)

        def _matching_panel_labels(*needles: str) -> list[str]:
            out: list[str] = []
            wanted = [str(n or "").lower() for n in needles if str(n or "").strip()]
            for label, _renderer in panels:
                text = str(label or "").lower()
                if any(n in text for n in wanted):
                    out.append(label)
            return out

        group_map = {
            "Analyse og prognose": _matching_panel_labels("ai kandidattest", "kandidattest", "analyseunivers", "prognose", "daily report", "interaktiv analyse"),
            "Marked og signaler": _matching_panel_labels("dataunderlag", "datakilder", "datagrunnlag", "analyseflyt", "test 1", "top picks", "alpha", "aktor", "aktør", "oljefond", "nbim", "finansavisen", "bjellesau", "beslut", "muligheter", "ipo", "varsler", "intelligence", "heatmaps", "regime", "makro", "nyheter", "marked", "marked/rangering", "watchlist", "valutavarsler"),
            "Testing og portefolje": _matching_panel_labels("testing", "auto test lab", "fond / etf", "portef", "paper"),
            "System": _matching_panel_labels("services", "system/admin"),
        }
        group_map["Marked og signaler"] = list(dict.fromkeys(
            group_map["Marked og signaler"] + _matching_panel_labels("finansavisen", "bjellesauer")
        ))
        known_labels = {label for labels_in_group in group_map.values() for label in labels_in_group}
        extra_labels = [label for label, _renderer in panels if label not in known_labels]
        if extra_labels:
            group_map["Andre paneler"] = extra_labels

        first_panel = next((labels[0] for labels in group_map.values() if labels), None)
        active_label = st.session_state.get("ai_control_center_active_panel_v1863ah") or first_panel or ""
        active_group = st.session_state.get("ai_control_center_group_v1863ah") or next((g for g, labels in group_map.items() if active_label in labels), "Analyse og prognose")
        if active_group not in group_map:
            active_group = "Analyse og prognose"
        show_home = bool(st.session_state.get("ai_control_center_show_home_v1863ah", True))
        submenu_open = bool(st.session_state.get("ai_control_center_submenu_open_v1863ah", True))

        st.markdown(
            f"""
            <div class="ptw-control-hero">
              <div class="ptw-control-hero-top">
                <div>
                  <div class="ptw-control-eyebrow">Samlet arbeidsflate</div>
                  <div class="ptw-control-title">AI Kontrollsenter</div>
                  <div class="ptw-control-caption">Velg hovedomrade, deretter funksjon. Bare valgt panel kjores.</div>
                </div>
                <div class="ptw-control-active-chip">Aktivt panel: {html.escape(str(active_label or "-"))}</div>
              </div>
              <div class="ptw-status-line" style="margin-top:.55rem;">
                <span class="ptw-pill ptw-pill-ai">Samlet AI workspace aktivt</span>
                <span class="ptw-pill">Kun valgt panel kjores</span>
                <span class="ptw-pill">Ingen skjulte analyser</span>
              </div>
            </div>
            <div class="ptw-control-selector-shell">
              <div class="ptw-control-selector-title">Velg oppgave</div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div class='ptw-control-home-button'>", unsafe_allow_html=True)
        if st.button("Til hovedvalg / vis alle bokser", key="ai_cc_home_v1863ah", use_container_width=True):
            st.session_state["ai_control_center_show_home_v1863ah"] = True
            st.session_state["ai_control_center_submenu_open_v1863ah"] = True
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        mode_map = {
            "Finne kjop": "Marked og signaler",
            "Overvake portefolje": "Testing og portefolje",
            "Teste strategi": "Testing og portefolje",
            "Administrere": "System",
        }
        mode_options = list(mode_map.keys())
        current_mode = st.session_state.get("ai_control_center_work_mode_v1863ah") or mode_options[0]

        if show_home:
            st.markdown("<div class='ptw-control-mini-title'>Arbeidsmodus</div>", unsafe_allow_html=True)
            mode_cols = st.columns(len(mode_options))
            for idx, mode in enumerate(mode_options):
                with mode_cols[idx]:
                    if st.button(mode, key=f"ai_cc_mode_v1863ah_{idx}", type="primary" if mode == current_mode else "secondary", use_container_width=True):
                        st.session_state["ai_control_center_work_mode_v1863ah"] = mode
                        st.session_state["ai_control_center_group_v1863ah"] = mode_map[mode]
                        st.session_state["ai_control_center_submenu_open_v1863ah"] = True
                        st.rerun()

            st.markdown("<div class='ptw-control-mini-title'>Hovedomrader</div>", unsafe_allow_html=True)
            groups = list(group_map.keys())
            group_cols = st.columns(len(groups))
            for idx, group_name in enumerate(groups):
                labels = [label for label in group_map.get(group_name, []) if label in panel_map]
                is_active = group_name == active_group
                with group_cols[idx]:
                    if st.button(f"{'ROD' if is_active else 'BLA'} {group_name} - {len(labels)}", key=f"ai_cc_group_v1863ah_{idx}", type="primary" if is_active else "secondary", use_container_width=True):
                        st.session_state["ai_control_center_group_v1863ah"] = group_name
                        st.session_state["ai_control_center_show_home_v1863ah"] = True
                        st.session_state["ai_control_center_submenu_open_v1863ah"] = True
                        st.rerun()

            favorite_needles = ["top picks", "paper trading", "paper-portef", "regime", "valutavarsler"]
            favorites: list[str] = []
            for needle in favorite_needles:
                match = next((label for label, _renderer in panels if needle in str(label).lower()), None)
                if match and match not in favorites:
                    favorites.append(match)
            if favorites:
                st.markdown("<div class='ptw-control-mini-title'>Favoritter</div>", unsafe_allow_html=True)
                fav_cols = st.columns(min(len(favorites), 5))
                for idx, label in enumerate(favorites[:5]):
                    with fav_cols[idx]:
                        if st.button(label, key=f"ai_cc_fav_v1863ah_{idx}", type="primary" if label == active_label else "secondary", use_container_width=True):
                            st.session_state["ai_control_center_active_panel_v1863ah"] = label
                            st.session_state["ai_control_center_show_home_v1863ah"] = False
                            st.session_state["ai_control_center_submenu_open_v1863ah"] = False
                            recent = st.session_state.get("ai_control_center_recent_panels_v1863ah", [])
                            st.session_state["ai_control_center_recent_panels_v1863ah"] = ([label] + [x for x in recent if x != label])[:4]
                            st.rerun()

            recent = [x for x in st.session_state.get("ai_control_center_recent_panels_v1863ah", []) if x in panel_map]
            if recent:
                st.markdown("<div class='ptw-control-mini-title'>Sist brukt</div>", unsafe_allow_html=True)
                recent_cols = st.columns(min(len(recent), 4))
                for idx, label in enumerate(recent[:4]):
                    with recent_cols[idx]:
                        if st.button(label, key=f"ai_cc_recent_v1863ah_{idx}", type="primary" if label == active_label else "secondary", use_container_width=True):
                            st.session_state["ai_control_center_active_panel_v1863ah"] = label
                            st.session_state["ai_control_center_show_home_v1863ah"] = False
                            st.session_state["ai_control_center_submenu_open_v1863ah"] = False
                            st.rerun()

            search_query = st.text_input("Sok i funksjoner", value="", key="ai_control_center_search_v1863ah", placeholder="Skriv f.eks. paper, valuta, regime, heatmap")
            panel_options = [label for label in group_map.get(active_group, []) if label in panel_map]
            title = f"Undermeny for {active_group}"
            if search_query.strip():
                q = search_query.strip().lower()
                panel_options = [label for label, _renderer in panels if q in str(label).lower()]
                title = f"Sokeresultat: {len(panel_options)} treff"

            if submenu_open and panel_options:
                st.markdown(f"<div class='ptw-control-submenu'><div class='ptw-control-submenu-title'>{html.escape(title)}</div>", unsafe_allow_html=True)
                for start in range(0, len(panel_options), 4):
                    row = panel_options[start:start + 4]
                    cols = st.columns(len(row))
                    for idx, label in enumerate(row):
                        with cols[idx]:
                            if st.button(label, key=f"ai_cc_panel_v1863ah_{start}_{idx}", type="primary" if label == active_label else "secondary", use_container_width=True):
                                st.session_state["ai_control_center_active_panel_v1863ah"] = label
                                st.session_state["ai_control_center_show_home_v1863ah"] = False
                                st.session_state["ai_control_center_submenu_open_v1863ah"] = False
                                recent = st.session_state.get("ai_control_center_recent_panels_v1863ah", [])
                                st.session_state["ai_control_center_recent_panels_v1863ah"] = ([label] + [x for x in recent if x != label])[:4]
                                for g_name, g_labels in group_map.items():
                                    if label in g_labels:
                                        st.session_state["ai_control_center_group_v1863ah"] = g_name
                                        break
                                st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        active_label = st.session_state.get("ai_control_center_active_panel_v1863ah") or active_label
        if active_label not in panel_map:
            st.info("Velg et panel i hovedvalget.")
            return None

        st.markdown(
            f"<div class='ptw-control-note-strong'>Du jobber na i: <b>{html.escape(str(active_label))}</b>. Bruk Til hovedvalg for a vise alle bokser igjen.</div>",
            unsafe_allow_html=True,
        )
        _run_control_panel(active_label, panel_map[active_label])
        return active_label


def _render_ai_control_center_v1863ai(extra_panels: Optional[Sequence[Tuple[str, Callable[[], None]]]] = None) -> Optional[str]:
    """Simple main boxes + compact submenu. No panel is opened by default."""
    with st.expander("AI KONTROLLSENTER - samlet arbeidsflate", expanded=True):
        base_panels: list[Tuple[str, Callable[[], None]]] = [
            ("Analyseunivers", lambda: render_ai_analysis_universe_workspace(expanded=True)),
            ("Prognose", _render_forecast_workspace_tab),
            ("Varsler", lambda: render_common_alert_center(location="workspace")),
            ("Daily Report", render_daily_ai_market_report),
            ("Intelligence", render_market_intelligence_center),
            ("Heatmaps", render_ai_heatmaps),
            ("Testing & Learning", lambda: (
                st.info("Strategi-test, Strategi-test Pro, prognose-vs-faktisk, scoreforklaring og backtest-laering er samlet her."),
                render_strategy_testing_workspace(),
                render_backtest_learning_panel(),
            )),
            ("Regime", render_market_regime_widget),
            ("Makro/renter", render_macro_rates_breadth_panel),
            ("Services", _render_storage_services_status),
        ]
        panels = base_panels + list(extra_panels or [])
        panel_map = dict(panels)

        def _matching_panel_labels(*needles: str) -> list[str]:
            out: list[str] = []
            wanted = [str(n or "").lower() for n in needles if str(n or "").strip()]
            for label, _renderer in panels:
                text = str(label or "").lower()
                if any(n in text for n in wanted):
                    out.append(label)
            return out

        group_map = {
            "Analyse og prognose": _matching_panel_labels("ai kandidattest", "kandidattest", "analyseunivers", "prognose", "daily report", "interaktiv analyse"),
            "Marked og signaler": _matching_panel_labels("top picks", "alpha", "aktor", "aktør", "oljefond", "nbim", "finansavisen", "bjellesau", "beslut", "muligheter", "ipo", "varsler", "intelligence", "heatmaps", "regime", "makro", "nyheter", "marked", "marked/rangering", "watchlist", "valutavarsler"),
            "Testing og portefolje": _matching_panel_labels("testing", "auto test lab", "fond / etf", "portef", "paper"),
            "System": _matching_panel_labels("services", "system/admin"),
        }
        group_map["Marked og signaler"] = list(dict.fromkeys(
            group_map["Marked og signaler"] + _matching_panel_labels("finansavisen", "bjellesauer")
        ))
        known_labels = {label for labels_in_group in group_map.values() for label in labels_in_group}
        extra_labels = [label for label, _renderer in panels if label not in known_labels]
        if extra_labels:
            group_map["Andre paneler"] = extra_labels

        active_group = st.session_state.get("ai_control_center_group_v1863ai") or ""
        active_label = st.session_state.get("ai_control_center_active_panel_v1863ai") or ""
        if active_group not in group_map:
            active_group = ""

        st.markdown(
            f"""
            <div class="ptw-control-hero">
              <div class="ptw-control-hero-top">
                <div>
                  <div class="ptw-control-eyebrow">Samlet arbeidsflate</div>
                  <div class="ptw-control-title">AI Kontrollsenter</div>
                  <div class="ptw-control-caption">Velg en hovedboks. En liten undermeny åpnes under raden. Ingen paneler åpnes før du velger en funksjon.</div>
                </div>
                <div class="ptw-control-active-chip">Aktivt panel: {html.escape(str(active_label or "Ingen valgt"))}</div>
              </div>
            </div>
            <div class="ptw-control-selector-shell">
              <div class="ptw-control-selector-title">Hovedvalg</div>
            """,
            unsafe_allow_html=True,
        )

        if active_label:
            st.markdown("<div class='ptw-control-home-button'>", unsafe_allow_html=True)
            if st.button("Til hovedvalg", key="ai_cc_home_v1863ai", use_container_width=True):
                st.session_state["ai_control_center_active_panel_v1863ai"] = ""
                st.session_state["ai_control_center_group_v1863ai"] = ""
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        groups = list(group_map.keys())
        group_cols = st.columns(len(groups))
        for idx, group_name in enumerate(groups):
            labels = [label for label in group_map.get(group_name, []) if label in panel_map]
            is_active = group_name == active_group
            label_text = f"{group_name} ({len(labels)})"
            with group_cols[idx]:
                if st.button(label_text, key=f"ai_cc_group_v1863ai_{idx}", type="primary" if is_active else "secondary", use_container_width=True):
                    st.session_state["ai_control_center_group_v1863ai"] = group_name
                    st.session_state["ai_control_center_active_panel_v1863ai"] = ""
                    st.rerun()

        if active_group:
            panel_options = [label for label in group_map.get(active_group, []) if label in panel_map]
            st.markdown(
                f"<div class='ptw-control-submenu'><div class='ptw-control-submenu-title'>Undermeny: {html.escape(active_group)}</div>",
                unsafe_allow_html=True,
            )
            for start in range(0, len(panel_options), 4):
                row = panel_options[start:start + 4]
                cols = st.columns(len(row))
                for idx, label in enumerate(row):
                    with cols[idx]:
                        if st.button(label, key=f"ai_cc_panel_v1863ai_{start}_{idx}", use_container_width=True):
                            st.session_state["ai_control_center_active_panel_v1863ai"] = label
                            st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        active_label = st.session_state.get("ai_control_center_active_panel_v1863ai") or ""
        if not active_label:
            st.markdown(
                "<div class='ptw-control-note-strong'>Ingen oppgave er åpnet. Velg en hovedboks og deretter en funksjon.</div>",
                unsafe_allow_html=True,
            )
            return None
        renderer = panel_map.get(active_label)
        if not renderer:
            st.info("Velg et panel i hovedvalget.")
            return None
        st.markdown(
            f"<div class='ptw-control-note-strong'>Du jobber nå i: <b>{html.escape(str(active_label))}</b>. Bruk Til hovedvalg for å lukke valgt oppgave.</div>",
            unsafe_allow_html=True,
        )
        _run_control_panel(active_label, renderer)
        return active_label


def _render_pipeline_quick_start_v1863bx(panel_map: dict, group_map: dict) -> None:
    """Visible entry point for the staged Dataunderlag -> Test 10 workflow."""
    data_panel = next(
        (
            label for label in group_map.get("Marked og signaler", [])
            if label in panel_map and ("dataunderlag" in str(label).lower() or "datakilder" in str(label).lower() or "datagrunnlag" in str(label).lower() or "test 1" in str(label).lower())
        ),
        "",
    )
    if not data_panel:
        return

    status_by_stage = {}
    stages = []
    stage_wizard_info_func = None
    try:
        from services.analysis_pipeline_service import get_analysis_pipeline_service, stage_definitions, stage_wizard_info
        from services.state_service import get_state_service
        from services.storage_service import get_storage_service

        stage_wizard_info_func = stage_wizard_info
        pipeline = get_analysis_pipeline_service(
            state_service=get_state_service(st.session_state),
            storage_service=get_storage_service(),
        )
        status_by_stage = {str(row.get("stage_id") or ""): row for row in pipeline.stage_status()}
        stages = stage_definitions()
    except Exception:
        stages = [
            {"stage_id": "data_foundation", "label": "Dataunderlag"},
            {"stage_id": "market_ranking", "label": "Marked/rangering"},
            {"stage_id": "smart_ai", "label": "Smart AI"},
            {"stage_id": "top_picks", "label": "Top Picks"},
            {"stage_id": "early_warning", "label": "Early Warning"},
            {"stage_id": "alpha_radar", "label": "Alpha Radar"},
            {"stage_id": "auto_test_lab", "label": "Auto Test Lab"},
            {"stage_id": "decision_support", "label": "Beslutning"},
            {"stage_id": "portfolio_analysis", "label": "Portefolje"},
            {"stage_id": "paper_trading", "label": "Paper Trading"},
        ]

    active_stage = str(st.session_state.get("analysis_pipeline_active_stage_v1863bz") or "")
    chips = []
    for idx, stage in enumerate(stages[:10], start=1):
        stage_id = str(stage.get("stage_id") or "")
        status = status_by_stage.get(stage_id, {})
        output_count = int(status.get("output") or 0)
        input_count = int(status.get("input") or 0)
        if active_stage == stage_id:
            bg, border, fg = "rgba(220,38,38,.32)", "rgba(248,113,113,.92)", "#fee2e2"
            suffix = "aktiv"
        elif output_count > 0:
            bg, border, fg = "rgba(22,163,74,.24)", "rgba(34,197,94,.70)", "#dcfce7"
            suffix = f"{output_count} ferdig"
        elif input_count > 0:
            bg, border, fg = "rgba(22,163,74,.18)", "rgba(74,222,128,.62)", "#dcfce7"
            suffix = f"{input_count} klar"
        elif idx == 1:
            bg, border, fg = "rgba(14,165,233,.26)", "rgba(125,211,252,.78)", "#eff6ff"
            suffix = "start"
        else:
            bg, border, fg = "rgba(15,23,42,.68)", "rgba(148,163,184,.34)", "#cbd5e1"
            suffix = "venter"
        label = html.escape(str(stage.get("label") or stage_id))
        prefix = "Steg 1" if stage_id == "data_foundation" else f"Test {idx}"
        chips.append(
            f"<span style='display:inline-flex;align-items:center;gap:.28rem;padding:.28rem .48rem;"
            f"border-radius:999px;border:1px solid {border};background:{bg};color:{fg};"
            f"font-size:.76rem;font-weight:800;white-space:nowrap;'>{prefix}: {label}"
            f"<small style='opacity:.82;font-weight:700;'> {html.escape(suffix)}</small></span>"
        )

    st.markdown(
        """
        <div class="ptw-control-note-strong" style="border-color:rgba(56,189,248,.52);">
          <b>Start anbefalt arbeidsflyt:</b> Begynn med 1. Dataunderlag, send resultatet videre, og jobb deg stegvis til Test 10 Paper Trading.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='display:flex;gap:.34rem;flex-wrap:wrap;align-items:center;margin:.12rem 0 .3rem 0;'>"
        + "".join(chips)
        + "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Hurtigtaster: åpner valgt steg og setter standardvalg, men starter ikke tunge analyser.")
    shortcut_cols = st.columns(5)
    for idx, stage in enumerate(stages[:10], start=1):
        stage_id = str(stage.get("stage_id") or "")
        info = stage_wizard_info_func(stage_id) if callable(stage_wizard_info_func) else {}
        label = str(stage.get("label") or stage_id)
        button_label = f"{idx}. {label}"
        if active_stage == stage_id:
            button_label = f"▶ {button_label}"
        elif int((status_by_stage.get(stage_id) or {}).get("output") or 0) > 0:
            button_label = f"✓ {button_label}"
        col = shortcut_cols[(idx - 1) % len(shortcut_cols)]
        with col:
            if st.button(button_label, key=f"analysis_pipeline_shortcut_{stage_id}_v1863bz", use_container_width=True, type="primary" if active_stage == stage_id else "secondary"):
                st.session_state["analysis_pipeline_pending_nav_v1863bw"] = {
                    "stage_id": stage_id,
                    "group": info.get("group") or "Marked og signaler",
                    "panel": info.get("panel_label") or (data_panel if stage_id == "data_foundation" else label),
                    "defaults": dict(info.get("defaults") or {}),
                    "auto_run": False,
                }
                st.session_state["analysis_pipeline_active_stage_v1863bz"] = stage_id
                st.rerun()


def _pipeline_relevant_panel_labels_v1864j(active_stage: str, panels: Sequence[Tuple[str, Callable[[], None]]]) -> list[str]:
    """Return the panels that are actually useful for the active pipeline step."""
    stage_needles: dict[str, tuple[str, ...]] = {
        "data_foundation": ("dataunderlag", "datakilder", "datagrunnlag", "finansavisen", "bjellesau", "aktor", "aktør", "register", "oljefond", "nbim", "folketrygdfondet", "kildetest"),
        "market_ranking": ("marked/rangering", "marked", "heatmaps", "regime", "makro", "nyheter"),
        "smart_ai": ("analyseunivers",),
        "top_picks": ("top picks", "marked/rangering"),
        "early_warning": ("alpha", "early warning", "nyheter", "finansavisen", "bjellesau"),
        "alpha_radar": ("alpha", "intelligence", "aktor", "aktør", "oljefond", "nbim", "finansavisen", "bjellesau"),
        "auto_test_lab": ("auto test lab", "testing", "learning", "fond / etf"),
        "decision_support": ("beslut",),
        "portfolio_analysis": ("portef", "fond / etf"),
        "paper_trading": ("paper",),
    }
    needles = stage_needles.get(str(active_stage or ""), ())
    if not needles:
        return []
    out: list[str] = []
    for label, _renderer in panels:
        text = str(label or "").lower()
        if any(needle in text for needle in needles):
            out.append(label)
    return list(dict.fromkeys(out))


def _render_ai_control_center_v1863aj(extra_panels: Optional[Sequence[Tuple[str, Callable[[], None]]]] = None) -> Optional[str]:
    """Stable radio-based control center navigation."""
    with st.expander("AI KONTROLLSENTER - samlet arbeidsflate", expanded=True):
        base_panels: list[Tuple[str, Callable[[], None]]] = [
            ("Analyseunivers", lambda: render_ai_analysis_universe_workspace(expanded=True)),
            ("Prognose", _render_forecast_workspace_tab),
            ("Varsler", lambda: render_common_alert_center(location="workspace")),
            ("Daily Report", render_daily_ai_market_report),
            ("Intelligence", render_market_intelligence_center),
            ("Heatmaps", render_ai_heatmaps),
            ("Testing & Learning", lambda: (
                st.info("Strategi-test, Strategi-test Pro, prognose-vs-faktisk, scoreforklaring og backtest-laering er samlet her."),
                render_strategy_testing_workspace(),
                render_backtest_learning_panel(),
            )),
            ("Regime", render_market_regime_widget),
            ("Makro/renter", render_macro_rates_breadth_panel),
            ("Services", _render_storage_services_status),
        ]
        panels = base_panels + list(extra_panels or [])
        panel_map = dict(panels)

        def _matching_panel_labels(*needles: str) -> list[str]:
            out: list[str] = []
            wanted = [str(n or "").lower() for n in needles if str(n or "").strip()]
            for label, _renderer in panels:
                text = str(label or "").lower()
                if any(n in text for n in wanted):
                    out.append(label)
            return out

        ai_candidate_group_name = "AI Kandidattest"
        ai_candidate_primary_labels = _matching_panel_labels("ai kandidattest", "kandidattest")
        ai_candidate_primary_label = next((label for label in ai_candidate_primary_labels if label in panel_map), "")
        ai_candidate_source_labels = _matching_panel_labels(
            "dataunderlag",
            "datakilder",
            "datagrunnlag",
            "aktor",
            "aktør",
            "register",
            "oljefond",
            "nbim",
            "folketrygdfondet",
            "finansavisen",
            "bjellesau",
            "alpha radar",
        )
        ai_candidate_labels = list(dict.fromkeys(ai_candidate_primary_labels + ai_candidate_source_labels))
        group_map = {
            ai_candidate_group_name: ai_candidate_labels,
            "Analyse og prognose": _matching_panel_labels("analyseunivers", "prognose", "daily report", "interaktiv analyse"),
            "Marked og signaler": _matching_panel_labels("dataunderlag", "datakilder", "datagrunnlag", "analyseflyt", "test 1", "top picks", "alpha", "aktor", "aktør", "register", "oljefond", "nbim", "folketrygdfondet", "finansavisen", "bjellesau", "beslut", "muligheter", "ipo", "varsler", "intelligence", "heatmaps", "regime", "makro", "nyheter", "marked", "marked/rangering", "watchlist", "valutavarsler"),
            "Testing og portefolje": _matching_panel_labels("testing", "auto test lab", "fond / etf", "portef", "paper"),
            "System": _matching_panel_labels("services", "system/admin"),
        }
        data_foundation_labels = _matching_panel_labels("dataunderlag", "datakilder", "datagrunnlag", "analyseflyt", "test 1")
        group_map["Marked og signaler"] = list(dict.fromkeys(
            data_foundation_labels + group_map["Marked og signaler"] + _matching_panel_labels("finansavisen", "bjellesauer", "folketrygdfondet")
        ))
        known_labels = {label for labels_in_group in group_map.values() for label in labels_in_group}
        extra_labels = [label for label, _renderer in panels if label not in known_labels]
        if extra_labels:
            group_map["Andre paneler"] = extra_labels

        def _stage_for_active_panel_v1864h(active_panel_label: str, stage_labels: dict[str, str]) -> str:
            if active_panel_label == "Alpha Radar":
                engine = str(st.session_state.get("alpha_radar_engine_v1863au") or "Alpha Radar")
                return "early_warning" if engine == "Early Warning V1" else "alpha_radar"
            for stage_id, panel_label in stage_labels.items():
                if str(panel_label) == str(active_panel_label):
                    return str(stage_id)
            return ""

        pending_nav = st.session_state.pop("analysis_pipeline_pending_nav_v1863bw", None)
        pending_nav_sync: dict[str, str] = {}
        pending_stage = ""
        if isinstance(pending_nav, dict):
            for key, value in (pending_nav.get("defaults") or {}).items():
                if key:
                    st.session_state[key] = value
            pending_group = str(pending_nav.get("group") or "")
            pending_panel = str(pending_nav.get("panel") or "")
            pending_stage = str(pending_nav.get("stage_id") or "")
            if pending_group in group_map and pending_panel in group_map.get(pending_group, []) and pending_panel in panel_map:
                st.session_state["ai_control_center_group_v1863aj"] = pending_group
                st.session_state["ai_control_center_active_panel_v1863aj"] = pending_panel
                if pending_stage:
                    st.session_state["analysis_pipeline_active_stage_v1863bz"] = pending_stage
                pending_nav_sync = {"group": pending_group, "panel": pending_panel}

        active_stage_hint = str(st.session_state.get("analysis_pipeline_active_stage_v1863bz") or "")
        stage_relevant_labels = _pipeline_relevant_panel_labels_v1864j(active_stage_hint, panels)
        stage_group_name = ""
        if stage_relevant_labels:
            stage_label = active_stage_hint
            try:
                from services.analysis_pipeline_service import stage_wizard_info

                stage_label = str(stage_wizard_info(active_stage_hint).get("label") or active_stage_hint)
            except Exception:
                pass
            stage_group_name = f"Analyseflyt: {stage_label}"
            group_map = {stage_group_name: stage_relevant_labels, **group_map}
            if pending_nav_sync and pending_stage == active_stage_hint and pending_nav_sync.get("panel") in stage_relevant_labels:
                st.session_state["ai_control_center_group_v1863aj"] = stage_group_name
                pending_nav_sync["group"] = stage_group_name

        group_options = ["Ingen valgt"] + [f"{name} ({len([x for x in labels if x in panel_map])})" for name, labels in group_map.items()]
        group_by_option = {"Ingen valgt": ""}
        for name, labels in group_map.items():
            group_by_option[f"{name} ({len([x for x in labels if x in panel_map])})"] = name

        if pending_nav_sync:
            pending_group = pending_nav_sync.get("group", "")
            pending_panel = pending_nav_sync.get("panel", "")
            group_option = next((opt for opt, name in group_by_option.items() if name == pending_group), "")
            if group_option:
                st.session_state["ai_control_center_group_radio_v1863aj"] = group_option
            if pending_group and pending_panel:
                st.session_state[f"ai_control_center_panel_radio_v1863aj_{pending_group}"] = pending_panel

        current_group = st.session_state.get("ai_control_center_group_v1863aj", "")
        if stage_group_name and st.session_state.get("ai_control_center_last_stage_menu_v1864j") != active_stage_hint:
            st.session_state["ai_control_center_group_v1863aj"] = stage_group_name
            st.session_state["ai_control_center_last_stage_menu_v1864j"] = active_stage_hint
            current_group = stage_group_name
        current_group_option = next((opt for opt, name in group_by_option.items() if name == current_group), "Ingen valgt")

        try:
            from services.analysis_pipeline_service import STAGE_PANEL_LABELS

            active_panel_for_sync = st.session_state.get("ai_control_center_active_panel_v1863aj") or ""
            active_stage_for_sync = _stage_for_active_panel_v1864h(str(active_panel_for_sync), STAGE_PANEL_LABELS)
            if active_stage_for_sync:
                st.session_state["analysis_pipeline_active_stage_v1863bz"] = active_stage_for_sync
        except Exception:
            pass

        st.markdown(
            f"""
            <div class="ptw-control-hero">
              <div class="ptw-control-hero-top">
                <div>
                  <div class="ptw-control-eyebrow">Samlet arbeidsflate</div>
                  <div class="ptw-control-title">AI Kontrollsenter</div>
                  <div class="ptw-control-caption">Starttilstand er Ingen valgt. Velg hovedområde for aa åpne relevant arbeidsflate.</div>
                  <div class="ptw-control-caption">AI Kandidattest er hovedarbeidsflaten; datakilder, eierimport og radarer ligger samlet under samme valg.</div>
                </div>
                <div class="ptw-control-active-chip">Aktivt panel: {html.escape(str(st.session_state.get("ai_control_center_active_panel_v1863aj") or "Ingen valgt"))}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        _render_pipeline_quick_start_v1863bx(panel_map, group_map)

        st.markdown(
            """
            <div class="ptw-control-selector-shell">
              <div class="ptw-control-selector-title">Hovedvalg</div>
            """,
            unsafe_allow_html=True,
        )

        selected_group_option = st.radio(
            "Velg hovedområde",
            group_options,
            index=group_options.index(current_group_option) if current_group_option in group_options else 0,
            horizontal=True,
            key="ai_control_center_group_radio_v1863aj",
        )
        selected_group = group_by_option.get(selected_group_option, "")
        if selected_group != current_group:
            st.session_state["ai_control_center_group_v1863aj"] = selected_group
            st.session_state["ai_control_center_active_panel_v1863aj"] = ""
            current_group = selected_group
            direct_panels = [label for label in group_map.get(selected_group, []) if label in panel_map]
            if len(direct_panels) == 1:
                st.session_state["ai_control_center_active_panel_v1863aj"] = direct_panels[0]
            elif selected_group == ai_candidate_group_name and ai_candidate_primary_label in direct_panels:
                st.session_state["ai_control_center_active_panel_v1863aj"] = ai_candidate_primary_label

        active_label = st.session_state.get("ai_control_center_active_panel_v1863aj") or ""
        if selected_group:
            direct_panels = [label for label in group_map.get(selected_group, []) if label in panel_map]
            if len(direct_panels) == 1:
                st.session_state["ai_control_center_active_panel_v1863aj"] = direct_panels[0]
                active_label = direct_panels[0]
            elif selected_group == ai_candidate_group_name and not active_label and ai_candidate_primary_label in direct_panels:
                st.session_state["ai_control_center_active_panel_v1863aj"] = ai_candidate_primary_label
                active_label = ai_candidate_primary_label
            panel_options = ["Ingen valgt"] + direct_panels
            current_panel_option = active_label if active_label in panel_options else "Ingen valgt"
            if len(direct_panels) > 1:
                submenu_title = (
                    "AI Kandidattest: analyse, kilder og radarer"
                    if selected_group == ai_candidate_group_name
                    else f"Undermeny: {selected_group}"
                )
                st.markdown(
                    f"<div class='ptw-control-submenu'><div class='ptw-control-submenu-title'>{html.escape(submenu_title)}</div>",
                    unsafe_allow_html=True,
                )
                selected_panel = st.radio(
                    "Velg funksjon",
                    panel_options,
                    index=panel_options.index(current_panel_option),
                    horizontal=True,
                    key=f"ai_control_center_panel_radio_v1863aj_{selected_group}",
                )
                st.markdown("</div>", unsafe_allow_html=True)
                if selected_panel != current_panel_option:
                    st.session_state["ai_control_center_active_panel_v1863aj"] = "" if selected_panel == "Ingen valgt" else selected_panel
                    active_label = st.session_state["ai_control_center_active_panel_v1863aj"]

        st.markdown("</div>", unsafe_allow_html=True)

        active_label = st.session_state.get("ai_control_center_active_panel_v1863aj") or ""
        if not active_label:
            st.markdown(
                "<div class='ptw-control-note-strong'>Ingen oppgave er åpnet. Velg hovedområde og funksjon når du vil starte et panel.</div>",
                unsafe_allow_html=True,
            )
            return None
        try:
            from services.analysis_pipeline_service import STAGE_PANEL_LABELS

            active_stage_for_sync = _stage_for_active_panel_v1864h(str(active_label), STAGE_PANEL_LABELS)
            if active_stage_for_sync:
                st.session_state["analysis_pipeline_active_stage_v1863bz"] = active_stage_for_sync
        except Exception:
            pass
        renderer = panel_map.get(active_label)
        if not renderer:
            st.info("Velg et panel i hovedvalget.")
            return None
        if st.button("Til hovedvalg / lukk oppgave", key="ai_cc_home_v1863aj", use_container_width=True):
            st.session_state["ai_control_center_active_panel_v1863aj"] = ""
            st.rerun()
        st.markdown(
            f"<div class='ptw-control-note-strong'>Du jobber nå i: <b>{html.escape(str(active_label))}</b>.</div>",
            unsafe_allow_html=True,
        )
        _run_control_panel(active_label, renderer)
        return active_label
