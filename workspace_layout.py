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
from app_version import get_app_build_label
from local_time import browser_header_clock_document
from navigation_state import get_global_navigation_state, set_global_navigation_state, clear_global_navigation_state, canonical_nav_for_panel_v19220_rc7
from control_center_route_state import consume_control_center_route_lock_v19220_rc6


def _autonomy_centered_v1900() -> bool:
    try:
        from autonomi_core.configuration.application_centered import application_centered_enabled
        return application_centered_enabled()
    except Exception:
        return False


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

        /* v18.6.25: modern dashboard polish without changing analysis logic. */
        html body .stApp {
            background:
                radial-gradient(circle at 12% 0%, rgba(14,165,233,.16), transparent 28%),
                radial-gradient(circle at 92% 4%, rgba(34,197,94,.10), transparent 25%),
                linear-gradient(180deg, #070d1d 0%, #0a1020 38%, #070b16 100%) !important;
        }
        html body .stApp .block-container {
            padding-left: 1.0rem !important;
            padding-right: 1.0rem !important;
        }
        .ptw-app-title {
            border: 1px solid rgba(125,211,252,.28) !important;
            background: linear-gradient(135deg, rgba(15,23,42,.92), rgba(8,47,73,.72) 52%, rgba(6,78,59,.28)) !important;
            border-radius: 18px !important;
            padding: .72rem .90rem !important;
            margin: .10rem 0 .46rem 0 !important;
            box-shadow: 0 18px 42px rgba(0,0,0,.28), 0 0 0 1px rgba(125,211,252,.08) inset !important;
            justify-content: space-between !important;
            flex-wrap: wrap !important;
        }
        .ptw-title-stack { display:flex; flex-direction:column; gap:.10rem; }
        .ptw-title-eyebrow {
            color:#67e8f9;
            font-size:.72rem;
            font-weight:950;
            letter-spacing:.08em;
            text-transform:uppercase;
        }
        .ptw-title-main {
            color:#f8fafc;
            font-size:1.48rem;
            font-weight:950;
            line-height:1.04;
        }
        .ptw-title-sub {
            color:rgba(219,234,254,.82);
            font-size:.82rem;
            font-weight:750;
            margin-top:.04rem;
        }
        .ptw-title-actions { display:flex; gap:.42rem; flex-wrap:wrap; align-items:center; }
        .ptw-title-chip {
            display:inline-flex;
            align-items:center;
            gap:.28rem;
            border:1px solid rgba(125,211,252,.34);
            background:rgba(15,23,42,.72);
            color:#e0f2fe;
            border-radius:999px;
            padding:.28rem .56rem;
            font-size:.76rem;
            font-weight:900;
        }
        .ptw-sticky-topbar,
        .v18532-header-status,
        .v18532-top-controls,
        .v18581-global-toolbar,
        .v18548-global-update-wrap {
            border-radius: 16px !important;
            border-color: rgba(125,211,252,.26) !important;
            background: linear-gradient(180deg, rgba(15,23,42,.82), rgba(8,16,34,.74)) !important;
            box-shadow: 0 12px 28px rgba(0,0,0,.20), 0 0 0 1px rgba(125,211,252,.05) inset !important;
        }
        html body .stApp div[data-testid="stExpander"] details summary {
            min-height: 42px !important;
            border-radius: 14px !important;
            background: linear-gradient(135deg, rgba(8,47,73,.68), rgba(15,23,42,.92)) !important;
            border-color: rgba(125,211,252,.34) !important;
            box-shadow: 0 10px 22px rgba(0,0,0,.16), 0 0 0 1px rgba(125,211,252,.07) inset !important;
        }
        html body .stApp div[data-testid="stExpander"] details[open] summary {
            background: linear-gradient(135deg, rgba(6,78,59,.62), rgba(15,23,42,.94)) !important;
            border-color: rgba(34,197,94,.42) !important;
        }
        .ptw-control-hero {
            border-radius: 20px !important;
            padding: .95rem 1.05rem !important;
            background: linear-gradient(135deg, rgba(6,78,59,.56), rgba(8,47,73,.82) 44%, rgba(15,23,42,.96)) !important;
        }
        .ptw-control-selector-shell {
            border-radius: 18px !important;
            background: linear-gradient(135deg, rgba(15,23,42,.88), rgba(8,47,73,.58)) !important;
            box-shadow: 0 14px 32px rgba(0,0,0,.20), 0 0 0 1px rgba(125,211,252,.10) inset !important;
        }
        .ptw-control-submenu {
            border-radius: 16px !important;
            background: rgba(2,6,23,.30) !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] { gap:.44rem .48rem !important; }
        div[data-testid="stRadio"] label {
            border-radius: 14px !important;
            padding: .40rem .64rem !important;
            background: linear-gradient(180deg, rgba(15,23,42,.82), rgba(8,47,73,.48)) !important;
            box-shadow: 0 8px 18px rgba(0,0,0,.12) !important;
        }
        div[data-testid="stRadio"] label:has(input:checked) {
            background: linear-gradient(180deg, rgba(22,163,74,.56), rgba(8,47,73,.66)) !important;
            box-shadow: 0 0 22px rgba(34,197,94,.18), 0 0 0 1px rgba(187,247,208,.12) inset !important;
        }


        /* v18.6.27: Modern Dashboard Skin - visual-only pass, no analysemotor changes. */
        :root {
            --aa-bg: #050914;
            --aa-panel: rgba(11, 18, 32, .78);
            --aa-panel-2: rgba(15, 23, 42, .84);
            --aa-border: rgba(148, 163, 184, .18);
            --aa-cyan: #22d3ee;
            --aa-blue: #38bdf8;
            --aa-green: #22c55e;
            --aa-text: #f8fafc;
            --aa-muted: #94a3b8;
        }
        html body .stApp {
            background:
                radial-gradient(circle at 15% -10%, rgba(14,165,233,.16), transparent 34rem),
                radial-gradient(circle at 88% 0%, rgba(34,197,94,.10), transparent 38rem),
                linear-gradient(180deg, #06101f 0%, #050914 48%, #040711 100%) !important;
        }
        html body .stApp .block-container {
            max-width: 97vw !important;
            padding-top: .35rem !important;
        }
        html body .stApp .ptw-app-title {
            position: relative !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 1rem !important;
            margin: .16rem 0 .52rem 0 !important;
            padding: .72rem .92rem !important;
            border: 1px solid rgba(125,211,252,.22) !important;
            border-radius: 20px !important;
            background:
                linear-gradient(135deg, rgba(15,23,42,.92), rgba(8,47,73,.62) 52%, rgba(6,78,59,.32)) !important;
            box-shadow: 0 22px 54px rgba(0,0,0,.28), 0 0 0 1px rgba(255,255,255,.04) inset !important;
            overflow: hidden !important;
        }
        html body .stApp .ptw-app-title::before {
            content: "";
            position: absolute;
            left: 0; right: 0; top: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(125,211,252,.85), rgba(34,197,94,.55), transparent);
        }
        html body .stApp .ptw-title-stack { min-width: 0 !important; }
        html body .stApp .ptw-title-eyebrow {
            color: #67e8f9 !important;
            font-size: .70rem !important;
            font-weight: 950 !important;
            letter-spacing: .11em !important;
            text-transform: uppercase !important;
            margin-bottom: .08rem !important;
        }
        html body .stApp .ptw-title-main {
            color: #f8fafc !important;
            font-size: clamp(1.10rem, 1.45vw, 1.68rem) !important;
            font-weight: 980 !important;
            letter-spacing: -.035em !important;
            line-height: 1.02 !important;
        }
        html body .stApp .ptw-title-sub {
            margin-top: .18rem !important;
            color: #cbd5e1 !important;
            font-size: .80rem !important;
            font-weight: 750 !important;
        }
        html body .stApp .ptw-title-actions {
            display: flex !important;
            flex-wrap: wrap !important;
            gap: .38rem !important;
            justify-content: flex-end !important;
        }
        html body .stApp .ptw-title-chip,
        html body .stApp .ptw-pill,
        html body .stApp .mini-status-chip,
        html body .stApp .v18-status-chip {
            border-radius: 999px !important;
            border: 1px solid rgba(125,211,252,.24) !important;
            background: rgba(15,23,42,.66) !important;
            color: #e2e8f0 !important;
            box-shadow: 0 6px 20px rgba(0,0,0,.12) !important;
        }
        html body .stApp .ptw-title-chip {
            padding: .32rem .58rem !important;
            font-size: .72rem !important;
            font-weight: 900 !important;
        }
        html body .stApp .ptw-sticky-topbar,
        html body .stApp .v18548-global-update-wrap,
        html body .stApp .v18534-trading-control-stack,
        html body .stApp .v18532-header-status {
            border-radius: 18px !important;
            border-color: rgba(148,163,184,.16) !important;
            background: rgba(7, 12, 24, .66) !important;
            box-shadow: 0 18px 44px rgba(0,0,0,.18), 0 0 0 1px rgba(255,255,255,.03) inset !important;
            backdrop-filter: blur(12px) !important;
        }
        html body .stApp .ptw-sticky-topbar {
            padding: .46rem .62rem !important;
            margin-bottom: .46rem !important;
        }
        html body .stApp .ticker-tape-wrap,
        html body .stApp .special-watch-tape-v18621 {
            border: 1px solid rgba(148,163,184,.14) !important;
            border-radius: 16px !important;
            background: rgba(248,250,252,.98) !important;
            box-shadow: 0 16px 34px rgba(0,0,0,.18) !important;
            min-height: 58px !important;
        }
        html body .stApp .ticker-card,
        html body .stApp .ticker-tape-card,
        html body .stApp .banner-card {
            border-radius: 14px !important;
            border-color: rgba(15,23,42,.08) !important;
            box-shadow: 0 3px 12px rgba(15,23,42,.06) !important;
        }
        html body .stApp div[data-testid="stExpander"] {
            border: 1px solid rgba(148,163,184,.14) !important;
            border-radius: 18px !important;
            background: rgba(7, 12, 24, .54) !important;
            box-shadow: 0 14px 34px rgba(0,0,0,.16) !important;
            margin-bottom: .54rem !important;
        }
        html body .stApp div[data-testid="stExpander"] details summary {
            min-height: 46px !important;
            border: 0 !important;
            border-bottom: 1px solid rgba(148,163,184,.12) !important;
            border-radius: 18px 18px 0 0 !important;
            background: linear-gradient(180deg, rgba(15,23,42,.86), rgba(8,47,73,.34)) !important;
            box-shadow: none !important;
        }
        html body .stApp div[data-testid="stExpander"] details:not([open]) summary {
            border-radius: 18px !important;
            border-bottom: 0 !important;
        }
        html body .stApp div[data-testid="stExpander"] details[open] summary {
            background: linear-gradient(180deg, rgba(6,78,59,.48), rgba(15,23,42,.84)) !important;
        }
        html body .stApp div[data-testid="stExpander"] details summary p {
            font-size: .92rem !important;
            letter-spacing: -.01em !important;
        }
        html body .stApp .ptw-control-hero {
            border: 1px solid rgba(125,211,252,.22) !important;
            border-radius: 22px !important;
            padding: 1.05rem 1.15rem !important;
            background:
                radial-gradient(circle at 0% 0%, rgba(56,189,248,.24), transparent 28rem),
                linear-gradient(135deg, rgba(15,23,42,.94), rgba(8,47,73,.66) 50%, rgba(6,78,59,.42)) !important;
            box-shadow: 0 24px 58px rgba(0,0,0,.25), 0 0 0 1px rgba(255,255,255,.04) inset !important;
        }
        html body .stApp .ptw-control-title {
            font-size: clamp(1.34rem, 2vw, 2.05rem) !important;
            letter-spacing: -.04em !important;
        }
        html body .stApp .ptw-control-caption {
            max-width: 72rem !important;
            color: #cbd5e1 !important;
            font-size: .88rem !important;
        }
        html body .stApp .ptw-control-active-chip {
            border-color: rgba(34,197,94,.36) !important;
            background: rgba(16,65,52,.42) !important;
            box-shadow: 0 0 24px rgba(34,197,94,.12) !important;
        }
        html body .stApp .ptw-control-selector-shell,
        html body .stApp .ptw-control-submenu,
        html body .stApp .ptw-control-panel-shell {
            border-radius: 20px !important;
            border-color: rgba(148,163,184,.14) !important;
            background: rgba(7, 12, 24, .58) !important;
            box-shadow: 0 18px 42px rgba(0,0,0,.16), 0 0 0 1px rgba(255,255,255,.03) inset !important;
        }
        html body .stApp .ptw-control-selector-title,
        html body .stApp .ptw-control-submenu-title,
        html body .stApp .ptw-control-panel-title {
            color: #e0f2fe !important;
            letter-spacing: .06em !important;
        }
        html body .stApp div[data-testid="stRadio"] label {
            border-radius: 16px !important;
            padding: .50rem .72rem !important;
            border-color: rgba(148,163,184,.16) !important;
            background: rgba(15,23,42,.64) !important;
            box-shadow: none !important;
        }
        html body .stApp div[data-testid="stRadio"] label:hover {
            border-color: rgba(56,189,248,.45) !important;
            background: rgba(8,47,73,.54) !important;
        }
        html body .stApp div[data-testid="stRadio"] label:has(input:checked) {
            border-color: rgba(34,197,94,.54) !important;
            background: linear-gradient(135deg, rgba(22,163,74,.38), rgba(8,47,73,.62)) !important;
            box-shadow: 0 0 0 1px rgba(187,247,208,.10) inset, 0 12px 28px rgba(34,197,94,.10) !important;
        }
        html body .stApp .v18-dark-row,
        html body .stApp .ptw-control-note-strong {
            border-radius: 16px !important;
            border-color: rgba(148,163,184,.14) !important;
            background: rgba(7, 12, 24, .60) !important;
            color: #dbeafe !important;
        }
        html body .stApp div[data-testid="stDataFrame"] {
            border-radius: 16px !important;
            overflow: hidden !important;
            box-shadow: 0 16px 34px rgba(0,0,0,.18) !important;
        }
        html body .stApp div[data-testid="stButton"] > button,
        html body .stApp div[data-testid="stFormSubmitButton"] > button {
            border-radius: 12px !important;
            font-weight: 950 !important;
            box-shadow: 0 10px 22px rgba(0,0,0,.14) !important;
        }
        section[data-testid="stSidebar"] {
            background:
                radial-gradient(circle at top, rgba(14,165,233,.14), transparent 18rem),
                linear-gradient(180deg, #050914, #020617) !important;
            border-right: 1px solid rgba(148,163,184,.13) !important;
        }
        section[data-testid="stSidebar"] .stButton > button {
            border-radius: 14px !important;
        }
        @media (max-width: 980px) {
            html body .stApp .ptw-app-title { align-items: flex-start !important; flex-direction: column !important; }
            html body .stApp .ptw-title-actions { justify-content: flex-start !important; }
            html body .stApp .ptw-control-hero-top { gap: .62rem !important; }
        }



        /* v18.6.31 Dashboard 2026 */
        html body .stApp .ptw-app-title {
            border: 1px solid rgba(148,163,184,.14) !important;
            border-radius: 22px !important;
            padding: .78rem .90rem !important;
            margin: .10rem 0 .64rem 0 !important;
            background:
                radial-gradient(circle at 0% 0%, rgba(56,189,248,.20), transparent 26rem),
                linear-gradient(135deg, rgba(7,12,24,.94), rgba(15,23,42,.84) 55%, rgba(6,78,59,.26)) !important;
            box-shadow: 0 24px 60px rgba(0,0,0,.22), 0 0 0 1px rgba(255,255,255,.035) inset !important;
        }
        html body .stApp .ptw-title-main { font-size: clamp(1.35rem, 2.2vw, 2.35rem) !important; }
        html body .stApp .ptw-title-sub { color:#cbd5e1 !important; }

        html body .stApp .dash2026-kpi-grid {
            display:grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap:.72rem;
            margin:.36rem 0 .72rem 0;
        }
        html body .stApp .dash2026-kpi-card {
            border:1px solid rgba(148,163,184,.14);
            border-radius:20px;
            padding:.78rem .88rem;
            min-height:92px;
            background:rgba(7,12,24,.68);
            box-shadow:0 18px 44px rgba(0,0,0,.18), 0 0 0 1px rgba(255,255,255,.03) inset;
        }
        html body .stApp .dash2026-kpi-label {
            color:#94a3b8;
            font-size:.74rem;
            font-weight:950;
            letter-spacing:.06em;
            text-transform:uppercase;
            margin-bottom:.22rem;
        }
        html body .stApp .dash2026-kpi-value {
            color:#f8fafc;
            font-size:clamp(1.32rem, 2vw, 2.05rem);
            font-weight:980;
            line-height:1.02;
            letter-spacing:-.04em;
        }
        html body .stApp .dash2026-kpi-sub {
            color:#cbd5e1;
            font-size:.78rem;
            font-weight:760;
            margin-top:.28rem;
            line-height:1.22;
        }
        html body .stApp .dash2026-kpi-card.buy { border-color:rgba(34,197,94,.28); background:linear-gradient(135deg, rgba(6,78,59,.50), rgba(7,12,24,.74)); }
        html body .stApp .dash2026-kpi-card.sell { border-color:rgba(248,113,113,.26); background:linear-gradient(135deg, rgba(127,29,29,.38), rgba(7,12,24,.74)); }
        html body .stApp .dash2026-kpi-card.alerts { border-color:rgba(251,191,36,.26); background:linear-gradient(135deg, rgba(120,53,15,.38), rgba(7,12,24,.74)); }
        html body .stApp .dash2026-kpi-card.best { border-color:rgba(56,189,248,.28); background:linear-gradient(135deg, rgba(8,47,73,.54), rgba(7,12,24,.74)); }
        html body .stApp .dash2026-section-label {
            margin:.12rem 0 .32rem 0;
            color:#bae6fd;
            font-size:.78rem;
            font-weight:950;
            letter-spacing:.08em;
            text-transform:uppercase;
        }
        html body .stApp .ptw-ai-control-anchor {
            height:1px;
            margin:.76rem 0 .12rem 0;
        }
        html body .stApp .ptw-control-hero {
            margin-top:.18rem !important;
            border-radius:24px !important;
        }
        html body .stApp .ptw-control-selector-shell div[data-testid="stRadio"] > div {
            display:grid !important;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)) !important;
            gap:.62rem !important;
            align-items:stretch !important;
        }
        html body .stApp .ptw-control-selector-shell div[data-testid="stRadio"] label {
            min-height:74px !important;
            align-items:flex-start !important;
            justify-content:flex-start !important;
            padding:.78rem .88rem !important;
            border-radius:18px !important;
            background:linear-gradient(135deg, rgba(15,23,42,.84), rgba(8,47,73,.34)) !important;
            border:1px solid rgba(148,163,184,.16) !important;
            box-shadow:0 12px 30px rgba(0,0,0,.14) !important;
        }
        html body .stApp .ptw-control-selector-shell div[data-testid="stRadio"] label p {
            font-size:.92rem !important;
            font-weight:950 !important;
            line-height:1.16 !important;
            color:#e2e8f0 !important;
        }
        html body .stApp .ptw-control-selector-shell div[data-testid="stRadio"] label:has(input:checked) {
            background:linear-gradient(135deg, rgba(6,78,59,.58), rgba(8,47,73,.62)) !important;
            border-color:rgba(34,197,94,.50) !important;
            box-shadow:0 0 0 1px rgba(187,247,208,.10) inset, 0 18px 44px rgba(34,197,94,.11) !important;
        }
        @media (max-width: 980px) {
            html body .stApp .dash2026-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media (max-width: 560px) {
            html body .stApp .dash2026-kpi-grid { grid-template-columns: 1fr; }
        }
</style>
        """,
        unsafe_allow_html=True,
    )


def render_workspace_title() -> None:
    """Render app title with a passive PC clock immediately before the build label."""
    title_col, status_col = st.columns([3.2, 2.0], vertical_alignment="center")
    with title_col:
        st.markdown(
            """<div class="ptw-app-title"><div class="ptw-title-stack"><div class="ptw-title-main">📈 AI Aksje Analyzer Pro</div></div></div>""",
            unsafe_allow_html=True,
        )
    with status_col:
        try:
            from streamlit.components.v1 import html as components_html
            components_html(browser_header_clock_document(get_app_build_label()), height=42, scrolling=False)
        except Exception:
            st.markdown(
                f"<div class='ptw-app-title' style='justify-content:flex-end'><span class='ptw-title-chip'>{html.escape(get_app_build_label())}</span></div>",
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
        st.dataframe(rows, width="stretch", hide_index=True, height=min(420, 42 + len(rows) * 34))
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
            "Marked og signaler": _matching_panel_labels("top picks", "long engine", "long", "alpha", "aktor", "aktør", "oljefond", "nbim", "finansavisen", "bjellesau", "beslut", "muligheter", "ipo", "varsler", "intelligence", "heatmaps", "regime", "makro", "nyheter", "marked", "marked/rangering", "watchlist"),
            "Testing og portefølje": _matching_panel_labels("testing", "auto test lab", "fond / etf", "portef", "paper"),
            "System": _matching_panel_labels("services", "system/admin"),
        }
        group_map["Marked og signaler"] = list(dict.fromkeys(
            group_map["Marked og signaler"] + _matching_panel_labels("finansavisen", "bjellesauer")
        ))

        known_labels = {label for labels_in_group in group_map.values() for label in labels_in_group}
        extra_labels = [label for label, _renderer in panels if label not in known_labels]
        if extra_labels and not _autonomy_centered_v1900():
            group_map["Andre paneler"] = extra_labels

        forced_nav_v18663 = str(st.session_state.pop("ai_control_center_force_nav_v18663", "") or "").strip().lower()
        if forced_nav_v18663 == "dashboard":
            for key in [
                "ai_control_center_group_v1863aj",
                "ai_control_center_active_panel_v1863aj",
                "ai_control_center_active_real_panel_v18598",
                "ai_control_center_group_radio_v1863aj",
                "analysis_pipeline_active_stage_v1863bz",
            ]:
                st.session_state.pop(key, None)
            for key in list(st.session_state.keys()):
                if str(key).startswith("ai_control_center_panel_radio_v1863aj_"):
                    st.session_state.pop(key, None)
            st.markdown(
                "<div class='ptw-control-note-strong'>Dashboard er aktivt. Velg en menyknapp eller et hovedområde for å åpne et panel.</div>",
                unsafe_allow_html=True,
            )
            return None
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
                  <div class="ptw-control-eyebrow">AI workspace</div>
                  <div class="ptw-control-title">🧠 AI Kontrollsenter</div>
                  <div class="ptw-control-caption">Velg én arbeidsflate. Bare valgt panel kjøres, slik at dashboardet holder seg raskt og ryddig.</div>
                </div>
                <div class="ptw-control-active-chip">Aktivt panel: {html.escape(str(previous_label or first_real_panel or "-"))}</div>
              </div>
              <div class="ptw-status-line" style="margin-top:.55rem;">
                <span class="ptw-pill ptw-pill-ai">🟢 AI workspace</span>
                <span class="ptw-pill">Kun valgt panel kjøres</span>
              </div>
            </div>
            <div class="ptw-control-selector-shell">
              <div class="ptw-control-selector-title">Velg oppgave</div>
            """,
            unsafe_allow_html=True,
        )

        # RC14: button actions below must not mutate the already-instantiated
        # group selectbox key. Consume the application-owned request before the
        # widget is created, then let the widget own its key for the full run.
        pending_simple_group_v19220_rc14 = str(
            st.session_state.pop("ai_control_center_group_pending_v19220_rc14", "") or ""
        ).strip()
        if pending_simple_group_v19220_rc14 in group_map:
            st.session_state["ai_control_center_group_v1863m"] = pending_simple_group_v19220_rc14

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
            "📈 Kandidater": "Marked og signaler",
            "🧠 Analyse": "Analyse og prognose",
            "🌍 Marked": "Marked og signaler",
            "💼 Portefølje": "Testing og portefølje",
            "⚙️ System": "System",
        }
        mode_options = list(mode_map.keys())
        current_mode = st.session_state.get("ai_control_center_work_mode_v1863ag") or mode_options[0]
        st.markdown("<div class='ptw-control-mini-title'>Arbeidsmodus</div>", unsafe_allow_html=True)
        mode_cols = st.columns(len(mode_options))
        for idx, mode in enumerate(mode_options):
            with mode_cols[idx]:
                if st.button(mode, key=f"ai_cc_mode_v1863ag_{idx}", type="primary" if mode == current_mode else "secondary", width="stretch"):
                    st.session_state["ai_control_center_work_mode_v1863ag"] = mode
                    st.session_state["ai_control_center_group_pending_v19220_rc14"] = mode_map[mode]
                    st.session_state["ai_control_center_menu_open_v1863ag"] = True
                    st.rerun()

        st.markdown("<div class='ptw-control-mini-title'>Hovedområder</div>", unsafe_allow_html=True)
        group_cols = st.columns(len(groups))
        for idx, group_name in enumerate(groups):
            labels = [label for label in group_map.get(group_name, []) if label in panel_map]
            active = group_name == active_group
            prefix = "🔴" if active else "🔵"
            with group_cols[idx]:
                if st.button(f"{prefix} {group_name} · {len(labels)}", key=f"ai_cc_group_v1863ag_{idx}", type="primary" if active else "secondary", width="stretch"):
                    st.session_state["ai_control_center_group_pending_v19220_rc14"] = group_name
                    st.session_state["ai_control_center_menu_open_v1863ag"] = True
                    st.rerun()

        favorite_needles = ["top picks", "long engine", "paper trading", "paper-portef", "regime", "valutavarsler"]
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
                    if st.button(label, key=f"ai_cc_fav_v1863ag_{idx}", type="primary" if label == active_label else "secondary", width="stretch"):
                        st.session_state["ai_control_center_active_panel_v1863m"] = label
                        st.session_state["ai_control_center_active_real_panel_v18598"] = label
                        st.session_state["ai_control_center_menu_open_v1863ag"] = False
                        for g_name, g_labels in group_map.items():
                            if label in g_labels:
                                st.session_state["ai_control_center_group_pending_v19220_rc14"] = g_name
                                break
                        st.rerun()

        recent = [x for x in st.session_state.get("ai_control_center_recent_panels_v1863ag", []) if x in panel_map]
        if recent:
            st.markdown("<div class='ptw-control-mini-title'>Sist brukt</div>", unsafe_allow_html=True)
            recent_cols = st.columns(min(len(recent), 4))
            for idx, label in enumerate(recent[:4]):
                with recent_cols[idx]:
                    if st.button(label, key=f"ai_cc_recent_v1863ag_{idx}", type="primary" if label == active_label else "secondary", width="stretch"):
                        st.session_state["ai_control_center_active_panel_v1863m"] = label
                        st.session_state["ai_control_center_active_real_panel_v18598"] = label
                        st.session_state["ai_control_center_menu_open_v1863ag"] = False
                        for g_name, g_labels in group_map.items():
                            if label in g_labels:
                                st.session_state["ai_control_center_group_pending_v19220_rc14"] = g_name
                                break
                        st.rerun()

        search_query = st.text_input("Søk i funksjoner", value="", key="ai_control_center_search_v1863ag", placeholder="Skriv f.eks. paper, valuta, regime, heatmap")
        quick_panel_options = [label for label in group_map.get(active_group, []) if label in panel_map]
        if search_query.strip():
            q = search_query.strip().lower()
            quick_panel_options = [label for label, _renderer in panels if q in str(label).lower()]
            menu_open = True
            submenu_title = f"Søkeresultat: {len(quick_panel_options)} treff"
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
                        if st.button(label, key=f"ai_cc_panel_v1863ag_{start}_{idx}", type="primary" if label == active_label else "secondary", width="stretch"):
                            st.session_state["ai_control_center_active_panel_v1863m"] = label
                            st.session_state["ai_control_center_active_real_panel_v18598"] = label
                            st.session_state["ai_control_center_menu_open_v1863ag"] = False
                            recent_next = [label] + [x for x in recent if x != label]
                            st.session_state["ai_control_center_recent_panels_v1863ag"] = recent_next[:4]
                            for g_name, g_labels in group_map.items():
                                if label in g_labels:
                                    st.session_state["ai_control_center_group_pending_v19220_rc14"] = g_name
                                    break
                            st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        elif not menu_open:
            if st.button("Åpne undermeny", key="ai_cc_open_submenu_v1863ag", width="stretch"):
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
            "Marked og signaler": _matching_panel_labels("dataunderlag", "datakilder", "datagrunnlag", "analyseflyt", "test 1", "top picks", "long engine", "long", "long engine", "long", "alpha", "aktor", "aktør", "oljefond", "nbim", "finansavisen", "bjellesau", "beslut", "muligheter", "ipo", "varsler", "intelligence", "heatmaps", "regime", "makro", "nyheter", "marked", "marked/rangering", "watchlist", "valutavarsler"),
            "Testing og portefolje": _matching_panel_labels("testing", "auto test lab", "fond / etf", "portef", "paper"),
            "System": _matching_panel_labels("services", "system/admin"),
        }
        group_map["Marked og signaler"] = list(dict.fromkeys(
            group_map["Marked og signaler"] + _matching_panel_labels("finansavisen", "bjellesauer")
        ))
        known_labels = {label for labels_in_group in group_map.values() for label in labels_in_group}
        extra_labels = [label for label, _renderer in panels if label not in known_labels]
        if extra_labels and not _autonomy_centered_v1900():
            group_map["Andre paneler"] = extra_labels

        forced_nav_v18663 = str(st.session_state.pop("ai_control_center_force_nav_v18663", "") or "").strip().lower()
        if forced_nav_v18663 == "dashboard":
            for key in [
                "ai_control_center_group_v1863aj",
                "ai_control_center_active_panel_v1863aj",
                "ai_control_center_active_real_panel_v18598",
                "ai_control_center_group_radio_v1863aj",
                "analysis_pipeline_active_stage_v1863bz",
            ]:
                st.session_state.pop(key, None)
            for key in list(st.session_state.keys()):
                if str(key).startswith("ai_control_center_panel_radio_v1863aj_"):
                    st.session_state.pop(key, None)
            st.markdown(
                "<div class='ptw-control-note-strong'>Dashboard er aktivt. Velg en menyknapp eller et hovedområde for å åpne et panel.</div>",
                unsafe_allow_html=True,
            )
            return None

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
        if st.button("Til hovedvalg / vis alle bokser", key="ai_cc_home_v1863ah", width="stretch"):
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
                    if st.button(mode, key=f"ai_cc_mode_v1863ah_{idx}", type="primary" if mode == current_mode else "secondary", width="stretch"):
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
                    if st.button(f"{'ROD' if is_active else 'BLA'} {group_name} - {len(labels)}", key=f"ai_cc_group_v1863ah_{idx}", type="primary" if is_active else "secondary", width="stretch"):
                        st.session_state["ai_control_center_group_v1863ah"] = group_name
                        st.session_state["ai_control_center_show_home_v1863ah"] = True
                        st.session_state["ai_control_center_submenu_open_v1863ah"] = True
                        st.rerun()

            favorite_needles = ["top picks", "long engine", "paper trading", "paper-portef", "regime", "valutavarsler"]
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
                        if st.button(label, key=f"ai_cc_fav_v1863ah_{idx}", type="primary" if label == active_label else "secondary", width="stretch"):
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
                        if st.button(label, key=f"ai_cc_recent_v1863ah_{idx}", type="primary" if label == active_label else "secondary", width="stretch"):
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
                            if st.button(label, key=f"ai_cc_panel_v1863ah_{start}_{idx}", type="primary" if label == active_label else "secondary", width="stretch"):
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
            "Marked og signaler": _matching_panel_labels("top picks", "long engine", "long", "alpha", "aktor", "aktør", "oljefond", "nbim", "finansavisen", "bjellesau", "beslut", "muligheter", "ipo", "varsler", "intelligence", "heatmaps", "regime", "makro", "nyheter", "marked", "marked/rangering", "watchlist", "valutavarsler"),
            "Testing og portefolje": _matching_panel_labels("testing", "auto test lab", "fond / etf", "portef", "paper"),
            "System": _matching_panel_labels("services", "system/admin"),
        }
        group_map["Marked og signaler"] = list(dict.fromkeys(
            group_map["Marked og signaler"] + _matching_panel_labels("finansavisen", "bjellesauer")
        ))
        known_labels = {label for labels_in_group in group_map.values() for label in labels_in_group}
        extra_labels = [label for label, _renderer in panels if label not in known_labels]
        if extra_labels and not _autonomy_centered_v1900():
            group_map["Andre paneler"] = extra_labels

        forced_nav_v18663 = str(st.session_state.pop("ai_control_center_force_nav_v18663", "") or "").strip().lower()
        if forced_nav_v18663 == "dashboard":
            for key in [
                "ai_control_center_group_v1863aj",
                "ai_control_center_active_panel_v1863aj",
                "ai_control_center_active_real_panel_v18598",
                "ai_control_center_group_radio_v1863aj",
                "analysis_pipeline_active_stage_v1863bz",
            ]:
                st.session_state.pop(key, None)
            for key in list(st.session_state.keys()):
                if str(key).startswith("ai_control_center_panel_radio_v1863aj_"):
                    st.session_state.pop(key, None)
            st.markdown(
                "<div class='ptw-control-note-strong'>Dashboard er aktivt. Velg en menyknapp eller et hovedområde for å åpne et panel.</div>",
                unsafe_allow_html=True,
            )
            return None

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
            if st.button("Til hovedvalg", key="ai_cc_home_v1863ai", width="stretch"):
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
                if st.button(label_text, key=f"ai_cc_group_v1863ai_{idx}", type="primary" if is_active else "secondary", width="stretch"):
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
                        if st.button(label, key=f"ai_cc_panel_v1863ai_{start}_{idx}", width="stretch"):
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
            if st.button(button_label, key=f"analysis_pipeline_shortcut_{stage_id}_v1863bz", width="stretch", type="primary" if active_stage == stage_id else "secondary"):
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
        "market_ranking": ("marked",),
        "smart_ai": ("analyseunivers",),
        "top_picks": ("top picks", "marked"),
        "early_warning": ("alpha", "early warning", "marked", "finansavisen", "bjellesau"),
        "alpha_radar": ("alpha", "aktor", "aktør", "oljefond", "nbim", "finansavisen", "bjellesau"),
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
    """Stable card-styled control center navigation for Dashboard 2026."""
    st.markdown("<div class='ptw-ai-control-anchor'></div>", unsafe_allow_html=True)
    with st.container():
        base_panels: list[Tuple[str, Callable[[], None]]] = [
            ("Analyseunivers", lambda: render_ai_analysis_universe_workspace(expanded=True)),
            ("Prognose", _render_forecast_workspace_tab),
            ("Daily Report", render_daily_ai_market_report),
            ("Testing & Learning", lambda: (
                st.info("Strategi-test, Strategi-test Pro, prognose-vs-faktisk, scoreforklaring og backtest-laering er samlet her."),
                render_strategy_testing_workspace(),
                render_backtest_learning_panel(),
            )),
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
            "kilder",
            "import",
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
            "markedsklima",
        )
        ai_candidate_labels = list(dict.fromkeys(ai_candidate_primary_labels + ai_candidate_source_labels))
        group_map = {
            ai_candidate_group_name: ai_candidate_labels,
            "Long Engine": _matching_panel_labels("long engine"),
            "Autonomi": _matching_panel_labels("autonomi"),
            "Analyse og prognose": _matching_panel_labels("analyseunivers", "prognose", "daily report", "interaktiv analyse"),
            "Marked og signaler": _matching_panel_labels("marked", "varsler og watchlist", "valutavarsler", "top picks", "beslut", "muligheter", "alpha"),
            "Testing og portefolje": _matching_panel_labels("testing", "auto test lab", "fond / etf", "portef", "paper"),
            "System": _matching_panel_labels("system/admin"),
        }
        known_labels = {label for labels_in_group in group_map.values() for label in labels_in_group}
        extra_labels = [label for label, _renderer in panels if label not in known_labels]
        if extra_labels and not _autonomy_centered_v1900():
            group_map["Andre paneler"] = extra_labels

        forced_nav_v18663 = str(st.session_state.pop("ai_control_center_force_nav_v18663", "") or "").strip().lower()
        if forced_nav_v18663 == "dashboard":
            for key in [
                "ai_control_center_group_v1863aj",
                "ai_control_center_active_panel_v1863aj",
                "ai_control_center_active_real_panel_v18598",
                "ai_control_center_group_radio_v1863aj",
                "analysis_pipeline_active_stage_v1863bz",
            ]:
                st.session_state.pop(key, None)
            for key in list(st.session_state.keys()):
                if str(key).startswith("ai_control_center_panel_radio_v1863aj_"):
                    st.session_state.pop(key, None)
            st.markdown(
                "<div class='ptw-control-note-strong'>Dashboard er aktivt. Velg en menyknapp eller et hovedområde for å åpne et panel.</div>",
                unsafe_allow_html=True,
            )
            return None

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

        active_stage_hint = ""
        stage_relevant_labels: list[str] = []
        stage_group_name = ""
        group_options = [f"{name} ({len([x for x in labels if x in panel_map])})" for name, labels in group_map.items()]
        group_by_option = {}
        for name, labels in group_map.items():
            group_by_option[f"{name} ({len([x for x in labels if x in panel_map])})"] = name

        # RC6: action-triggered reruns must preserve the panel that initiated
        # the action before stale radio values are allowed to synchronize.
        consume_control_center_route_lock_v19220_rc6(
            st.session_state, group_map, panel_map, group_by_option
        )

        # v18.6.74c: Browser refresh/deep-link restore. On a fresh
        # Streamlit session the URL may carry aa_group/aa_panel from the last
        # click. Apply it once after group_map/panel_map exist, before radio
        # widgets render, and preserve remember_token.
        if not st.session_state.get("ai_cc_url_bootstrap_done_v18674c"):
            st.session_state["ai_cc_url_bootstrap_done_v18674c"] = True
            url_state_v18674c = get_global_navigation_state(st)
            url_group = str(url_state_v18674c.get("group") or "").strip()
            url_panel = str(url_state_v18674c.get("panel") or "").strip()
            if url_panel and url_panel in panel_map and (not url_group or url_group not in group_map):
                url_group = next((g for g, labels in group_map.items() if url_panel in labels), url_group)
            if url_group in group_map:
                valid_panels = [label for label in group_map.get(url_group, []) if label in panel_map]
                if not url_panel and len(valid_panels) == 1:
                    url_panel = valid_panels[0]
                st.session_state["ai_control_center_group_v1863aj"] = url_group
                group_option = next((opt for opt, name in group_by_option.items() if name == url_group), "")
                if group_option:
                    st.session_state["ai_control_center_group_radio_v1863aj"] = group_option
                if url_panel in valid_panels:
                    st.session_state["ai_control_center_active_panel_v1863aj"] = url_panel
                    st.session_state["ai_control_center_active_real_panel_v18598"] = url_panel
                    st.session_state[f"ai_control_center_panel_radio_v1863aj_{url_group}"] = url_panel

        if pending_nav_sync:
            pending_group = pending_nav_sync.get("group", "")
            pending_panel = pending_nav_sync.get("panel", "")
            group_option = next((opt for opt, name in group_by_option.items() if name == pending_group), "")
            if group_option:
                st.session_state["ai_control_center_group_radio_v1863aj"] = group_option
            if pending_group and pending_panel:
                st.session_state[f"ai_control_center_panel_radio_v1863aj_{pending_group}"] = pending_panel

        group_radio_key = "ai_control_center_group_radio_v1863aj"
        current_group = st.session_state.get("ai_control_center_group_v1863aj", "")
        if current_group and current_group not in group_map:
            current_group = ""
            st.session_state["ai_control_center_group_v1863aj"] = ""
            st.session_state["ai_control_center_active_panel_v1863aj"] = ""

        # v18.6.74a: Streamlit reruns after a radio click with the radio value
        # already stored, but the previous implementation rendered the top chip
        # before syncing that value into the active panel state. This caused
        # stale messages like "Aktivt panel: Paper Trading og kontroll" while
        # the user was actually inside Andre paneler -> AI Discovery.
        preselected_group_option = st.session_state.get(group_radio_key)
        preselected_group = group_by_option.get(preselected_group_option or "", "")
        if preselected_group and preselected_group != current_group:
            previous_active_label = st.session_state.get("ai_control_center_active_panel_v1863aj") or ""
            direct_panels = [label for label in group_map.get(preselected_group, []) if label in panel_map]
            st.session_state["ai_control_center_group_v1863aj"] = preselected_group
            if previous_active_label in direct_panels:
                st.session_state["ai_control_center_active_panel_v1863aj"] = previous_active_label
            elif len(direct_panels) == 1:
                st.session_state["ai_control_center_active_panel_v1863aj"] = direct_panels[0]
            elif preselected_group == ai_candidate_group_name and ai_candidate_primary_label in direct_panels:
                st.session_state["ai_control_center_active_panel_v1863aj"] = ai_candidate_primary_label
            else:
                st.session_state["ai_control_center_active_panel_v1863aj"] = ""
            current_group = preselected_group

        active_for_group = st.session_state.get("ai_control_center_active_panel_v1863aj") or ""
        if current_group and active_for_group and active_for_group not in [label for label in group_map.get(current_group, []) if label in panel_map]:
            direct_panels = [label for label in group_map.get(current_group, []) if label in panel_map]
            st.session_state["ai_control_center_active_panel_v1863aj"] = direct_panels[0] if len(direct_panels) == 1 else ""

        current_group_option = next((opt for opt, name in group_by_option.items() if name == current_group), None)
        if st.session_state.get(group_radio_key) not in group_options:
            st.session_state.pop(group_radio_key, None)

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
                  <div class="ptw-control-caption">Velg hovedområde for å åpne relevant arbeidsflate.</div>
                  <div class="ptw-control-caption">AI Kandidattest er hovedarbeidsflaten; datakilder, eierimport og radarer ligger samlet under samme valg.</div>
                </div>
                <div class="ptw-control-active-chip">Aktivt hovedområde: {html.escape(str(st.session_state.get("ai_control_center_group_v1863aj") or "Lukket"))}<br>Aktivt panel: {html.escape(str(st.session_state.get("ai_control_center_active_panel_v1863aj") or "Lukket"))}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="ptw-control-selector-shell">
              <div class="ptw-control-selector-title">Hovedvalg</div>
            """,
            unsafe_allow_html=True,
        )

        group_radio_kwargs = {
            "horizontal": True,
            "key": group_radio_key,
        }
        # v19.16.0: A widget key that already exists in Session State must not
        # also receive an explicit default/index. This removes Streamlit's
        # duplicate-value warning while preserving deep-link restoration.
        if group_radio_key not in st.session_state:
            group_radio_kwargs["index"] = (
                group_options.index(current_group_option)
                if current_group_option in group_options else None
            )
        selected_group_option = st.radio(
            "Velg hovedområde",
            group_options,
            **group_radio_kwargs,
        )
        selected_group = group_by_option.get(selected_group_option or "", "")
        if selected_group != current_group:
            previous_active_label = st.session_state.get("ai_control_center_active_panel_v1863aj") or ""
            st.session_state["ai_control_center_group_v1863aj"] = selected_group
            st.session_state["ai_control_center_active_panel_v1863aj"] = ""
            current_group = selected_group
            direct_panels = [label for label in group_map.get(selected_group, []) if label in panel_map]
            if previous_active_label in direct_panels:
                st.session_state["ai_control_center_active_panel_v1863aj"] = previous_active_label
            elif len(direct_panels) == 1:
                st.session_state["ai_control_center_active_panel_v1863aj"] = direct_panels[0]
            elif selected_group == ai_candidate_group_name and ai_candidate_primary_label in direct_panels:
                st.session_state["ai_control_center_active_panel_v1863aj"] = ai_candidate_primary_label
            route_panel_v19220_rc7 = st.session_state.get("ai_control_center_active_panel_v1863aj") or ""
            route_nav_v19220_rc7 = canonical_nav_for_panel_v19220_rc7(selected_group, route_panel_v19220_rc7)
            st.session_state["active_nav_target_v18674c"] = route_nav_v19220_rc7
            set_global_navigation_state(
                st,
                nav=route_nav_v19220_rc7,
                group=selected_group,
                panel=route_panel_v19220_rc7,
            )

        active_label = st.session_state.get("ai_control_center_active_panel_v1863aj") or ""
        if selected_group:
            direct_panels = [label for label in group_map.get(selected_group, []) if label in panel_map]
            if len(direct_panels) == 1:
                st.session_state["ai_control_center_active_panel_v1863aj"] = direct_panels[0]
                active_label = direct_panels[0]
            elif selected_group == ai_candidate_group_name and not active_label and ai_candidate_primary_label in direct_panels:
                st.session_state["ai_control_center_active_panel_v1863aj"] = ai_candidate_primary_label
                active_label = ai_candidate_primary_label
            panel_options = direct_panels
            current_panel_option = active_label if active_label in panel_options else None
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
                panel_radio_key = f"ai_control_center_panel_radio_v1863aj_{selected_group}"
                if st.session_state.get(panel_radio_key) not in panel_options:
                    st.session_state.pop(panel_radio_key, None)
                selected_panel = st.radio(
                    "Velg funksjon",
                    panel_options,
                    index=panel_options.index(current_panel_option) if current_panel_option in panel_options else None,
                    horizontal=True,
                    key=panel_radio_key,
                )
                st.markdown("</div>", unsafe_allow_html=True)
                if selected_panel:
                    st.session_state["ai_control_center_active_panel_v1863aj"] = selected_panel
                    active_label = st.session_state["ai_control_center_active_panel_v1863aj"]
                    route_nav_v19220_rc7 = canonical_nav_for_panel_v19220_rc7(selected_group, selected_panel)
                    st.session_state["active_nav_target_v18674c"] = route_nav_v19220_rc7
                    set_global_navigation_state(st, nav=route_nav_v19220_rc7, group=selected_group, panel=selected_panel)
                    if selected_panel != current_panel_option:
                        st.session_state["ai_control_center_active_real_panel_v18598"] = selected_panel

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
        def _close_control_center_panel_v18611() -> None:
            st.session_state["ai_control_center_active_panel_v1863aj"] = ""
            st.session_state["ai_control_center_group_v1863aj"] = ""
            st.session_state.pop("ai_control_center_group_radio_v1863aj", None)
            st.session_state.pop("analysis_pipeline_active_stage_v1863bz", None)
            for key in list(st.session_state.keys()):
                if str(key).startswith("ai_control_center_panel_radio_v1863aj_"):
                    st.session_state.pop(key, None)
            clear_global_navigation_state(st)

        close_col, spacer_col = st.columns([0.18, 0.82])
        with close_col:
            if st.button("Lukk oppgave", key="ai_cc_home_v1863aj"):
                _close_control_center_panel_v18611()
                st.rerun()
        active_group_label = st.session_state.get("ai_control_center_group_v1863aj") or next((g for g, labels in group_map.items() if active_label in labels), "")
        route_nav_v19220_rc7 = canonical_nav_for_panel_v19220_rc7(active_group_label, active_label)
        st.session_state["active_nav_target_v18674c"] = route_nav_v19220_rc7
        set_global_navigation_state(st, nav=route_nav_v19220_rc7, group=active_group_label, panel=active_label)
        st.markdown(
            f"<div class='ptw-control-note-strong'>Du jobber nå i: <b>{html.escape(str(active_group_label or '-'))}</b> → <b>{html.escape(str(active_label))}</b>.</div>",
            unsafe_allow_html=True,
        )
        _run_control_panel(active_label, renderer)
        return active_label
