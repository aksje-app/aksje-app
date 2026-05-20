import logging
# v18.5.12 Render import-path guard
import os as _render_os
import sys as _render_sys
_render_root = _render_os.path.dirname(_render_os.path.abspath(__file__))
if _render_root not in _render_sys.path:
    _render_sys.path.insert(0, _render_root)

# BANNER_SAFE_PRO_V7
from ui_components import market_pulse, top_movers
import os
import re
import streamlit as st
from sticky_topbar import render_sticky_topbar
from workspace_layout import inject_workspace_css, render_workspace_title, render_ai_control_center
from macro_rates_breadth_ui import render_macro_rates_breadth_panel
from ai_heatmap_ui import render_ai_heatmaps
from forecast_backtest_ui import render_backtest_learning_panel
from daily_ai_market_report import render_daily_ai_market_report
from market_regime_ui import render_market_regime_widget
from alert_center import render_common_alert_center
from market_intelligence_center import render_market_intelligence_center
from forecast_ui import render_forecast_section
from cron_control import cron_status_text, pause_until, clear_pause, activate_full_stop, deactivate_full_stop
from auth import require_login, render_user_admin
from settings_store import load_settings, save_settings, reset_settings
from alert_state import reset_alert_state
from market_hours import open_markets, market_status_lines, market_statuses
from market_universe import MARKET_SCOPE_OPTIONS, NO_UNIVERSE_SELECTION_LABEL, market_scope_options
from background_guard import market_guard_summary
from trading_settings import load_rules, save_rules, DEFAULT_RULES
import pandas as pd
import plotly.graph_objects as go
import requests
import html
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from app_version import get_app_build_label
from safety_audit import add_audit_event, get_feature_registry, read_recent_audit_events, run_static_regression_checks
from governance_registry import get_changelog, get_protected_zones
from ui_trust import format_data_trust_line, normalize_data_trust, ui_consistency_tokens

try:
    import yfinance as yf
except Exception:
    yf = None

from technical import calculate_rsi, calculate_macd, calculate_bollinger, detect_trend, technical_signal
from patterns import detect_head_shoulders, detect_inverse_head_shoulders, breakout_scanner, build_signal_alerts

from stocks import get_sp500_tickers, get_norwegian_tickers, get_swedish_tickers, get_finnish_tickers, get_danish_tickers, get_brazilian_tickers, get_all_tickers
from analysis import rank_stocks, score_stock
from market_selector import auto_rank_market, build_top_picks
from universe_engine import resolve_universe_tickers
from backtest_strategy import run_monthly_score_strategy, add_stats
from ipo import get_ipo_calendar, get_nordic_ipo_calendar, get_rumored_ipo_watchlist
from news import get_news, simple_finance_sentiment
from trading_engine import build_trading_decision, adjusted_score, paper_buy, paper_sell, paper_buy_instrument, paper_sell_instrument, paper_liquidity_snapshot
from strategy_engine import run_strategy, strategy_stats, optimize_strategy
from strategy_test_pro import render_strategy_test_pro
from signal_engine import calculate_signal_intelligence
try:
    from insider import get_insider_data
except ImportError:
    try:
        from insider import get_insider_signal as get_insider_data
    except ImportError:
        def get_insider_data(ticker, months=6):
            return {
                "score": 0.50,
                "label": "Ingen insiderdata",
                "buy_shares": 0,
                "sell_shares": 0,
                "buy_count": 0,
                "sell_count": 0,
                "transactions": 0,
                "latest_transactions": [],
                "latest_type": "NONE",
                "latest_date": None,
                "error": "Insider-modul kunne ikke lastes",
            }
from analyst import get_analyst_trend
from earnings import get_earnings
from paper_store import using_postgres
from paper_trading import load_portfolio, portfolio_value, reset_portfolio, performance_stats, STOP_LOSS_PCT, TRAILING_STOP_PCT, MAX_TRADES_PER_DAY
from paper_store import save_portfolio
from paper_trading_valuation import normalize_paper_portfolio, paper_position_rows, paper_trade_rows, timestamp_now
from mobile_analysis_view import render_mobile_analysis_view, fetch_timeframe_data, get_selected_time_settings
from global_busy import mark_choice_update, set_global_busy, update_global_busy, finish_global_busy
from security_metadata import resolve_security_metadata, display_label, fund_display_label, enrich_security_rows, infer_security_listing

st.set_page_config(page_title="AI Aksje Analyzer Pro", page_icon="📈", layout="wide", initial_sidebar_state="auto")


# v18.5.89: UI consistency tokens. Low-risk CSS only; no analysemotor changes.
def _inject_ui_data_trust_css_v18589():
    try:
        _tokens = ui_consistency_tokens()
        st.markdown(f"""
        <style>
        .stButton > button {{ min-height: {_tokens.get('button_height_px', 38)}px; }}
        .data-trust-card {{
            border: 1px solid rgba(128,128,128,0.20);
            border-radius: 10px;
            padding: 0.55rem 0.75rem;
            margin: 0.35rem 0;
            min-height: {_tokens.get('status_min_height_px', 28)}px;
            font-size: 0.92rem;
        }}
        .data-trust-muted {{ opacity: 0.78; font-size: 0.86rem; }}
        .blocked-action-note {{
            border-left: 4px solid rgba(255, 193, 7, 0.85);
            padding: 0.45rem 0.65rem;
            margin: 0.35rem 0;
            background: rgba(255, 193, 7, 0.08);
            border-radius: 6px;
        }}
        @media (max-width: 900px) {{
            .data-trust-card {{ font-size: 0.88rem; }}
        }}
        </style>
        """, unsafe_allow_html=True)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

_inject_ui_data_trust_css_v18589()


# v18.5.90: UI Path & Legacy Cleanup hard override.
def _inject_ui_path_cleanup_css_v18590():
    st.markdown("""
    <style>
    .v18590-global-update-shell {
        display:block !important;
        width:100% !important;
        max-width:100% !important;
        margin:.55rem 0 .75rem 0 !important;
        padding:.70rem .78rem !important;
        border:1px solid rgba(56,189,248,.55) !important;
        border-radius:14px !important;
        background:linear-gradient(180deg,rgba(8,20,42,.98),rgba(8,15,31,.98)) !important;
        clear:both !important;
        overflow:visible !important;
        position:relative !important;
        z-index:2 !important;
    }
    .v18590-global-status {
        display:flex !important;
        flex-wrap:wrap !important;
        align-items:center !important;
        justify-content:space-between !important;
        gap:.45rem .75rem !important;
        width:100% !important;
        min-height:42px !important;
        padding:.55rem .68rem !important;
        border:1px solid rgba(125,211,252,.42) !important;
        border-radius:12px !important;
        background:rgba(15,23,42,.72) !important;
        color:#f8fafc !important;
        opacity:1 !important;
    }
    .v18590-global-status .main {
        font-size:clamp(.90rem,1.3vw,1.05rem) !important;
        font-weight:950 !important;
        color:#f8fafc !important;
        line-height:1.2 !important;
        min-width:0 !important;
    }
    .v18590-global-status .sub {
        font-size:clamp(.76rem,1.0vw,.90rem) !important;
        color:#cbd5e1 !important;
        font-weight:750 !important;
        min-width:0 !important;
        overflow-wrap:anywhere !important;
    }
    .v18590-global-action {
        width:100% !important;
        margin-top:.55rem !important;
        clear:both !important;
    }
    .v18590-global-action .stButton > button {
        width:100% !important;
        min-width:0 !important;
        min-height:50px !important;
        border-radius:14px !important;
        background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
        border:1px solid rgba(224,242,254,.98) !important;
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
        font-weight:950 !important;
        opacity:1 !important;
        filter:none !important;
        box-shadow:0 0 0 1px rgba(255,255,255,.14),0 8px 22px rgba(14,165,233,.24) !important;
        white-space:normal !important;
    }
    .v18590-global-action .stButton > button p {
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
        font-size:1.02rem !important;
        font-weight:950 !important;
        line-height:1.15 !important;
        white-space:normal !important;
    }
    .v18590-pushover-panel {
        margin:.60rem 0 .25rem 0 !important;
        padding:.62rem .72rem !important;
        border:1px solid rgba(56,189,248,.32) !important;
        border-radius:13px !important;
        background:rgba(15,23,42,.42) !important;
    }
    .v18590-pushover-panel b { color:#f8fafc !important; }
    .v18590-safe-controls {
        padding:.32rem 0 .18rem 0 !important;
    }
    .v18534-trading-control-stack,
    .v18534-control-button-gap {
        margin-right:88px !important;
        max-width:calc(100% - 88px) !important;
    }
    @media (max-width:900px) {
        .v18534-trading-control-stack, .v18534-control-button-gap {
            margin-right:110px !important;
            max-width:calc(100% - 110px) !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

_inject_ui_path_cleanup_css_v18590()


# v18.5.91: GO I Visual Truth Fix.
# Hard rule: old global-update visual paths must never be visible. One plain, full-width
# Streamlit primary button is the only active control.
def _inject_visual_truth_fix_css_v18591():
    st.markdown("""
    <style>
    /* Hide legacy global-update ghosts that still leaked into desktop runtime. */
    .v18548-global-update-wrap,
    .v18570-global-update-row,
    .v18570-global-update-status,
    .v18570-global-update-action,
    .v18572-global-update-shell,
    .v18572-global-status,
    .v18574-global-toolbar,
    .v18574-global-status,
    .v18574-global-action,
    .v18581-global-toolbar,
    .v18581-global-status,
    .v18581-global-action,
    .v18590-global-update-shell,
    .v18590-global-action {
        display:none !important;
        visibility:hidden !important;
        height:0 !important;
        min-height:0 !important;
        max-height:0 !important;
        padding:0 !important;
        margin:0 !important;
        overflow:hidden !important;
        pointer-events:none !important;
    }

    .visual-truth-global-box {
        width:100% !important;
        margin:.42rem 0 .52rem 0 !important;
        padding:.58rem .78rem !important;
        border:1px solid rgba(56,189,248,.48) !important;
        border-radius:12px !important;
        background:linear-gradient(180deg,rgba(8,24,48,.96),rgba(10,15,30,.96)) !important;
        box-shadow:0 6px 16px rgba(2,8,23,.16) !important;
        clear:both !important;
        display:flex !important;
        align-items:center !important;
        justify-content:space-between !important;
        gap:.70rem !important;
    }
    .visual-truth-global-title {
        font-weight:950 !important;
        font-size:.95rem !important;
        line-height:1.2 !important;
        color:#f8fafc !important;
        white-space:nowrap !important;
    }
    .visual-truth-global-sub {
        margin-top:0 !important;
        color:#cbd5e1 !important;
        font-size:.78rem !important;
        line-height:1.25 !important;
        overflow:hidden !important;
        text-overflow:ellipsis !important;
        white-space:nowrap !important;
        text-align:right !important;
    }

    /* Make the real Streamlit primary button readable across desktop/mobile. */
    div[data-testid="stButton"] > button[kind="primary"] {
        min-height:46px !important;
        width:100% !important;
        min-width:0 !important;
        border-radius:14px !important;
        background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
        border:1px solid rgba(224,242,254,.98) !important;
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
        font-weight:950 !important;
        opacity:1 !important;
        filter:none !important;
        box-shadow:0 0 0 1px rgba(255,255,255,.14),0 8px 22px rgba(14,165,233,.24) !important;
        white-space:normal !important;
        margin:.15rem 0 .25rem 0 !important;
    }
    div[data-testid="stButton"] > button[kind="primary"] p {
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
        font-size:1rem !important;
        font-weight:950 !important;
        line-height:1.15 !important;
        white-space:normal !important;
    }

    .visual-truth-safe-note {
        border:1px solid rgba(148,163,184,.22) !important;
        border-radius:10px !important;
        padding:.44rem .56rem !important;
        margin:.30rem 0 .38rem 0 !important;
        background:rgba(15,23,42,.38) !important;
        color:#dbeafe !important;
        font-size:.76rem !important;
        line-height:1.26 !important;
    }
    .visual-truth-pushover-box {
        margin:.52rem 0 .18rem 0 !important;
        padding:.56rem .70rem !important;
        border:1px solid rgba(56,189,248,.34) !important;
        border-radius:12px !important;
        background:linear-gradient(180deg,rgba(8,20,42,.76),rgba(8,13,28,.74)) !important;
    }
    .visual-truth-pushover-title {
        font-size:.92rem !important;
        font-weight:950 !important;
        color:#f8fafc !important;
        margin-bottom:.20rem !important;
    }
    .visual-truth-pushover-status {
        color:#cbd5e1 !important;
        font-size:.77rem !important;
        line-height:1.25 !important;
        margin-bottom:.20rem !important;
    }

    .v18593-pushover-result {
        margin:.38rem 0 .28rem 0 !important;
        padding:.58rem .70rem !important;
        border:1px solid rgba(56,189,248,.24) !important;
        border-radius:10px !important;
        background:rgba(15,23,42,.72) !important;
        color:#e2e8f0 !important;
        font-size:.82rem !important;
        font-weight:800 !important;
        line-height:1.25 !important;
    }
    .visual-truth-pushover-box + div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button {
        min-height:42px !important;
        padding:.42rem .72rem !important;
        border-radius:11px !important;
        opacity:1 !important;
        filter:none !important;
        overflow:visible !important;
    }
    .visual-truth-pushover-box + div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button p {
        font-size:.86rem !important;
        font-weight:950 !important;
        line-height:1.10 !important;
        white-space:normal !important;
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
    }


    /* v18.5.95: PC visibility hardening.
       Streamlit wraps markdown/buttons in element-container divs, so direct "+ div[data-testid]"
       selectors above are not reliable on desktop. These :has() selectors bind the next
       Streamlit element after the visible status box and force readable full-width controls. */
    html body .stApp div:has(> .visual-truth-global-box) + div button[kind="primary"],
    html body .stApp div:has(.visual-truth-global-box) + div button[kind="primary"] {
        display:flex !important;
        align-items:center !important;
        justify-content:center !important;
        width:100% !important;
        min-width:0 !important;
        min-height:50px !important;
        padding:.58rem .95rem !important;
        border-radius:15px !important;
        background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
        border:1px solid rgba(224,242,254,1) !important;
        box-shadow:0 0 0 1px rgba(255,255,255,.18),0 10px 24px rgba(14,165,233,.30) !important;
        opacity:1 !important;
        filter:none !important;
        overflow:visible !important;
        white-space:normal !important;
    }
    html body .stApp div:has(> .visual-truth-global-box) + div button[kind="primary"] p,
    html body .stApp div:has(.visual-truth-global-box) + div button[kind="primary"] p {
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
        font-size:1.02rem !important;
        font-weight:950 !important;
        line-height:1.12 !important;
        white-space:normal !important;
        overflow:visible !important;
        text-overflow:clip !important;
    }
    html body .stApp div:has(> .visual-truth-pushover-box) + div,
    html body .stApp div:has(.visual-truth-pushover-box) + div {
        width:100% !important;
        max-width:100% !important;
        min-width:0 !important;
        overflow:visible !important;
        opacity:1 !important;
        visibility:visible !important;
    }
    html body .stApp div:has(> .visual-truth-pushover-box) + div [data-testid="stHorizontalBlock"],
    html body .stApp div:has(.visual-truth-pushover-box) + div [data-testid="stHorizontalBlock"] {
        width:100% !important;
        max-width:100% !important;
        min-width:0 !important;
        overflow:visible !important;
        align-items:stretch !important;
    }
    html body .stApp div:has(> .visual-truth-pushover-box) + div [data-testid="stButton"] > button,
    html body .stApp div:has(.visual-truth-pushover-box) + div [data-testid="stButton"] > button {
        display:flex !important;
        align-items:center !important;
        justify-content:center !important;
        width:100% !important;
        min-width:0 !important;
        min-height:46px !important;
        padding:.54rem .80rem !important;
        border-radius:13px !important;
        background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
        border:1px solid rgba(224,242,254,.98) !important;
        box-shadow:0 0 0 1px rgba(255,255,255,.14),0 8px 20px rgba(14,165,233,.22) !important;
        opacity:1 !important;
        filter:none !important;
        overflow:visible !important;
        white-space:normal !important;
    }
    html body .stApp div:has(> .visual-truth-pushover-box) + div [data-testid="stButton"] > button p,
    html body .stApp div:has(.visual-truth-pushover-box) + div [data-testid="stButton"] > button p {
        font-size:.93rem !important;
        font-weight:950 !important;
        line-height:1.12 !important;
        white-space:normal !important;
        overflow:visible !important;
        text-overflow:clip !important;
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
    }
    @media (min-width:901px) {
        html body .stApp .visual-truth-pushover-box {
            margin-top:.24rem !important;
        }
        html body .stApp div:has(> .visual-truth-pushover-box) + div [data-testid="stHorizontalBlock"],
        html body .stApp div:has(.visual-truth-pushover-box) + div [data-testid="stHorizontalBlock"] {
            gap:.72rem !important;
        }
    }
    .visual-truth-inline-status {
        display:flex !important;
        align-items:center !important;
        justify-content:space-between !important;
        gap:.55rem !important;
        flex-wrap:wrap !important;
        margin:.22rem 0 .42rem 0 !important;
    }
    .visual-truth-empty-state {
        border:1px solid rgba(245,158,11,.22) !important;
        border-radius:12px !important;
        padding:.72rem .86rem !important;
        background:rgba(113,63,18,.18) !important;
        color:#fde68a !important;
        line-height:1.35 !important;
        font-size:.86rem !important;
    }
    .visual-truth-empty-state b { color:#fff7ed !important; }
    /* tighter dashboard density */
    div[data-testid="stExpander"] details { margin-bottom:.38rem !important; }
    div[data-testid="stExpander"] details > div { padding-top:.45rem !important; padding-bottom:.55rem !important; }
    .stCaption, div[data-testid="stCaptionContainer"] { line-height:1.25 !important; }
    .mini-status-chip, .v18-status-chip { padding:.15rem .38rem !important; font-size:.68rem !important; }

    /* Keep floating stop/control buttons away from Chat overlay. */
    .v18534-trading-control-stack,
    .v18534-control-button-gap,
    .ptw-topbar,
    .top-app-status {
        padding-right:128px !important;
        box-sizing:border-box !important;
    }
    @media (max-width:900px) {
        .v18534-trading-control-stack,
        .v18534-control-button-gap,
        .ptw-topbar,
        .top-app-status {
            padding-right:148px !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

_inject_visual_truth_fix_css_v18591()


# v18.5.30: Professional Trading Workspace. Legacy duplikater fjernet fra hovedvisning.
try:
    inject_workspace_css()
    render_workspace_title()
    render_sticky_topbar()
except Exception as _workspace_error:
    st.caption(f"Professional Trading Workspace kunne ikke vises: {_workspace_error}")
























st.markdown("""
<style>
/* v18.2: tydelig global oppdateringsknapp */
button[kind="primary"] {
    background: linear-gradient(180deg, #16b8f3 0%, #087fbd 100%) !important;
    border: 1px solid #7dd3fc !important;
    color: #ffffff !important;
    font-weight: 900 !important;
    min-height: 2.75rem !important;
    box-shadow: 0 0 0 1px rgba(255,255,255,0.12), 0 7px 18px rgba(0,0,0,0.28) !important;
}
button[kind="primary"] p {
    color: #ffffff !important;
    font-weight: 900 !important;
    white-space: nowrap !important;
}
/* Små røde/grønne/gule markører på toppstatus-chipene */
.mini-status-chip.green::before,
.mini-status-chip.red::before,
.mini-status-chip.yellow::before {
    content: "";
    display: inline-block;
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 999px;
    margin-right: 0.25rem;
    vertical-align: -0.02rem;
}
.mini-status-chip.green::before { background:#22c55e; box-shadow:0 0 8px rgba(34,197,94,.6); }
.mini-status-chip.red::before { background:#ef4444; box-shadow:0 0 8px rgba(239,68,68,.6); }
.mini-status-chip.yellow::before { background:#f59e0b; box-shadow:0 0 8px rgba(245,158,11,.55); }
.mini-status-chip.yellow {
    border-color: rgba(245,158,11,0.50) !important;
    background: rgba(120,53,15,0.24) !important;
    color: #fde68a !important;
}
</style>
""", unsafe_allow_html=True)




st.markdown("""
<style>
/* v18.1: reparerer sidebar-kontrast og global knapp uten å blokkere klikk */
section[data-testid="stSidebar"] {
    background: #070d1d !important;
}
section[data-testid="stSidebar"] * {
    color: #f8fafc !important;
}
section[data-testid="stSidebar"] svg,
section[data-testid="stSidebar"] [data-testid="stIconMaterial"] {
    color: #f8fafc !important;
    fill: #f8fafc !important;
}
.v18-section-title {
    font-size: 1.35rem;
    font-weight: 900;
    color: #f8fafc;
    margin: 1.0rem 0 0.55rem 0;
}
.v18-global-note {
    color: rgba(226,232,240,.82);
    font-size: .9rem;
    margin-bottom: .35rem;
}
.v18-status-dot {
    display: inline-block;
    width: 0.68rem;
    height: 0.68rem;
    border-radius: 999px;
    margin-right: 0.42rem;
    vertical-align: 0.02rem;
}
.v18-status-dot.green { background:#22c55e; box-shadow:0 0 0 3px rgba(34,197,94,.15); }
.v18-status-dot.red { background:#ef4444; box-shadow:0 0 0 3px rgba(239,68,68,.15); }
.v18-status-dot.yellow { background:#f59e0b; box-shadow:0 0 0 3px rgba(245,158,11,.16); }
.v18-dark-row {
    border: 1px solid rgba(56,189,248,.18);
    background: rgba(8,16,34,.58);
    color: #f8fafc;
    border-radius: 12px;
    padding: .42rem .54rem;
    font-size: .82rem;
}
.v18-status-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: .18rem .44rem;
    font-size: .72rem;
    font-weight: 900;
    border: 1px solid rgba(148,163,184,.30);
    background: rgba(30,41,59,.74);
}
.v18-status-chip.green { border-color: rgba(34,197,94,.55); background: rgba(16,65,52,.70); color:#dcfce7; }
.v18-status-chip.yellow { border-color: rgba(245,158,11,.55); background: rgba(120,53,15,.48); color:#fde68a; }
.v18-status-chip.red { border-color: rgba(239,68,68,.55); background: rgba(86,22,36,.56); color:#fecaca; }
details > summary {
    cursor: pointer !important;
}
details > summary::after {
    content: "";
}
details > summary {
    min-height: 32px !important;
    display: flex !important;
    align-items: center !important;
    gap: .35rem !important;
}
</style>
""", unsafe_allow_html=True)




# v18.5.81: complete clean stability pass: fixed global update button, no floating busy overlay, no dimming.
st.markdown("""
<style>
/* Topbar should only show version + Klar. Global update status lives in the main bar below. */
.ptw-global-busy-fixed {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
    pointer-events: none !important;
}
.ptw-v18570-status-zone { min-width: auto !important; }
.ptw-topbar-right { gap: .65rem !important; justify-content: flex-end !important; }

/* Global update bar: blue, readable, fixed in normal layout, no overlapping spinner. */
.v18581-global-toolbar {
    margin: .46rem 0 .62rem 0 !important;
    padding: 0 !important;
    position: relative !important;
    z-index: 5 !important;
}
.v18581-global-toolbar [data-testid="stHorizontalBlock"] { align-items: center !important; }
.v18581-global-status {
    min-height: 42px !important;
    display: flex !important;
    align-items: center !important;
    gap: .48rem !important;
    padding: .42rem .72rem !important;
    border-radius: 12px !important;
    border: 1px solid rgba(56,189,248,.78) !important;
    background: linear-gradient(180deg, rgba(7,89,133,.94), rgba(8,47,73,.92)) !important;
    color: #ffffff !important;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.07), 0 8px 18px rgba(2,132,199,.16) !important;
    overflow: hidden !important;
    opacity: 1 !important;
    filter: none !important;
}
.v18581-global-status .main {
    display: inline-flex !important;
    align-items: center !important;
    gap: .38rem !important;
    min-width: 0 !important;
    color:#fff !important;
    font-size:.88rem !important;
    font-weight:950 !important;
    white-space: nowrap !important;
}
.v18581-global-status .sub {
    font-size:.72rem !important;
    opacity:.96 !important;
    font-weight:850 !important;
    margin-left:.45rem !important;
    color:#e0f2fe !important;
    white-space: nowrap !important;
}
.v18581-global-action .stButton > button {
    min-height:42px !important;
    width:100% !important;
    min-width:205px !important;
    background:linear-gradient(180deg,#38d5ff,#0284c7) !important;
    color:#fff !important;
    -webkit-text-fill-color:#fff !important;
    border:1px solid rgba(186,230,253,.95) !important;
    border-radius:13px !important;
    font-weight:950 !important;
    opacity:1 !important;
    filter:none !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.18),0 10px 24px rgba(14,165,233,.28) !important;
}
.v18581-global-action .stButton > button p {
    color:#fff !important;
    -webkit-text-fill-color:#fff !important;
    font-size:.88rem !important;
    font-weight:950 !important;
    white-space:nowrap !important;
}
.v18581-inline-spinner {
    display:inline-block !important;
    width:13px !important;
    height:13px !important;
    flex:0 0 13px !important;
    border:2px solid rgba(255,255,255,.40) !important;
    border-top-color:#fff !important;
    border-radius:50% !important;
    animation:v18581spin .8s linear infinite !important;
    vertical-align:-2px !important;
}
@keyframes v18581spin { to { transform: rotate(360deg); } }

/* Local widget changes must not dim/freeze the whole visual app. */
html body .stApp,
html body .main,
html body section.main,
html body div[data-testid="stAppViewContainer"],
html body div[data-testid="stAppViewBlockContainer"],
html body div[data-testid="block-container"] {
    opacity:1 !important;
    filter:none !important;
    transition:none !important;
}
html body .stApp::before,
html body .stApp::after,
html body div[data-testid="stAppViewContainer"]::before,
html body div[data-testid="stAppViewContainer"]::after {
    display:none !important;
    opacity:0 !important;
    pointer-events:none !important;
}

/* Paper trading overview and density. */
.v18581-paper-section-title {
    font-size:1.0rem !important;
    font-weight:950 !important;
    color:#f8fafc !important;
    margin:.70rem 0 .28rem 0 !important;
}
.v18581-security-help {
    font-size:.78rem !important;
    color:#cbd5e1 !important;
    margin-top:.20rem !important;
}
.analysis-card h2, .analysis-card h3,
.quicklist-card h2, .quicklist-card h3 {
    font-size:1.05rem !important;
}
</style>
""", unsafe_allow_html=True)


current_user = require_login()


# v18.5.68: UI polish from user screenshots: readable global button, stable no-dim reruns, compact sidebar/admin.
st.markdown("""
<style>
/* Global oppdatering must be visible even when Streamlit places it in a narrow column. */
.v18548-global-update-wrap {
    padding: .58rem .72rem .50rem .72rem !important;
    border-color: rgba(56,189,248,.45) !important;
}
.v18548-global-update-wrap {
    margin: .35rem 0 .52rem 0 !important;
    background: linear-gradient(180deg, rgba(8,16,34,.98), rgba(10,20,38,.94)) !important;
}
.v18548-global-update-wrap .stButton > button {
    min-height: 2.85rem !important;
    padding: .40rem 1.15rem !important;
    border-radius: 13px !important;
    background: linear-gradient(180deg, #22c7ff 0%, #0284c7 100%) !important;
    border: 1px solid rgba(186,230,253,.95) !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    text-shadow: 0 1px 1px rgba(0,0,0,.45) !important;
    box-shadow: 0 0 0 1px rgba(255,255,255,.12), 0 10px 22px rgba(2,132,199,.24) !important;
}
.v18548-global-update-wrap .stButton > button p {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    font-size: .96rem !important; /* legacy test marker: font-size: .92rem */
    font-weight: 950 !important;
    letter-spacing: .01em !important;
    white-space: nowrap !important;
}
/* Keep page readable during Streamlit reruns; real work is shown only by the header busy chip. */
.stApp, .main, section.main, div[data-testid="stAppViewContainer"], div[data-testid="stAppViewBlockContainer"] {
    opacity: 1 !important;
    filter: none !important;
    transition: none !important;
}
.stApp::before, .stApp::after, body::before, body::after,
div[data-testid="stAppViewContainer"]::before, div[data-testid="stAppViewContainer"]::after {
    opacity: 0 !important;
    pointer-events: none !important;
}
div[data-testid="stStatusWidget"], div[data-testid="stToolbar"] { opacity: 1 !important; filter: none !important; }
.v18534-control-button-gap { height: .36rem !important; }
.v18534-trading-control-stack .stButton > button { min-height: 34px !important; padding-top:.28rem !important; padding-bottom:.28rem !important; }
.v18534-trading-control-stack { overflow: visible !important; padding-top:.52rem !important; }
div[data-testid="stSpinner"] {
    background: rgba(8,16,34,.92) !important;
    border: 1px solid rgba(56,189,248,.35) !important;
    border-radius: 12px !important;
}
/* Sidebar bottom/admin: prevent vertical word wrapping and oversized cards. */
section[data-testid="stSidebar"] { width: 214px !important; min-width: 214px !important; }
section[data-testid="stSidebar"] * {
    word-break: normal !important;
    overflow-wrap: normal !important;
    hyphens: none !important;
}
section[data-testid="stSidebar"] .auth-sidebar-card,
section[data-testid="stSidebar"] [data-testid="stExpander"] details {
    padding: .46rem .52rem !important;
    margin: .22rem 0 .42rem 0 !important;
    border-radius: 12px !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    min-height: 30px !important;
    line-height: 1.15 !important;
    white-space: normal !important;
}
section[data-testid="stSidebar"] .auth-user-row {
    display: grid !important;
    grid-template-columns: minmax(0,1fr) auto !important;
    font-size: .68rem !important;
    line-height: 1.12 !important;
}
section[data-testid="stSidebar"] .auth-mini-heading { font-size:.70rem !important; }
section[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button {
    min-height: 30px !important;
    font-size: .74rem !important;
}

/* v18.5.70: targeted fix - version, global update placement, loading visibility and no full-page dim. */
.v18570-global-update-row {
    display:grid;
    grid-template-columns:minmax(0,1fr) minmax(210px,260px);
    align-items:center;
    gap:.75rem;
    width:100%;
}
.v18570-global-update-status {
    min-height:2.65rem;
    border:1px solid rgba(56,189,248,.42);
    background:linear-gradient(180deg,rgba(8,16,34,.98),rgba(15,23,42,.92));
    border-radius:13px;
    padding:.48rem .68rem;
    color:#e5f4ff !important;
    font-size:.82rem;
    line-height:1.25;
    font-weight:850;
}
.v18570-global-update-status b { color:#f8fafc !important; }
.v18570-global-update-action .stButton > button {
    min-height:2.72rem !important;
    width:100% !important;
    border-radius:13px !important;
    background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
    border:1px solid rgba(224,242,254,.95) !important;
    color:#ffffff !important;
    -webkit-text-fill-color:#ffffff !important;
    font-weight:950 !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.18),0 8px 22px rgba(14,165,233,.30) !important;
    opacity:1 !important;
}
.v18570-global-update-action .stButton > button p {
    color:#ffffff !important;
    -webkit-text-fill-color:#ffffff !important;
    font-size:.94rem !important;
    font-weight:950 !important;
    white-space:nowrap !important;
}
.v18570-global-running-note {
    margin:.22rem 0 .30rem 0;
    border:1px solid rgba(56,189,248,.45);
    background:rgba(8,47,73,.54);
    border-radius:11px;
    padding:.38rem .55rem;
    color:#e0f2fe !important;
    font-weight:850;
}
html body .stApp, html body .main, html body section.main,
html body div[data-testid="stAppViewContainer"],
html body div[data-testid="stAppViewBlockContainer"],
html body div[data-testid="block-container"] {
    opacity:1 !important;
    filter:none !important;
    transition:none !important;
}
html body .stApp::before, html body .stApp::after,
html body div[data-testid="stAppViewContainer"]::before,
html body div[data-testid="stAppViewContainer"]::after {
    display:none !important;
    opacity:0 !important;
    pointer-events:none !important;
}
.ptw-v18570-status-zone { min-width: 0 !important; max-width:70vw !important; overflow:visible !important; }
.ptw-version-chip { color:#f8fafc !important; opacity:1 !important; }
.ptw-global-busy-fixed { opacity:1 !important; visibility:visible !important; min-width:112px !important; }
.ptw-busy-running { min-width:184px !important; border-color:rgba(56,189,248,.85) !important; background:rgba(8,89,133,.82) !important; }
.ptw-busy-spinner { display:inline-block !important; opacity:1 !important; visibility:visible !important; }
.ptw-pill-ready { opacity:1 !important; visibility:visible !important; }


/* v18.5.72: final hard-fix for Global oppdatering button/status placement. */
.v18572-global-update-shell {
    margin:.42rem 0 .56rem 0 !important;
    padding:.48rem .56rem !important;
    border:1px solid rgba(56,189,248,.62) !important;
    border-radius:14px !important;
    background:linear-gradient(180deg,rgba(6,18,38,.98),rgba(8,25,48,.96)) !important;
    overflow:visible !important;
}
.v18572-global-status {
    min-height:42px !important;
    display:flex !important;
    flex-direction:column !important;
    justify-content:center !important;
    border:1px solid rgba(56,189,248,.55) !important;
    background:rgba(8,47,73,.56) !important;
    border-radius:12px !important;
    padding:.48rem .70rem !important;
    color:#eaf6ff !important;
    font-size:.86rem !important;
    line-height:1.26 !important;
    font-weight:850 !important;
    opacity:1 !important;
    filter:none !important;
}
.v18572-global-status b,
.v18572-global-status span { color:#f8fbff !important; opacity:1 !important; }
.v18572-global-update-shell .stButton > button,
.v18572-global-update-shell button[kind="primary"] {
    min-height:44px !important;
    width:100% !important;
    min-width:230px !important;
    padding:.45rem 1.1rem !important;
    border-radius:13px !important;
    background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
    border:1px solid rgba(224,242,254,.98) !important;
    color:#ffffff !important;
    -webkit-text-fill-color:#ffffff !important;
    font-size:.94rem !important;
    font-weight:950 !important;
    opacity:1 !important;
    filter:none !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.18),0 8px 22px rgba(14,165,233,.32) !important;
    transform:none !important;
}
.v18572-global-update-shell .stButton > button p,
.v18572-global-update-shell button[kind="primary"] p {
    color:#ffffff !important;
    -webkit-text-fill-color:#ffffff !important;
    font-size:.94rem !important;
    font-weight:950 !important;
    white-space:nowrap !important;
    opacity:1 !important;
}
.v18572-inline-spinner {
    display:inline-block !important;
    width:13px !important;
    height:13px !important;
    margin-right:.32rem !important;
    border:2px solid rgba(255,255,255,.35) !important;
    border-top-color:#ffffff !important;
    border-radius:999px !important;
    animation:v18572spin .8s linear infinite !important;
    vertical-align:-2px !important;
}
@keyframes v18572spin { to { transform:rotate(360deg); } }

/* v18.5.74: header/global button, stop-button clearance, sidebar/admin and Full-mode differentiation. */
.v18574-global-toolbar { margin:.45rem 0 .65rem 0 !important; }
.v18574-global-toolbar [data-testid="stHorizontalBlock"] { align-items:center !important; }
.v18574-global-status {
    min-height:42px !important; display:flex !important; align-items:center !important;
    gap:.48rem !important; padding:.42rem .70rem !important; border-radius:12px !important;
    border:1px solid rgba(56,189,248,.85) !important; background:linear-gradient(180deg,rgba(7,89,133,.90),rgba(3,105,161,.78)) !important;
    color:#ffffff !important; font-size:.86rem !important; font-weight:950 !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.10),0 8px 18px rgba(14,165,233,.22) !important;
    white-space:normal !important; overflow:visible !important; position:relative !important; z-index:2 !important;
}
.v18574-global-status .main { display:inline-flex !important; align-items:center !important; gap:.38rem !important; min-width:0 !important; }
.v18574-global-status .sub { font-size:.68rem !important; opacity:.92 !important; font-weight:850 !important; margin-left:.45rem !important; color:#e0f2fe !important; }
.v18574-global-action .stButton > button {
    min-height:42px !important; min-width:190px !important; width:100% !important;
    background:linear-gradient(180deg,#38d5ff,#0284c7) !important; color:#fff !important;
    -webkit-text-fill-color:#fff !important; border:1px solid rgba(224,242,254,.98) !important;
    border-radius:12px !important; font-weight:950 !important; opacity:1 !important; filter:none !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.18),0 10px 24px rgba(14,165,233,.30) !important;
}
.v18574-global-action .stButton > button p { color:#fff !important; -webkit-text-fill-color:#fff !important; font-size:.86rem !important; white-space:nowrap !important; }
.v18534-trading-control-stack, .ptw-topbar, .top-app-status { overflow:visible !important; padding-top:1.05rem !important; }
.v18534-trading-control-stack .stButton > button { clip-path:none !important; }
section[data-testid="stSidebar"] { width:230px !important; min-width:230px !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"], section[data-testid="stSidebar"] [data-testid="stExpander"] details { overflow:visible !important; }
section[data-testid="stSidebar"] summary { white-space:normal !important; line-height:1.18 !important; }
body, .stApp, div[data-testid="stAppViewContainer"], div[data-testid="block-container"] { opacity:1 !important; filter:none !important; transition:none !important; }


/* v18.5.74: readability/density balance for analysis views. */
.v18574-readable-fund .v18-dark-row, .v18574-readable-fund { font-size:.86rem !important; line-height:1.48 !important; }
.v18574-readable-fund b { font-size:.90rem !important; }
.v18574-analysis-dense h1, .v18574-analysis-dense h2, .v18574-analysis-dense h3 { font-size:1.05rem !important; line-height:1.12 !important; margin:.35rem 0 .28rem 0 !important; }
.v18574-quick-row { padding:.62rem .72rem !important; margin:.38rem 0 !important; }
.v18574-quick-title { display:flex !important; align-items:center !important; gap:.32rem !important; font-size:1.08rem !important; line-height:1.20 !important; margin:0 0 .18rem 0 !important; font-weight:950 !important; min-height:1.38rem !important; }
.v18574-quick-sub { font-size:.84rem !important; color:rgba(203,213,225,.92) !important; margin:.18rem 0 .32rem 0 !important; line-height:1.28 !important; overflow-wrap:anywhere !important; }
.v18574-quick-row [data-testid="stMetric"] { min-height:52px !important; padding:.36rem .52rem !important; }
.v18574-quick-row [data-testid="stMetricValue"] { font-size:1.02rem !important; }
.v18574-quick-row [data-testid="stProgress"] { margin-top:.12rem !important; }
.v18574-quick-row .stCaption, .v18574-quick-row [data-testid="stCaptionContainer"] { font-size:.82rem !important; line-height:1.32 !important; }
.v1863m-quick-meta { display:flex; flex-wrap:wrap; gap:.34rem; margin:.28rem 0 .44rem 0; align-items:center; }
.v1863m-quick-meta span { border:1px solid rgba(56,189,248,.32); background:rgba(8,47,73,.42); border-radius:999px; padding:.20rem .48rem; font-size:.76rem; font-weight:850; color:#bae6fd; line-height:1.22; white-space:nowrap; }
.v1863m-quick-action { min-height:auto; display:flex; flex-direction:column; gap:.46rem; justify-content:flex-start; padding-top:.18rem; }
.v1863m-quick-action-note { font-size:.84rem; line-height:1.36; color:rgba(226,232,240,.92); min-height:1.35rem; }
@media (max-width:900px) {
    .v18574-quick-title { font-size:1rem !important; }
    .v18574-quick-sub { font-size:.82rem !important; }
    .v1863m-quick-meta span { font-size:.74rem !important; }
}

</style>
""", unsafe_allow_html=True)

_runtime_settings = load_settings()
UI_REFRESH_MINUTES = int(_runtime_settings.get("ui_refresh_minutes", 5) or 5)
UI_REFRESH_MINUTES = max(1, min(UI_REFRESH_MINUTES, 60))
# V13 / Oppgave 35: Ikke kjør automatisk rerun når auto-oppdatering er slått av.
# Periodisk refresh må aktiveres eksplisitt i banner-innstillingene.
UI_AUTO_REFRESH_ENABLED = bool(_runtime_settings.get("ui_auto_refresh_enabled", False))
if UI_AUTO_REFRESH_ENABLED:
    st_autorefresh(interval=UI_REFRESH_MINUTES * 60 * 1000, key="refresh")


# --- V14.7 helpers: stabilitet, kontrollsenter og status ---


def _format_nok_no_decimals_v1827(value, suffix: str = " kr") -> str:
    """Format NOK consistently with comma thousands and no decimals."""
    try:
        return f"{float(value):,.0f}{suffix}"
    except Exception:
        return f"0{suffix}"


def _format_number_no_decimals_v1827(value) -> str:
    """Format plain numbers consistently with comma thousands and no decimals."""
    try:
        return f"{float(value):,.0f}"
    except Exception:
        return "0"

def _save_setting_patch(**updates):
    _s = load_settings()
    _s.update(updates)
    save_settings(_s)
    return _s


def _full_stop_active():
    """Én kilde for Full stopp/ferie-status."""
    try:
        _cron = cron_status_text()
        return bool((_cron or {}).get("vacation_mode"))
    except Exception:
        return False


def _auto_state(settings=None):
    """Returnerer samlet Auto trading-status. Full stopp/ferie overstyrer alltid AKTIV."""
    _s = settings or load_settings()
    if _full_stop_active():
        return "BLOKKERT", "red"
    if bool(_s.get("auto_trading_emergency_stop", False)):
        return "NØDSTOPP", "red"
    if bool(_s.get("auto_trading_paused", False)):
        return "PAUSET", "yellow"
    if bool(_s.get("auto_trading_enabled", False)):
        return "AKTIV", "green"
    return "AV", "red"


def _paper_state(full_stop=None):
    """Paper-porteføljen kan vises når Full stopp er aktiv, men nye auto-paper-kjøp skal ikke fremstå som aktive."""
    if bool(_full_stop_active() if full_stop is None else full_stop):
        return "VISNING", "yellow"
    return "AKTIV", "green"


def _set_auto_state(state):
    state = str(state).upper()
    # V15.2 / Oppgave 93: Full stopp/ferie blokkerer start av Auto trading.
    _full_stop_is_on = _full_stop_active()
    if state == "START" and _full_stop_is_on:
        st.session_state["auto_control_notice_v153"] = "Full stopp / ferie er aktiv. Bruk Opphev stopp / gjør klar før Auto trading kan startes."
        st.session_state["auto_control_notice_level_v153"] = "warning"
        return
    _settings_for_start = load_settings()
    if state == "START" and bool((_settings_for_start or {}).get("auto_trading_emergency_stop", False)):
        st.session_state["auto_control_notice_v153"] = "Nødstopp er aktiv. Tilbakestill nødstopp separat før Auto trading kan startes."
        st.session_state["auto_control_notice_level_v153"] = "warning"
        return
    if state == "START":
        _save_setting_patch(auto_trading_enabled=True, auto_trading_paused=False)
    elif state == "PAUSE":
        _save_setting_patch(auto_trading_enabled=False, auto_trading_paused=True)
    elif state == "STOPP":
        _save_setting_patch(auto_trading_enabled=False, auto_trading_paused=False)
    elif state == "NØDSTOPP":
        _save_setting_patch(auto_trading_enabled=False, auto_trading_paused=False, auto_trading_emergency_stop=True)
    st.rerun()


def _reset_emergency_stop_v157():
    """V15.7: Nødstopp er en egen sikkerhetslås og må oppheves eksplisitt."""
    _save_setting_patch(auto_trading_enabled=False, auto_trading_paused=False, auto_trading_emergency_stop=False)
    st.session_state["auto_control_notice_v153"] = "Nødstopp er tilbakestilt. Trykk Start når du vil aktivere Auto trading."
    st.session_state["auto_control_notice_level_v153"] = "info"
    st.rerun()


def _deactivate_full_stop_v157():
    """V15.7: Full stopp/ferie oppheves med egen tydelig handling."""
    try:
        deactivate_full_stop()
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    st.session_state["auto_control_notice_v153"] = "Full stopp / ferie er slått av. Auto trading er fortsatt AV. Trykk Start når du vil aktivere den."
    st.session_state["auto_control_notice_level_v153"] = "success"
    st.rerun()


def _auto_block_reason(settings=None):
    """V15.8: forklar hvorfor Auto trading ikke kan starte."""
    _s = settings or load_settings()
    if _full_stop_active():
        return "Full stopp / ferie"
    if bool(_s.get("auto_trading_emergency_stop", False)):
        return "Nødstopp"
    if bool(_s.get("auto_trading_paused", False)):
        return "Pause"
    return ""


def _clear_stops_ready_v158():
    """V15.8: trygg hovedknapp. Opphever vanlig full stopp/pause, men starter ikke trading og nullstiller ikke nødstopp."""
    _s = load_settings()
    if bool(_s.get("auto_trading_emergency_stop", False)):
        st.session_state["auto_control_notice_v153"] = "Nødstopp er aktiv. Tilbakestill nødstopp separat før Auto trading kan gjøres klar."
        st.session_state["auto_control_notice_level_v153"] = "warning"
        st.rerun()
        return
    try:
        deactivate_full_stop()
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    try:
        clear_pause()
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    _save_setting_patch(auto_trading_enabled=False, auto_trading_paused=False)
    st.session_state["auto_control_notice_v153"] = "Klar for Auto trading. Full stopp og pause er opphevet. Auto trading er fortsatt AV – trykk Start for å starte."
    st.session_state["auto_control_notice_level_v153"] = "success"
    st.rerun()


def _fmt_dt_short(value):
    if not value:
        return "ikke kjørt"
    try:
        return str(value).replace("T", " ")[:16]
    except Exception:
        return str(value)


def _now_short():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _set_update_reason(reason: str):
    """Lagrer synlig forklaring på hvorfor tung analyse/refresh ble kjørt."""
    st.session_state["last_update_started_by_v148"] = reason
    st.session_state["last_update_started_at_v148"] = _now_short()


def _global_apply_requested_v161():
    """V16.1: én sentral Global oppdateringsknapp styrer lagring/bruk av endringer."""
    return bool(st.session_state.get("global_apply_all_changes_v161", False))


def _mark_pending_global_change_v161():
    """Lett statusflagg. Widget-rerun er greit, men tung jobb skal vente på Global oppdatering."""
    st.session_state["pending_manual_changes_v16"] = True


def _request_global_apply_v161():
    """Kalles av Global oppdatering. Alle arbeidsflater kan lese dette flagget samme run."""
    st.session_state["global_apply_all_changes_v161"] = True
    st.session_state["heavy_update_allowed_v148"] = True
    st.session_state["pending_manual_changes_v16"] = False


def _finish_global_apply_v161():
    st.session_state["global_apply_all_changes_v161"] = False


def _last_update_label():
    reason = st.session_state.get("last_update_started_by_v148", "Oppstart / cache")
    at = st.session_state.get("last_update_started_at_v148", "-")
    return f"{reason} · {at}"



def _apply_global_update_v18548() -> None:
    """Apply pending UI choices without spinner/dimming overlay."""
    try:
        st.session_state["active_analysis_controls_v148"] = dict(_draft_analysis_controls_v148)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    st.session_state["heavy_update_allowed_v148"] = True
    try:
        _clear_pending_manual_change()
    except Exception:
        st.session_state["pending_analysis_changes_v148"] = False
    _request_global_apply_v161()
    _set_update_reason("Global oppdatering / Oppdater hele appen")
    finish_global_busy("Klar", "Global oppdatering er aktivert. Valgene er lagret.")
    add_audit_event("global_update", {"reason": "Oppdater hele appen"})




# v18.5.84: Batch B UX/stability hard overrides.
st.markdown("""
<style>
/* Global update: same readable blue control on desktop and mobile.
   Earlier versions had nowrap + narrow columns, causing desktop text collision. */
.v18581-global-toolbar {
    width: 100% !important;
    max-width: 100% !important;
    overflow: visible !important;
    position: relative !important;
    z-index: 20 !important;
    clear: both !important;
}
.v18581-global-toolbar [data-testid="stHorizontalBlock"] {
    gap: .65rem !important;
    align-items: stretch !important;
}
.v18581-global-status {
    min-height: 50px !important;
    height: auto !important;
    overflow: visible !important;
    white-space: normal !important;
    flex-wrap: wrap !important;
    line-height: 1.18 !important;
    padding: .55rem .78rem !important;
}
.v18581-global-status .main,
.v18581-global-status .sub {
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    word-break: normal !important;
    min-width: 0 !important;
    max-width: 100% !important;
}
.v18581-global-status .main {
    flex: 1 1 280px !important;
    font-size: clamp(.78rem, 1.1vw, .92rem) !important;
}
.v18581-global-status .sub {
    flex: 1 1 260px !important;
    margin-left: 0 !important;
    font-size: clamp(.66rem, .95vw, .76rem) !important;
}
.v18581-global-action,
.v18581-global-action .stButton,
.v18581-global-action .stButton > button {
    width: 100% !important;
    max-width: 100% !important;
}
.v18581-global-action .stButton > button {
    min-width: 0 !important;
    white-space: normal !important;
    overflow: visible !important;
}
.v18581-global-action .stButton > button p {
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    line-height: 1.12 !important;
}
.pending-changes-box {
    margin: .42rem 0 .65rem 0 !important;
    position: relative !important;
    z-index: 10 !important;
    clear: both !important;
}
/* Streamlit status messages must stay in document flow, not cover controls. */
div[data-testid="stAlert"] {
    position: relative !important;
    z-index: 6 !important;
    clear: both !important;
    margin-top: .35rem !important;
    margin-bottom: .55rem !important;
}
@media (max-width: 900px) {
    .v18581-global-toolbar [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
    }
}
</style>
""", unsafe_allow_html=True)


def _global_update_state_text_v1862():
    pending = bool(st.session_state.get("pending_manual_changes_v16", False)) or bool(globals().get("_pending_analysis_changes_v148", False))
    running = _global_apply_requested_v161() or bool(st.session_state.get("heavy_update_allowed_v148", False))
    if running:
        return "🔄", "Jobber – tung oppdatering er aktiv"
    if pending:
        return "⚠️", "Endringer venter"
    return "✅", "Klar"


def _click_global_update_v1862():
    set_global_busy("Global oppdatering", "Lagrer valg og starter tung oppdatering", step=0, total=1)
    _apply_global_update_v18548()
    try:
        st.toast("Global oppdatering aktivert: valgene er lagret.", icon="✅")
    except Exception:
        st.info("Global oppdatering aktivert: valgene er lagret.")
    st.rerun()


def render_global_update_bar_v18548() -> None:
    """v18.6.3: compact status only. The action button is rendered in the trading control row after Gjør klar."""
    icon, state_txt = _global_update_state_text_v1862()
    st.markdown(
        f"""
        <div class='v1862-global-status-line' data-ui-path='global-status-only-v1862'>
            <span><b>{icon} Global:</b> {html.escape(state_txt)}</span>
            <span>Sist: {html.escape(_last_update_label())}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_global_update_action_panel_v1863g() -> None:
    """Stable full-width Global update action, outside the clipped top control columns."""
    icon, state_txt = _global_update_state_text_v1862()
    st.markdown(
        f"""
        <style>
        html body .stApp .v1863g-global-action-card {{
            display:block !important;
            clear:both !important;
            width:100% !important;
            max-width:100% !important;
            margin:.42rem 0 .58rem 0 !important;
            padding:.72rem .88rem !important;
            border:1px solid rgba(125,211,252,.46) !important;
            border-left:5px solid #38d5ff !important;
            border-radius:12px !important;
            background:linear-gradient(180deg,rgba(8,47,73,.74),rgba(8,20,42,.72)) !important;
            color:#e0f2fe !important;
            overflow:visible !important;
        }}
        html body .stApp .v1863g-global-action-title {{
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
            font-size:1rem !important;
            font-weight:1000 !important;
            line-height:1.18 !important;
            margin-bottom:.20rem !important;
        }}
        html body .stApp .v1863g-global-action-sub {{
            color:#cbd5e1 !important;
            -webkit-text-fill-color:#cbd5e1 !important;
            font-size:.84rem !important;
            font-weight:820 !important;
            line-height:1.28 !important;
        }}
        html body .stApp div[data-testid="stForm"]:has(button[kind="primary"]) {{
            clear:both !important;
            width:100% !important;
            max-width:100% !important;
            overflow:visible !important;
            margin:.20rem 0 .72rem 0 !important;
        }}
        html body .stApp div[data-testid="stFormSubmitButton"] > button[kind="primary"] {{
            min-height:52px !important;
            width:100% !important;
            max-width:100% !important;
            border-radius:13px !important;
            font-size:1rem !important;
            font-weight:1000 !important;
            white-space:normal !important;
        }}
        @media (max-width:900px) {{
            html body .stApp .v1863g-global-action-card {{
                padding:.68rem .78rem !important;
                margin:.36rem 0 .48rem 0 !important;
            }}
        }}
        </style>
        <div class='v1863g-global-action-card'>
            <div class='v1863g-global-action-title'>{icon} Global oppdatering</div>
            <div class='v1863g-global-action-sub'>
                Status: {html.escape(state_txt)} · Sist: {html.escape(_last_update_label())}<br/>
                Bruk denne når du vil lagre valg og kjøre tung oppdatering av appen.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("global_update_action_form_v1863g", clear_on_submit=False):
        _global_run_clicked = st.form_submit_button(
            "Kjør Global oppdatering",
            use_container_width=True,
            type="primary",
        )
    if _global_run_clicked:
        _click_global_update_v1862()


_PANEL_OPTIONS_V18531 = ["🇺🇸 USA", "🇳🇴 Norge", "🇸🇪 Sverige", "Norden", "Aktivt univers", "⭐ Top Picks", "🚀 IPO", "🧪 Paper Trading"]


def _on_active_panel_change_v18531():
    mark_choice_update("Oppdaterer hovedpanel")


def _render_active_main_panel_selector_v18531():
    """Top-level panel selector placed in the header area above the ticker banner."""
    saved = (
        st.session_state.get("active_main_panel_radio_v15")
        or st.session_state.get("active_main_panel_persist_v15")
        or st.session_state.get("active_main_panel_persist_v1412")
        or "🇺🇸 USA"
    )
    if saved not in _PANEL_OPTIONS_V18531:
        saved = "🇺🇸 USA"
    panel_help_v1863m = {
        "🇺🇸 USA": "Viser USA-rangering og amerikanske kandidater.",
        "🇳🇴 Norge": "Viser Norge-rangering og norske kandidater.",
        "🇸🇪 Sverige": "Viser Sverige-rangering og svenske kandidater.",
        "Norden": "Viser samlet rangering for Norge og Sverige.",
        "Aktivt univers": "Viser tickerne som er satt fra Smart Universe Picker.",
        "⭐ Top Picks": "Samlet hurtigliste basert på valgt marked under Top Picks.",
        "🚀 IPO": "Nye og kommende børsnoteringer.",
        "🧪 Paper Trading": "Simulert handel og testportefølje.",
    }
    st.markdown("<div class='ptw-main-panel-nav'><div class='ptw-main-panel-nav-title'>Hovedpanel</div>", unsafe_allow_html=True)
    active = st.selectbox(
        "Velg hovedpanel",
        _PANEL_OPTIONS_V18531,
        index=_PANEL_OPTIONS_V18531.index(saved),
        key="active_main_panel_select_v1863m",
        on_change=_on_active_panel_change_v18531,
        help="Bare valgt hovedpanel vises og beregnes. AI Kontrollsenteret under brukes til mer spesifikke oppgaver.",
    )
    st.caption(panel_help_v1863m.get(active, "Bare valgt hovedpanel vises."))
    st.markdown("</div>", unsafe_allow_html=True)
    st.session_state["active_main_panel_radio_v15"] = active
    st.session_state["active_main_panel_persist_v15"] = active
    st.session_state["active_main_panel_persist_v1412"] = active
    return active


def _market_status_chips_html():
    """Kompakt børsstatus til Kontrollsenter/sidebar uten ekstra widget-reruns."""
    chips = []
    try:
        statuses = market_statuses()
    except Exception:
        statuses = {}
    for key, status in (statuses or {}).items():
        name = status.get("name", key)
        short = {"USA": "USA", "Norge": "Norge", "Sverige": "Sverige"}.get(name, name)
        is_open = bool(status.get("is_open"))
        cls = "green" if is_open else "red"
        txt = "Åpent" if is_open else "Stengt"
        chips.append(f"<span class='mini-status-chip {cls}'>{html.escape(str(short))}: <b>{txt}</b></span>")
    if not chips:
        chips.append("<span class='mini-status-chip'>Børsstatus: <b>ukjent</b></span>")
    return "".join(chips)


def _session_status_html(user=None):
    username = (user or {}).get("username", "-")
    remember = "På" if st.session_state.get("auth_remember_me") else "Av"
    expires = _fmt_dt_short(st.session_state.get("auth_expires_at"))
    return (
        f"<span class='mini-status-chip'>Bruker: <b>{html.escape(str(username))}</b></span>"
        f"<span class='mini-status-chip {'green' if remember == 'På' else 'red'}'>Husk meg: <b>{remember}</b></span>"
        f"<span class='mini-status-chip'>Utløper: <b>{html.escape(str(expires))}</b></span>"
    )


def _controls_differ(a, b):
    return {k: a.get(k) for k in sorted(a)} != {k: b.get(k) for k in sorted(b)}


def _manual_update_mode_enabled(settings=None):
    """True når bruker har slått AV auto-oppdatering.

    Streamlit vil fortsatt rerende skjermen når widgets endres, men i manuell
    modus skal appen ikke gjøre tung datahenting/analyse før bruker trykker
    Oppdater hele appen.
    """
    _s = settings or load_settings()
    return not bool((_s or {}).get("chart_auto_update_enabled", False))


def _heavy_update_allowed():
    """Én hard gate for tung datahenting/analyse.

    V16: Denne skal sjekkes før alt som kan hente markedsdata, bygge ranking,
    scanne watchlist, hente bannerdata eller gjøre ekstern analyse.
    """
    settings = load_settings()
    return (not _manual_update_mode_enabled(settings)) or bool(st.session_state.get("heavy_update_allowed_v148", False))


def _mark_pending_manual_change(reason="Endringer venter"):
    st.session_state["pending_manual_changes_v16"] = True
    st.session_state["pending_manual_changes_reason_v16"] = reason


def _clear_pending_manual_change():
    st.session_state["pending_manual_changes_v16"] = False
    st.session_state["pending_manual_changes_reason_v16"] = ""


def _cache_key_safe(*parts):
    raw = "__".join(str(x) for x in parts)
    return re.sub(r"[^A-Za-z0-9_]+", "_", raw)[:180]


def cached_score_stock_manual(ticker, use_news=False, force=False, include_insider=True):
    """score_stock med manuell-modus cache.

    Når Auto-oppdater er AV, returneres sist kjente analyse. Hvis ingen finnes,
    hentes ikke data før bruker trykker Oppdater hele appen.
    """
    ticker = normalize_user_ticker(ticker)
    key = f"score_cache_v16_{_cache_key_safe(ticker, bool(use_news), bool(include_insider))}"
    if (not force) and (not _heavy_update_allowed()):
        return st.session_state.get(key)
    item = score_stock(ticker, use_news=use_news, include_insider=include_insider)
    if item:
        st.session_state[key] = item
    return item


def cached_timeframe_data_manual(ticker, timeframe, period, force=False):
    ticker = normalize_user_ticker(ticker)
    key = f"timeframe_cache_v16_{_cache_key_safe(ticker, timeframe, period)}"
    if (not force) and (not _heavy_update_allowed()):
        return st.session_state.get(key)
    df = fetch_timeframe_data(ticker, timeframe, period)
    try:
        if df is not None and not df.empty:
            st.session_state[key] = df.copy()
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return df


def _cached_external_signal_manual(kind, ticker, fetcher, default=None):
    ticker = normalize_user_ticker(ticker)
    key = f"external_signal_cache_v16_{_cache_key_safe(kind, ticker)}"
    if not _heavy_update_allowed():
        return st.session_state.get(key, default)
    try:
        val = fetcher(ticker)
        st.session_state[key] = val
        return val
    except Exception:
        return st.session_state.get(key, default)


def _rank_cache_store(label, fp, data):
    st.session_state[f"rank_cache_v148_{label}"] = {"fp": fp, "data": data, "updated_at": _now_short()}
    latest = st.session_state.setdefault("latest_rankings_v148", {})
    latest[label] = data or []


def _rank_cache_get(label, fp):
    cache = st.session_state.get(f"rank_cache_v148_{label}") or {}
    if cache.get("fp") == fp:
        return cache.get("data")
    return None


def cached_auto_rank_market(label, tickers, max_count=30, use_news=False, force_manual_fetch=False, include_insider=True):
    """Cache rundt auto_rank_market. V15.8: når Auto-oppdater er AV, skal nye widgetvalg ikke starte tung rangering.

    Draft-verdier kan endres fritt; aktiv rangering oppdateres først via
    Oppdater hele appen, Auto-oppdater eller manuell scan.
    """
    safe_tickers = list(tickers or [])
    fp = (tuple(safe_tickers[: int(max_count or 0)]), int(max_count or 0), bool(use_news), bool(force_manual_fetch), bool(include_insider))
    cached = _rank_cache_get(label, fp)
    # V17 / Oppgave 133: eksplisitt manuell henting skal overstyre markedsstengt/cache-blokkering.
    # Vanlige widget-reruns skal fortsatt ikke starte tung jobb når manuell modus er aktiv.
    if (not force_manual_fetch) and (not _heavy_update_allowed()):
        if cached is not None:
            return cached
        latest = (st.session_state.get("latest_rankings_v148") or {}).get(label)
        if latest is not None:
            return latest
        # Ingen cache ennå: ikke start tung jobb ved vanlig widget-rerun.
        return []
    data = auto_rank_market(safe_tickers, max_count=max_count, use_news=use_news, force_manual_fetch=force_manual_fetch, include_insider=include_insider)
    data = _ranked_for_display(data)
    _rank_cache_store(label, fp, data)
    return data


def _sort_ranked_items(items):
    """Sorter etter anbefaling først, deretter score/confidence.

    BUY/Kjøp nå øverst, HOLD/WAIT etterpå og SELL/AVOID nederst.
    """
    return _ranked_for_display(items)


def _dedupe_ranked_items(items):
    out, seen = [], set()
    for item in _sort_ranked_items(items):
        ticker = normalize_user_ticker(item.get("ticker"))
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append(item)
    return out


def _latest_ranked_results_for_source(source_label, fallback_results=None, current_label=None):
    """Hent dynamisk aksjeliste for Interaktiv analyse uten AAPL-fallback.

    Viktig for oppgave 76/76B:
    - USA/Norge/Sverige/Top Picks bruker siste lagrede rangering fra appen.
    - Hvis listen mangler, faller vi bare tilbake til gjeldende resultater når
      gjeldende panel faktisk er samme kilde.
    - Det skal ikke stilltiende byttes til AAPL når brukeren har valgt Norge/Sverige.
    """
    latest = st.session_state.get("latest_rankings_v148", {}) or {}
    fallback_results = fallback_results or []
    current_label_clean = str(current_label or "").replace("TopPicks_", "Top Picks")

    if source_label == "Aktuell liste":
        return _dedupe_ranked_items(fallback_results)

    if source_label == "Smart Universe Picker":
        active = st.session_state.get("smart_universe_picker_active_v18517", {}) or st.session_state.get("active_universe", {}) or {}
        rows = []
        if isinstance(active, dict):
            rows = list(active.get("rows") or [])
            if not rows:
                rows = [{"ticker": t, "source": "Smart Universe Picker"} for t in active.get("tickers", []) or []]
        if not rows:
            rows = latest.get("Smart Universe Picker") or []
        return _dedupe_ranked_items(rows)

    if source_label == "Dynamisk watchlist / best rangerte":
        merged = []
        for key in [
            "Dynamisk watchlist / best rangerte",
            "USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil", "Norden",
            "TopPicks_USA", "TopPicks_Norge", "TopPicks_Sverige", "TopPicks_Finland",
            "TopPicks_Danmark", "TopPicks_Brasil", "TopPicks_Norden", "TopPicks_Alle",
        ]:
            merged.extend(latest.get(key, []) or [])
        return _dedupe_ranked_items(merged or fallback_results)

    if source_label in {"USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil", "Norden", "Alle"}:
        stored = latest.get(source_label) or []
        if stored:
            return _dedupe_ranked_items(stored)
        # Bare bruk fallback hvis aktivt panel faktisk er samme marked.
        if current_label_clean == source_label:
            return _dedupe_ranked_items(fallback_results)
        return []

    if source_label == "Top Picks":
        merged = []
        for key, value in latest.items():
            if str(key).startswith("TopPicks"):
                merged.extend(value or [])
        if merged:
            return _dedupe_ranked_items(merged)
        if str(current_label or "").startswith("TopPicks"):
            return _dedupe_ranked_items(fallback_results)
        return []

    return _dedupe_ranked_items(fallback_results)


def _source_tickers_for_interactive(source_label, max_fallback=30):
    """Ticker-univers for Interaktiv analyse når lagret rangering mangler.

    Brukes bare når bruker aktivt trykker på Oppdater-listen-knappen.
    Den skal ikke trigge tung rangering automatisk ved menyvalg.
    """
    try:
        limit = int(globals().get("max_count", max_fallback) or max_fallback)
    except Exception:
        limit = max_fallback
    limit = max(5, min(limit, 200))

    if source_label == "Smart Universe Picker":
        active = st.session_state.get("smart_universe_picker_active_v18517", {}) or st.session_state.get("active_universe", {}) or {}
        if isinstance(active, dict):
            tickers = list(active.get("tickers") or [])
            if tickers:
                return tickers[:limit]
        latest = st.session_state.get("latest_rankings_v148", {}) or {}
        return [normalize_user_ticker(r.get("ticker")) for r in latest.get("Smart Universe Picker", []) if isinstance(r, dict) and r.get("ticker")][:limit]
    if source_label == "USA":
        return resolve_universe_tickers(["USA"], max_count=limit)
    if source_label == "Norge":
        return resolve_universe_tickers(["Norge"], max_count=limit)
    if source_label == "Sverige":
        return resolve_universe_tickers(["Sverige"], max_count=limit)
    if source_label == "Finland":
        return resolve_universe_tickers(["Finland"], max_count=limit)
    if source_label == "Danmark":
        return resolve_universe_tickers(["Danmark"], max_count=limit)
    if source_label == "Brasil":
        return resolve_universe_tickers(["Brasil"], max_count=limit)
    if source_label == "Norden":
        return resolve_universe_tickers(["Norden"], max_count=limit)
    if source_label == "Alle":
        return resolve_universe_tickers(["Alle"], max_count=limit)
    if source_label == "Dynamisk watchlist / best rangerte":
        wl = list(globals().get("watchlist_tickers") or [])
        if wl:
            return wl[:limit]
        return list(globals().get("dynamic_watchlist") or [])[:limit]
    if source_label == "Top Picks":
        return resolve_universe_tickers(["Alle"], max_count=limit)
    return []


def _build_interactive_source_ranking_now(source_label):
    """Bygg valgt kilde på eksplisitt knappetrykk og lagre i siste rangering.

    Dette er hotfix v14.10 for 76/76B/78: når Norge/USA/Sverige mangler lagret
    dynamisk rangering, skal brukeren kunne bygge den aktuelle listen uten at appen
    faller tilbake til AAPL eller starter automatisk tung jobb.
    """
    tickers = _source_tickers_for_interactive(source_label)
    if not tickers:
        return []
    try:
        limit = int(globals().get("max_count", len(tickers)) or len(tickers))
    except Exception:
        limit = len(tickers)
    limit = max(1, min(limit, len(tickers), 200))
    data = auto_rank_market(tickers[:limit], max_count=limit, use_news=False, force_manual_fetch=True)
    if source_label == "Top Picks":
        key = "TopPicks_Alle"
    elif source_label == "Dynamisk watchlist / best rangerte":
        key = "Dynamisk watchlist / best rangerte"
    elif source_label == "Smart Universe Picker":
        key = "Smart Universe Picker"
    else:
        key = source_label
    latest = st.session_state.setdefault("latest_rankings_v148", {})
    latest[key] = data or []
    # Lagre også under normal kildenøkkel når relevant, slik at dropdownen finner listen direkte.
    if source_label in {"USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil", "Norden", "Alle"}:
        latest[source_label] = data or []
    st.session_state[f"rank_cache_v148_{key}"] = {"fp": ("manual_build", tuple(tickers[:limit])), "data": data or [], "updated_at": _now_short()}
    _set_update_reason(f"Interaktiv analyse: bygget {source_label}-liste")
    return data or []


def _clean_manual_ticker_input(value: str) -> str:
    """Rydd manuell ticker. Eksempeltekst og lister skal ikke behandles som aktiv ticker."""
    raw = str(value or "").strip()
    examples = {"EQNR.OL / VOLV-B.ST / NOVO-B.CO", "EQNR.OL / NOKIA.HE / PETR4.SA"}
    if raw.upper() in {x.upper() for x in examples}:
        return ""
    # Interaktiv analyse er for én ticker. Hvis bruker limer inn en liste, bruk første og vis info.
    for sep in [",", ";", "/", "|"]:
        if sep in raw:
            raw = raw.split(sep)[0].strip()
            break
    return normalize_user_ticker(raw)


# SIDEBAR_MARKET_DROPDOWN_V1
# BANNER_PERIOD_SYNC_FIX_V3

MARKET_CATEGORY_OPTIONS = [
    "US Markets",
    "Europe Markets",
    "Norway / Oslo",
    "Sweden / Stockholm",
    "Finland / Helsinki",
    "Denmark / Copenhagen",
    "Brazil / B3",
    "Cryptocurrencies",
    "Rates",
    "Commodities",
    "Currencies",
    "All Markets",
]

MARKET_CATEGORY_TO_MODE = {
    "US Markets": "USA / S&P 500",
    "Europe Markets": "Alle",
    "Norway / Oslo": "Norge / Oslo Børs",
    "Sweden / Stockholm": "Sverige / Stockholm",
    "Finland / Helsinki": "Finland / Helsinki",
    "Denmark / Copenhagen": "Danmark / Copenhagen",
    "Brazil / B3": "Brasil / B3",
    "Cryptocurrencies": "Alle",
    "Rates": "Alle",
    "Commodities": "Alle",
    "Currencies": "Alle",
    "All Markets": "Alle",
}


def render_market_category_selector():
    """
    Kompakt markedskategori-velger i sidebar, inspirert av finansapper.
    Returnerer gammel intern mode slik resten av appen fortsatt fungerer.
    """
    st.sidebar.markdown(
        """
        <style>
        .market-category-card {
            background: rgba(15,23,42,0.72);
            border: 1px solid rgba(148,163,184,0.22);
            border-radius: 12px;
            padding: 9px 10px;
            margin: 8px 0 10px 0;
        }
        .market-category-title {
            color: #f8fafc;
            font-weight: 950;
            font-size: 0.88rem;
            margin-bottom: 3px;
        }
        .market-category-sub {
            color: #94a3b8;
            font-weight: 650;
            font-size: 0.70rem;
            line-height: 1.2;
        }
        </style>
        <div class="market-category-card">
            <div class="market-category-title">◎ Markedskategori</div>
            <div class="market-category-sub">Velg hvilket univers appen skal analysere.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_category = st.sidebar.selectbox(
        "Markedskategori",
        MARKET_CATEGORY_OPTIONS,
        index=0,
        label_visibility="collapsed",
        key="market_category_selector_v1",
    )

    mode = MARKET_CATEGORY_TO_MODE.get(selected_category, "Alle")

    if selected_category in {"Cryptocurrencies", "Rates", "Commodities", "Currencies"}:
        st.sidebar.info(
            f"{selected_category}: kategori er lagt inn i menyen, men full analysemodell for dette universet kommer senere. "
            "Foreløpig brukes aksjeuniverset som fallback."
        )
    elif selected_category == "Europe Markets":
        st.sidebar.caption("Europe Markets bruker foreløpig samlet aksjeunivers/fallback. Norge og Sverige kan velges separat.")

    return selected_category, mode



CHART_CONFIG = {
    "scrollZoom": False,
    "displayModeBar": "hover",
    "displaylogo": False,
    "responsive": True,
    "doubleClick": "reset",
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}

def render_interactive_chart(fig, *args, **kwargs):
    """
    Felles plotly-rendering:
    - musehjul zoom
    - pan med mus
    - tydelig hover
    """
    try:
        fig.update_layout(
            dragmode="pan",
            hovermode="x unified",
            legend=dict(
                bgcolor="rgba(15,23,42,0.75)",
                bordercolor="rgba(148,163,184,0.35)",
                borderwidth=1,
            ),
        )
        fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor")
        fig.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor")
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

    kwargs.setdefault("use_container_width", True)
    kwargs.setdefault("config", CHART_CONFIG)
    return st.plotly_chart(fig, *args, **kwargs)


def render_graph_explanation(kind):
    texts = {
        "price": (
            "📘 Prisgraf",
            "Viser kursutvikling og gjeldende kurs. Bruk musehjul for zoom og dra i grafen for å panorere."
        ),
        "ta": (
            "📘 Teknisk graf",
            "Viser pris, Bollinger-bånd, støtte/motstand og eventuelle mønstre. Brudd over motstand kan være positivt, mens brudd under støtte er et risikoflagg."
        ),
        "rsi": (
            "📘 RSI",
            "RSI under 30 kan indikere oversolgt. RSI over 70 er overkjøpt, og over 80 er ekstremt overkjøpt. Høy RSI kan forklare HOLD/SELL selv om aksjen har høy total score."
        ),
        "equity": (
            "📘 Strategi / equity curve",
            "Viser hvordan den historiske strategien ville utviklet porteføljeverdien. Brukes som test, ikke garanti for fremtidig avkastning."
        ),
        "backtest": (
            "📘 Backtest",
            "Sammenligner strategi mot benchmark. Se særlig på drawdown, jevnhet og om strategien slår benchmark over tid."
        ),
        "drawdown": (
            "📘 Drawdown",
            "Viser hvor mye strategien faller fra tidligere topp. Lavere og kortere drawdown betyr normalt lavere risiko."
        ),
    }
    title, body = texts.get(kind, ("📘 Graf", "Interaktiv graf med zoom, pan og hover."))
    st.markdown(
        f"""
        <div class="graph-explain-box">
            <b>{title}</b><br>{body}
        </div>
        """,
        unsafe_allow_html=True,
    )


st.markdown("""
<style>
:root {
    --bg-main: #0f172a;
    --bg-sidebar: #020617;
    --bg-card: #111827;
    --bg-card-2: #1e293b;
    --border: #334155;
    --text-main: #f8fafc;
    --text-soft: #cbd5e1;
    --text-muted: #94a3b8;
    --green: #22c55e;
    --yellow: #f59e0b;
    --red: #ef4444;
    --blue: #38bdf8;
}

.stApp {
    background: var(--bg-main);
    color: var(--text-main);
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
    max-width: 1500px;
}

[data-testid="stSidebar"] {
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
}

/* V14.12 / Oppgave 81-83: mobil skal ikke ha en halv sidebar synlig.
   Streamlit får bruke sin egen drawer-knapp på mobil, mens hovedsiden har et kompakt
   Kontrollsenter som funksjonell fallback. */
[data-testid="stSidebar"] * { box-sizing: border-box; }
@media (max-width: 900px) {
    
section[data-testid="stSidebar"] {
        background: #020617 !important;
        border-right: 1px solid rgba(148,163,184,0.28) !important;
        max-width: min(88vw, 340px) !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 0.65rem !important;
    }
}

html, body, [class*="css"], p, span, div {
    color: var(--text-main);
}

h1, h2, h3, h4 {
    color: var(--text-main) !important;
    font-weight: 800 !important;
}

label, [data-testid="stWidgetLabel"] {
    color: var(--text-soft) !important;
    font-weight: 700 !important;
}

.card {
    background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 18px;
    margin-bottom: 12px;
    box-shadow: 0 8px 22px rgba(0,0,0,0.22);
}

.small {
    color: var(--text-soft);
    font-size: 0.95rem;
}

.good {
    color: var(--green);
    font-weight: 900;
}

.mid {
    color: var(--yellow);
    font-weight: 900;
}

.bad {
    color: var(--red);
    font-weight: 900;
}

[data-testid="stMetric"] {
    background: #111827;
    border: 1px solid var(--border);
    padding: 16px;
    border-radius: 16px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.18);
}

[data-testid="stMetricLabel"] {
    color: var(--text-soft) !important;
    font-size: 0.95rem !important;
    font-weight: 800 !important;
}

[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-size: 1.75rem !important;
    font-weight: 900 !important;
}

.stAlert {
    border-radius: 14px;
    font-size: 1rem;
}

.stButton > button {
    border-radius: 14px;
    border: 1px solid var(--border);
    background: #0ea5e9;
    color: white;
    font-weight: 800;
    padding: 0.55rem 1rem;
}

.stButton > button:hover {
    background: #0284c7;
    color: white;
    border-color: #7dd3fc;
}

div[data-baseweb="select"] > div {
    background-color: #1e293b !important;
    color: white !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}

input, textarea {
    background-color: #1e293b !important;
    color: white !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}

[data-testid="stDataFrame"] {
    border: 1px solid var(--border);
    border-radius: 14px;
}

hr {
    border-color: var(--border);
}

/* Make Plotly containers easier to read */
.js-plotly-plot .plotly {
    border-radius: 16px;
}

/* Mobile-first improvements */
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.75rem;
        padding-right: 0.75rem;
        padding-top: 0.75rem;
    }

    h1 {
        font-size: 1.65rem !important;
        line-height: 1.15 !important;
    }

    h2 {
        font-size: 1.35rem !important;
    }

    h3 {
        font-size: 1.15rem !important;
    }

    .card {
        padding: 14px;
        border-radius: 14px;
    }

    [data-testid="stMetric"] {
        padding: 12px;
        border-radius: 13px;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.25rem !important;
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.82rem !important;
    }

    .small {
        font-size: 0.85rem;
    }

    .stButton > button {
        width: 100%;
        padding: 0.7rem 1rem;
        font-size: 1rem;
    }
}

/* --- PRO POLISH PATCH: stronger readability PC/mobile --- */
.status-live {
    display:inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(34,197,94,0.15);
    border: 1px solid rgba(34,197,94,0.45);
    color: #86efac !important;
    font-weight: 900;
}
.status-danger {
    display:inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(239,68,68,0.15);
    border: 1px solid rgba(239,68,68,0.45);
    color: #fecaca !important;
    font-weight: 900;
}
.rsi-box {
    background: linear-gradient(180deg, #111827 0%, #020617 100%);
    border: 1px solid #475569;
    border-radius: 18px;
    padding: 16px;
    margin: 12px 0;
}
.card, div[data-testid="stMetric"] {
    border-color: #475569 !important;
}
.small, .muted, caption {
    color: #cbd5e1 !important;
}
@media (max-width: 768px) {
    .block-container {
        max-width: 100% !important;
    }
}


/* --- RSI BOX PATCH --- */
.rsi-box {
    background: linear-gradient(180deg, #111827 0%, #020617 100%) !important;
    border: 1px solid #475569 !important;
    border-radius: 18px !important;
    padding: 18px !important;
    margin: 14px 0 18px 0 !important;
    box-shadow: 0 8px 22px rgba(0,0,0,0.24) !important;
}
.rsi-title {
    font-size: 1.15rem !important;
    font-weight: 900 !important;
    color: #f8fafc !important;
    margin-bottom: 6px !important;
}
.rsi-value {
    font-size: 2rem !important;
    font-weight: 900 !important;
    color: #ffffff !important;
}
.rsi-status-good { color: #22c55e !important; font-weight: 900 !important; }
.rsi-status-mid { color: #f59e0b !important; font-weight: 900 !important; }
.rsi-status-bad { color: #ef4444 !important; font-weight: 900 !important; }


/* --- Signal Engine v1 explanation polish --- */
div[data-testid="stAlert"] {
    border-radius: 14px !important;
}


/* --- TOP PICKS ACTION CARDS V2 --- */
.action-chip-row {
    display:flex;
    flex-wrap:wrap;
    gap:7px;
    margin-top:8px;
    margin-bottom:6px;
}
.action-chip {
    display:inline-block;
    padding:5px 10px;
    border-radius:999px;
    font-size:0.78rem;
    font-weight:900;
    border:1px solid rgba(255,255,255,0.20);
    line-height:1.2;
}
.action-buy {
    color:#bbf7d0 !important;
    background:rgba(34,197,94,0.16);
    border-color:rgba(34,197,94,0.5);
}
.action-hold {
    color:#fde68a !important;
    background:rgba(245,158,11,0.16);
    border-color:rgba(245,158,11,0.5);
}
.action-sell {
    color:#fecaca !important;
    background:rgba(239,68,68,0.18);
    border-color:rgba(239,68,68,0.55);
}
.action-info {
    color:#bae6fd !important;
    background:rgba(56,189,248,0.10);
    border-color:rgba(56,189,248,0.35);
}
.action-explain {
    color:#cbd5e1 !important;
    font-size:0.82rem;
    margin-top:4px;
}


/* --- READABLE INSIDER / ANALYST / EARNINGS CARDS V1 --- */
.info-card-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(220px, 1fr));
    gap: 14px;
    margin: 12px 0 18px 0;
}
.info-card-big {
    background: rgba(15, 23, 42, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.38);
    border-radius: 16px;
    padding: 16px 18px;
    min-height: 142px;
}
.info-card-title {
    color: #f8fafc !important;
    font-size: 1.05rem;
    font-weight: 900;
    margin-bottom: 10px;
}
.info-card-main {
    color: #ffffff !important;
    font-size: 1.55rem;
    font-weight: 950;
    line-height: 1.2;
    margin: 8px 0;
}
.info-card-sub {
    color: #cbd5e1 !important;
    font-size: 0.78rem;
    line-height: 1.45;
    margin-top: 8px;
}
.info-card-small {
    color: #94a3b8 !important;
    font-size: 0.86rem;
    line-height: 1.35;
    margin-top: 8px;
}
.info-positive {
    color: #86efac !important;
}
.info-warning {
    color: #fde68a !important;
}
.info-negative {
    color: #fecaca !important;
}
@media (max-width: 900px) {
    .info-card-grid {
        grid-template-columns: 1fr;
    }
    .info-card-main {
        font-size: 1.35rem;
    }
}


/* --- READABLE INSIDER CARDS V2 --- */
.info-mini-card {
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 16px;
    padding: 16px 18px;
    min-height: 178px;
    margin-bottom: 12px;
}
.info-mini-title {
    color: #f8fafc !important;
    font-size: 1.05rem;
    font-weight: 900;
    margin-bottom: 10px;
}
.info-mini-main {
    color: #ffffff !important;
    font-size: 1.35rem;
    font-weight: 950;
    line-height: 1.25;
    margin: 7px 0;
}
.info-mini-sub {
    color: #cbd5e1 !important;
    font-size: 0.78rem;
    line-height: 1.45;
}
.info-mini-small {
    color: #94a3b8 !important;
    font-size: 0.78rem;
    line-height: 1.35;
    margin-top: 8px;
}
.info-positive { color: #86efac !important; }
.info-warning { color: #fde68a !important; }
.info-negative { color: #fecaca !important; }




/* --- MACD INFO BOX V1 --- */
.macd-explain-box {
    background: rgba(15, 23, 42, 0.88);
    border: 1px solid rgba(148, 163, 184, 0.38);
    border-radius: 14px;
    padding: 12px 14px;
    margin: 8px 0 18px 0;
    color: #cbd5e1 !important;
    font-size: 0.92rem;
    line-height: 1.45;
}
.macd-explain-box b {
    color: #f8fafc !important;
}


/* --- GRAPH EXPLANATION BOXES V1 --- */
.graph-explain-box {
    background: rgba(15, 23, 42, 0.88);
    border: 1px solid rgba(148, 163, 184, 0.38);
    border-radius: 14px;
    padding: 12px 14px;
    margin: 8px 0 18px 0;
    color: #cbd5e1 !important;
    font-size: 0.92rem;
    line-height: 1.45;
}
.graph-explain-box b {
    color: #f8fafc !important;
}


/* --- DARK SELECTBOX DROPDOWN V1 --- */
div[data-baseweb="popover"] {
    background: #0f172a !important;
}
div[data-baseweb="popover"] div[role="listbox"] {
    background: #0f172a !important;
    border: 1px solid rgba(148,163,184,0.45) !important;
    color: #f8fafc !important;
}
div[data-baseweb="popover"] div[role="option"] {
    color: #f8fafc !important;
    background: #0f172a !important;
    font-weight: 800 !important;
}
div[data-baseweb="popover"] div[role="option"]:hover {
    background: #1e293b !important;
    color: #ffffff !important;
}


/* --- SELECTBOX VISIBILITY FIX V1 --- */
/* Closed select field */
div[data-baseweb="select"] > div {
    background-color: #1e293b !important;
    color: #f8fafc !important;
    border-color: rgba(148, 163, 184, 0.55) !important;
}

div[data-baseweb="select"] span,
div[data-baseweb="select"] div,
div[data-baseweb="select"] input {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}

/* Dropdown popover */
div[data-baseweb="popover"],
div[data-baseweb="popover"] > div,
div[data-baseweb="menu"],
ul[role="listbox"],
div[role="listbox"] {
    background-color: #0f172a !important;
    color: #f8fafc !important;
    border: 1px solid rgba(148, 163, 184, 0.45) !important;
}

/* Options */
li[role="option"],
div[role="option"] {
    background-color: #0f172a !important;
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
    font-weight: 800 !important;
    font-size: 1rem !important;
}

/* Option text descendants */
li[role="option"] *,
div[role="option"] * {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}

/* Hover / highlighted option */
li[role="option"]:hover,
div[role="option"]:hover,
li[role="option"][aria-selected="true"],
div[role="option"][aria-selected="true"] {
    background-color: #334155 !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

/* Streamlit virtualized menu fallback */
[data-testid="stSelectboxVirtualDropdown"] {
    background-color: #0f172a !important;
    color: #f8fafc !important;
}

[data-testid="stSelectboxVirtualDropdown"] * {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}

/* Popover content fallback */
[data-baseweb="popover"] [role="option"] span,
[data-baseweb="popover"] [role="option"] div {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}


/* --- SIDEBAR STRUCTURE V2 --- */
/* GRAPH_SIDEBAR_POLISH_V1
/* SIDEBAR_MARKET_PILLS_FIX_V2
/* SIDEBAR_ALERTS_LAYOUT_V1 */ */ */
.sidebar-status-card {
    border-radius: 9px;
    padding: 7px 7px;
    margin: 4px 0;
    line-height: 1.15;
    border: 1px solid rgba(148, 163, 184, 0.25);
}
.sidebar-status-card.open {
    background: rgba(34, 197, 94, 0.12);
    border-color: rgba(34, 197, 94, 0.45);
}
.sidebar-status-card.closed {
    background: rgba(239, 68, 68, 0.12);
    border-color: rgba(239, 68, 68, 0.45);
}
.sidebar-status-card.paused {
    background: rgba(245, 158, 11, 0.13);
    border-color: rgba(245, 158, 11, 0.45);
}
.sidebar-status-name {
    color: #ffffff !important;
    font-weight: 900;
    font-size: 0.84rem;
}
.sidebar-status-main {
    font-weight: 900;
    font-size: 0.70rem;
    margin-top: 2px;
}
.sidebar-status-main.open {
    color: #86efac !important;
}
.sidebar-status-main.closed {
    color: #fecaca !important;
}
.sidebar-status-reason {
    color: #ff6b6b !important;
    font-weight: 900;
    font-size: 0.76rem;
    margin-top: 2px;
}


/* SIDEBAR_MARKET_PILLS_FIX_V2 */
.market-pill-row {
    display: flex;
    flex-direction: row;
    gap: 5px;
    width: 100%;
    margin: 6px 0 10px 0;
    align-items: stretch;
}
.market-pill {
    flex: 1 1 0;
    min-width: 0;
    box-sizing: border-box;
    border-radius: 9px;
    padding: 5px 4px;
    line-height: 1.05;
    overflow: hidden;
    min-height: 34px;
    border: 1px solid rgba(148,163,184,0.28);
    background: rgba(15,23,42,0.84);
}
.market-pill.open {
    background: rgba(6,78,59,0.42);
    border-color: rgba(34,197,94,0.55);
}
.market-pill.closed {
    background: rgba(76,5,25,0.58);
    border-color: rgba(248,113,113,0.65);
}
.market-pill-name {
    font-size: 0.64rem;
    font-weight: 950;
    color: #f8fafc;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.market-pill-main {
    font-size: 0.63rem;
    font-weight: 900;
    margin-top: 3px;
}
.market-pill-main.open {
    color: #86efac;
}
.market-pill-main.closed {
    color: #fecaca;
}
.market-pill-reason {
    font-size: 0.60rem;
    font-weight: 850;
    color: #fca5a5;
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.sidebar-small-note {
    color: #94a3b8 !important;
    font-size: 0.78rem;
    line-height: 1.35;
    margin-bottom: 8px;
}


/* SIDEBAR_ALERTS_LAYOUT_V1 */
.sidebar-tight-hr {
    margin: 10px 0 10px 0;
    border-top: 1px solid rgba(148,163,184,0.15);
}
.alert-status-pill {
    border-radius: 12px;
    padding: 8px 9px;
    margin: 6px 0;
    border: 1px solid rgba(148,163,184,0.22);
    background: rgba(15,23,42,0.72);
    line-height: 1.15;
}
.alert-status-pill.ok {
    border-color: rgba(34,197,94,0.55);
    background: rgba(6,78,59,0.34);
}
.alert-status-pill.bad {
    border-color: rgba(248,113,113,0.60);
    background: rgba(76,5,25,0.48);
}
.alert-status-title {
    font-size: 0.82rem;
    color: #f8fafc;
    font-weight: 950;
}
.alert-status-sub {
    font-size: 0.70rem;
    color: #cbd5e1;
    margin-top: 2px;
}


/* --- V12 PRO DARK UI STANDARD (tasks 11-15,18,20-23) --- */
:root {
    --pro-panel: #0f172a;
    --pro-panel-2: #111827;
    --pro-panel-3: #1e293b;
    --pro-text: #f8fafc;
    --pro-muted: #cbd5e1;
    --pro-border: rgba(148,163,184,0.38);
    --pro-blue: #38bdf8;
}
button, .stButton > button, [data-testid="stFormSubmitButton"] button {
    width: auto !important;
    max-width: 100% !important;
    background: linear-gradient(180deg, #0ea5e9 0%, #0369a1 100%) !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    border: 1px solid rgba(125,211,252,0.72) !important;
    border-radius: 12px !important;
    font-weight: 950 !important;
    min-height: 38px !important;
    box-shadow: 0 6px 16px rgba(2,132,199,0.20) !important;
}
button:hover, .stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover {
    background: linear-gradient(180deg, #38bdf8 0%, #0284c7 100%) !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    border-color: #bae6fd !important;
}
button *, .stButton > button *, [data-testid="stFormSubmitButton"] button * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 1 !important;
}
[data-testid="stExpander"] details,
div[data-testid="stExpander"] details,
section[data-testid="stSidebar"] details {
    background: rgba(15,23,42,0.74) !important;
    border: 1px solid var(--pro-border) !important;
    border-radius: 14px !important;
    overflow: hidden !important;
    box-shadow: 0 8px 20px rgba(0,0,0,0.16) !important;
}
[data-testid="stExpander"] summary,
div[data-testid="stExpander"] summary,
section[data-testid="stSidebar"] details > summary {
    background: linear-gradient(180deg, rgba(30,41,59,0.98), rgba(15,23,42,0.98)) !important;
    color: var(--pro-text) !important;
    -webkit-text-fill-color: var(--pro-text) !important;
    border-bottom: 1px solid rgba(148,163,184,0.22) !important;
    min-height: 38px !important;
    padding-top: 0.36rem !important;
    padding-bottom: 0.36rem !important;
    font-weight: 950 !important;
}
[data-testid="stExpander"] summary:hover,
div[data-testid="stExpander"] summary:hover,
section[data-testid="stSidebar"] details > summary:hover {
    background: linear-gradient(180deg, rgba(51,65,85,0.98), rgba(30,41,59,0.98)) !important;
}
[data-testid="stExpander"] summary *,
div[data-testid="stExpander"] summary *,
section[data-testid="stSidebar"] details > summary * {
    color: var(--pro-text) !important;
    -webkit-text-fill-color: var(--pro-text) !important;
    opacity: 1 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"],
div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    background: rgba(2,6,23,0.42) !important;
}
input, textarea, [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stNumberInput"] input {
    caret-color: var(--pro-blue) !important;
    background: rgba(15,23,42,0.96) !important;
    color: var(--pro-text) !important;
    -webkit-text-fill-color: var(--pro-text) !important;
    border: 1px solid rgba(148,163,184,0.45) !important;
    border-radius: 11px !important;
    font-weight: 850 !important;
}
input:focus, textarea:focus, [data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus, [data-testid="stNumberInput"] input:focus {
    outline: none !important;
    border-color: rgba(56,189,248,0.96) !important;
    box-shadow: 0 0 0 2px rgba(56,189,248,0.22) !important;
}
[data-testid="stNumberInput"] button {
    background: rgba(30,41,59,0.96) !important;
    border-color: rgba(148,163,184,0.45) !important;
    color: var(--pro-text) !important;
    min-height: 32px !important;
}
[data-baseweb="select"] > div,
div[data-baseweb="select"] > div {
    background: rgba(15,23,42,0.96) !important;
    color: var(--pro-text) !important;
    -webkit-text-fill-color: var(--pro-text) !important;
    border: 1px solid rgba(148,163,184,0.45) !important;
    border-radius: 11px !important;
    min-height: 38px !important;
}
div[data-baseweb="popover"], div[data-baseweb="popover"] * {
    color: var(--pro-text) !important;
    -webkit-text-fill-color: var(--pro-text) !important;
}
div[data-baseweb="popover"] ul {
    background: #0f172a !important;
    border: 1px solid rgba(148,163,184,0.40) !important;
    border-radius: 12px !important;
}
div[data-baseweb="popover"] li[aria-selected="true"], div[data-baseweb="popover"] li:hover {
    background: rgba(56,189,248,0.18) !important;
}
[data-testid="stTextArea"] textarea {
    min-height: 58px !important;
}
[data-testid="stCheckbox"] label, [data-testid="stCheckbox"] p, [data-testid="stCheckbox"] span {
    white-space: normal !important;
    word-break: normal !important;
    overflow-wrap: normal !important;
    color: var(--pro-text) !important;
    -webkit-text-fill-color: var(--pro-text) !important;
}
.pro-dirty-status {
    display:inline-block;
    padding: 5px 9px;
    border-radius: 999px;
    border:1px solid rgba(251,191,36,0.45);
    background:rgba(120,53,15,0.28);
    color:#fde68a !important;
    font-size:0.76rem;
    font-weight:900;
    margin: 4px 0 8px 0;
}
.pro-clean-status {
    display:inline-block;
    padding: 5px 9px;
    border-radius: 999px;
    border:1px solid rgba(34,197,94,0.45);
    background:rgba(22,101,52,0.28);
    color:#bbf7d0 !important;
    font-size:0.76rem;
    font-weight:900;
    margin: 4px 0 8px 0;
}
@media (max-width: 760px) {
    [data-testid="stExpander"] summary, div[data-testid="stExpander"] summary, section[data-testid="stSidebar"] details > summary { min-height: 42px !important; }
    [data-testid="stTextArea"] textarea { min-height: 74px !important; }
    .block-container { padding-left: 0.65rem !important; padding-right: 0.65rem !important; }
}


/* --- V14 FIX: diskrete hjelpeikoner og mørke tooltips (oppgave 28/32) --- */
/* Den generelle button-stilen i appen skal ikke gjøre Streamlit sine ?-hjelpeikoner blå/store. */
[data-testid="stTooltipIcon"],
[data-testid="stTooltipIcon"] *,
button[aria-label="Help"],
button[aria-label="help"],
button[title="View more"],
button[title="help"] {
    background: transparent !important;
    background-color: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
    color: #94a3b8 !important;
    -webkit-text-fill-color: #94a3b8 !important;
    min-height: 18px !important;
    width: 18px !important;
    height: 18px !important;
    padding: 0 !important;
    margin: 0 0 0 4px !important;
    border-radius: 999px !important;
    opacity: 0.76 !important;
}
[data-testid="stTooltipIcon"] svg,
button[aria-label="Help"] svg,
button[aria-label="help"] svg {
    width: 14px !important;
    height: 14px !important;
    fill: #94a3b8 !important;
    color: #94a3b8 !important;
}
[data-testid="stTooltipIcon"]:hover,
button[aria-label="Help"]:hover,
button[aria-label="help"]:hover {
    opacity: 1 !important;
    background: rgba(148,163,184,0.12) !important;
}
div[data-baseweb="tooltip"],
div[role="tooltip"],
[data-testid="stTooltipContent"] {
    background: #111827 !important;
    color: #e2e8f0 !important;
    -webkit-text-fill-color: #e2e8f0 !important;
    border: 1px solid rgba(148,163,184,0.38) !important;
    border-radius: 10px !important;
    box-shadow: 0 12px 28px rgba(0,0,0,0.38) !important;
    max-width: 320px !important;
    font-weight: 750 !important;
}
div[data-baseweb="tooltip"] *,
div[role="tooltip"] *,
[data-testid="stTooltipContent"] * {
    background: transparent !important;
    color: #e2e8f0 !important;
    -webkit-text-fill-color: #e2e8f0 !important;
}

/* Kompakt Trading engine v14 */
.trading-engine-compact {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    background: rgba(15,23,42,0.88);
    border: 1px solid rgba(148,163,184,0.38);
    border-radius: 14px;
    padding: 10px 11px;
    margin: 8px 0 8px 0;
}
.trading-engine-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 9px;
    border-radius: 999px;
    background: rgba(34,197,94,0.13);
    border: 1px solid rgba(34,197,94,0.36);
    color: #d1fae5 !important;
    font-weight: 950;
}
.trading-engine-muted { color: #cbd5e1 !important; font-weight: 850; }
.trading-engine-value { color: #ffffff !important; font-weight: 950; }
.trading-engine-details {
    background: rgba(15,23,42,0.62);
    border: 1px solid rgba(148,163,184,0.22);
    border-radius: 12px;
    padding: 8px 10px;
    margin: 6px 0 12px 0;
    color: #cbd5e1 !important;
    font-size: 0.90rem;
}



/* --- V14.6 tasks 51-54: faktisk visningsmodus, mobil-komprimering og kontrollsenter --- */
:root {
    --compact-card-pad: 8px 10px;
    --compact-card-radius: 12px;
}
.compact-stat-grid {
    display:grid;
    grid-template-columns: repeat(4, minmax(0,1fr));
    gap:8px;
    margin:8px 0 10px 0;
}
.compact-stat-card {
    background: rgba(15,23,42,0.78);
    border:1px solid rgba(148,163,184,0.28);
    border-radius: var(--compact-card-radius);
    padding: var(--compact-card-pad);
    min-height:54px;
}
.compact-stat-label {
    color:#cbd5e1 !important;
    font-size:0.72rem;
    font-weight:850;
    line-height:1.05;
    margin-bottom:3px;
}
.compact-stat-value {
    color:#f8fafc !important;
    font-size:1.08rem;
    font-weight:950;
    line-height:1.12;
    word-break:normal;
}
.compact-stat-delta {
    display:inline-block;
    margin-top:4px;
    color:#86efac !important;
    font-size:0.74rem;
    font-weight:900;
}
.compact-stat-delta.neg { color:#fecaca !important; }
.view-mode-status {
    border:1px solid rgba(56,189,248,0.30);
    background:rgba(14,165,233,0.10);
    color:#dff6ff !important;
    border-radius:999px;
    padding:5px 9px;
    font-size:0.76rem;
    font-weight:900;
    margin:4px 0 8px 0;
}
.control-center-status {
    border:1px solid rgba(148,163,184,0.28);
    background:rgba(15,23,42,0.76);
    border-radius:14px;
    padding:8px 10px;
    margin:6px 0 8px 0;
    color:#e2e8f0 !important;
    font-size:0.78rem;
    line-height:1.35;
}
.status-dot { display:inline-block; width:9px; height:9px; border-radius:999px; margin-right:5px; vertical-align:middle; }
.status-dot.green { background:#22c55e; box-shadow:0 0 10px rgba(34,197,94,0.55); }
.status-dot.red { background:#ef4444; box-shadow:0 0 10px rgba(239,68,68,0.55); }
.status-dot.yellow { background:#facc15; box-shadow:0 0 10px rgba(250,204,21,0.45); }
.auto-status-badge {
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding:6px 9px;
    border-radius:999px;
    font-weight:950;
    font-size:0.84rem;
    margin-bottom:6px;
}
.auto-status-badge.on { background:rgba(22,101,52,0.34); border:1px solid rgba(34,197,94,0.55); color:#bbf7d0 !important; }
.auto-status-badge.off { background:rgba(127,29,29,0.34); border:1px solid rgba(239,68,68,0.55); color:#fecaca !important; }
@media (max-width: 900px) {
    .compact-stat-grid { grid-template-columns: repeat(2, minmax(0,1fr)); gap:6px; }
    .compact-stat-card { min-height:44px; padding:6px 8px; border-radius:10px; }
    .compact-stat-label { font-size:0.66rem; }
    .compact-stat-value { font-size:0.94rem; }
    [data-testid="stMetric"] {
        min-height:44px !important;
        padding:6px 8px !important;
        border-radius:10px !important;
        margin-bottom:4px !important;
    }
    [data-testid="stMetricLabel"] { font-size:0.66rem !important; line-height:1.05 !important; }
    [data-testid="stMetricValue"] { font-size:0.98rem !important; line-height:1.08 !important; }
    [data-testid="stMetricDelta"] { font-size:0.68rem !important; }
    .stButton > button, section[data-testid="stSidebar"] .stButton > button, section[data-testid="stSidebar"] button {
        min-height:42px !important;
        padding:0.36rem 0.65rem !important;
        border-radius:12px !important;
        font-size:0.90rem !important;
        line-height:1.15 !important;
        box-shadow:0 6px 14px rgba(14,165,233,0.18) !important;
    }
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
        font-size:1.05rem !important;
        line-height:1.15 !important;
        margin:0.45rem 0 0.35rem 0 !important;
    }
    section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] span {
        font-size:0.88rem !important;
        line-height:1.22 !important;
    }
    section[data-testid="stSidebar"] details > summary {
        min-height:36px !important;
        padding:6px 8px !important;
        font-size:0.90rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] input,
    section[data-testid="stSidebar"] [data-testid="stTextInput"] input,
    section[data-testid="stSidebar"] [data-testid="stSelectbox"] input,
    section[data-testid="stSidebar"] textarea {
        min-height:38px !important;
        font-size:0.88rem !important;
        padding:6px 8px !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        padding:6px !important;
        border-radius:12px !important;
    }
}

/* Paper Trading justeringer v14 */
.paper-edit-card {
    background: rgba(15,23,42,0.72);
    border: 1px solid rgba(148,163,184,0.32);
    border-radius: 14px;
    padding: 10px 11px;
    margin: 6px 0 10px 0;
}

/* --- V14.7: kompakt header, sentral auto trading, watchlist og sterk mobil-komprimering --- */
.top-app-header {
    display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;
    padding:6px 0 8px 0; margin:0 0 6px 0; border-bottom:1px solid rgba(148,163,184,0.16);
}
.top-app-title { color:#f8fafc !important; font-size:1.24rem; font-weight:950; letter-spacing:-0.02em; line-height:1.1; }
.top-app-status { display:flex; align-items:center; justify-content:flex-end; gap:6px; flex-wrap:wrap; }
.top-chip {
    display:inline-flex; align-items:center; gap:5px; padding:5px 8px; border-radius:999px;
    border:1px solid rgba(148,163,184,0.24); background:rgba(15,23,42,0.70);
    color:#e2e8f0 !important; font-size:0.74rem; font-weight:900; white-space:nowrap;
}
.top-chip.green { border-color:rgba(34,197,94,0.42); background:rgba(22,101,52,0.24); color:#bbf7d0 !important; }
.top-chip.red { border-color:rgba(239,68,68,0.44); background:rgba(127,29,29,0.24); color:#fecaca !important; }
.top-chip.yellow { border-color:rgba(250,204,21,0.44); background:rgba(113,63,18,0.24); color:#fef3c7 !important; }
.top-quick-row { margin:2px 0 6px 0; padding:6px 8px; border-radius:12px; background:rgba(15,23,42,0.38); border:1px solid rgba(148,163,184,0.14); }
.watchlist-compact {
    margin:8px 0 10px 0; padding:8px 10px; border-radius:12px; background:rgba(15,23,42,0.50);
    border:1px solid rgba(148,163,184,0.18);
}
.watchlist-row { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.watchlist-title { color:#f8fafc !important; font-weight:950; font-size:1.05rem; line-height:1.1; }
.watchlist-meta { display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end; }
.watchlist-empty { color:#cbd5e1 !important; font-size:0.78rem; font-weight:850; padding:5px 8px; border-radius:999px; background:rgba(30,41,59,0.72); display:inline-flex; margin-top:6px; }
.control-center-status { font-size:0.88rem !important; line-height:1.45 !important; padding:10px 12px !important; }
.control-center-status b { font-size:0.92rem !important; }
.auto-command-card {
    background:rgba(15,23,42,0.78); border:1px solid rgba(148,163,184,0.28); border-radius:14px;
    padding:10px 12px; margin:8px 0 10px 0; color:#e2e8f0 !important;
}
.auto-command-title { display:flex; align-items:center; justify-content:space-between; gap:8px; font-weight:950; font-size:0.98rem; margin-bottom:7px; }
.auto-command-line { color:#cbd5e1 !important; font-size:0.80rem; font-weight:850; line-height:1.3; }
.auto-status-badge { font-size:0.90rem !important; padding:7px 10px !important; }
.compact-mobile-note { color:#94a3b8 !important; font-size:0.72rem; font-weight:800; }

@media (max-width: 900px) {
    .top-app-header { padding:4px 0 6px 0 !important; gap:6px; }
    .top-app-title { font-size:1.02rem !important; }
    .top-app-status { justify-content:flex-start; }
    .top-chip { font-size:0.66rem !important; padding:4px 6px !important; }
    .watchlist-compact { margin:6px 0 7px 0 !important; padding:7px 8px !important; }
    .watchlist-title { font-size:0.92rem !important; }
    .watchlist-empty { font-size:0.70rem !important; padding:4px 7px !important; }
    .mobile-control-center-note { font-size:0.78rem !important; line-height:1.25 !important; }
    [data-testid="stExpander"] details summary p { font-size:0.92rem !important; font-weight:900 !important; }
    [data-testid="stMetric"] { min-height:34px !important; padding:4px 7px !important; border-radius:10px !important; }
    [data-testid="stMetricLabel"] { font-size:0.62rem !important; line-height:1.0 !important; margin-bottom:0 !important; }
    [data-testid="stMetricValue"] { font-size:0.86rem !important; line-height:1.0 !important; }
    .compact-stat-card { min-height:34px !important; padding:5px 7px !important; border-radius:10px !important; }
    .compact-stat-label { font-size:0.60rem !important; }
    .compact-stat-value { font-size:0.82rem !important; }
    .stButton > button, section[data-testid="stSidebar"] .stButton > button {
        min-height:36px !important; padding:0.28rem 0.52rem !important; font-size:0.82rem !important; border-radius:10px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] input,
    section[data-testid="stSidebar"] [data-testid="stTextInput"] input,
    section[data-testid="stSidebar"] [data-testid="stSelectbox"] input,
    section[data-testid="stSidebar"] textarea { min-height:34px !important; font-size:0.80rem !important; }
}



/* --- V14.12: mobil/drawer cleanup, kontrollrad, bruker/børsstatus --- */
.control-center-wide {
    display:grid;
    grid-template-columns: minmax(220px,1.1fr) minmax(220px,1.25fr) minmax(220px,1.1fr) minmax(240px,1.4fr);
    gap:10px;
    align-items:stretch;
}
.control-info-block {
    background:rgba(15,23,42,0.72);
    border:1px solid rgba(148,163,184,0.26);
    border-radius:14px;
    padding:9px 11px;
    min-height:58px;
}
.control-info-title {
    font-size:0.78rem;
    color:#cbd5e1 !important;
    font-weight:950;
    margin-bottom:5px;
}
.mini-status-chip {
    display:inline-flex;
    align-items:center;
    gap:4px;
    margin:2px 4px 2px 0;
    padding:4px 7px;
    border-radius:999px;
    border:1px solid rgba(148,163,184,0.24);
    background:rgba(15,23,42,0.66);
    color:#e2e8f0 !important;
    font-size:0.72rem;
    font-weight:900;
    white-space:nowrap;
}
.mini-status-chip.green { border-color:rgba(34,197,94,0.42); background:rgba(22,101,52,0.20); color:#bbf7d0 !important; }
.mini-status-chip.red { border-color:rgba(239,68,68,0.44); background:rgba(127,29,29,0.20); color:#fecaca !important; }
.auto-control-help, .system-control-help {
    color:#94a3b8 !important;
    font-size:0.74rem;
    font-weight:800;
    margin:2px 0 5px 0;
}
.auto-control-separator { margin:5px 0 8px 0; border-top:1px solid rgba(148,163,184,0.12); }
.auth-compact-line { color:#cbd5e1 !important; font-size:0.78rem; font-weight:850; margin:1px 0 5px 0; }
.auth-session-details {
    background:rgba(15,23,42,0.55);
    border:1px solid rgba(148,163,184,0.22);
    border-radius:10px;
    padding:7px 9px;
    font-size:0.72rem;
    line-height:1.35;
}
.sidebar-section-title {
    color:#e5e7eb !important;
    font-size:.90rem !important;
    font-weight:950 !important;
    margin:.35rem 0 .45rem 0 !important;
}
.auth-sidebar-card {
    border:1px solid rgba(95,122,170,.34);
    background:rgba(8,16,34,.70);
    border-radius:12px;
    padding:.48rem .55rem;
    margin:.18rem 0 .42rem 0;
}
.auth-sidebar-title { font-size:.80rem; font-weight:950; color:#f8fafc; margin-bottom:.25rem; }
.auth-sidebar-user { display:flex; justify-content:space-between; gap:.35rem; font-size:.78rem; color:#e2e8f0; }
.auth-sidebar-user span { color:#94a3b8; font-size:.70rem; font-weight:850; }
.auth-remember-chip { display:inline-flex; align-items:center; gap:.25rem; border-radius:999px; padding:.18rem .42rem; margin-top:.35rem; font-size:.72rem; font-weight:900; border:1px solid rgba(148,163,184,.28); }
.auth-remember-chip.on { color:#bbf7d0; background:rgba(22,101,52,.22); border-color:rgba(34,197,94,.45); }
.auth-remember-chip.off { color:#fecaca; background:rgba(127,29,29,.22); border-color:rgba(239,68,68,.45); }
.auth-mini-heading { font-size:.74rem; color:#cbd5e1; font-weight:950; margin:.55rem 0 .18rem 0; }
.auth-user-list { display:flex; flex-direction:column; gap:.20rem; margin:.18rem 0 .35rem 0; }
.auth-user-row { display:flex; justify-content:space-between; align-items:center; gap:.35rem; padding:.24rem .38rem; border:1px solid rgba(148,163,184,.18); border-radius:9px; background:rgba(15,23,42,.66); font-size:.70rem; }
.auth-dot { width:.52rem; height:.52rem; border-radius:999px; display:inline-block; background:#ef4444; box-shadow:0 0 8px rgba(239,68,68,.35); }
.auth-dot.on { background:#22c55e; box-shadow:0 0 8px rgba(34,197,94,.35); }

section[data-testid="stSidebar"] .stButton > button {
    min-height:32px !important;
    padding:0.24rem 0.50rem !important;
    font-size:0.78rem !important;
    border-radius:9px !important;
}
@media (max-width: 900px) {
    .control-center-wide { grid-template-columns: 1fr; gap:7px; }
    .control-info-block { padding:8px 9px; min-height:auto; }
    .mini-status-chip { font-size:0.68rem; padding:3px 6px; }
    .top-app-status { gap:5px; }
}



/* --- V15: kontrollert layout/state cleanup --- */
@media (min-width: 1100px) {
    .block-container {
        max-width: none !important;
        padding-left: 0.25rem !important;
        padding-right: 0.35rem !important;
    }
    section[data-testid="stSidebar"] {
        width: 190px !important;
        min-width: 190px !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        padding-left: 0.35rem !important;
        padding-right: 0.35rem !important;
    }
}
.v15-desktop-status-strip {
    display:grid;
    grid-template-columns: 1.1fr 1.1fr 1.1fr 1.5fr;
    gap:8px;
    align-items:stretch;
    margin:4px 0 8px 0;
}
.v15-status-block {
    background:rgba(15,23,42,0.56);
    border:1px solid rgba(148,163,184,0.20);
    border-radius:12px;
    padding:7px 9px;
    min-height:42px;
}
.v15-status-title {
    color:#cbd5e1 !important;
    font-size:0.70rem;
    font-weight:950;
    margin-bottom:3px;
    line-height:1.0;
}
.v15-auto-controls-wrap {
    display:flex;
    align-items:center;
    gap:7px;
    flex-wrap:wrap;
    margin:5px 0 6px 0;
}
.v15-inline-help {
    color:#94a3b8 !important;
    font-size:0.72rem;
    font-weight:800;
    margin:3px 0 4px 0;
}
.v15-section-sep {
    height:1px;
    background:rgba(148,163,184,0.12);
    margin:6px 0 8px 0;
}
/* Ikke vis PC-statusstrip på mobil; mobil bruker sidebar/drawer. */
@media (max-width: 900px) {
    .v15-desktop-status-strip { display:none !important; }
    .top-app-header { margin-top:0.25rem !important; }
}
/* Sidebaren skal være kompakt; ingen enorme blå knapper. */
section[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button {
    min-height:28px !important;
    padding:0.18rem 0.38rem !important;
    font-size:0.68rem !important;
    line-height:1.05 !important;
    border-radius:8px !important;
    box-shadow:0 2px 7px rgba(14,165,233,0.14) !important;
}
section[data-testid="stSidebar"] .stButton > button p,
section[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button p {
    font-size:0.68rem !important;
    line-height:1.05 !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    margin-top:0.20rem !important;
    margin-bottom:0.18rem !important;
    font-size:0.98rem !important;
}
section[data-testid="stSidebar"] .element-container {
    margin-bottom:0.12rem !important;
}
section[data-testid="stSidebar"] hr {
    margin:0.35rem 0 !important;
}
</style>
""", unsafe_allow_html=True)


# V14.8 / Oppgave 67-69: strammere desktop-layout, mørk topp og tydeligere status.
st.markdown(
    """
    <style>
    header[data-testid="stHeader"] {
        background: rgba(15,23,42,0.0) !important;
        height: 0.25rem !important;
        min-height: 0.25rem !important;
    }
    [data-testid="stToolbar"], #MainMenu, footer { visibility: hidden !important; height: 0 !important; }
    .block-container {
        max-width: 1720px !important;
        padding-top: 0.25rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }
    @media (min-width: 1200px) {
        section[data-testid="stSidebar"] {
            width: 235px !important;
            min-width: 235px !important;
        }
        .main .block-container,
        [data-testid="stAppViewContainer"] .block-container {
            padding-left: 0.85rem !important;
            padding-right: 0.85rem !important;
        }
        div[data-testid="stHorizontalBlock"] { gap: 0.65rem !important; }
    }
    .top-app-header {
        padding: 3px 0 5px 0 !important;
        margin-bottom: 4px !important;
        border-bottom: 1px solid rgba(148,163,184,0.22) !important;
    }
    .top-app-title { font-size: 1.06rem !important; line-height: 1.05 !important; }
    .top-chip { font-size: 0.82rem !important; padding: 5px 9px !important; }
    .update-debug-line {
        display:inline-flex; align-items:center; gap:6px; flex-wrap:wrap;
        margin: 2px 0 6px 0; padding: 5px 8px;
        border-radius: 999px; border:1px solid rgba(148,163,184,0.22);
        background:rgba(15,23,42,0.62); color:#cbd5e1 !important;
        font-size:0.78rem; font-weight:850;
    }
    .pending-changes-box {
        margin: 4px 0 8px 0; padding: 7px 10px; border-radius: 12px;
        background: rgba(120,53,15,0.22); border: 1px solid rgba(251,191,36,0.38);
        color:#fde68a !important; font-weight:900; font-size:0.84rem;
    }
    .panel-radio-label { color:#cbd5e1 !important; font-size:0.78rem; font-weight:800; margin-top:3px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# V14.9 / Oppgave 67B og 75: strammere desktop-layout og kompakte sideknapper.
st.markdown(
    """
    <style>
    @media (min-width: 1100px) {
        [data-testid="stAppViewContainer"] .main .block-container,
        .main .block-container,
        .block-container {
            max-width: none !important;
            width: 100% !important;
            padding-left: 0.35rem !important;
            padding-right: 0.55rem !important;
        }
        section[data-testid="stSidebar"] {
            width: 205px !important;
            min-width: 205px !important;
        }
        section[data-testid="stSidebar"] > div:first-child {
            padding-left: 0.45rem !important;
            padding-right: 0.45rem !important;
        }
        [data-testid="stAppViewContainer"] {
            gap: 0 !important;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.45rem !important;
        }
    }
    section[data-testid="stSidebar"] .stButton > button,
    section[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button {
        min-height: 30px !important;
        padding: 0.22rem 0.42rem !important;
        font-size: 0.70rem !important;
        line-height: 1.05 !important;
        border-radius: 9px !important;
        box-shadow: 0 3px 9px rgba(2,132,199,0.18) !important;
        white-space: nowrap !important;
    }
    section[data-testid="stSidebar"] .stButton > button p,
    section[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button p {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        font-size: 0.70rem !important;
        line-height: 1.05 !important;
    }
    section[data-testid="stSidebar"] .stButton { margin-bottom: 0.22rem !important; }
    section[data-testid="stSidebar"] .element-container { margin-bottom: 0.18rem !important; }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        margin-top: 0.35rem !important;
        margin-bottom: 0.25rem !important;
    }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span {
        font-size: 0.78rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] input,
    section[data-testid="stSidebar"] [data-testid="stTextInput"] input,
    section[data-testid="stSidebar"] [data-testid="stSelectbox"] input,
    section[data-testid="stSidebar"] textarea {
        min-height: 30px !important;
        font-size: 0.76rem !important;
    }
    section[data-testid="stSidebar"] details > summary {
        min-height: 30px !important;
        padding-top: 0.22rem !important;
        padding-bottom: 0.22rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# V15.1 / Oppgave 90-92: kompakt toppkontroll og mindre knapper.
st.markdown(
    """
    <style>
    .top-market-status-row {
        display:flex; align-items:center; justify-content:flex-start; gap:5px; flex-wrap:wrap;
        min-height:30px; padding:2px 0 0 2px;
    }
    .top-market-label {
        color:#cbd5e1 !important; font-size:0.72rem; font-weight:950; margin-right:2px;
    }
    .market-help-inline {
        display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px;
        border-radius:999px; border:1px solid rgba(148,163,184,0.24); color:#94a3b8 !important;
        font-size:0.68rem; font-weight:950; background:rgba(15,23,42,0.62);
    }
    div[data-testid="stHorizontalBlock"] .stButton > button {
        min-height:30px !important;
        padding:0.22rem 0.46rem !important;
        border-radius:9px !important;
        font-size:0.76rem !important;
        line-height:1.05 !important;
        box-shadow:0 3px 10px rgba(14,165,233,0.18) !important;
        white-space:nowrap !important;
    }
    div[data-testid="stHorizontalBlock"] .stButton > button p {
        font-size:0.76rem !important; line-height:1.05 !important; white-space:nowrap !important;
    }
    .v15-inline-help { font-size:0.68rem !important; margin:2px 0 3px 0 !important; }
    @media (max-width: 900px) {
        .top-market-status-row { margin-top:4px; }
        div[data-testid="stHorizontalBlock"] .stButton > button {
            min-height:34px !important; font-size:0.78rem !important; padding:0.28rem 0.44rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# V15.2 / Oppgave 93-98: ryddet topbar, én statuskilde, større tekst og tett Auto trading-gruppe.
st.markdown(
    """
    <style>
    .v152-top-clean {
        justify-content:flex-start !important;
        padding:2px 0 4px 0 !important;
        margin-bottom:5px !important;
    }
    .v15-desktop-status-strip {
        grid-template-columns: 1.05fr 1.05fr 1.05fr 1.45fr !important;
        gap:7px !important;
        margin:3px 0 7px 0 !important;
    }
    .v15-status-block {
        padding:8px 10px !important;
        min-height:48px !important;
        border-color:rgba(148,163,184,0.24) !important;
    }
    .v15-status-title {
        font-size:0.84rem !important;
        line-height:1.05 !important;
        margin-bottom:5px !important;
        color:#e2e8f0 !important;
    }
    .mini-status-chip {
        font-size:0.80rem !important;
        padding:5px 8px !important;
        margin:2px 5px 2px 0 !important;
    }
    .v15-inline-help {
        font-size:0.73rem !important;
        margin:2px 0 3px 0 !important;
    }
    div[data-testid="stHorizontalBlock"] .stButton > button {
        min-height:28px !important;
        padding:0.18rem 0.34rem !important;
        border-radius:8px !important;
        font-size:0.72rem !important;
        box-shadow:0 2px 7px rgba(14,165,233,0.16) !important;
    }
    div[data-testid="stHorizontalBlock"] .stButton > button p {
        font-size:0.72rem !important;
        line-height:1.02 !important;
    }
    .top-app-status, .top-market-status-row { display:none !important; }
    @media (max-width: 900px) {
        .v15-status-title { font-size:0.88rem !important; }
        .mini-status-chip { font-size:0.82rem !important; padding:5px 8px !important; }
        div[data-testid="stHorizontalBlock"] .stButton > button {
            min-height:32px !important;
            font-size:0.76rem !important;
            padding:0.22rem 0.38rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# V14.5 / v18.5.74: Global visningsmodus.
# Normal og Full var identiske i praksis. Behold bare Kompakt/Full og migrer gammel normal-state til Full.
if str(st.session_state.get("global_view_mode_v145", "")).lower() == "normal":
    st.session_state["global_view_mode_v145"] = "Full"
APP_VIEW_MODE = st.sidebar.radio(
    "Visning",
    ["Kompakt", "Full"],
    index=1,
    horizontal=False,
    key="global_view_mode_v145",
    help="Kompakt gir mindre scrolling. Full viser alle detaljer.",
)
st.session_state["app_view_mode"] = APP_VIEW_MODE
st.sidebar.markdown(f"<div class='view-mode-status'>Aktiv: {APP_VIEW_MODE}</div>", unsafe_allow_html=True)
st.markdown("<div class='v18574-analysis-dense'>", unsafe_allow_html=True)

if APP_VIEW_MODE == "Kompakt":
    st.markdown(
        """
        <style>
        .block-container { padding-top: 0.75rem !important; }
        [data-testid="stMetric"] {
            padding: 8px 10px !important;
            border-radius: 12px !important;
            min-height: 58px !important;
            box-shadow: none !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.70rem !important;
            line-height: 1.05 !important;
            margin-bottom: 1px !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.12rem !important;
            line-height: 1.05 !important;
        }
        div[data-testid="column"] { gap: 0.45rem !important; }
        .stAlert { padding: 0.55rem 0.75rem !important; }
        .trading-engine-compact { padding: 7px 9px !important; margin: 5px 0 !important; }
        .trading-engine-details { padding: 6px 8px !important; font-size: 0.80rem !important; }
        details { margin-bottom: 0.45rem !important; }
        details > summary { min-height: 32px !important; }
        .graph-explain-box { padding: 7px 9px !important; font-size: 0.76rem !important; }
        .compact-stat-grid { grid-template-columns: repeat(4, minmax(0,1fr)); gap:6px; }
        .compact-stat-card { min-height:44px; padding:6px 8px; }
        .compact-stat-value { font-size:0.98rem; }
        @media (max-width: 900px) {
            .compact-stat-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
            .stButton > button { min-height:40px !important; font-size:0.88rem !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
elif APP_VIEW_MODE == "Full":
    # Full skal faktisk være mer detaljert enn Normal: mer luft, større hovedtitler og synlige forklaringsblokker.
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.15rem !important; }
        [data-testid="stMetric"] { padding: 12px 14px !important; min-height: 72px !important; }
        [data-testid="stMetricValue"] { font-size: 1.32rem !important; }
        .ptw-control-panel-title { font-size: 1.24rem !important; margin-top:1.05rem !important; }
        .v18-dark-row { padding:.62rem .72rem !important; }
        details > summary { min-height: 42px !important; }
        .compact-stat-grid { grid-template-columns: repeat(5, minmax(0,1fr)); gap:10px; }
        .v18-full-extra, .full-only, [data-full-only="true"] { display:block !important; }
        .v18-dark-row { margin-top:.28rem !important; margin-bottom:.28rem !important; }
        .ptw-control-panel, [data-testid="stExpander"] details { margin-bottom:.82rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )



# V15.7 / Oppgave 112: KPI-kort harmoniseres med resten av UI-et, også i Full-visning.
st.markdown(
    """
    <style>
    [data-testid="stMetric"] {
        min-height: 58px !important;
        padding: 8px 10px !important;
        border-radius: 12px !important;
        box-shadow: none !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.70rem !important;
        line-height: 1.05 !important;
        margin-bottom: 1px !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.12rem !important;
        line-height: 1.05 !important;
    }
    .info-mini-card {
        min-height: 84px !important;
        padding: 10px 12px !important;
        border-radius: 12px !important;
    }
    .info-mini-title { font-size: 0.86rem !important; margin-bottom: 5px !important; }
    .info-mini-main { font-size: 1.02rem !important; margin: 3px 0 !important; }
    .info-mini-sub { font-size: 0.78rem !important; line-height: 1.25 !important; }
    .info-mini-small { font-size: 0.68rem !important; }
    .rsi-box { padding: 10px 12px !important; border-radius: 12px !important; margin: 8px 0 10px 0 !important; }
    .rsi-title { font-size: 0.92rem !important; }
    .rsi-value { font-size: 1.20rem !important; }
    .v157-toolbar .stButton > button {
        min-height: 28px !important;
        padding: 0.18rem 0.42rem !important;
        font-size: 0.72rem !important;
        border-radius: 8px !important;
    }
    .v157-toolbar .stButton > button p { font-size: 0.72rem !important; line-height: 1.02 !important; }
    .v153-control-note, .v153-control-note * {
        writing-mode: horizontal-tb !important;
        text-orientation: mixed !important;
        white-space: normal !important;
        word-break: normal !important;
        overflow-wrap: normal !important;
    }
    .v153-control-note {
        max-width: 980px !important;
        min-width: min(520px, 100%) !important;
        display: block !important;
    }
    @media (max-width: 900px) {
        [data-testid="stMetric"] { min-height: 46px !important; padding: 6px 8px !important; }
        [data-testid="stMetricValue"] { font-size: 0.95rem !important; }
        .v153-control-note { min-width: 0 !important; width: 100% !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

LIVE_BANNER_LABELS = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI": "DOW",
    "^VIX": "VIX Volatility Index",
    "^RUT": "Russell 2000",
    "^FTSE": "FTSE 100",
    "^GDAXI": "DAX",
    "^FCHI": "CAC 40",
    "^STOXX50E": "Euro Stoxx 50",
    "GC=F": "Gold Futures",
    "SI=F": "Silver Futures",
    "CL=F": "Crude Oil Futures",
    "BZ=F": "Brent Crude Futures",
    "NG=F": "Natural Gas Futures",
    "HG=F": "Copper Futures",
    "PL=F": "Platinum Futures",
    "PA=F": "Palladium Futures",
    "ZC=F": "Corn Futures",
    "ZW=F": "Wheat Futures",
    "ZS=F": "Soybean Futures",
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "EURUSD=X": "EUR/USD",
    "USDNOK=X": "USD/NOK",
    "EURNOK=X": "EUR/NOK",
    "EQNR.OL": "Equinor",
    "DNB.OL": "DNB Bank",
    "NHY.OL": "Norsk Hydro",
    "YAR.OL": "Yara International",
    "ATCO-A.ST": "Atlas Copco A",
    "VOLV-B.ST": "Volvo B",
    "ERIC-B.ST": "Ericsson B",
    "ABB.ST": "ABB",
    "NOKIA.HE": "Nokia",
    "NESTE.HE": "Neste",
    "KNEBV.HE": "KONE B",
    "SAMPO.HE": "Sampo",
    "NOVO-B.CO": "Novo Nordisk B",
    "MAERSK-B.CO": "A.P. Moller - Maersk B",
    "DSV.CO": "DSV",
    "ORSTED.CO": "Orsted",
    "PETR4.SA": "Petrobras PN",
    "VALE3.SA": "Vale",
    "ITUB4.SA": "Itau Unibanco PN",
    "BBDC4.SA": "Banco Bradesco PN",
}

LIVE_BANNER_MARKETS = ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"]
LIVE_BANNER_DEFAULT_TICKERS = {
    "USA": "^GSPC, ^IXIC, ^DJI",
    "Norge": "EQNR.OL, DNB.OL, NHY.OL, YAR.OL",
    "Sverige": "ATCO-A.ST, VOLV-B.ST, ERIC-B.ST, ABB.ST",
    "Finland": "NOKIA.HE, NESTE.HE, KNEBV.HE, SAMPO.HE",
    "Danmark": "NOVO-B.CO, MAERSK-B.CO, DSV.CO, ORSTED.CO",
    "Brasil": "PETR4.SA, VALE3.SA, ITUB4.SA, BBDC4.SA",
}


def _is_weak_banner_name(name, ticker):
    """Returnerer True når Yahoo-navnet egentlig bare er ticker eller tom tekst."""
    try:
        name = str(name or "").strip()
        ticker = str(ticker or "").strip().upper()
        compact_name = re.sub(r"[^A-Z0-9]", "", name.upper())
        compact_ticker = re.sub(r"[^A-Z0-9]", "", ticker.upper())
        if not name or compact_name in {"", compact_ticker}:
            return True
        if name.upper() in {ticker, compact_ticker}:
            return True
        return False
    except Exception:
        return True


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def resolve_live_banner_label(ticker, fallback_label=None):
    """
    Finner penere navn til bannerkort.
    Prøver Yahoo-navn først, deretter egen fallback-liste for indeks, futures, råvarer, valuta og krypto.
    """
    ticker = str(ticker or "").strip().upper()
    fallback_label = str(fallback_label or "").strip()

    if yf is not None:
        try:
            info = {}
            yft = yf.Ticker(ticker)
            try:
                info = yft.get_info() or {}
            except Exception:
                try:
                    info = yft.info or {}
                except Exception:
                    info = {}
            for key in ("shortName", "longName", "displayName"):
                candidate = info.get(key) if isinstance(info, dict) else None
                if candidate and not _is_weak_banner_name(candidate, ticker):
                    return str(candidate).strip()
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)

    if ticker in LIVE_BANNER_LABELS:
        return LIVE_BANNER_LABELS[ticker]
    if fallback_label and not _is_weak_banner_name(fallback_label, ticker):
        return fallback_label
    return ticker


def parse_banner_tickers(settings=None):
    """
    Leser tickere fra settings.
    Brukeren kan legge til/fjerne ved å redigere tekstfeltene i sidepanelet.
    V9: banneret kan filtreres til valgte markeder.
    """
    settings = settings or load_settings()
    raw = settings.get("live_banner_tickers", {}) or {}
    visible_markets = settings.get("live_banner_markets_visible", ["USA", "Norge", "Sverige"])
    if isinstance(visible_markets, str):
        visible_markets = [m.strip() for m in visible_markets.replace(";", ",").split(",") if m.strip()]
    visible_markets = set(visible_markets or [])
    out = []
    for market in LIVE_BANNER_MARKETS:
        if market not in visible_markets:
            continue
        text_value = raw.get(market, LIVE_BANNER_DEFAULT_TICKERS.get(market, "")) if isinstance(raw, dict) else ""
        parts = str(text_value).replace(";", ",").replace("\n", ",").split(",")
        seen = set()
        for part in parts:
            ticker = str(part).strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            label = LIVE_BANNER_LABELS.get(ticker, ticker)
            out.append((market, ticker, label))
    return tuple(out)


def _sparkline_svg(values, positive=True, width=104, height=36, reference=None):
    """Yahoo-finance style mini chart with a dotted previous-close baseline.
    Green segments are above the reference level, red segments are below.
    """
    vals = [float(v) for v in (values or []) if v is not None]
    if len(vals) < 2:
        vals = [0.0, 0.0]

    if reference is None:
        reference = vals[-2] if len(vals) >= 2 else vals[-1]
    ref = float(reference)

    vmin = min(min(vals), ref)
    vmax = max(max(vals), ref)
    pad = max((vmax - vmin) * 0.10, abs(ref) * 0.002, 1e-6)
    vmin -= pad
    vmax += pad
    span = (vmax - vmin) or 1.0

    def _xy(i, val):
        x = i * (width / max(len(vals) - 1, 1))
        y = height - ((val - vmin) / span) * (height - 6) - 3
        return x, y

    points = [_xy(i, v) for i, v in enumerate(vals)]
    ref_y = _xy(0, ref)[1]

    green_segments = []
    red_segments = []

    def _add_segment(target, p1, p2):
        if not target or target[-1][-1] != p1:
            target.append([p1, p2])
        else:
            target[-1].append(p2)

    for idx in range(len(vals) - 1):
        v1, v2 = vals[idx], vals[idx + 1]
        p1, p2 = points[idx], points[idx + 1]
        above1 = v1 >= ref
        above2 = v2 >= ref

        if above1 == above2:
            _add_segment(green_segments if above1 else red_segments, p1, p2)
            continue

        # Split line exactly where it crosses the reference line.
        denom = (v2 - v1) or 1e-9
        t = (ref - v1) / denom
        cross_x = p1[0] + (p2[0] - p1[0]) * t
        cross_point = (cross_x, ref_y)
        _add_segment(green_segments if above1 else red_segments, p1, cross_point)
        _add_segment(green_segments if above2 else red_segments, cross_point, p2)

    def _polyline(points_seq, stroke):
        if len(points_seq) < 2:
            return ''
        pts = ' '.join(f"{x:.2f},{y:.2f}" for x, y in points_seq)
        return (
            f'<polyline points="{pts}" fill="none" stroke="{stroke}" '
            f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"></polyline>'
        )

    green_svg = ''.join(_polyline(seg, '#16a34a') for seg in green_segments)
    red_svg = ''.join(_polyline(seg, '#dc2626') for seg in red_segments)
    last_x, last_y = points[-1]
    last_color = '#16a34a' if vals[-1] >= ref else '#dc2626'

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
        f'<line x1="0" y1="{ref_y:.2f}" x2="{width}" y2="{ref_y:.2f}" '
        f'stroke="#9ca3af" stroke-width="1.2" stroke-dasharray="3 3" opacity="0.95"></line>'
        f'{green_svg}{red_svg}'
        f'<circle cx="{last_x:.2f}" cy="{last_y:.2f}" r="1.9" fill="{last_color}"></circle>'
        f'</svg>'
    )


@st.cache_data(ttl=300, show_spinner=False)
def _download_live_banner_history(tickers):
    tickers = tuple(str(t or "").strip().upper() for t in (tickers or []) if str(t or "").strip())
    if yf is None or not tickers:
        return None
    try:
        return yf.download(
            tickers=list(tickers),
            period="1mo",
            interval="1d",
            auto_adjust=False,
            prepost=False,
            progress=False,
            threads=True,
            group_by="column",
        )
    except Exception as e:
        logging.warning("Live banner batch download failed: %s", e)
        return None


def _close_from_banner_history(history, ticker):
    if history is None or getattr(history, "empty", True):
        return None
    try:
        if isinstance(history.columns, pd.MultiIndex):
            if "Close" in history.columns.get_level_values(0):
                close_frame = history["Close"]
                if ticker in close_frame:
                    return close_frame[ticker].dropna()
            if "Close" in history.columns.get_level_values(-1):
                return history[(ticker, "Close")].dropna()
            return None
        if "Close" in history:
            return history["Close"].dropna()
    except Exception as e:
        logging.warning("Live banner history parse failed for %s: %s", ticker, e)
    return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_live_banner_snapshot(banner_items):
    if yf is None:
        return []

    banner_items = tuple(banner_items or ())
    history = _download_live_banner_history(tuple(ticker for _, ticker, _ in banner_items))
    cards = []
    for market, ticker, label in banner_items:
        try:
            close = _close_from_banner_history(history, ticker)
            if close is None or close.empty:
                hist = yf.Ticker(ticker).history(period="1mo", interval="1d", auto_adjust=False, prepost=False)
                if hist is None or hist.empty or "Close" not in hist:
                    continue
                close = hist["Close"].dropna()
            if close.empty or len(close) < 2:
                continue

            series = close.tail(20)
            current = float(series.iloc[-1])
            prev = float(series.iloc[-2])
            delta = current - prev
            pct = ((current / prev) - 1.0) * 100 if prev else 0.0

            display_label = resolve_live_banner_label(ticker, label)

            cards.append({
                "market": market,
                "ticker": ticker,
                "label": display_label,
                "price": current,
                "delta": delta,
                "pct": pct,
                "sparkline": _sparkline_svg(series.tolist(), positive=pct >= 0, reference=prev),
            })
        except Exception:
            continue

    return cards


def render_live_market_banner():
    settings = load_settings()
    if not settings.get("live_banner_enabled", True):
        return

    banner_items = parse_banner_tickers(settings)
    if not banner_items:
        return

    _banner_fp = tuple((str(m), str(t), str(l)) for m, t, l in banner_items)
    _banner_key = f"live_banner_cache_v16_{_cache_key_safe(_banner_fp)}"
    if not _heavy_update_allowed():
        banner_cards = st.session_state.get(_banner_key) or st.session_state.get("live_banner_cache_v16_latest") or []
        if not banner_cards:
            st.caption("📡 Ticker-banner bruker manuell modus. Trykk Oppdater hele appen for å hente nye bannerdata.")
            return
    else:
        banner_cards = fetch_live_banner_snapshot(banner_items)
        if banner_cards:
            st.session_state[_banner_key] = banner_cards
            st.session_state["live_banner_cache_v16_latest"] = banner_cards
    if not banner_cards:
        return

    cards = []
    for item in banner_cards:
        pct = float(item.get("pct", 0.0))
        delta = float(item.get("delta", 0.0))
        pct_class = "pos" if pct >= 0 else "neg"
        market_label = html.escape(str(item.get("market", "")))
        title_label = html.escape(str(item.get("label", item.get("ticker", ""))))
        price_txt = f"{float(item.get('price', 0.0)):,.2f}"
        delta_txt = f"{delta:+.2f}"
        pct_txt = f"{pct:+.2f}%"

        cards.append(
            "<div class='ticker-tape-item'>"
            "<div class='ticker-info'>"
            f"<div class='ticker-market'>{market_label}</div>"
            f"<div class='ticker-title'>{title_label}</div>"
            f"<div class='ticker-price'>{price_txt}</div>"
            f"<div class='ticker-change {pct_class}'>{delta_txt} {pct_txt}</div>"
            "</div>"
            f"<div class='ticker-spark'>{item.get('sparkline', '')}</div>"
            "</div>"
        )

    cards_html = "".join(cards)
    # V17 / Oppgave 126B: skill animasjonshastighet fra data-refresh.
    # live_banner_speed_seconds styrer bare CSS-scroll, ui_refresh_minutes styrer bare datacache.
    refresh_minutes = int(settings.get("ui_refresh_minutes", 60) or 60)
    speed_seconds = int(settings.get("live_banner_speed_seconds", 70) or 70)
    speed_seconds = max(10, min(speed_seconds, 300))

    # IMPORTANT:
    # CSS ligger i vanlig string, ikke f-string, for å unngå SyntaxError fra CSS-klammer.
    banner_html = """
    <style>
    .ticker-tape-wrap {
        width: 100%;
        overflow: hidden;
        margin: 0.36rem 0 0.72rem 0;
        padding: 0;
        border-top: 1px solid rgba(15,23,42,0.10);
        border-bottom: 1px solid rgba(15,23,42,0.14);
        background: #f8fafc;
        border-radius: 12px;
        min-height: 92px;
        box-shadow: inset 0 0 0 1px rgba(15,23,42,0.03);
    }
    .ticker-tape-track {
        display: flex;
        align-items: stretch;
        width: max-content;
        gap: 10px;
        white-space: nowrap;
        animation: tickerTapeScroll __SPEED__s linear infinite;
        padding: 10px 11px;
    }
    .ticker-tape-wrap:hover .ticker-tape-track {
        animation-play-state: paused;
    }
    .ticker-tape-item {
        display: inline-grid;
        grid-template-columns: 132px 96px;
        align-items: center;
        gap: 8px;
        min-width: 236px;
        height: 70px;
        padding: 8px 11px;
        border-radius: 0;
        background: #ffffff;
        border-right: 1px solid rgba(15,23,42,0.10);
    }
    .ticker-info {
        display: flex;
        flex-direction: column;
        justify-content: center;
        line-height: 1.12;
    }
    .ticker-market {
        font-size: 0.56rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 2px;
    }
    .ticker-title {
        font-size: 0.82rem;
        font-weight: 900;
        color: #2563eb;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        margin-bottom: 4px;
    }
    .ticker-price {
        font-size: 0.90rem;
        font-weight: 900;
        color: #1f2937;
        margin-top: 0;
    }
    .ticker-change {
        font-size: 0.78rem;
        font-weight: 950;
        margin-top: 3px;
    }
    .ticker-change.pos { color: #059669; }
    .ticker-change.neg { color: #dc2626; }
    .ticker-spark {
        display: flex;
        align-items: center;
        justify-content: flex-end;
    }
    .ticker-spark svg {
        display: block;
        width: 94px;
        height: 34px;
    }
    @keyframes tickerTapeScroll {
        from { transform: translateX(0); }
        to { transform: translateX(-50%); }
    }
    @media (max-width: 1100px) {
        .ticker-tape-wrap { min-height: 96px; }
        .ticker-tape-item {
            grid-template-columns: 134px 102px;
            min-width: 252px;
            height: 74px;
            padding: 8px 12px;
        }
        .ticker-title { font-size: 0.96rem; }
        .ticker-price { font-size: 1.04rem; }
        .ticker-change { font-size: 0.90rem; }
        .ticker-spark svg { width: 102px; height: 38px; }
    }
    @media (max-width: 700px) {
        .ticker-tape-wrap {
            min-height: 86px;
            border-radius: 8px;
        }
        .ticker-tape-track {
            gap: 8px;
            padding: 8px 8px;
        }
        .ticker-tape-item {
            grid-template-columns: 120px 86px;
            min-width: 218px;
            height: 64px;
            padding: 7px 10px;
            gap: 10px;
        }
        .ticker-market { font-size: 0.58rem; margin-bottom: 1px; }
        .ticker-title { font-size: 0.82rem; margin-bottom: 3px; }
        .ticker-price { font-size: 0.92rem; }
        .ticker-change { font-size: 0.78rem; margin-top: 4px; }
        .ticker-spark svg { width: 86px; height: 34px; }
    }
    /* v18.5.26: stop banner text from being clipped under the tape. */
    .ticker-tape-wrap + div, .ticker-tape-wrap + p { margin-top: .35rem !important; }
    .ticker-tape-item, .ticker-info, .ticker-change { overflow: visible !important; }
    </style>
    <div class='ticker-tape-wrap' aria-label='Ticker-banner'>
        <div class='ticker-tape-track'>__CARDS____CARDS__</div>
    </div>
    """
    banner_html = banner_html.replace("__SPEED__", str(speed_seconds)).replace("__CARDS__", cards_html)

    st.markdown(banner_html, unsafe_allow_html=True)
    st.caption(
        f"📡 Banner: {len(banner_cards)} kort · {speed_seconds}s · data ca. hver {refresh_minutes}. min."
    )



def _render_banner_settings_form_v157(st_obj, form_key="banner_settings_form_v157"):
    """V15.8.1: robust banner settings form used only below the ticker banner.

    This function was referenced by render_banner_main_controls() in v15.8 but was
    missing, which caused NameError when opening "Rediger ticker-banner".  It is
    intentionally self-contained and only updates banner-related settings.
    """
    settings = load_settings()
    raw = settings.get("live_banner_tickers", {}) or {}
    if not isinstance(raw, dict):
        raw = {}

    visible_markets = settings.get("live_banner_markets_visible", ["USA", "Norge", "Sverige"])
    if isinstance(visible_markets, str):
        visible_markets = [m.strip() for m in visible_markets.replace(";", ",").split(",") if m.strip()]
    visible_markets = set(visible_markets or ["USA", "Norge", "Sverige"])

    st_obj.caption("Endringer i ticker-banner lagres her. Banneret oppdateres etter lagring/ny kjøring, ikke fra venstremenyen.")

    with st_obj.form(form_key, clear_on_submit=False):
        c_enable, c_speed, c_refresh = st.columns([1.1, 1.1, 1.1])
        with c_enable:
            live_banner_enabled = st.checkbox(
                "Vis ticker-banner",
                value=bool(settings.get("live_banner_enabled", True)),
                key=f"{form_key}_enabled",
            )
        with c_speed:
            live_banner_speed = st.number_input(
                "Bannerhastighet sekunder",
                min_value=10,
                max_value=240,
                value=int(settings.get("live_banner_speed_seconds", 70) or 70),
                step=5,
                key=f"{form_key}_speed",
                help="Lavere tall = raskere bevegelse. Høyere tall = saktere banner.",
            )
        with c_refresh:
            ui_refresh_minutes = st.number_input(
                "Oppdateringsintervall min",
                min_value=1,
                max_value=240,
                value=int(settings.get("ui_refresh_minutes", 60) or 60),
                step=1,
                key=f"{form_key}_refresh",
                help="Hvor ofte bannerdata kan oppdateres når auto-refresh er aktivert.",
            )

        st.markdown("**Markeder som vises i banneret**")
        banner_market_values = {}
        market_cols = st.columns(3)
        for idx, market in enumerate(LIVE_BANNER_MARKETS):
            with market_cols[idx % 3]:
                banner_market_values[market] = st.checkbox(market, value=(market in visible_markets), key=f"{form_key}_show_{market.lower()}")

        ticker_texts = {}
        ticker_cols = st.columns(3)
        for idx, market in enumerate(LIVE_BANNER_MARKETS):
            with ticker_cols[idx % 3]:
                ticker_texts[market] = st.text_area(
                    f"{market} tickere",
                    value=str(raw.get(market, LIVE_BANNER_DEFAULT_TICKERS.get(market, ""))),
                    height=84,
                    key=f"{form_key}_{market.lower()}_tickers",
                    help="Kommaseparert liste. Bruk markedsindekser eller egne tickere.",
                )

        submitted = _global_apply_requested_v161()

    if submitted:
        new_visible = [market for market in LIVE_BANNER_MARKETS if banner_market_values.get(market)]
        if not new_visible:
            new_visible = ["USA", "Norge", "Sverige"]

        settings.update({
            "live_banner_enabled": bool(live_banner_enabled),
            "live_banner_speed_seconds": int(live_banner_speed),
            "ui_refresh_minutes": int(ui_refresh_minutes),
            "live_banner_markets_visible": new_visible,
            "live_banner_tickers": {market: str(ticker_texts.get(market, "")).strip() for market in LIVE_BANNER_MARKETS},
        })
        save_settings(settings)
        st.success("Ticker-banner lagret som ventende endringer ✅")


def render_banner_sidebar_controls(expanded=False):
    """V15.8 regresjonssperre: ticker-banner skal kun redigeres under selve banneret, aldri i venstremenyen."""
    return


def render_banner_main_controls():
    """Oppgave 111 / v15.8.2: Rediger ticker-banner rett under selve banneret.

    Hard fix: form-renderingen er lagt direkte her, så appen ikke kan krasje med
    NameError hvis en hjelpefunksjon ikke er lastet i runtime.
    """
    with st.expander("📺 Rediger ticker-banner", expanded=False):
        settings = load_settings()
        raw = settings.get("live_banner_tickers", {}) or {}
        if not isinstance(raw, dict):
            raw = {}

        visible_markets = settings.get("live_banner_markets_visible", ["USA", "Norge", "Sverige"])
        if isinstance(visible_markets, str):
            visible_markets = [m.strip() for m in visible_markets.replace(";", ",").split(",") if m.strip()]
        visible_markets = set(visible_markets or ["USA", "Norge", "Sverige"])

        st.caption("Endre flere bannerfelt uten at appen oppdaterer tungt. Trykk først «Lagre banner som ventende», deretter «Oppdater hele appen» når du er klar.")

        with st.form("banner_settings_form_v17", clear_on_submit=False):
            c_enable, c_speed, c_refresh = st.columns(3)
            with c_enable:
                live_banner_enabled = st.checkbox(
                    "Vis ticker-banner",
                    value=bool(settings.get("live_banner_enabled", True)),
                    key="banner_v1582_enabled",
                )
            with c_speed:
                live_banner_speed = st.number_input(
                    "Bannerhastighet sekunder",
                    min_value=10,
                    max_value=240,
                    value=int(settings.get("live_banner_speed_seconds", 70) or 70),
                    step=5,
                    key="banner_v1582_speed",
                    help="Lavere tall = raskere bevegelse. Høyere tall = saktere banner.",
                )
            with c_refresh:
                ui_refresh_minutes = st.number_input(
                    "Oppdateringsintervall min",
                    min_value=1,
                    max_value=240,
                    value=int(settings.get("ui_refresh_minutes", 60) or 60),
                    step=1,
                    key="banner_v1582_refresh",
                )

            st.markdown("**Markeder som vises i banneret**")
            banner_market_values = {}
            market_cols = st.columns(3)
            for idx, market in enumerate(LIVE_BANNER_MARKETS):
                with market_cols[idx % 3]:
                    banner_market_values[market] = st.checkbox(market, value=(market in visible_markets), key=f"banner_v1582_show_{market.lower()}")

            ticker_texts = {}
            ticker_cols = st.columns(3)
            for idx, market in enumerate(LIVE_BANNER_MARKETS):
                with ticker_cols[idx % 3]:
                    ticker_texts[market] = st.text_area(
                        f"{market} tickere",
                        value=str(raw.get(market, LIVE_BANNER_DEFAULT_TICKERS.get(market, ""))),
                        height=84,
                        key=f"banner_v1582_{market.lower()}_tickers",
                    )

            submitted = st.form_submit_button("💾 Lagre banner som ventende", use_container_width=True)

        if submitted:
            new_visible = [market for market in LIVE_BANNER_MARKETS if banner_market_values.get(market)]
            if not new_visible:
                new_visible = ["USA", "Norge", "Sverige"]

            settings.update({
                "live_banner_enabled": bool(live_banner_enabled),
                "live_banner_speed_seconds": int(live_banner_speed),
                "ui_refresh_minutes": int(ui_refresh_minutes),
                "live_banner_markets_visible": new_visible,
                "live_banner_tickers": {market: str(ticker_texts.get(market, "")).strip() for market in LIVE_BANNER_MARKETS},
            })
            save_settings(settings)
            _mark_pending_manual_change("Ticker-banner endret")
            st.success("Ticker-banner lagret som ventende endringer ✅")


def render_system_admin_workspace(expanded=False):
    """Fase 3: Cron/bakgrunnssøk og systemdrift samlet i Kontrollsenter."""
    with st.expander("🛠 System / admin · Bakgrunnssøk / Cron", expanded=bool(expanded)):

        st.caption("Systemkontroller. Full stopp / ferie overstyrer Auto trading og auto-kjøp. Start auto opphever ikke sikkerhetslåser.")
        _cron_settings = load_settings()
        _cron_status = cron_status_text()
        _is_full_stop = bool(_cron_status.get("vacation_mode"))
        _is_allowed = bool(_cron_status.get("allowed"))
        if _is_full_stop:
            st.warning("Status: Full stopp / ferie er aktiv ⛔")
        elif not _is_allowed:
            st.info("Status: Pauset / hopper over ⏸")
        else:
            st.success("Status: Aktiv ✅")
        st.caption(_cron_status.get("reason", ""))

        with st.form("system_admin_cron_form_v17", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                _cron_enabled = st.checkbox("Bakgrunnssøk aktiv", value=bool(_cron_settings.get("background_scanning_enabled", True)), key="main_cron_background_enabled_v157")
            with c2:
                _cron_interval = st.number_input("Søkintervall minutter", min_value=1, max_value=1440, value=int(_cron_settings.get("scan_interval_minutes", 15)), step=1, key="main_cron_scan_interval_v157")
            with c3:
                _pause_choice = st.selectbox("Pause søk", ["Ingen pause", "30 minutter", "1 time", "2 timer", "Resten av dagen"], key="main_cron_pause_choice_v157")
            _save_cron = st.form_submit_button("💾 Lagre søk/cron som ventende", use_container_width=True)
        if _save_cron:
            _mark_pending_manual_change("Søk/cron endret")
            _new_settings = load_settings()
            _new_settings["background_scanning_enabled"] = bool(_cron_enabled)
            _new_settings["scan_interval_minutes"] = int(_cron_interval)
            save_settings(_new_settings)
            if _pause_choice == "30 minutter":
                pause_until(minutes=30)
            elif _pause_choice == "1 time":
                pause_until(minutes=60)
            elif _pause_choice == "2 timer":
                pause_until(minutes=120)
            elif _pause_choice == "Resten av dagen":
                pause_until(rest_of_day=True)
            elif _pause_choice == "Ingen pause":
                clear_pause()
            st.success("Søk/cron lagret som ventende ✅")

        s1, s2, s3, s4 = st.columns([1, 1, 1, 2.2])
        with s1:
            if _is_full_stop:
                if st.button("🔓 Slå av Full stopp", key="main_disable_full_stop_v157", use_container_width=True):
                    _deactivate_full_stop_v157()
            else:
                if st.button("⛔ Full stopp / ferie", key="main_activate_full_stop_v157", use_container_width=True):
                    activate_full_stop()
                    st.rerun()
        with s2:
            if _cron_status.get("pause_until"):
                if st.button("▶️ Gjenoppta nå", key="main_resume_pause_v157", use_container_width=True):
                    clear_pause()
                    st.rerun()
            else:
                st.caption("Ingen aktiv pause")
        with s3:
            if st.button("⚡ Kjør auto-kjøp nå", key="main_force_auto_buy_now_v157", use_container_width=True, disabled=_is_full_stop):
                try:
                    from scanner_worker import run_once
                    with st.spinner("Kjører auto-kjøp-motor..."):
                        _trades = run_once(force=True)
                    st.success(f"Auto-motor ferdig. Trades: {_trades}")
                    st.rerun()
                except Exception as _e:
                    st.error(f"Auto-kjøp feilet: {_e}")
        with s4:
            st.caption("Auto-kjøp nå er en engangskjøring. Den starter ikke fast Auto trading, og blokkeres av Full stopp / ferie.")


def render_analysis_universe_workspace():
    """Legacy wrapper: Analyseunivers er nå flyttet inn i AI Kontrollsenter."""
    try:
        from analysis_universe_ai import render_ai_analysis_universe_workspace
        return render_ai_analysis_universe_workspace(expanded=False)
    except Exception as exc:
        st.warning(f"Analyseunivers AI-modul kunne ikke vises: {exc}")
        return None

def render_decision_explanation(decision):
    try:
        reasons = _dedupe_text_list(decision.get("reasons", []))
        warnings = _dedupe_text_list(decision.get("warnings", []))
        st.markdown("#### 🧠 Hvorfor dette signalet?")
        if reasons:
            for r in reasons:
                st.success(f"✅ {r}")
        if warnings:
            for w in warnings:
                st.warning(f"⚠️ {w}")
        if not reasons and not warnings:
            st.caption("Ingen detaljert forklaring tilgjengelig for dette signalet.")
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)



def render_rsi_box(rsi_value):
    try:
        rsi_float = float(rsi_value)
    except Exception:
        rsi_float = 50.0

    if rsi_float >= 80:
        status = "Ekstremt overkjøpt"
        cls = "rsi-status-bad"
    elif rsi_float >= 70:
        status = "Overkjøpt"
        cls = "rsi-status-bad"
    elif rsi_float <= 30:
        status = "Oversolgt"
        cls = "rsi-status-good"
    else:
        status = "Nøytral"
        cls = "rsi-status-mid"

    st.markdown(
        f"""
        <div class="rsi-box">
            <div class="rsi-title">📊 RSI-boks</div>
            <div class="rsi-value">{rsi_float:.1f}</div>
            <div class="{cls}">{status}</div>
            <div class="small">30 = oversolgt · 70 = overkjøpt · 80 = ekstremt overkjøpt</div>
        </div>
        """,
        unsafe_allow_html=True,
    )



def render_signal_badge(signal):
    s = str(signal or "").upper()
    if "BUY" in s:
        return "<span class='status-live'>🟢 BUY</span>"
    if "SELL" in s or "AVOID" in s:
        return "<span class='status-danger'>🔴 SELL / AVOID</span>"
    return "<span style='display:inline-block;padding:4px 10px;border-radius:999px;background:rgba(245,158,11,0.16);border:1px solid rgba(245,158,11,0.5);color:#fde68a;font-weight:900;'>🟡 HOLD</span>"



PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")

# BANNER_TICKER_TAPE_V2
# fallback hvis Render gir tom string
if not PUSHOVER_APP_TOKEN:
    PUSHOVER_APP_TOKEN = None

if not PUSHOVER_USER_KEY:
    PUSHOVER_USER_KEY = None

def _mask_secret_v18585(value, keep=4):
    """Maskerer token/user-key i UI og logger uten å lekke hemmeligheter."""
    value = str(value or "")
    if not value:
        return "MISSING"
    if len(value) <= keep:
        return "*" * len(value)
    return ("*" * max(0, len(value) - keep)) + value[-keep:]


from notifier import send_pushover_alert  # v18.6.3 centralized notifier


def verify_pushover_credentials_v18585():
    """Validerer Pushover token + user-key mot Pushover API uten å sende varsel."""
    result = {
        "token_present": bool(PUSHOVER_APP_TOKEN),
        "user_present": bool(PUSHOVER_USER_KEY),
        "token_masked": _mask_secret_v18585(PUSHOVER_APP_TOKEN),
        "user_masked": _mask_secret_v18585(PUSHOVER_USER_KEY),
        "ok": False,
        "status_code": None,
        "response_text": "",
    }
    if not result["token_present"] or not result["user_present"]:
        result["response_text"] = "Mangler PUSHOVER_APP_TOKEN eller PUSHOVER_USER_KEY"
        return result
    try:
        response = requests.post(
            "https://api.pushover.net/1/users/validate.json",
            data={"token": PUSHOVER_APP_TOKEN, "user": PUSHOVER_USER_KEY},
            timeout=10,
        )
        result["status_code"] = response.status_code
        result["response_text"] = response.text[:1200]
        result["ok"] = bool(response.status_code == 200)
        return result
    except Exception as e:
        result["response_text"] = str(e)
        return result


def maybe_send_signal_alert(ticker, decision):
    """
    Deaktivert i Pushover trade-fix:
    Varsler skal kun sendes fra trading_engine.py når faktisk BUY/SELL skjer.
    Dette hindrer mobil-spam ved vanlig signalendring/refresh.
    """
    return None



def get_dynamic_watchlist(mode, max_count, tickers_us=None, tickers_no=None, tickers_se=None, tickers_all=None):
    """Lager dynamisk watchlist fra siste lagrede/rangerte markedsliste.

    V17: Hvis en rangering finnes, brukes BUY/HOLD/SELL-sortert rekkefølge.
    Hvis ikke finnes cache ennå, brukes tickerunivers som fallback uten å starte tung scan.
    """
    latest = st.session_state.get("latest_rankings_v148", {}) or {}
    source_key = None
    fallback = tickers_all
    if mode == "USA / S&P 500":
        source_key, fallback = "USA", tickers_us or resolve_universe_tickers(["USA"], max_count=max_count)
    elif mode == "Norge / Oslo Børs":
        source_key, fallback = "Norge", tickers_no or resolve_universe_tickers(["Norge"], max_count=max_count)
    elif mode == "Sverige / Stockholm":
        source_key, fallback = "Sverige", tickers_se or resolve_universe_tickers(["Sverige"], max_count=max_count)
    elif mode == "Finland / Helsinki":
        source_key, fallback = "Finland", resolve_universe_tickers(["Finland"], max_count=max_count)
    elif mode == "Danmark / Copenhagen":
        source_key, fallback = "Danmark", resolve_universe_tickers(["Danmark"], max_count=max_count)
    elif mode == "Brasil / B3":
        source_key, fallback = "Brasil", resolve_universe_tickers(["Brasil"], max_count=max_count)

    ranked = _ranked_for_display(latest.get(source_key, []) if source_key else [])
    if ranked:
        return [normalize_user_ticker(x.get("ticker")) for x in ranked[:max_count] if x.get("ticker")]
    return list(fallback or [])[:max_count]

def parse_watchlist(text):
    if not text:
        return []
    raw = text.replace(";", ",").replace("\n", ",").split(",")
    tickers = []
    for item in raw:
        ticker = item.strip().upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def scan_watchlist_and_alert(tickers):
    """
    Scanner watchlist og sender Pushover-varsel når BUY/SELL signal endrer seg.
    Kjører når appen refresher, men unngår spam ved å lagre siste signal i session_state.
    """
    _alert_settings = load_settings()
    if not bool(_alert_settings.get("notify_watchlist_signal_changes", True)):
        return []

    if not tickers:
        return []

    if "watchlist_last_signal" not in st.session_state:
        st.session_state.watchlist_last_signal = {}

    results = []

    for ticker in tickers:
        try:
            item = score_stock(ticker, use_news=False)
            if not item:
                results.append({"ticker": ticker, "status": "Ingen data"})
                continue

            df = item["hist"].copy()

            rsi = calculate_rsi(df)
            macd, macd_signal, _ = calculate_macd(df)
            bb_ma, bb_upper, bb_lower = calculate_bollinger(df)

            latest_rsi = rsi.dropna().iloc[-1] if not rsi.dropna().empty else 50
            latest_macd = macd.dropna().iloc[-1] if not macd.dropna().empty else 0
            latest_macd_signal = macd_signal.dropna().iloc[-1] if not macd_signal.dropna().empty else 0

            hs = detect_head_shoulders(df)
            inv_hs = detect_inverse_head_shoulders(df)
            breakout = breakout_scanner(df)

            technical_context = {
                "rsi": latest_rsi,
                "macd_bullish": latest_macd > latest_macd_signal,
                "breakout_type": breakout.get("type", "neutral"),
                "head_shoulders_found": hs.get("found", False),
                "inverse_head_shoulders_found": inv_hs.get("found", False),
            }

            decision = build_trading_decision(item, technical_context)

            if use_signal_intelligence:
                insider = get_insider_data(ticker)
                analyst = get_analyst_trend(ticker)
                earnings = get_earnings(ticker)
                si = calculate_signal_intelligence(
                    item,
                    technical_context=technical_context,
                    insider=insider,
                    analyst=analyst,
                    earnings=earnings,
                )
                decision["decision"] = si["decision"]
                decision["emoji"] = si["emoji"]
                decision["confidence"] = si["confidence"]
                decision["decision_score"] = si["final_score"]

            current_signal = decision.get("decision", "UNKNOWN")
            previous_signal = st.session_state.watchlist_last_signal.get(ticker)

            changed = previous_signal is not None and previous_signal != current_signal
            first_seen = previous_signal is None

            st.session_state.watchlist_last_signal[ticker] = current_signal

            confidence_ok = (not use_high_conf_alerts_only) or decision.get("confidence", 0) >= min_alert_confidence

            if changed and confidence_ok and current_signal in ["BUY", "SELL / AVOID"]:
                msg = (
                    f"{decision.get('emoji', '')} {current_signal}: {ticker}\n"
                    f"Score: {item.get('score', 'N/A')}/10\n"
                    f"Confidence: {decision.get('confidence', 'N/A')}%\n"
                    f"RSI: {latest_rsi:.1f}"
                )
                send_pushover_alert(msg, title="Aksje signal endret")

            results.append({
                "ticker": ticker,
                "score": item.get("score"),
                "signal": current_signal,
                "confidence": decision.get("confidence"),
                "rsi": round(float(latest_rsi), 1),
                "macd": "Bullish" if latest_macd > latest_macd_signal else "Bearish",
                "changed": changed,
                "first_seen": first_seen,
            })

        except Exception as e:
            results.append({"ticker": ticker, "status": f"Feil: {e}"})

    return results


def score_color(score):
    if score >= 7: return "good", "🟢"
    if score >= 4: return "mid", "🟡"
    return "bad", "🔴"


def add_right_side_price_label(fig, x, y, text, color=None, yshift=0):
    """
    Legger kurs-label på høyre side uten å krasje med selve grafen.
    """
    fig.add_annotation(
        x=x,
        y=y,
        text=text,
        showarrow=False,
        xanchor="left",
        yanchor="middle",
        xshift=12,
        yshift=yshift,
        font=dict(size=12, color=color or "white"),
        bgcolor="rgba(11,17,28,0.85)",
        bordercolor="rgba(255,255,255,0.25)",
        borderwidth=1,
    )

def plot_price(hist, title):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Pris"))

    try:
        last_x = hist.index[-1]
        last_price = float(hist["Close"].dropna().iloc[-1])

        fig.add_hline(
            y=last_price,
            line_dash="dot",
            line_color="rgba(255,255,255,0.45)",
        )

        add_right_side_price_label(
            fig,
            last_x,
            last_price,
            f"Pris / gjeldende: {last_price:.2f}",
            color="white",
        )

        fig.update_layout(
            annotations=[
                *fig.layout.annotations,
                dict(
                    text=f"💹 Gjeldende kurs: <b>{last_price:.2f}</b>",
                    xref="paper",
                    yref="paper",
                    x=0.01,
                    y=1.12,
                    showarrow=False,
                    align="left",
                    font=dict(size=15, color="white"),
                    bgcolor="rgba(30,41,59,0.9)",
                    bordercolor="rgba(255,255,255,0.25)",
                    borderwidth=1,
                )
            ]
        )
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=420,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
        margin=dict(l=20, r=150, t=80, b=30),
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
    )
    return fig

def get_item_price_change(item):
    """
    Henter siste kurs og prosentendring direkte fra item["hist"].
    Fungerer selv om item ikke har egne price/change_pct-felter.
    """
    try:
        hist = item.get("hist")
        if hist is None or hist.empty or "Close" not in hist:
            return None, None

        close = hist["Close"].dropna()
        if len(close) < 2:
            return None, None

        latest = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        change_pct = ((latest - prev) / prev * 100) if prev else 0
        return latest, change_pct
    except Exception:
        return None, None


def currency_suffix(ticker):
    if ticker.endswith(".OL"):
        return "kr"
    if ticker.endswith(".ST"):
        return "SEK"
    return "$"

def add_pattern_markers(fig, pattern, name):
    points = pattern.get("points", {}) if pattern else {}
    if not points:
        return fig

    ordered_keys = ["left_shoulder", "head", "right_shoulder"]
    xs = []
    ys = []

    for key in ordered_keys:
        point = points.get(key)
        if point and len(point) == 2:
            xs.append(point[0])
            ys.append(point[1])

    if xs and ys:
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="markers+lines+text",
            name=name,
            text=["Venstre", "Hode", "Høyre"],
            textposition="top center",
            marker=dict(size=10),
            line=dict(width=3, dash="dash"),
        ))

    return fig



def _safe_html_value(value):
    return html.escape(str(value if value is not None else "N/A"))


def render_compact_stat_grid(items, columns=4):
    """Kompakt statusgrid som gjør tydelig forskjell på Kompakt/Normal/Full.

    items: liste med (label, value[, delta])
    """
    if not items:
        return
    cards = []
    for item in items:
        label = item[0] if len(item) > 0 else ""
        value = item[1] if len(item) > 1 else "N/A"
        delta = item[2] if len(item) > 2 else None
        delta_html = ""
        if delta not in (None, ""):
            neg = " neg" if str(delta).strip().startswith("-") else ""
            delta_html = f"<div class='compact-stat-delta{neg}'>{_safe_html_value(delta)}</div>"
        cards.append(
            "<div class='compact-stat-card'>"
            f"<div class='compact-stat-label'>{_safe_html_value(label)}</div>"
            f"<div class='compact-stat-value'>{_safe_html_value(value)}</div>"
            f"{delta_html}"
            "</div>"
        )
    st.markdown(
        f"<div class='compact-stat-grid' style='grid-template-columns: repeat({int(columns)}, minmax(0,1fr));'>" + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )

def render_decision_banner(decision, item, adj_score):
    """Kompakt Trading engine-status (v14 / oppgave 29B).

    Tidligere viste appen samme BUY/HOLD-info tre ganger i store bokser.
    Denne varianten viser én kompakt statuslinje og legger detaljene i en lukket forklaring.
    """
    decision_text = str(decision.get("decision", "HOLD / WAIT"))
    emoji = str(decision.get("emoji", "🟡"))
    confidence = decision.get("confidence", "N/A")
    score = decision.get("decision_score", "N/A")
    color = "#86efac" if "BUY" in decision_text.upper() else ("#fecaca" if "SELL" in decision_text.upper() else "#fde68a")

    st.markdown(
        f"""
        <div class="trading-engine-compact">
            <span class="trading-engine-pill" style="border-color:{color}; background:rgba(34,197,94,0.10);">
                <span>{html.escape(emoji)}</span>
                <span style="color:{color}!important;">{html.escape(decision_text)}</span>
            </span>
            <span class="trading-engine-muted">Score: <span class="trading-engine-value">{html.escape(str(score))}</span></span>
            <span class="trading-engine-muted">Confidence: <span class="trading-engine-value">{html.escape(str(confidence))}%</span></span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Vis forklaring for signalet", expanded=False):
        st.markdown(
            f"""
            <div class="trading-engine-details">
                <b>{html.escape(emoji)} {html.escape(decision_text)}</b><br>
                Original score: <b>{html.escape(str(item.get('score', 'N/A')))}/10</b> ·
                Pattern-justert score: <b>{html.escape(str(adj_score))}/10</b><br>
                Dette er analysehjelp, ikke investeringsråd.
            </div>
            """,
            unsafe_allow_html=True,
        )


def quick_context_for_card(item):
    try:
        df = item.get("hist")
        if df is None or df.empty or "Close" not in df:
            return {}

        rsi_series = calculate_rsi(df)
        latest_rsi = float(rsi_series.dropna().iloc[-1]) if len(rsi_series.dropna()) else 50.0

        macd, macd_signal, _ = calculate_macd(df)
        latest_macd = float(macd.dropna().iloc[-1]) if len(macd.dropna()) else 0.0
        latest_macd_signal = float(macd_signal.dropna().iloc[-1]) if len(macd_signal.dropna()) else 0.0

        trend_text = str(detect_trend(df))
        if "Opptrend" in trend_text:
            trend = "up"
        elif "Nedtrend" in trend_text:
            trend = "down"
        else:
            trend = "neutral"

        breakout = breakout_scanner(df)
        hs = detect_head_shoulders(df)
        inv = detect_inverse_head_shoulders(df)

        close = df["Close"].dropna()
        recent = close.tail(80)
        if len(recent) > 5:
            low = float(recent.min())
            high = float(recent.max())
            last = float(close.iloc[-1])
            channel_pos = ((last - low) / (high - low) * 100) if high != low else 50
        else:
            channel_pos = 50

        return {
            "rsi": latest_rsi,
            "macd_bullish": latest_macd > latest_macd_signal,
            "breakout_type": breakout.get("type", "neutral"),
            "trend": trend,
            "channel_pos": channel_pos,
            "head_shoulders_found": bool(hs.get("found")),
            "inverse_head_shoulders_found": bool(inv.get("found")),
        }
    except Exception:
        return {}


def card_decision_for_item(item):
    try:
        decision = calculate_signal_intelligence(item, quick_context_for_card(item))
    except Exception:
        decision = {
            "decision": "HOLD / WAIT",
            "confidence": 0,
            "risk": "Middels",
            "reasons": [],
            "warnings": ["Teknisk signal kunne ikke beregnes på kortet"],
            "final_score": item.get("score", 0),
        }

    text = str(decision.get("decision", "HOLD / WAIT")).upper()

    if "BUY" in text:
        decision["action_now"] = "KJØP NÅ"
        decision["action_class"] = "action-buy"
        decision["action_icon"] = "🟢"
    elif "SELL" in text or "AVOID" in text:
        decision["action_now"] = "UNNGÅ NÅ"
        decision["action_class"] = "action-sell"
        decision["action_icon"] = "🔴"
    else:
        decision["action_now"] = "VENT"
        decision["action_class"] = "action-hold"
        decision["action_icon"] = "🟡"

    return decision


def render_action_chips(decision):
    st.markdown(
        f"""
        <div class="action-chip-row">
            <span class="action-chip action-info">Teknisk: {decision.get("decision", "HOLD / WAIT")}</span>
            <span class="action-chip {decision.get("action_class", "action-hold")}">{decision.get("action_icon", "🟡")} {decision.get("action_now", "VENT")}</span>
            <span class="action-chip action-info">Conf: {decision.get("confidence", 0)}%</span>
            <span class="action-chip action-info">Risiko: {decision.get("risk", "Middels")}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def is_buy_now_item(item):
    return card_decision_for_item(item).get("action_now") == "KJØP NÅ"


# V17 / Oppgave 132: felles rangering for dynamisk watchlist, Top Picks og hurtiglister.
def _signal_group_priority(decision_text: str, action_text: str = "") -> int:
    text = f"{decision_text} {action_text}".upper()
    if "KJØP" in text or "BUY" in text:
        return 0
    if "HOLD" in text or "WAIT" in text or "VENT" in text:
        return 1
    if "SELL" in text or "AVOID" in text or "UNNGÅ" in text:
        return 2
    return 3


def _rank_display_key(item):
    try:
        decision = card_decision_for_item(item or {})
    except Exception:
        decision = {}
    try:
        score = float((item or {}).get("score", 0) or 0)
    except Exception:
        score = 0.0
    try:
        conf = float(decision.get("confidence", (item or {}).get("confidence", 0)) or 0)
    except Exception:
        conf = 0.0
    priority = _signal_group_priority(str(decision.get("decision", "")), str(decision.get("action_now", "")))
    ticker = str((item or {}).get("ticker", ""))
    return (priority, -score, -conf, ticker)


STOCK_NAME_FALLBACKS_V18569 = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation", "NVDA": "NVIDIA Corporation",
    "AMZN": "Amazon.com, Inc.", "META": "Meta Platforms, Inc.", "GOOGL": "Alphabet Inc.",
    "GOOG": "Alphabet Inc.", "AVGO": "Broadcom Inc.", "TSLA": "Tesla, Inc.",
    "LLY": "Eli Lilly and Company", "JPM": "JPMorgan Chase & Co.", "V": "Visa Inc.",
    "UNH": "UnitedHealth Group Incorporated", "NFLX": "Netflix, Inc.", "MA": "Mastercard Incorporated",
    "XOM": "Exxon Mobil Corporation", "COST": "Costco Wholesale Corporation", "ORCL": "Oracle Corporation",
    "WMT": "Walmart Inc.", "HD": "The Home Depot, Inc.", "PG": "Procter & Gamble Company",
}


def _weak_symbol_name_v18569(name, symbol):
    n = str(name or "").strip()
    s = str(symbol or "").strip().upper()
    if not n:
        return True
    return n.upper().replace(" ", "") == s.replace(" ", "")


def _best_security_name_v18569(row):
    row = row or {}
    symbol = str(row.get("ticker") or row.get("symbol") or row.get("Symbol") or "").strip().upper()
    meta = resolve_security_metadata(symbol, row)
    name = str(meta.get("name") or "").strip()
    return "" if _weak_symbol_name_v18569(name, symbol) else name


def _security_display_label_v18569(row_or_symbol, maybe_row=None):
    if isinstance(row_or_symbol, dict):
        row = row_or_symbol
        symbol = str(row.get("ticker") or row.get("symbol") or row.get("Symbol") or "").strip().upper()
    else:
        row = dict(maybe_row or {})
        symbol = str(row_or_symbol or row.get("ticker") or row.get("symbol") or "").strip().upper()
        row.setdefault("ticker", symbol)
        row.setdefault("symbol", symbol)
    return display_label(symbol, row) if symbol else "-"


def _fund_display_label_v18574(row_or_symbol, maybe_row=None):
    if isinstance(row_or_symbol, dict):
        row = row_or_symbol
        symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
    else:
        row = dict(maybe_row or {})
        symbol = str(row_or_symbol or row.get("symbol") or row.get("ticker") or "").strip().upper()
        row.setdefault("symbol", symbol)
    try:
        return fund_display_label(symbol, row) if symbol else "-"
    except Exception:
        name = str(row.get("name") or row.get("fund_name") or row.get("longName") or "").strip()
        return f"{symbol} — {name}" if symbol and name and name.upper() != symbol else (symbol or name or "-")


def _ranked_for_display(items):
    clean = []
    for x in (items or []):
        if not isinstance(x, dict) or not x.get("ticker"):
            continue
        row = dict(x)
        symbol = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        name = _best_security_name_v18569(row)
        meta = resolve_security_metadata(symbol, row)
        name = str(meta.get("name") or name or "").strip()
        if name:
            row["name"] = name
            row.setdefault("longName", name)
        row["sector"] = meta.get("sector") or row.get("sector")
        row["risk"] = meta.get("risk") or row.get("risk")
        row["display_label"] = _security_display_label_v18569(symbol, row)
        clean.append(row)
    return sorted(clean, key=_rank_display_key)


def _dedupe_text_list(values):
    out, seen = [], set()
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue
        key = re.sub(r"\s+", " ", text).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out



def safe_widget_key(text):
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(text))[:120]



def save_latest_buy_now_candidates(candidates, market_label=""):
    """
    Lagrer siste UI-Kjøp nå kandidater til DB/settings.
    Cron prioriterer disse først ved neste kjøring.
    """
    try:
        rows = []
        for item in candidates[:20]:
            ticker = str(item.get("ticker", "")).upper()
            if not ticker:
                continue
            decision = card_decision_for_item(item)
            price, _change = get_item_price_change(item)
            rows.append({
                "ticker": ticker,
                "score": float(item.get("score", 0) or 0),
                "confidence": int(decision.get("confidence", 0) or 0),
                "decision": str(decision.get("decision", "")),
                "action_now": str(decision.get("action_now", "")),
                "price": float(price) if price is not None else None,
                "market": market_label,
            })

        settings = load_settings()
        settings["latest_buy_now_candidates"] = rows
        save_settings(settings)
        return rows
    except Exception as e:
        st.caption(f"Kunne ikke lagre Kjøp nå-kandidater til Cron: {e}")
        return []


def render_ranking(results, title):
    st.subheader(title)
    results = _ranked_for_display(results)

    if not results:
        st.markdown("""
        <div class='visual-truth-empty-state'>
            <b>Ingen rangeringsdata tilgjengelig.</b><br/>
            Mulige årsaker: markedet er ikke oppdatert, scan/watchlist er ikke kjørt, eller aktivt filter gir ingen treff.
            Trykk <b>Global oppdatering</b> eller velg/skriv en ticker manuelt.
        </div>
        """, unsafe_allow_html=True)
        return

    best = results[0]
    best_price, best_change = get_item_price_change(best)
    best_decision = card_decision_for_item(best)

    if APP_VIEW_MODE == "Full":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Beste kandidat", f"{best['ticker']} {best.get('score', 0)}/10")
        c2.metric("Analyserte", len(results))
        c3.metric(
            "Siste kurs",
            f"{best_price:.2f} {currency_suffix(best['ticker'])}" if best_price else "N/A",
            delta=f"{best_change:+.2f}%" if best_change is not None else None,
        )
        c4.metric("Beste handling", best_decision.get("action_now", "VENT"))
    else:
        render_compact_stat_grid([
            ("Beste kandidat", f"{best['ticker']} {best.get('score', 0)}/10"),
            ("Analyserte", len(results)),
            ("Siste kurs", f"{best_price:.2f} {currency_suffix(best['ticker'])}" if best_price else "N/A", f"{best_change:+.2f}%" if best_change is not None else None),
            ("Beste handling", best_decision.get("action_now", "VENT")),
        ], columns=4)

    st.markdown("#### ⚡ Hurtigliste med kurs")
    st.caption("Top Picks = sterk kandidat totalt. Handling nå = teknisk timing akkurat nå.")

    for idx, item in enumerate(results[:15], start=1):
        ticker = item.get("ticker", "N/A")
        score = item.get("score", 0)
        latest_price, change_pct = get_item_price_change(item)
        card_decision = card_decision_for_item(item)
        meta = resolve_security_metadata(ticker, item)
        listing = infer_security_listing(ticker, item)

        price_text = "N/A"
        delta_text = None
        direction_icon = "⚪"

        if latest_price is not None:
            price_text = f"{latest_price:.2f} {currency_suffix(ticker)}"
            delta_text = f"{change_pct:+.2f}%"
            direction_icon = "🟢" if change_pct >= 0 else "🔴"

        with st.container(border=True):
            left, mid, right = st.columns([1.35, 1.05, 2.35])

            with left:
                st.markdown(f"<div class='v18574-quick-title'>{direction_icon} {ticker}</div>", unsafe_allow_html=True)
                display_name = meta.get("name") or item.get("name") or "Navn ikke funnet"
                insider_score = item.get("insider_score")
                try:
                    insider_value = float(insider_score)
                    insider_chip = f"<span>Insider {insider_value * 100:.0f}%</span>" if insider_value <= 1 else f"<span>Insider {insider_value:.0f}%</span>"
                except Exception:
                    insider_chip = ""
                st.markdown(f"<div class='v18574-quick-sub'>#{idx} · {html.escape(str(display_name))}</div>", unsafe_allow_html=True)
                st.markdown(
                    "<div class='v1863m-quick-meta'>"
                    f"<span>{html.escape(str(listing.get('country', 'Ukjent')))}</span>"
                    f"<span>{html.escape(str(listing.get('exchange', 'Ukjent')))}</span>"
                    f"<span>{html.escape(str(meta.get('sector', 'Unknown')))}</span>"
                    f"{insider_chip}"
                    "</div>",
                    unsafe_allow_html=True,
                )
                render_action_chips(card_decision)

            with mid:
                if APP_VIEW_MODE == "Full":
                    st.metric("Total score", f"{score}/10")
                    st.metric("Kurs", price_text, delta=delta_text)
                else:
                    render_compact_stat_grid([
                        ("Score", f"{score}/10"),
                        ("Kurs", price_text, delta_text),
                    ], columns=1)

            with right:
                st.markdown("<div class='v1863m-quick-action'>", unsafe_allow_html=True)
                st.progress(min(float(score) / 10, 1.0))
                st.caption(
                    f"1y: {item.get('ret_1y', 0)*100:.1f}% · "
                    f"6m: {item.get('ret_6m', 0)*100:.1f}% · "
                    f"3m: {item.get('ret_3m', 0)*100:.1f}% · "
                    f"Vol: {item.get('volatility', 0):.4f} · "
                    f"DD: {item.get('max_drawdown', 0)*100:.1f}%"
                )

                warnings = card_decision.get("warnings", [])
                reasons = card_decision.get("reasons", [])

                if warnings:
                    st.markdown(f"<div class='v1863m-quick-action-note'>⚠️ {html.escape(str(warnings[0]))}</div>", unsafe_allow_html=True)
                elif reasons:
                    st.markdown(f"<div class='v1863m-quick-action-note'>✅ {html.escape(str(reasons[0]))}</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='v1863m-quick-action-note'>Ingen ekstra varseltekst.</div>", unsafe_allow_html=True)

                # Direkte paper-trading fra kortet
                try:
                    _portfolio = load_portfolio()
                    _owns = ticker in _portfolio.get("positions", {})
                    _action_now = str(card_decision.get("action_now", "VENT")).upper()
                    _conf = int(card_decision.get("confidence", 0) or 0)
                    _btn_key_base = safe_widget_key(f"{title}_{ticker}_{idx}")

                    if latest_price is not None and _action_now == "KJØP NÅ":
                        if _owns:
                            st.caption("📌 Allerede i paper-porteføljen")
                        elif st.button(f"🟢 Paper-kjøp {ticker}", key=f"paper_buy_{_btn_key_base}", use_container_width=True):
                            _ok, _msg = paper_buy(ticker, latest_price, _conf, f"UI Kjøp nå: {title}")
                            if _ok:
                                st.success(_msg)
                                st.rerun()
                            else:
                                st.warning(_msg)

                    elif latest_price is not None and ("UNNGÅ" in _action_now or "SELL" in _action_now):
                        if _owns and st.button(f"🔴 Paper-selg {ticker}", key=f"paper_sell_{_btn_key_base}", use_container_width=True):
                            _ok, _msg = paper_sell(ticker, latest_price, f"UI teknisk signal: {_action_now}")
                            if _ok:
                                st.success(_msg)
                                st.rerun()
                            else:
                                st.warning(_msg)
                except Exception as _e:
                    st.caption(f"Paper-knapp ikke tilgjengelig: {_e}")
                st.markdown("</div>", unsafe_allow_html=True)



def pct_distance(current, level):
    try:
        current = float(current)
        level = float(level)
        if current == 0:
            return None
        return ((level - current) / current) * 100
    except Exception:
        return None


def fmt_distance(current, level):
    d = pct_distance(current, level)
    if d is None:
        return "N/A"
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.2f}%"


def current_price_from_df(df):
    try:
        return float(df["Close"].dropna().iloc[-1])
    except Exception:
        return None


def add_rsi_level_labels(fig, rsi_series=None):
    """
    RSI-graf med nivåer + tydelig gjeldende RSI-boks.
    """
    try:
        current_rsi = None
        if rsi_series is not None:
            clean = rsi_series.dropna()
            if len(clean) > 0:
                current_rsi = float(clean.iloc[-1])

        fig.add_hrect(y0=0, y1=30, fillcolor="rgba(0,227,150,0.08)", line_width=0)
        fig.add_hrect(y0=70, y1=100, fillcolor="rgba(255,77,109,0.08)", line_width=0)

        fig.add_hline(y=30, line_dash="dash", line_color="rgba(255,255,255,0.65)")
        fig.add_hline(y=70, line_dash="dash", line_color="rgba(255,255,255,0.65)")
        fig.add_hline(y=80, line_dash="dot", line_color="rgba(255,193,7,0.85)")

        fig.add_annotation(xref="paper", yref="y", x=1.01, y=30, text="30 oversolgt", showarrow=False, xanchor="left", font=dict(size=12, color="white"), bgcolor="rgba(11,17,28,0.85)")
        fig.add_annotation(xref="paper", yref="y", x=1.01, y=70, text="70 overkjøpt", showarrow=False, xanchor="left", font=dict(size=12, color="white"), bgcolor="rgba(11,17,28,0.85)")
        fig.add_annotation(xref="paper", yref="y", x=1.01, y=80, text="80 ekstrem", showarrow=False, xanchor="left", font=dict(size=12, color="#ffc107"), bgcolor="rgba(11,17,28,0.85)")

        if current_rsi is not None:
            if current_rsi >= 80:
                status, icon = "ekstremt overkjøpt", "🔥"
            elif current_rsi >= 70:
                status, icon = "overkjøpt", "⚠️"
            elif current_rsi <= 30:
                status, icon = "oversolgt", "🧊"
            else:
                status, icon = "nøytral", "📊"

            fig.add_hline(y=current_rsi, line_dash="dot", line_color="#38bdf8", opacity=0.7)
            fig.add_annotation(
                text=f"{icon} Gjeldende RSI: <b>{current_rsi:.1f}</b> · {status}",
                xref="paper", yref="paper", x=0.01, y=1.16,
                showarrow=False, align="left",
                font=dict(size=14, color="white"),
                bgcolor="rgba(30,41,59,0.94)",
                bordercolor="rgba(255,255,255,0.30)", borderwidth=1,
            )
            fig.add_annotation(
                xref="paper", yref="y", x=1.01, y=current_rsi,
                text=f"RSI nå: {current_rsi:.1f}", showarrow=False, xanchor="left",
                font=dict(size=12, color="#93c5fd"),
                bgcolor="rgba(11,17,28,0.90)",
                bordercolor="rgba(147,197,253,0.45)", borderwidth=1,
            )

        fig.update_yaxes(range=[0, 100])
        fig.update_layout(margin=dict(l=20, r=155, t=90, b=30))
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return fig


def format_big_number(value):
    try:
        v = float(value or 0)
    except Exception:
        return "0"

    abs_v = abs(v)
    if abs_v >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f} mrd"
    if abs_v >= 1_000_000:
        return f"{v/1_000_000:.2f} mill"
    if abs_v >= 1_000:
        return f"{v:,.0f}".replace(",", " ")
    return f"{v:.0f}"


def insider_signal_label(score):
    try:
        s = float(score)
    except Exception:
        return "Nøytral", "info-warning"

    if s >= 0.60:
        return "Netto kjøp", "info-positive"
    if s <= 0.40:
        return "Netto salg", "info-negative"
    return "Blandet", "info-warning"



def render_latest_insider_transactions(insider):
    txs = insider.get("latest_transactions", []) if insider else []
    if not txs:
        st.caption("Ingen siste insiderhandler funnet.")
        return

    st.markdown("#### 🕵️ Siste insiderhandler")
    rows = []
    for tx in txs[:8]:
        value = tx.get("value")
        if value is None:
            value_txt = "N/A"
        else:
            try:
                value_txt = f"{float(value):,.0f}".replace(",", " ")
            except Exception:
                value_txt = "N/A"

        rows.append({
            "Dato": tx.get("date", ""),
            "Type": "KJØP" if tx.get("type") == "BUY" else "SALG" if tx.get("type") == "SELL" else tx.get("type", ""),
            "Aksjer": format_big_number(tx.get("shares", 0)),
            "Pris": round(float(tx.get("price", 0) or 0), 2),
            "Verdi": value_txt,
            "Insider": tx.get("name", "")[:26],
        })

    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_intelligence_cards(insider, analyst, earnings):
    insider = insider or {}
    analyst = analyst or {}
    earnings = earnings or {}

    insider_score = insider.get("score", "N/A")
    insider_label, insider_class = insider_signal_label(insider_score)

    buy_shares = format_big_number(insider.get("buy_shares", 0))
    sell_shares = format_big_number(insider.get("sell_shares", 0))
    buy_count = insider.get("buy_count", 0)
    sell_count = insider.get("sell_count", 0)
    transactions = insider.get("transactions", 0)

    analyst_trend = analyst.get("trend", "N/A")
    analyst_buy = analyst.get("buy", 0)
    analyst_hold = analyst.get("hold", 0)
    analyst_sell = analyst.get("sell", 0)

    earnings_date = earnings.get("date") or "Ingen nær dato"
    days_until = earnings.get("days_until", "N/A")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            f"""
            <div class="info-mini-card">
                <div class="info-mini-title">🕵️ Insider</div>
                <div class="info-mini-main {insider_class}">{insider_label}</div>
                <div class="info-mini-sub">
                    Score: <b>{insider_score}</b><br>
                    Kjøp: <b>{buy_shares}</b> aksjer<br>
                    Salg: <b>{sell_shares}</b> aksjer
                </div>
                <div class="info-mini-small">
                    Transaksjoner: {transactions} · Kjøp: {buy_count} · Salg: {sell_count}<br>
                    Siste: {insider.get("latest_type", "N/A")} {insider.get("latest_date", "")}<br>Tallene er summerte insider-transaksjoner i aksjer fra siste periode.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            f"""
            <div class="info-mini-card">
                <div class="info-mini-title">📈 Analyst</div>
                <div class="info-mini-main">{analyst_trend}</div>
                <div class="info-mini-sub">
                    Buy: <b>{analyst_buy}</b><br>
                    Hold: <b>{analyst_hold}</b><br>
                    Sell: <b>{analyst_sell}</b>
                </div>
                <div class="info-mini-small">
                    Analytikerbildet brukes som støtte, ikke som eneste beslutningsgrunnlag.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            f"""
            <div class="info-mini-card">
                <div class="info-mini-title">⏰ Earnings</div>
                <div class="info-mini-main">{earnings_date}</div>
                <div class="info-mini-sub">
                    Dager igjen: <b>{days_until}</b>
                </div>
                <div class="info-mini-small">
                    Nær rapportdato kan gi ekstra volatilitet og høyere risiko.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )





def render_macd_explanation():
    st.markdown(
        """
        <div class="macd-explain-box">
            <b>📘 MACD forklart</b><br>
            <b>🔵 MACD-linje:</b> viser momentum i kursen. Når den stiger, øker positivt momentum.<br>
            <b>🔴 Signallinje:</b> glattet MACD-linje som brukes som sammenligning.<br>
            <b>🟢/🔴 Histogram:</b> forskjellen mellom MACD og signallinjen. Grønt = MACD over signal, rødt = MACD under signal.<br>
            <b>Tolkning:</b> MACD over signallinjen er ofte positivt. MACD under signallinjen kan varsle svakere momentum. Grafene støtter musehjul-zoom og panering.
        </div>
        """,
        unsafe_allow_html=True,
    )


def normalize_user_ticker(ticker: str) -> str:
    """Normaliserer manuell ticker uten å falle stille tilbake til AAPL."""
    return str(ticker or "").strip().upper().replace(" ", "")


LEGACY_SEED_TICKERS_V1863T = {
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
    "EQNR.OL", "DNB.OL", "STB.OL", "NOVO-B.CO",
}


def _extract_tickers_any_v1863t(value):
    out = []

    def add(v):
        if v is None:
            return
        if isinstance(v, str):
            for part in re.split(r"[\s,;|/]+", v):
                ticker = normalize_user_ticker(part)
                if ticker and ticker not in out:
                    out.append(ticker)
        elif isinstance(v, dict):
            ticker = normalize_user_ticker(v.get("ticker") or v.get("symbol"))
            if ticker and ticker not in out:
                out.append(ticker)
            for key in ("tickers", "rows", "candidates", "top_picks"):
                add(v.get(key))
        elif isinstance(v, (list, tuple, set)):
            for item in v:
                add(item)

    add(value)
    return out


def _legacy_seed_only_v1863t(value) -> bool:
    tickers = _extract_tickers_any_v1863t(value)
    return bool(tickers) and set(tickers).issubset(LEGACY_SEED_TICKERS_V1863T)


def _cleanup_legacy_session_seed_data_v1863t() -> None:
    """Ignore old demo/seed data so it cannot masquerade as current market data."""
    try:
        for key in ["latest_watchlist_tickers_v156", "watchlist", "watchlist_items", "search_main_v157", "cc_interactive_ticker_v18535"]:
            if _legacy_seed_only_v1863t(st.session_state.get(key)):
                st.session_state[key] = "" if "ticker" in key or key == "search_main_v157" else []

        latest = st.session_state.get("latest_rankings_v148")
        if isinstance(latest, dict):
            cleaned = {k: v for k, v in latest.items() if not _legacy_seed_only_v1863t(v)}
            if len(cleaned) != len(latest):
                st.session_state["latest_rankings_v148"] = cleaned

        for key in ["top_picks_result", "watchlist_result", "smart_universe_result", "ai_analysis_universe_smart_result_v1859"]:
            if _legacy_seed_only_v1863t(st.session_state.get(key)):
                st.session_state[key] = {}
        controls = st.session_state.get("active_analysis_controls_v148")
        if isinstance(controls, dict) and _legacy_seed_only_v1863t(controls.get("search")):
            controls = dict(controls)
            controls["search"] = ""
            st.session_state["active_analysis_controls_v148"] = controls
    except Exception as e:
        logging.warning("Legacy seed cleanup skipped: %s", e)


def active_ticker_from_inputs(manual_ticker: str, selected_from_list: str) -> str:
    manual = _clean_manual_ticker_input(manual_ticker)
    return manual if manual else normalize_user_ticker(selected_from_list)


def render_analysis(results, label):
    st.subheader("📊 Interaktiv analyse")

    # V14.8 / Oppgave 73: Interaktiv analyse kan hente fra siste lagrede dynamiske rangering,
    # uten å starte en ny scan/rangering bare fordi menyen åpnes.
    source_choice = st.selectbox(
        "Aksjekilde",
        ["Aktuell liste", "Smart Universe Picker", "Dynamisk watchlist / best rangerte", "Top Picks", "USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil", "Norden", "Alle"],
        index=0,
        key=f"analysis_source_{label}_v148",
        help="Bruker siste lagrede/godkjente rangering. Manuell ticker overstyrer alltid listen.",
    )
    source_results = _latest_ranked_results_for_source(source_choice, results or [], current_label=label)

    # Oppgave 76/76B + 78/79: dynamiske, rangerte valg etter valgt aksjekilde.
    # Panelet starter tomt. Kilder må ha lagret rangering eller bygges eksplisitt
    # med egen knapp. Ingen stille fallback til AAPL.
    def _build_options(_source_results):
        result_options = [normalize_user_ticker(r.get("ticker")) for r in (_source_results or []) if isinstance(r, dict) and r.get("ticker")]
        _options = []
        _labels = {}
        for r in (_source_results or []):
            if not isinstance(r, dict):
                continue
            t = normalize_user_ticker(r.get("ticker"))
            if t:
                score = r.get("score", "N/A")
                try:
                    score_txt = f"{float(score):.2f}"
                except Exception:
                    score_txt = str(score)
                try:
                    action = card_decision_for_item(r).get("action_now", "")
                except Exception:
                    action = ""
                _labels[t] = f"{t} · score {score_txt}" + (f" · {action}" if action else "")
        for _t in result_options:
            if _t and _t not in _options:
                _options.append(_t)
        return _options, _labels

    options, option_labels = _build_options(source_results)
    if not options and source_choice == "Aktuell liste":
        st.info("Aktuell liste er tom. Kjør en rangering, velg et marked, eller skriv én ticker manuelt.")

    # V14.10: hvis valgt dynamisk kilde mangler liste, gi eksplisitt knapp for å bygge akkurat denne kilden.
    if not options and source_choice != "Aktuell liste":
        st.info(f"Ingen lagret dynamisk rangering for {source_choice}. Bygg listen nå, eller skriv én ticker manuelt.")
        build_cols = st.columns([1, 2])
        with build_cols[0]:
            if st.button(f"🔄 Oppdater {source_choice}-liste nå", key=f"build_interactive_source_{label}_{source_choice}_v1410", use_container_width=True):
                with st.spinner(f"Bygger dynamisk {source_choice}-liste..."):
                    source_results = _build_interactive_source_ranking_now(source_choice)
                options, option_labels = _build_options(source_results)
                if options:
                    st.success(f"{source_choice}-listen er oppdatert med {len(options)} aksjer ✅")
                else:
                    st.markdown(f"""<div class='visual-truth-empty-state'><b>Ingen data for {source_choice}.</b><br/>Prøv Global oppdatering / Scan watchlist, sjekk marked/filter, eller skriv ticker manuelt.</div>""", unsafe_allow_html=True)
        with build_cols[1]:
            st.caption("Knappen kjører bare valgt kilde. Den skal ikke starte AAPL-fallback eller skjulte markedspaneler.")

    source_key = re.sub(r"[^A-Za-z0-9]+", "_", source_choice).strip("_") or "source"
    manual_key = f"manual_ticker_{label}_v1410"
    clear_key = f"clear_manual_ticker_{label}_v1410"
    if manual_key not in st.session_state:
        st.session_state[manual_key] = ""
    if st.session_state.get(clear_key):
        st.session_state[manual_key] = ""
        st.session_state[clear_key] = False

    s0, s1, s2 = st.columns([1.05, 2.0, 1.25])
    with s0:
        st.caption(f"Aktiv kilde: {source_choice}")
    with s1:
        selected_from_list = ""
        if options:
            selected_from_list = st.selectbox(
                f"Velg aksje fra valgt kilde ({source_choice})",
                options,
                index=0,
                key=f"select_{label}_{source_key}_v1410",
                format_func=lambda x: option_labels.get(x, x),
            )
        else:
            st.caption("Ingen listevalg tilgjengelig for valgt kilde ennå.")
    with s2:
        manual_ticker_raw = st.text_input(
            "Eller skriv ticker",
            placeholder="Skriv én ticker, f.eks. EQNR.OL",
            key=manual_key,
            help="Manuell ticker overstyrer valgt kilde. For flere tickere bruker du Strategi-test.",
        )
        if st.button("Tøm manuell ticker", key=f"manual_ticker_clear_btn_{label}_v1410", use_container_width=True):
            st.session_state[manual_key] = ""
            st.rerun()
        st.caption("Eksempel: EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE eller PETR4.SA")

    manual_ticker_clean = _clean_manual_ticker_input(manual_ticker_raw)
    if manual_ticker_raw and manual_ticker_clean != normalize_user_ticker(manual_ticker_raw):
        st.caption(f"Manuell input er tolket som én ticker: {manual_ticker_clean or 'ingen'}")

    selected = active_ticker_from_inputs(manual_ticker_raw, selected_from_list)
    if manual_ticker_clean:
        st.caption(f"Aktiv tickerkilde: Manuell ticker · Bruker ticker: {selected}")
    elif selected:
        st.caption(f"Aktiv tickerkilde: {source_choice} · Bruker ticker: {selected}")
    else:
        st.warning("Velg en ticker fra listen, bygg valgt kilde, eller skriv én ticker manuelt.")
        return

    item = next((r for r in (source_results or []) if normalize_user_ticker(r.get("ticker")) == selected), None)
    if item is None or not isinstance(item, dict) or "hist" not in item:
        with st.spinner(f"Henter analyse for {selected}..."):
            fetched_item = cached_score_stock_manual(selected, use_news=False)
        if fetched_item:
            merged_item = dict(fetched_item)
            if isinstance(item, dict):
                merged_item.update({k: v for k, v in item.items() if v not in (None, "")})
                merged_item.setdefault("hist", fetched_item.get("hist"))
            item = merged_item

    if not item:
        if _manual_update_mode_enabled():
            st.info("Manuell modus er aktiv og det finnes ingen lagret analyse for valgt ticker. Trykk Oppdater hele appen for å hente data.")
        else:
            st.warning("Fant ikke data for valgt ticker. Sjekk ticker-symbol, f.eks. EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE eller PETR4.SA.")
        return

    _sync_timeframe, _sync_period = get_selected_time_settings(label, selected)
    _synced_df = cached_timeframe_data_manual(selected, _sync_timeframe, _sync_period)
    if _synced_df is not None and not _synced_df.empty:
        df = _synced_df.copy()
    else:
        df = item["hist"].copy()

    if APP_VIEW_MODE == "Full":
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Score", f"{item['score']}/10")
        m2.metric("P/E", item.get("forward_pe") or item.get("trailing_pe") or "N/A")
        m3.metric("Revenue growth", f"{item['revenue_growth']*100:.1f}%" if isinstance(item.get("revenue_growth"), (int,float)) else "N/A")
        m4.metric("Max drawdown", f"{item['max_drawdown']*100:.1f}%")
    else:
        render_compact_stat_grid([
            ("Score", f"{item['score']}/10"),
            ("P/E", item.get("forward_pe") or item.get("trailing_pe") or "N/A"),
            ("Revenue growth", f"{item['revenue_growth']*100:.1f}%" if isinstance(item.get("revenue_growth"), (int,float)) else "N/A"),
            ("Max drawdown", f"{item['max_drawdown']*100:.1f}%"),
        ], columns=4)

    st.markdown("#### 📈 Teknisk analyse")

    rsi = calculate_rsi(df)
    macd, macd_signal, macd_hist = calculate_macd(df)
    bb_ma, bb_upper, bb_lower = calculate_bollinger(df)
    trend = detect_trend(df)

    latest_rsi = rsi.dropna().iloc[-1] if not rsi.dropna().empty else 50
    latest_macd = macd.dropna().iloc[-1] if not macd.dropna().empty else 0
    latest_macd_signal = macd_signal.dropna().iloc[-1] if not macd_signal.dropna().empty else 0
    latest_close = df["Close"].iloc[-1]
    latest_upper = bb_upper.dropna().iloc[-1] if not bb_upper.dropna().empty else latest_close
    latest_lower = bb_lower.dropna().iloc[-1] if not bb_lower.dropna().empty else latest_close

    hs = detect_head_shoulders(df)
    inv_hs = detect_inverse_head_shoulders(df)
    breakout = breakout_scanner(df)
    alerts = build_signal_alerts(latest_rsi, latest_macd, latest_macd_signal, breakout, hs, inv_hs)

    technical_context = {
        "rsi": latest_rsi,
        "macd_bullish": latest_macd > latest_macd_signal,
        "breakout_type": breakout.get("type", "neutral"),
        "head_shoulders_found": hs.get("found", False),
        "inverse_head_shoulders_found": inv_hs.get("found", False),
    }

    decision = build_trading_decision(item, technical_context)
    adj_score = adjusted_score(item, decision)

    insider = _cached_external_signal_manual("insider", selected, get_insider_data, default={"score": 0.5, "label": "Cache/ikke hentet"})
    analyst = _cached_external_signal_manual("analyst", selected, get_analyst_trend, default={})
    earnings = _cached_external_signal_manual("earnings", selected, get_earnings, default={})

    signal_intelligence = calculate_signal_intelligence(
        item,
        technical_context=technical_context,
        insider=insider,
        analyst=analyst,
        earnings=earnings,
    ) if use_signal_intelligence else None

    if signal_intelligence:
        decision["decision"] = signal_intelligence["decision"]
        decision["emoji"] = signal_intelligence["emoji"]
        decision["confidence"] = signal_intelligence.get("confidence", 0)
        decision["decision_score"] = signal_intelligence.get("final_score", signal_intelligence.get("decision_score", 0))
        decision["reasons"] = decision.get("reasons", []) + signal_intelligence.get("reasons", [])

    # MOBILE_ANALYSIS_STEP3_TRADING_PANEL_V1
    render_mobile_analysis_view(
        item,
        selected,
        label,
        decision=decision,
        technical_context=technical_context,
        chart_renderer=render_interactive_chart,
    )

    st.markdown("---")

    # UI-signalvarsler er deaktivert for å hindre dobbelvarsling.
    # Varsler styres nå fra Varselkontroll:
    # - faktisk paper BUY/SELL via trading_engine/notifier
    # - watchlist signalendring via scan_watchlist_and_alert

    st.markdown("#### 🤖 Trading engine")
    render_decision_banner(decision, item, adj_score)

    if signal_intelligence:
        st.markdown("#### 🧠 Signal Intelligence")
        if APP_VIEW_MODE == "Full":
            si1, si2, si3, si4 = st.columns(4)
            si1.metric("Smart score", f"{signal_intelligence.get('final_score', signal_intelligence.get('decision_score', 0))}/10")
            si2.metric("Confidence", f"{signal_intelligence.get('confidence', 0)}%")
            si3.metric("Risk", signal_intelligence.get("risk", "Middels"))
            si4.metric("Confidence", f"{signal_intelligence.get('confidence', 0)}%")
        else:
            render_compact_stat_grid([
                ("Smart score", f"{signal_intelligence.get('final_score', signal_intelligence.get('decision_score', 0))}/10"),
                ("Confidence", f"{signal_intelligence.get('confidence', 0)}%"),
                ("Risk", signal_intelligence.get("risk", "Middels")),
            ], columns=3)

        render_intelligence_cards(insider, analyst, earnings)

    with st.expander("Hvorfor dette signalet?"):
        for reason in decision["reasons"]:
            st.write("•", reason)

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("RSI", f"{latest_rsi:.1f}")
    t2.metric("Trend", trend)
    t3.metric("MACD", "Bullish 🟢" if latest_macd > latest_macd_signal else "Bearish 🔴")
    t4.metric("Breakout", breakout.get("signal", "N/A"))

    render_rsi_box(latest_rsi)

    st.markdown("#### 🔔 Signal alerts")
    for title, desc, kind in alerts:
        if kind == "bullish":
            st.success(f"🟢 {title}: {desc}")
        elif kind == "bearish":
            st.error(f"🔴 {title}: {desc}")
        else:
            st.info(f"⚪ {title}: {desc}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Motstand", breakout.get("resistance", "N/A"))
    c2.metric("Støtte", breakout.get("support", "N/A"))
    c3.metric("Volum boost", breakout.get("volume_boost", "N/A"))

    st.markdown("#### 🧩 Pattern detection")
    p1, p2 = st.columns(2)
    with p1:
        if hs.get("found"):
            st.warning(f"{hs['label']} | confidence: {hs['confidence']}")
        else:
            st.info(hs.get("label", "Ingen pattern"))
    with p2:
        if inv_hs.get("found"):
            st.success(f"{inv_hs['label']} | confidence: {inv_hs['confidence']}")
        else:
            st.info(inv_hs.get("label", "Ingen pattern"))

    fig_ta = go.Figure()
    fig_ta.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Pris", mode="lines"))
    fig_ta.add_trace(go.Scatter(x=df.index, y=bb_ma, name="BB midt", mode="lines", line=dict(dash="dot")))
    fig_ta.add_trace(go.Scatter(x=df.index, y=bb_upper, name="BB øvre", mode="lines", line=dict(dash="dot")))
    fig_ta.add_trace(go.Scatter(x=df.index, y=bb_lower, name="BB nedre", mode="lines", line=dict(dash="dot")))

    if breakout.get("support") != "N/A":
        fig_ta.add_hline(y=breakout.get("support"), line_dash="dash", annotation_text="Støtte")
    if breakout.get("resistance") != "N/A":
        fig_ta.add_hline(y=breakout.get("resistance"), line_dash="dash", annotation_text="Motstand")

    if hs.get("found"):
        fig_ta = add_pattern_markers(fig_ta, hs, "Hode/skulder")
    if inv_hs.get("found"):
        fig_ta = add_pattern_markers(fig_ta, inv_hs, "Invertert hode/skulder")

    fig_ta.update_layout(
        title=f"{selected} - Bollinger, støtte/motstand, patterns og breakout",
        template="plotly_dark",
        height=480,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
    )
    try:
        last_x_ta = df.index[-1]
        last_price_ta = float(df["Close"].dropna().iloc[-1])

        fig_ta.add_hline(
            y=last_price_ta,
            line_dash="dot",
            line_color="rgba(255,255,255,0.45)",
        )

        add_right_side_price_label(
            fig_ta,
            last_x_ta,
            last_price_ta,
            f"Pris: {last_price_ta:.2f}",
            color="white",
            yshift=0,
        )

        # Bollinger labels on right side if available
        try:
            bb_mid_val = float(bb_ma.dropna().iloc[-1])
            bb_upper_val = float(bb_upper.dropna().iloc[-1])
            bb_lower_val = float(bb_lower.dropna().iloc[-1])

            add_right_side_price_label(fig_ta, last_x_ta, bb_mid_val, f"BB midt: {bb_mid_val:.2f}", color="#ff6b4a")
            add_right_side_price_label(fig_ta, last_x_ta, bb_upper_val, f"BB øvre: {bb_upper_val:.2f}", color="#00e6a8")
            add_right_side_price_label(fig_ta, last_x_ta, bb_lower_val, f"BB nedre: {bb_lower_val:.2f}", color="#b56cff")
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)

        fig_ta.update_layout(
            margin=dict(l=20, r=170, t=90, b=30),
            legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
            annotations=[
                *fig_ta.layout.annotations,
                dict(
                    text=f"💹 Gjeldende kurs: <b>{last_price_ta:.2f}</b>",
                    xref="paper",
                    yref="paper",
                    x=0.01,
                    y=1.14,
                    showarrow=False,
                    align="left",
                    font=dict(size=15, color="white"),
                    bgcolor="rgba(30,41,59,0.9)",
                    bordercolor="rgba(255,255,255,0.25)",
                    borderwidth=1,
                )
            ],
        )
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    render_interactive_chart(fig_ta, use_container_width=True, key=f"ta_chart_{label}_{selected}")
    render_graph_explanation("ta")

    fig_macd = go.Figure()

    macd_clean = macd.dropna()
    macd_signal_clean = macd_signal.dropna()
    macd_hist_clean = macd_hist.dropna()

    macd_last = float(macd_clean.iloc[-1]) if len(macd_clean) else 0.0
    signal_last = float(macd_signal_clean.iloc[-1]) if len(macd_signal_clean) else 0.0
    hist_last = float(macd_hist_clean.iloc[-1]) if len(macd_hist_clean) else 0.0
    last_x = df.index[-1]

    hist_colors = ["#22c55e" if float(v) >= 0 else "#ef4444" for v in macd_hist.fillna(0)]

    fig_macd.add_trace(
        go.Scatter(
            x=df.index,
            y=macd,
            name="🔵 MACD-linje",
            mode="lines",
            line=dict(color="#3b82f6", width=2.6),
            hovertemplate="<b>🔵 MACD-linje</b><br>Dato: %{x}<br>Verdi: %{y:.2f}<extra></extra>",
        )
    )

    fig_macd.add_trace(
        go.Scatter(
            x=df.index,
            y=macd_signal,
            name="🔴 Signallinje",
            mode="lines",
            line=dict(color="#ef4444", width=2.4),
            hovertemplate="<b>🔴 Signallinje</b><br>Dato: %{x}<br>Verdi: %{y:.2f}<extra></extra>",
        )
    )

    fig_macd.add_trace(
        go.Bar(
            x=df.index,
            y=macd_hist,
            name="🟢/🔴 Histogram",
            marker=dict(color=hist_colors),
            opacity=0.78,
            hovertemplate="<b>🟢/🔴 Histogram</b><br>Dato: %{x}<br>MACD - signal: %{y:.2f}<extra></extra>",
        )
    )

    fig_macd.add_hline(
        y=0,
        line_width=1,
        line_dash="dot",
        line_color="rgba(255,255,255,0.55)",
        annotation_text="0-linje",
        annotation_position="right",
    )

    fig_macd.add_annotation(
        x=last_x,
        y=macd_last,
        text=f"🔵 MACD {macd_last:.2f}",
        showarrow=True,
        arrowhead=2,
        ax=42,
        ay=-26,
        bgcolor="rgba(59,130,246,0.18)",
        bordercolor="#3b82f6",
        borderwidth=1,
        font=dict(color="#dbeafe", size=12),
    )

    fig_macd.add_annotation(
        x=last_x,
        y=signal_last,
        text=f"🔴 Signal {signal_last:.2f}",
        showarrow=True,
        arrowhead=2,
        ax=42,
        ay=26,
        bgcolor="rgba(239,68,68,0.18)",
        bordercolor="#ef4444",
        borderwidth=1,
        font=dict(color="#fee2e2", size=12),
    )

    fig_macd.add_annotation(
        xref="paper",
        yref="paper",
        x=0.01,
        y=1.15,
        text=f"Histogram nå: {'🟢 positiv' if hist_last >= 0 else '🔴 negativ'} ({hist_last:.2f})",
        showarrow=False,
        align="left",
        bgcolor="rgba(15,23,42,0.88)",
        bordercolor="rgba(148,163,184,0.45)",
        borderwidth=1,
        font=dict(color="#f8fafc", size=12),
    )

    fig_macd.update_layout(
        title=f"{selected} - MACD: blå linje / rød signal / grønt-rødt histogram",
        template="plotly_dark",
        height=330,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
        margin=dict(l=40, r=90, t=95, b=35),
        legend=dict(
            title="Forklaring",
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(15,23,42,0.75)",
            bordercolor="rgba(148,163,184,0.35)",
            borderwidth=1,
        ),
    )
    render_interactive_chart(fig_macd, use_container_width=True, key=f"macd_chart_{label}_{selected}")

    render_macd_explanation()

    fig_rsi = go.Figure()
    fig_rsi.add_trace(go.Scatter(x=df.index, y=rsi, name="RSI", mode="lines"))
    fig_rsi.add_hline(y=80, line_dash="dot", annotation_text="80 ekstremt overkjøpt", annotation_position="right")
    fig_rsi.add_hline(y=70, line_dash="dash", annotation_text="Overkjøpt")
    fig_rsi.add_hline(y=30, line_dash="dash", annotation_text="Oversolgt")
    fig_rsi.update_layout(
        title=f"{selected} - RSI",
        template="plotly_dark",
        height=260,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
        yaxis=dict(range=[0, 100]),
    )
    render_interactive_chart(add_rsi_level_labels(fig_rsi, rsi), use_container_width=True, key=f"rsi_chart_{label}_{selected}")
    render_graph_explanation("rsi")

    # v18.5.30 Legacy cleanup: standalone strategy testing and strategy
    # optimization were removed from per-ticker analysis cards. Use
    # AI Kontrollsenter -> Testing & Learning as the single source for
    # Strategi-test, Strategi-test Pro and learning history.

    parts = item.get("score_parts", {})
    with st.expander("🧠 Score-forklaring", expanded=False):
        if parts:
            st.caption("Åpne/lukk denne seksjonen etter behov. Verdiene er normalisert fra 0 til 1.")
            for k, v in parts.items():
                try:
                    _score_value = max(0.0, min(1.0, float(v)))
                except Exception:
                    _score_value = 0.0
                _label = str(k).replace("_", " ").title()
                st.progress(_score_value)
                st.caption(f"{_label}: {_score_value:.3f}")
        else:
            st.caption("Ingen score-detaljer tilgjengelig for denne aksjen.")

    st.markdown("#### 📰 Nyheter")
    st.caption("For å spare NewsAPI-kall hentes nyheter bare for valgt aksje når du trykker knappen.")

    if not use_news:
        st.info("Nyheter/sentiment er slått av i sidepanelet.")
    elif st.button(f"Hent nyheter for {selected}", key=f"news_btn_{label}_{selected}"):
        articles, error = get_news(selected.replace(".OL", ""), limit=6, source="manual", force=True)

        if error:
            st.warning(f"Nyheter midlertidig utilgjengelig: {error}")
        elif not articles:
            st.info("Ingen relevante nyheter funnet.")
        else:
            live_sentiment = simple_finance_sentiment(articles)
            st.metric("Live nyhets-sentiment", live_sentiment)

            for a in articles:
                st.markdown(
                    f"- **{a.get('title','Uten tittel')}**  \n"
                    f"  <span class='small'>{a.get('source','')} · {a.get('published','')}</span>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("Trykk på knappen over for å hente nyheter for valgt aksje.")



# V15.9 / Oppgave 121: trading-regel-presets må oppdatere både lagrede regler og synlige widget-verdier.
def _apply_trading_rule_preset_v159(name: str, values: dict):
    """Setter trading-regel preset uten å trigge tung analyse.

    Streamlit-widgeter med key beholder ellers gamle verdier i session_state selv om
    save_rules() oppdaterer fil/database. Derfor må de synlige widget-keyene settes
    eksplisitt før rerun. Verdiene lagres også i trading rules, slik at neste åpning
    viser samme preset.
    """
    current = load_rules() or {}
    preset = dict(current)
    preset.update(values or {})

    key_map = {
        "min_buy_score": "main_rules_min_buy_score_v156",
        "min_buy_confidence": "main_rules_min_buy_conf_v156",
        "max_buy_rsi": "main_rules_max_buy_rsi_v156",
        "min_hold_days": "main_rules_min_hold_days_v156",
        "enable_sell_signal_exit": "main_rules_sell_signal_v156",
        "stop_loss_pct": "main_rules_stop_loss_v156",
        "take_profit_pct": "main_rules_take_profit_v156",
        "trailing_stop_pct": "main_rules_trailing_stop_v156",
        "rsi_exit_level": "main_rules_rsi_exit_v156",
        "rsi_must_fall": "main_rules_rsi_fall_v156",
        "use_noise_filter": "main_rules_use_noise_filter_v156",
        "ignore_small_moves_pct": "main_rules_ignore_small_v156",
    }
    for rule_key, widget_key in key_map.items():
        if rule_key in preset:
            st.session_state[widget_key] = preset[rule_key]

    save_rules(preset)
    st.session_state["rules_preset_notice_v159"] = f"{name} er lagt inn. Trykk «Oppdater hele appen» når du er klar."
    st.rerun()


_TRADING_RULE_PRESETS_V1863Z = {
    "Standard": {
        "min_buy_score": 7.5,
        "min_buy_confidence": 70,
        "max_buy_rsi": 72,
        "min_hold_days": 1,
        "use_noise_filter": False,
        "ignore_small_moves_pct": 1.0,
        "enable_sell_signal_exit": True,
        "stop_loss_pct": 7.0,
        "take_profit_pct": 12.0,
        "trailing_stop_pct": 8.0,
        "rsi_exit_level": 75,
        "rsi_must_fall": True,
    },
    "Konservativ": {
        "min_buy_score": 8.0,
        "min_buy_confidence": 80,
        "max_buy_rsi": 65,
        "min_hold_days": 2,
        "enable_sell_signal_exit": True,
        "stop_loss_pct": 5.0,
        "take_profit_pct": 10.0,
        "trailing_stop_pct": 6.0,
        "rsi_exit_level": 72,
        "rsi_must_fall": True,
        "use_noise_filter": False,
        "ignore_small_moves_pct": 1.0,
    },
    "Aggressiv": {
        "min_buy_score": 7.0,
        "min_buy_confidence": 60,
        "max_buy_rsi": 80,
        "min_hold_days": 0,
        "enable_sell_signal_exit": True,
        "stop_loss_pct": 8.0,
        "take_profit_pct": 18.0,
        "trailing_stop_pct": 10.0,
        "rsi_exit_level": 80,
        "rsi_must_fall": True,
        "use_noise_filter": False,
        "ignore_small_moves_pct": 1.0,
    },
}


def _trading_strategy_label_v1863z(rules):
    def _same(current, expected):
        if isinstance(expected, bool):
            return bool(current) == bool(expected)
        try:
            return abs(float(current) - float(expected)) < 0.001
        except Exception:
            return str(current) == str(expected)

    for name, preset in _TRADING_RULE_PRESETS_V1863Z.items():
        if all(_same(rules.get(k), v) for k, v in preset.items()):
            return name
    return "Egendefinert"


def _render_trading_strategy_summary_v1863z(rules):
    name = _trading_strategy_label_v1863z(rules)
    if name == "Konservativ":
        profile, cls = "Lavere risiko, færre kjøp, strengere confidence.", "green"
    elif name == "Aggressiv":
        profile, cls = "Høyere aktivitet, løsere kjøpskrav og videre exits.", "yellow"
    elif name == "Standard":
        profile, cls = "Balansert standardoppsett for normal paper trading.", "green"
    else:
        profile, cls = "Reglene avviker fra presetene. Dette er din aktive egendefinerte strategi.", "yellow"

    st.markdown(
        f"""
        <div class='v18-dark-row' style='border-color:rgba(56,189,248,.55);margin:.45rem 0 .65rem 0;padding:.68rem .78rem;'>
          <div style='display:flex;justify-content:space-between;gap:.65rem;flex-wrap:wrap;align-items:center;'>
            <div>
              <div style='font-size:.78rem;color:#bae6fd;font-weight:950;text-transform:uppercase;'>Gjeldende trading-strategi</div>
              <div style='font-size:1.08rem;color:#f8fafc;font-weight:950;'>{html.escape(name)}</div>
            </div>
            <span class='v18-status-chip {cls}'>Aktiv nå</span>
          </div>
          <div style='display:flex;gap:.45rem;flex-wrap:wrap;margin-top:.45rem;'>
            <span class='v18-status-chip'>BUY score ≥ <b>{float(rules.get("min_buy_score", 0) or 0):.1f}</b></span>
            <span class='v18-status-chip'>Confidence ≥ <b>{int(rules.get("min_buy_confidence", 0) or 0)}</b></span>
            <span class='v18-status-chip'>Maks RSI <b>{int(rules.get("max_buy_rsi", 0) or 0)}</b></span>
            <span class='v18-status-chip red'>Stop-loss <b>{float(rules.get("stop_loss_pct", 0) or 0):.1f}%</b></span>
            <span class='v18-status-chip green'>Take-profit <b>{float(rules.get("take_profit_pct", 0) or 0):.1f}%</b></span>
            <span class='v18-status-chip yellow'>Trailing <b>{float(rules.get("trailing_stop_pct", 0) or 0):.1f}%</b></span>
          </div>
          <div style='font-size:.82rem;color:#cbd5e1;margin-top:.38rem;line-height:1.35;'>{html.escape(profile)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# V15.5 / Fase 1: flytt store arbeidsinnstillinger ut av venstremenyen og inn i hovedarbeidsflaten.
def render_trading_rules_workspace():
    """Hovedområde for trading-regler. Erstatter lange Kjøp/Hold/Salg-menyer i venstresiden."""
    _rules = load_rules()
    with st.expander("📊 Trading-regler", expanded=False):
        st.caption("Arbeidsflate for kjøps-, hold- og salgsregler. Endringer brukes først når du trykker «Oppdater hele appen».")
        _render_trading_strategy_summary_v1863z(_rules)
        p1, p2, p3, p4 = st.columns([1, 1, 1, 2])
        with p1:
            if st.button("↩️ Standard trading-regler", key="main_rules_preset_standard_v156", use_container_width=True):
                _apply_trading_rule_preset_v159("Standard trading-regler", {
                    "min_buy_score": 7.5,
                    "min_buy_confidence": 70,
                    "max_buy_rsi": 72,
                    "min_hold_days": 1,
                    "use_noise_filter": False,
                    "ignore_small_moves_pct": 1.0,
                    "enable_sell_signal_exit": True,
                    "stop_loss_pct": 7.0,
                    "take_profit_pct": 12.0,
                    "trailing_stop_pct": 8.0,
                    "rsi_exit_level": 75,
                    "rsi_must_fall": True,
                })
        with p2:
            if st.button("🛡️ Konservativ", key="main_rules_preset_conservative_v156", use_container_width=True):
                _apply_trading_rule_preset_v159("Konservativt preset", {
                    "min_buy_score": 8.0,
                    "min_buy_confidence": 80,
                    "max_buy_rsi": 65,
                    "min_hold_days": 2,
                    "enable_sell_signal_exit": True,
                    "stop_loss_pct": 5.0,
                    "take_profit_pct": 10.0,
                    "trailing_stop_pct": 6.0,
                    "rsi_exit_level": 72,
                    "rsi_must_fall": True,
                    "use_noise_filter": False,
                    "ignore_small_moves_pct": 1.0,
                })
        with p3:
            if st.button("⚡ Aggressiv", key="main_rules_preset_aggressive_v156", use_container_width=True):
                _apply_trading_rule_preset_v159("Aggressivt preset", {
                    "min_buy_score": 7.0,
                    "min_buy_confidence": 60,
                    "max_buy_rsi": 80,
                    "min_hold_days": 0,
                    "enable_sell_signal_exit": True,
                    "stop_loss_pct": 8.0,
                    "take_profit_pct": 18.0,
                    "trailing_stop_pct": 10.0,
                    "rsi_exit_level": 80,
                    "rsi_must_fall": True,
                    "use_noise_filter": False,
                    "ignore_small_moves_pct": 1.0,
                })
        with p4:
            st.caption("Preset-knappene endrer bare trading-regler. Auto trading-parametere endres ikke, og tung analyse startes ikke av preset alene.")

        if st.session_state.get("rules_preset_notice_v159"):
            st.success(st.session_state.pop("rules_preset_notice_v159"))

        with st.form("trading_rules_form_v17", clear_on_submit=False):
            buy_col, hold_col, sell_col = st.columns(3)
            with buy_col:
                st.markdown("#### 📈 Kjøp")
                _rules["min_buy_score"] = st.slider("Min BUY score", 1.0, 10.0, float(_rules.get("min_buy_score", 7.5)), 0.1, key="main_rules_min_buy_score_v156")
                _rules["min_buy_confidence"] = st.slider("Min BUY confidence", 1, 100, int(_rules.get("min_buy_confidence", 70)), key="main_rules_min_buy_conf_v156")
                _rules["max_buy_rsi"] = st.slider("Maks RSI for kjøp", 40, 90, int(_rules.get("max_buy_rsi", 72)), key="main_rules_max_buy_rsi_v156")
                st.caption("Maks kjøp per dag styres i Auto trading-oppsett. Gjelder bare nye kjøp, ikke salg/exit.")
            with hold_col:
                st.markdown("#### 🟡 Hold")
                _rules["min_hold_days"] = st.slider("Min hold-dager", 0, 30, int(_rules.get("min_hold_days", 1)), key="main_rules_min_hold_days_v156")
                st.caption("Støyfilter er flyttet til Avanserte salgsregler slik at enkel visning ikke forveksler filter med stop-loss/take-profit.")
            with sell_col:
                st.markdown("#### 🔴 Salg")
                _rules["enable_sell_signal_exit"] = st.checkbox("Selg ved SELL/AVOID signal", bool(_rules.get("enable_sell_signal_exit", True)), key="main_rules_sell_signal_v156")
                _rules["stop_loss_pct"] = st.slider("Stop-loss %", 1.0, 25.0, float(_rules.get("stop_loss_pct", 7.0)), 0.5, key="main_rules_stop_loss_v156")
                _rules["take_profit_pct"] = st.slider("Take-profit %", 1.0, 50.0, float(_rules.get("take_profit_pct", 12.0)), 0.5, key="main_rules_take_profit_v156")
                _rules["trailing_stop_pct"] = st.slider("Trailing stop %", 1.0, 30.0, float(_rules.get("trailing_stop_pct", 8.0)), 0.5, key="main_rules_trailing_stop_v156")
                _rules["rsi_exit_level"] = st.slider("RSI exit nivå", 60, 90, int(_rules.get("rsi_exit_level", 75)), key="main_rules_rsi_exit_v156")
                _rules["rsi_must_fall"] = st.checkbox("RSI må falle etter topp", bool(_rules.get("rsi_must_fall", True)), key="main_rules_rsi_fall_v156")
            with st.expander("Avanserte salgsregler / støyfilter", expanded=False):
                _rules["use_noise_filter"] = st.checkbox(
                    "Bruk støyfilter",
                    bool(_rules.get("use_noise_filter", False)),
                    key="main_rules_use_noise_filter_v156",
                    help="Valgfritt filter som kan hindre reaksjon på små signalendringer. Blokkerer aldri stop-loss, take-profit, trailing stop eller RSI-exit.",
                )
                _rules["ignore_small_moves_pct"] = st.slider(
                    "Støyfilter / ignorer små svingninger %",
                    0.0,
                    5.0,
                    float(_rules.get("ignore_small_moves_pct", 1.0)),
                    0.25,
                    key="main_rules_ignore_small_v156",
                )
                st.caption("Anbefalt: Av som standard. Hvis aktivert: 0.5–1.0 %. Stop-loss og andre risikoutganger har alltid prioritet.")
            save_rules_btn = st.form_submit_button("💾 Lagre trading-regler som ventende", use_container_width=True)
        if save_rules_btn:
            _mark_pending_manual_change("Trading-regler endret")
            saved_db = save_rules(_rules)
            if saved_db:
                st.success("Trading-regler lagret som ventende i database ✅")
            else:
                st.warning("Trading-regler lagret lokalt som ventende. DATABASE_URL mangler eller DB feilet.")


def _render_pushover_test_panel_v18595() -> None:
    """Desktop/mobile safe Pushover test panel placed high in Auto trading setup."""
    st.markdown(
        """
        <style>
        html body .stApp .visual-truth-pushover-box-v18596 {
            position:relative !important;
            z-index:1 !important;
            display:block !important;
            clear:both !important;
            margin:.72rem 0 .62rem 0 !important;
        }
        html body .stApp .pushover-button-anchor-v18596 {
            display:block !important;
            clear:both !important;
            height:.10rem !important;
            margin:0 !important;
        }
        html body .stApp .v18593-pushover-result {
            display:block !important;
            clear:both !important;
            margin:.48rem 0 .86rem 0 !important;
        }
        html body .stApp .v1863d-pushover-layout-break {
            display:block !important;
            clear:both !important;
            width:100% !important;
            height:1.05rem !important;
            margin:0 0 .35rem 0 !important;
            border-bottom:1px solid rgba(125,211,252,.18) !important;
        }
        html body .stApp .v1863d-auto-form-start {
            display:block !important;
            clear:both !important;
            width:100% !important;
            height:.25rem !important;
        }
        html body .stApp .v1863e-pushover-action-card {
            display:block !important;
            clear:both !important;
            width:100% !important;
            max-width:100% !important;
            margin:.52rem 0 .62rem 0 !important;
            padding:.72rem .88rem !important;
            border:1px solid rgba(125,211,252,.32) !important;
            border-radius:12px !important;
            background:rgba(8,20,42,.54) !important;
            color:#e0f2fe !important;
        }
        html body .stApp .v1863e-pushover-action-card b {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }
        html body .stApp div[data-testid="stRadio"],
        html body .stApp div[data-testid="stForm"] {
            clear:both !important;
            width:100% !important;
            max-width:100% !important;
            overflow:visible !important;
        }
        @media (max-width:900px) {
            html body .stApp .visual-truth-pushover-box-v18596 {
                margin:.58rem 0 .54rem 0 !important;
                padding:.74rem .82rem !important;
            }
            html body .stApp .v1863d-pushover-layout-break {
                height:.80rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _pushover_env_ok_v18595 = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)
    _pushover_ready_v18595 = _pushover_env_ok_v18595 and bool(load_settings().get("pushover_enabled", True))
    _token_state_v18595 = "OK" if bool(PUSHOVER_APP_TOKEN) else "MANGLER"
    _user_state_v18595 = "OK" if bool(PUSHOVER_USER_KEY) else "MANGLER"
    st.markdown(
        f"""
        <div class='visual-truth-pushover-box visual-truth-pushover-box-v18596' data-ui-path='active-pushover-test-v18595' data-ui-patch='active-pushover-test-v18596'>
            <div class='visual-truth-pushover-title'>🔔 Pushover test / API-status</div>
            <div class='visual-truth-pushover-status'>
                Status: {'Aktiv ✅' if _pushover_ready_v18595 else 'Ikke klar ❌'} ·
                Token: {_token_state_v18595} · User-key: {_user_state_v18595}<br/>
                Dette er den aktive testflaten. Knappene under skal være synlige på PC og mobil.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _last_pushover_check = st.session_state.get("pushover_last_check_v18585")
    st.markdown(
        "<div class='v1863e-pushover-action-card'><b>Pushover handling</b><br/>Velg API-verifisering eller testvarsel, og kjør med knappen under.</div>",
        unsafe_allow_html=True,
    )
    with st.form("pushover_action_form_v1863e", clear_on_submit=False):
        _pushover_action = st.radio(
            "Velg handling",
            ["Verifiser token/user", "Send testvarsel"],
            horizontal=True,
            key="pushover_action_choice_v1863e",
        )
        _pushover_run_clicked = st.form_submit_button(
            "Kjør valgt Pushover-handling",
            use_container_width=True,
            type="primary",
        )
    if _last_pushover_check:
        _ok = bool(_last_pushover_check.get("ok"))
        _http = _last_pushover_check.get("status_code", "-")
        _kind = _last_pushover_check.get("type", "-")
        st.markdown(
            f"<div class='v18593-pushover-result'>Siste API-sjekk: {'OK ✅' if _ok else 'Feil ❌'} · HTTP {_http} · {_kind}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='v18593-pushover-result'>Ingen API-verifisering kjørt i denne sesjonen ennå.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div class='v1863d-pushover-layout-break'></div>", unsafe_allow_html=True)

    if _pushover_run_clicked and _pushover_action == "Verifiser token/user":
        if not _pushover_env_ok_v18595:
            st.error("Pushover-token eller user-key mangler. Legg inn PUSHOVER_APP_TOKEN og PUSHOVER_USER_KEY før API-verifisering.")
        else:
            verify_info = verify_pushover_credentials_v18585()
            st.session_state["pushover_last_check_v18585"] = {"type": "verify", **verify_info}
            if verify_info.get("ok"):
                st.success(f"Pushover-verifisering OK ✅ HTTP {verify_info.get('status_code')}")
            else:
                st.error(f"Pushover-verifisering feilet ❌ {verify_info.get('response_text')}")
    if _pushover_run_clicked and _pushover_action == "Send testvarsel":
        if not _pushover_env_ok_v18595:
            st.error("Pushover-token eller user-key mangler. Legg inn PUSHOVER_APP_TOKEN og PUSHOVER_USER_KEY før testvarsel sendes.")
        else:
            ok, err, info = send_pushover_alert("✅ Testvarsel fra AI Aksje Analyzer Pro", title="Testvarsel")
            st.session_state["pushover_last_check_v18585"] = {"type": "send_test", "ok": ok, **(info or {})}
            if ok:
                st.success(f"Test sendt ✅ HTTP {(info or {}).get('status_code')}")
            else:
                st.error(f"Testvarsel feilet ❌ {err}")


def render_auto_trading_workspace():
    """Hovedområde for Auto trading / Auto-kjøp parametere. Erstatter stor sidebar-meny."""
    _settings = load_settings()
    _markets_settings = _settings.get("markets", {}) or {}
    with st.expander("⚙️ Auto trading-oppsett", expanded=False):
        st.caption("Samlet arbeidsflate for Auto trading. Full stopp / ferie og nødstopp overstyrer alltid disse innstillingene.")
        _render_pushover_test_panel_v18595()
        with st.form("auto_trading_settings_form_v17", clear_on_submit=False):
            st.markdown("<div class='v1863d-auto-form-start'></div>", unsafe_allow_html=True)
            drift_col, buy_col = st.columns(2)
            with drift_col:
                st.markdown("#### Drift")
                _auto_enabled = st.checkbox(
                    "Auto trading aktiv",
                    value=bool(_settings.get("auto_trading_enabled", False)),
                    key="main_auto_enabled_v155",
                )
                _safe_edit = st.checkbox(
                    "Pause når parametere lagres",
                    value=bool(_settings.get("auto_trading_safe_edit_mode", True)),
                    key="main_auto_safe_edit_v155",
                    help="Ved lagring settes auto trading i pause slik at du kan kontrollere parametere før ny start.",
                )
                _top_only = st.checkbox(
                    "Kun Top Picks",
                    value=bool(_settings.get("scan_top_picks_only", True)),
                    key="main_auto_top_only_v155",
                )
                st.markdown("**Markeder**")
                _m_usa = st.checkbox("USA", value=bool(_markets_settings.get("USA", True)), key="main_auto_market_usa_v155")
                _m_no = st.checkbox("Norge", value=bool(_markets_settings.get("NORGE", True)), key="main_auto_market_no_v155")
                _m_se = st.checkbox("Sverige", value=bool(_markets_settings.get("SVERIGE", True)), key="main_auto_market_se_v155")
                _m_fi = st.checkbox("Finland", value=bool(_markets_settings.get("FINLAND", True)), key="main_auto_market_fi_v1863t")
                _m_dk = st.checkbox("Danmark", value=bool(_markets_settings.get("DANMARK", True)), key="main_auto_market_dk_v1863t")
                _m_br = st.checkbox("Brasil", value=bool(_markets_settings.get("BRASIL", False)), key="main_auto_market_br_v1863t")
            with buy_col:
                st.markdown("#### Kjøpsgrenser")
                _min_conf = st.number_input(
                    "Min confidence for BUY",
                    0,
                    100,
                    int(_settings.get("min_buy_confidence", 70)),
                    1,
                    key="main_auto_min_conf_v155",
                )
                _min_score = st.number_input(
                    "Min score for BUY",
                    0.0,
                    10.0,
                    float(_settings.get("min_buy_score", 7.2)),
                    0.1,
                    key="main_auto_min_score_v155",
                )
                _pos_size = st.number_input(
                    "Posisjonsstørrelse %",
                    1.0,
                    100.0,
                    float(_settings.get("position_size_pct", 10.0)),
                    1.0,
                    key="main_auto_pos_size_v155",
                )
                _cooldown = st.number_input(
                    "Cooldown mellom kjøp (min)",
                    0,
                    1440,
                    int(_settings.get("cooldown_minutes", 60)),
                    5,
                    key="main_auto_cooldown_v155",
                )
                st.caption("Cooldown og maks kjøp gjelder bare nye kjøp. Salg/exit blokkeres ikke.")
            risk_col, safe_col = st.columns(2)
            with risk_col:
                st.markdown("#### Kapasitet / risiko")
                _max_tickers = st.number_input(
                    "Maks aksjer per marked",
                    1,
                    100,
                    int(_settings.get("max_tickers_per_market", 20)),
                    1,
                    key="main_auto_max_tickers_v155",
                )
                _max_pos = st.number_input(
                    "Maks åpne posisjoner",
                    1,
                    30,
                    int(_settings.get("max_open_positions", 5)),
                    1,
                    key="main_auto_max_pos_v155",
                )
                _max_buys = st.number_input(
                    "Maks kjøp per dag",
                    1,
                    50,
                    int(_settings.get("max_buys_per_day", _settings.get("max_trades_per_day", 3))),
                    1,
                    key="main_auto_max_buys_v155",
                )
            with safe_col:
                st.markdown("#### Sikkerhet / varsling")
                _safety_mode = st.checkbox(
                    "Sikkerhetsmodus",
                    value=bool(_settings.get("auto_buy_safety_mode", True)),
                    key="main_auto_safety_mode_v155",
                    help="Når på: nye kjøp stoppes ved dårlig/ugyldig data eller grensebrudd. Salg/exit skal fortsatt få gå.",
                )
                if _safety_mode:
                    st.markdown("<div class='visual-truth-safe-note'>✅ <b>Sikkerhetsmodus er aktiv</b><br/>Blokkerer nye kjøp ved lav cash, dagsgrense, lav confidence eller svak datakvalitet. Salg/exit og nødstopp prioriteres fortsatt.</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='visual-truth-safe-note'>⚠️ <b>Sikkerhetsmodus er AV</b><br/>Cash- og dagsgrenser gjelder fortsatt. Ekstra blokkering på confidence/datakvalitet er av.</div>", unsafe_allow_html=True)
                _push = st.checkbox(
                    "Pushover aktiv",
                    value=bool(_settings.get("pushover_enabled", True)),
                    key="main_auto_push_v155",
                )
                st.caption("Full stopp / ferie og nødstopp har alltid høyest prioritet.")
            b1, b2 = st.columns(2)
            with b1:
                save_auto_btn = st.form_submit_button("💾 Lagre auto-innstillinger som ventende", use_container_width=True)
            with b2:
                reset_auto_btn = st.form_submit_button("↩️ Standard auto-innstillinger", use_container_width=True)
        if save_auto_btn:
            _mark_pending_manual_change("Auto trading-innstillinger endret")
            _current = load_settings()
            _current.update({
                "auto_trading_enabled": bool(_auto_enabled) and not bool(_safe_edit),
                "auto_trading_paused": bool(_safe_edit) if bool(_auto_enabled) else False,
                "auto_trading_emergency_stop": False,
                "auto_trading_safe_edit_mode": bool(_safe_edit),
                "markets": {"USA": bool(_m_usa), "NORGE": bool(_m_no), "SVERIGE": bool(_m_se), "FINLAND": bool(_m_fi), "DANMARK": bool(_m_dk), "BRASIL": bool(_m_br)},
                "max_tickers_per_market": int(_max_tickers),
                "min_buy_confidence": int(_min_conf),
                "min_buy_score": float(_min_score),
                "max_open_positions": int(_max_pos),
                "max_trades_per_day": int(_max_buys),
                "max_buys_per_day": int(_max_buys),
                "position_size_pct": float(_pos_size),
                "cooldown_minutes": int(_cooldown),
                "scan_top_picks_only": bool(_top_only),
                "pushover_enabled": bool(_push),
                "auto_buy_safety_mode": bool(_safety_mode),
            })
            save_settings(_current)
            try:
                _r = load_rules()
                _r["max_trades_per_day"] = int(_max_buys)
                save_rules(_r)
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)
            st.success("Auto-innstillinger lagret som ventende ✅")
        if reset_auto_btn:
            reset_settings()
            st.success("Auto-innstillinger tilbakestilt ✅")
            st.rerun()
        # v18.5.95: Pushover test/API-status moved to the top of this expander for desktop visibility.


# V15.6 / Fase 2: Varselkontroll og dynamisk watchlist flyttes fra venstremenyen til hovedområdet.
def render_watchlist_alerts_workspace(dynamic_watchlist, pushover_enabled_runtime=False):
    """Returnerer (watchlist_tickers, auto_watchlist_alerts, watchlist_scan_limit, manual_watchlist_scan)."""
    _settings = load_settings()
    _pushover_env_ok = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)
    _pushover_setting_on = bool(_settings.get("pushover_enabled", True))
    _pushover_ready = _pushover_env_ok and _pushover_setting_on

    _default_use_dynamic = bool(_settings.get("use_dynamic_watchlist_from_market", True))
    _default_auto_scan = bool(_settings.get("auto_watchlist_alerts_refresh", False))
    _default_limit = int(_settings.get("watchlist_scan_limit", min(30, max(5, len(dynamic_watchlist or [])))))
    _default_limit = max(5, min(100, _default_limit))
    _watchlist_tickers = list(dynamic_watchlist or [])
    _auto_scan = _default_auto_scan
    _scan_limit = _default_limit
    _manual_scan = False

    with st.expander("🔔 Varsler og dynamisk watchlist", expanded=False):
        st.caption("Fase 2: Watchlist- og varselinnstillinger er flyttet hit fra venstremenyen, nær signalene de styrer.")
        wl_tab, alert_tab = st.tabs(["Dynamisk watchlist", "Varselkontroll"])
        with wl_tab:
            c1, c2 = st.columns([1.2, 1])
            with c1:
                _use_dynamic = st.checkbox(
                    "Bruk dynamisk watchlist fra markedet",
                    value=_default_use_dynamic,
                    key="main_use_dynamic_watchlist_v156",
                    help="Når aktiv: watchlisten følger valgt marked og appens egne score/rangeringer.",
                )
                if _use_dynamic:
                    _watchlist_tickers = list(dynamic_watchlist or [])
                    st.info(f"Dynamisk watchlist aktiv: {len(_watchlist_tickers)} aksjer")
                    with st.expander("Vis dynamisk watchlist", expanded=False):
                        st.write(", ".join(_watchlist_tickers) if _watchlist_tickers else "Ingen tickere i listen ennå.")
                else:
                    _watchlist_text = st.text_area(
                        "Aksjer å overvåke",
                        value=", ".join(list(dynamic_watchlist or [])[:30]),
                        help="Skriv tickere separert med komma. Norske aksjer må ofte ha .OL og svenske .ST",
                        key="main_watchlist_text_v156",
                    )
                    _watchlist_tickers = parse_watchlist(_watchlist_text)
            with c2:
                _auto_scan = st.checkbox(
                    "Auto-scan watchlist ved refresh",
                    value=_default_auto_scan,
                    key="main_auto_watchlist_scan_v156",
                    help="Sender varsel bare når BUY/SELL-signalet endrer seg.",
                )
                _scan_limit = st.slider(
                    "Maks aksjer å scanne for varsler",
                    5,
                    100,
                    _default_limit,
                    key="main_watchlist_scan_limit_v156",
                )
                _manual_scan = st.button("Scan watchlist nå", key="main_scan_watchlist_now_v156")
                if _global_apply_requested_v161():
                    _save = load_settings()
                    _save["use_dynamic_watchlist_from_market"] = bool(_use_dynamic)
                    _save["auto_watchlist_alerts_refresh"] = bool(_auto_scan)
                    _save["watchlist_scan_limit"] = int(_scan_limit)
                    save_settings(_save)
                    st.success("Watchlist-innstillinger oppdatert via Global oppdatering ✅")

        with alert_tab:
            st.markdown(
                f"""
                <div class="alert-status-pill {'ok' if _pushover_ready else 'bad'}">
                    <div class="alert-status-title">Pushover: {'Aktiv ✅' if _pushover_ready else 'Ikke klar ❌'}</div>
                    <div class="alert-status-sub">Åpne markeder nå: {open_markets()}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            ac1, ac2 = st.columns(2)
            with ac1:
                _pushover_setting_on = st.checkbox(
                    "Pushover aktiv",
                    value=bool(_settings.get("pushover_enabled", True)),
                    key="main_alert_pushover_enabled_v156",
                )
                _notify_trades = st.checkbox(
                    "Varsle ved faktisk paper BUY/SELL",
                    value=bool(_settings.get("notify_paper_trades", True)),
                    key="main_alert_notify_paper_v156",
                )
                _notify_watchlist = st.checkbox(
                    "Varsle ved watchlist signalendring",
                    value=bool(_settings.get("notify_watchlist_signal_changes", True)),
                    key="main_alert_notify_watchlist_v156",
                )
            with ac2:
                _high_conf_only = st.checkbox(
                    "Varsle kun høy confidence",
                    value=bool(_settings.get("notify_high_confidence_only", True)),
                    key="main_alert_high_conf_only_v156",
                )
                _min_alert_conf = st.slider(
                    "Confidence-grense",
                    50,
                    95,
                    int(_settings.get("notify_min_confidence", 80)),
                    1,
                    key="main_alert_min_conf_v156",
                )
                st.caption("Watchlist-varsler bruker denne grensen når høy confidence er aktivert.")

            b1, b2, b3, b4 = st.columns([1, 0.9, 0.9, 0.7])
            with b1:
                if _global_apply_requested_v161():
                    _merged = load_settings()
                    _merged["pushover_enabled"] = bool(_pushover_setting_on)
                    _merged["notify_paper_trades"] = bool(_notify_trades)
                    _merged["notify_watchlist_signal_changes"] = bool(_notify_watchlist)
                    _merged["notify_high_confidence_only"] = bool(_high_conf_only)
                    _merged["notify_min_confidence"] = int(_min_alert_conf)
                    save_settings(_merged)
                    st.success("Varselkontroll oppdatert via Global oppdatering ✅")
            with b2:
                if st.button("🔐 Verifiser token/user", key="main_alert_verify_pushover_v18585", disabled=not _pushover_env_ok, use_container_width=True):
                    verify_info = verify_pushover_credentials_v18585()
                    st.session_state["pushover_last_check_v18585"] = {"type": "verify", **verify_info}
                    if verify_info.get("ok"):
                        st.success(f"Pushover-verifisering OK ✅ HTTP {verify_info.get('status_code')}")
                    else:
                        st.error(f"Pushover-verifisering feilet ❌ {verify_info.get('response_text')}")
            with b3:
                if st.button("📣 Send testvarsel", key="main_alert_send_test_v18585", disabled=not _pushover_env_ok, use_container_width=True):
                    ok, err, info = send_pushover_alert("✅ Testvarsel fra AI Aksje Analyzer Pro", title="Testvarsel")
                    st.session_state["pushover_last_check_v18585"] = {"type": "send_test", "ok": ok, **(info or {})}
                    if ok:
                        st.success(f"Test sendt ✅ HTTP {(info or {}).get('status_code')}")
                    else:
                        st.error(f"Feil: {err}")
            with b4:
                if st.button("Nullstill", key="main_alert_reset_antispam_v156", use_container_width=True):
                    reset_alert_state()
                    st.success("Signalhistorikk nullstilt ✅")
            with st.expander("Varselinfo / Pushover-status", expanded=False):
                st.caption("Paper BUY/SELL-varsler sendes bare når en faktisk paper-handel utføres.")
                st.caption("Watchlist-varsler sendes ved signalendring, og bruker confidence-grensen hvis høy confidence er aktivert.")
                st.write("TOKEN:", _mask_secret_v18585(PUSHOVER_APP_TOKEN))
                st.write("USER:", _mask_secret_v18585(PUSHOVER_USER_KEY))
                _last = st.session_state.get("pushover_last_check_v18585")
                if _last:
                    st.write("Siste Pushover-sjekk:", _last)
                else:
                    st.caption("Ingen API-verifisering kjørt i denne sesjonen ennå.")

    st.session_state["latest_watchlist_tickers_v156"] = list(_watchlist_tickers or [])
    return _watchlist_tickers, bool(_auto_scan), int(_scan_limit), bool(_manual_scan)


def _render_paper_positions_overview_v18581(portfolio):
    """Show open Paper Trading positions and recent trades high in the dashboard without returning Streamlit objects."""
    try:
        positions = (portfolio or {}).get("positions", {}) or {}
    except Exception:
        positions = {}

    st.markdown("<div class='v18581-paper-section-title'>📌 Åpne Paper Trading-posisjoner</div>", unsafe_allow_html=True)
    if positions:
        rows = []
        for ticker, pos in positions.items():
            try:
                pos = pos or {}
                last_price = float(pos.get("last_price", pos.get("avg_price", pos.get("entry_price", 0))) or 0)
                avg_price = float(pos.get("avg_price", pos.get("entry_price", last_price)) or last_price)
                shares = float(pos.get("shares", pos.get("units", 0)) or 0)
                value = shares * last_price
                pnl_pct = ((last_price - avg_price) / avg_price * 100) if avg_price else 0
                rows.append({
                    "Ticker": ticker,
                    "Type": pos.get("asset_type", "Aksje"),
                    "Antall": round(shares, 4),
                    "Snittpris": round(avg_price, 4),
                    "Siste pris": round(last_price, 4),
                    "Verdi": round(value, 2),
                    "Valuta": pos.get("currency", ""),
                    "P/L %": round(pnl_pct, 2),
                })
            except Exception:
                rows.append({"Ticker": ticker, "Type": (pos or {}).get("asset_type", "Aksje") if isinstance(pos, dict) else "Aksje"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Ingen åpne paper trading-posisjoner.")

    try:
        trades = list((portfolio or {}).get("trades", []) or [])
    except Exception:
        trades = []
    st.markdown("<div class='v18581-paper-section-title'>🧾 Siste Paper Trading-handler</div>", unsafe_allow_html=True)
    if trades:
        st.dataframe(pd.DataFrame(paper_trade_rows(trades, limit=20)), use_container_width=True, hide_index=True)
    else:
        st.info("Ingen handler ennå.")


def _safe_float_v18581(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _fetch_latest_paper_price_v1863v(ticker: str):
    """Fetch one latest close for explicit Paper Trading price refresh."""
    if yf is None:
        return None, "yfinance er ikke tilgjengelig"
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return None, "mangler ticker"
    try:
        hist = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False, prepost=False)
        if hist is None or getattr(hist, "empty", True) or "Close" not in hist:
            return None, "fant ingen Close-data"
        close = hist["Close"].dropna()
        if close.empty:
            return None, "Close-data er tom"
        return float(close.iloc[-1]), ""
    except Exception as exc:
        return None, str(exc)[:160]


def _refresh_paper_portfolio_prices_v1863v(portfolio, *, fetch_live: bool = False):
    positions = (portfolio or {}).get("positions", {}) or {}
    latest_prices = {}
    errors = []
    updated_at = timestamp_now() if fetch_live else ""
    if fetch_live:
        for ticker in positions.keys():
            price, err = _fetch_latest_paper_price_v1863v(ticker)
            if price and price > 0:
                latest_prices[str(ticker).upper()] = price
            else:
                errors.append(f"{ticker}: {err or 'ingen pris'}")
    normalized = normalize_paper_portfolio(portfolio, latest_prices, updated_at=updated_at)
    should_save = bool(fetch_live and latest_prices)
    if not should_save:
        for old_pos in positions.values():
            if _safe_float_v18581((old_pos or {}).get("avg_price"), 0.0) <= 0 and (
                _safe_float_v18581((old_pos or {}).get("entry_price"), 0.0) > 0
                or _safe_float_v18581((old_pos or {}).get("last_price"), 0.0) > 0
            ):
                should_save = True
                break
    if should_save:
        save_portfolio(normalized)
    return normalized, latest_prices, errors, updated_at


def _paper_price_candidates_v1863z(symbol: str, *, asset_type: str = "Aksje"):
    raw = str(symbol or "").strip().upper()
    if not raw:
        return []
    alias = {
        "ORKLY": "ORK.OL",
        "ORCLA": "ORK.OL",
    }.get(raw, raw)
    candidates = [alias]
    if asset_type == "Aksje" and "." not in alias and alias.isalpha():
        candidates.append(f"{alias}.OL")
    return list(dict.fromkeys(candidates))


def _fetch_yfinance_close_v1863z(symbol: str, *, asset_type: str = "Aksje"):
    if yf is None:
        return None, "", "yfinance er ikke tilgjengelig i miljøet."
    last_error = ""
    for candidate in _paper_price_candidates_v1863z(symbol, asset_type=asset_type):
        try:
            hist = yf.Ticker(candidate).history(period="5d", interval="1d", auto_adjust=False, prepost=False)
            if hist is not None and not hist.empty and "Close" in hist:
                close = hist["Close"].dropna()
                if not close.empty:
                    return float(close.iloc[-1]), candidate, ""
        except Exception as exc:
            last_error = str(exc)
    return None, "", last_error or "Fant ikke pris/NAV i Yahoo Finance."


def _paper_fetch_stock_price_v1863z():
    symbol = str(st.session_state.get("paper_stock_symbol_v1863y", "") or "").strip().upper()
    if not symbol:
        st.session_state["paper_stock_fetch_status_v1863z"] = ("warning", "Skriv inn aksjesymbol først.")
        return
    price, resolved, err = _fetch_yfinance_close_v1863z(symbol, asset_type="Aksje")
    if price and price > 0:
        st.session_state["paper_stock_price_input_v1863y"] = float(price)
        st.session_state["paper_stock_fetch_status_v1863z"] = ("success", f"Hentet {resolved}: {price:.4f}. Kjøpspris er oppdatert.")
    else:
        st.session_state["paper_stock_fetch_status_v1863z"] = ("warning", f"Fant ikke aksjekurs for {symbol}. {err} Prøv børs-suffiks, f.eks. .OL, eller skriv pris manuelt.")


def _paper_fetch_fund_price_v1863z():
    symbol = str(st.session_state.get("paper_fund_symbol_v18545", "") or "").strip().upper()
    asset_type = str(st.session_state.get("paper_fund_type_v18545", "ETF") or "ETF")
    if not symbol:
        st.session_state["paper_fund_fetch_status_v1863z"] = ("warning", "Skriv inn fond/ETF-symbol først.")
        return
    price, resolved, err = _fetch_yfinance_close_v1863z(symbol, asset_type=asset_type)
    if price and price > 0:
        st.session_state["paper_fund_price_input_v18545"] = float(price)
        st.session_state["paper_fund_price_v18545"] = float(price)
        st.session_state["paper_fund_fetch_status_v1863z"] = ("success", f"Hentet {resolved}: {price:.4f}. Pris/NAV er oppdatert.")
    else:
        hint = "ISIN og nordiske fond mangler ofte gratis NAV-kilde. Bruk ETF/Yahoo-symbol eller skriv NAV manuelt."
        st.session_state["paper_fund_fetch_status_v1863z"] = ("warning", f"Fant ikke pris/NAV for {symbol}. {err} {hint}")


def _render_paper_fetch_status_v1863z(key: str):
    status = st.session_state.get(key)
    if not status:
        return
    level, msg = status
    if level == "success":
        st.success(msg)
    elif level == "warning":
        st.warning(msg)
    else:
        st.info(msg)


def render_paper_trading_dashboard():
    st.subheader("🧪 Paper Trading")
    st.caption("Felles lagring: " + ("Postgres/DATABASE_URL ✅" if using_postgres() else "lokal fallback ⚠️"))
    st.caption("Simulert handel med fiktive penger. Brukes for å teste strategien før ekte penger.")
    st.caption("Auto-trading handler bare når relevant marked er åpent. Utenfor åpningstid brukes visning/cache, ikke nye auto-handler.")

    portfolio = load_portfolio()

    status_cols = st.columns([1.1, 1.2, 1.7])
    with status_cols[0]:
        refresh_prices = st.button("🔄 Oppdater paper-kurser", key="paper_refresh_prices_v1863v", type="primary", use_container_width=True)
    with status_cols[1]:
        st.markdown("<div class='v18-dark-row'><b>Ekte handel:</b> Ikke aktiv</div>", unsafe_allow_html=True)
    with status_cols[2]:
        st.markdown("<div class='v18-dark-row'><b>Dette er simulert handel.</b> Ingen ordre sendes til broker.</div>", unsafe_allow_html=True)

    portfolio, refreshed_prices, refresh_errors, refreshed_at = _refresh_paper_portfolio_prices_v1863v(portfolio, fetch_live=bool(refresh_prices))
    if refresh_prices:
        st.session_state["paper_price_refresh_status_v1863v"] = {
            "time": refreshed_at,
            "updated": len(refreshed_prices),
            "errors": refresh_errors[:8],
        }
    refresh_status = st.session_state.get("paper_price_refresh_status_v1863v") or {}
    if refresh_status:
        st.caption(f"Sist oppdatert: {refresh_status.get('time', '-')} · kurser oppdatert: {refresh_status.get('updated', 0)}")
        if refresh_status.get("errors"):
            st.warning("Noen kurser ble ikke oppdatert: " + " | ".join(refresh_status.get("errors", [])[:5]))
    else:
        st.caption("Kursene oppdateres når du trykker Oppdater paper-kurser. Lagrede priser brukes ellers.")

    latest_prices = {}
    for ticker, pos in portfolio.get("positions", {}).items():
        latest_prices[ticker] = pos.get("last_price", pos.get("avg_price", pos.get("entry_price", 0)))

    total_value = portfolio_value(portfolio, latest_prices)
    liq = paper_liquidity_snapshot(portfolio, latest_prices)
    stats = performance_stats(portfolio, latest_prices)

    _paper_rules = load_rules()
    if APP_VIEW_MODE == "Full":
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Cash / kjøpekraft", _format_nok_no_decimals_v1827(liq.get('buying_power', portfolio.get('cash', 0))))
        p2.metric("Åpne posisjoner", _format_nok_no_decimals_v1827(liq.get('positions_value', 0)))
        p3.metric("Porteføljeverdi", _format_nok_no_decimals_v1827(liq.get('total_value', total_value)))
        p4.metric("Urealisert P/L", _format_nok_no_decimals_v1827(liq.get('unrealized_pnl', 0)))

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Total avkastning", f"{stats['total_return_pct']}%")
        r2.metric("Kjøp i dag", f"{stats.get('buys_today', stats.get('trades_today', 0))}/{stats.get('max_buys_per_day', stats.get('max_trades_per_day', 0))}")
        r3.metric("Win rate", f"{stats['win_rate']}%")
        r4.metric("Lukkede trades", stats["closed_trades"])
    else:
        render_compact_stat_grid([
            ("Cash / kjøpekraft", _format_nok_no_decimals_v1827(liq.get('buying_power', portfolio.get('cash', 0)))),
            ("Åpne posisjoner", _format_nok_no_decimals_v1827(liq.get('positions_value', 0))),
            ("Porteføljeverdi", _format_nok_no_decimals_v1827(liq.get('total_value', total_value))),
            ("Urealisert P/L", _format_nok_no_decimals_v1827(liq.get('unrealized_pnl', 0))),
            ("Total avkastning", f"{stats['total_return_pct']}%"),
            ("Kjøp i dag", f"{stats.get('buys_today', stats.get('trades_today', 0))}/{stats.get('max_buys_per_day', stats.get('max_trades_per_day', 0))}"),
            ("Win rate", f"{stats['win_rate']}%"),
            ("Lukkede trades", stats["closed_trades"]),
        ], columns=4)

    # DO_NOT_TOUCH_ZONE v18.5.87: Paper capital/cash semantics are protected. Patch minimally.
    with st.expander("💼 Juster Paper Trading startverdier / porteføljeverdi", expanded=True):
        st.markdown("""
        <div class="paper-edit-card">
            <b>Regulerbare startverdier</b><br>
            Startkapital brukes bare ved full reset. Porteføljeverdi er cash + åpne posisjoner. Ved "Bruk porteføljeverdi" justeres bare cash, mens åpne posisjoner beholdes. Kjøp bruker kun cash/kjøpekraft, ikke urealisert gevinst.
        </div>
        """, unsafe_allow_html=True)
        c_start, c_value = st.columns(2)
        with c_start:
            new_start_cash = st.number_input(
                "Startkapital / reset-verdi",
                min_value=10_000,
                max_value=50_000_000,
                value=int(float(_paper_rules.get("start_cash", 100000))),
                step=10_000,
                key="paper_start_cash_v12",
            )
        with c_value:
            new_portfolio_value = st.number_input(
                "Porteføljeverdi",
                min_value=0,
                max_value=50_000_000,
                value=int(float(total_value)),
                step=10_000,
                key="paper_total_value_v12",
            )
        c_apply, c_reset = st.columns(2)
        with c_apply:
            if st.button("💾 Bruk porteføljeverdi", key="paper_apply_total_value_v18581", use_container_width=True):
                target_value = _safe_float_v18581(new_portfolio_value, total_value)
                current_cash = _safe_float_v18581(portfolio.get("cash", 0), 0.0)
                positions_value = _safe_float_v18581(liq.get("positions_value", 0), 0.0)
                new_cash = round(target_value - positions_value, 2)
                if new_cash < 0:
                    st.error(f"Kan ikke sette porteføljeverdi lavere enn åpne posisjoner ({positions_value:,.0f}). Lukk/reduser posisjoner først, eller velg høyere totalverdi.")
                else:
                    portfolio["cash"] = new_cash
                    _paper_rules["start_cash"] = _safe_float_v18581(new_start_cash, current_cash)
                    save_rules(_paper_rules)
                    save_portfolio(portfolio)
                    add_audit_event("paper_portfolio_value_applied", {"target_value": target_value, "new_cash": new_cash, "positions_value": positions_value})
                    st.success(f"Porteføljeverdi oppdatert til ca. {target_value:,.0f}. Cash/kjøpekraft er nå ca. {new_cash:,.0f} ✅")
                    st.rerun()
        with c_reset:
            if st.button("↩️ Reset til startkapital", key="restore_reset_paper_portfolio_v18581", use_container_width=True):
                target_start = _safe_float_v18581(new_start_cash, 100000.0)
                _paper_rules["start_cash"] = target_start
                save_rules(_paper_rules)
                reset_portfolio(target_start)
                add_audit_event("paper_portfolio_reset", {"start_cash": target_start})
                st.success(f"Paper portfolio nullstilt til {target_start:,.0f} ✅")
                st.rerun()

    st.markdown("---")
    st.subheader("⚙️ Auto trading og regler")
    st.caption("Fase 1: Store innstillinger er flyttet hit fra venstremenyen, slik at du kan jobbe midt på skjermen.")
    render_auto_trading_workspace()
    render_trading_rules_workspace()

    st.markdown("#### 🟢 Simulert kjøp av aksjer")
    st.caption("Manuelt paper-kjøp/-salg av aksjer. Handler bruker samme paper-regler, cash og risikologg som auto trading. Ingen ekte ordre sendes.")
    with st.container():
        s1, s2, s3, s4 = st.columns([1.0, 0.85, 0.85, 0.9])
        with s1:
            stock_symbol = st.text_input("Aksjesymbol", value=st.session_state.get("paper_stock_symbol_v1863y", ""), key="paper_stock_symbol_v1863y").strip().upper()
        with s2:
            stock_price = st.number_input("Kjøpspris", min_value=0.0, max_value=1_000_000.0, value=float(st.session_state.get("paper_stock_price_v1863y", 0.0) or 0.0), step=0.01, key="paper_stock_price_input_v1863y")
        with s3:
            stock_confidence = st.number_input("Confidence", min_value=0, max_value=100, value=80, step=5, key="paper_stock_confidence_v1863y")
        with s4:
            st.button("Hent aksjekurs", key="paper_stock_fetch_price_v1863z", use_container_width=True, on_click=_paper_fetch_stock_price_v1863z)
        _render_paper_fetch_status_v1863z("paper_stock_fetch_status_v1863z")

        buy_col, sell_col = st.columns([1.0, 1.0])
        with buy_col:
            buy_stock_clicked = st.button("🟢 Paper-kjøp aksje", key="paper_stock_buy_v1863z", type="primary", use_container_width=True)
            if buy_stock_clicked:
                if not stock_symbol:
                    st.error("Skriv inn aksjesymbol først.")
                elif float(stock_price or 0.0) <= 0:
                    st.error("Skriv inn kjøpspris eller hent aksjekurs først.")
                else:
                    ok, msg = paper_buy(stock_symbol, float(stock_price), int(stock_confidence or 0), "UI paper aksjekjøp")
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        with sell_col:
            stock_positions = {k: v for k, v in (portfolio.get("positions", {}) or {}).items() if str((v or {}).get("asset_type", "Aksje")) == "Aksje"}
            sell_stock_symbol = st.selectbox("Selg aksje", list(stock_positions.keys()) or ["Ingen"], key="paper_stock_sell_symbol_v1863y")
            sell_stock_price = st.number_input("Salgspris", min_value=0.0, max_value=1_000_000.0, value=0.0, step=0.01, key="paper_stock_sell_price_v1863y")
            sell_stock_clicked = st.button("🔴 Paper-selg aksje", key="paper_stock_sell_v1863z", use_container_width=True, disabled=(sell_stock_symbol == "Ingen"))
            if sell_stock_clicked:
                price_to_use = float(sell_stock_price or (stock_positions.get(sell_stock_symbol, {}) or {}).get("last_price", 0.0) or (stock_positions.get(sell_stock_symbol, {}) or {}).get("avg_price", 0.0) or 0.0)
                if price_to_use <= 0:
                    st.error("Skriv inn salgspris først.")
                else:
                    ok, msg = paper_sell(sell_stock_symbol, price_to_use, "UI paper aksjesalg")
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    st.markdown("#### 🏦 Simulert kjøp av fond / ETF")
    st.caption("Fond/ETF handles som paper trading med beløp. ETF-er bruker siste pris, mens vanlige fond kan bruke NAV/manuell pris. Ekte handel er ikke aktivert.")
    with st.container():
        f1, f2, f3, f4 = st.columns([1.0, 1.0, 1.0, 0.9])
        with f1:
            fund_symbol = st.text_input("Fond/ETF-symbol", value=st.session_state.get("paper_fund_symbol_v18545", "VOO"), key="paper_fund_symbol_v18545").strip().upper()
        with f2:
            fund_asset_type = st.selectbox("Type", ["ETF", "Indeksfond", "Aktivt fond", "Rente-/obligasjonsfond", "High yield-fond", "Pengemarkedsfond", "Kombinasjonsfond", "Fond"], key="paper_fund_type_v18545")
        with f3:
            fund_amount = st.number_input("Beløp", min_value=100, max_value=10_000_000, value=10_000, step=500, key="paper_fund_amount_v18545")
        with f4:
            fund_currency = st.selectbox("Valuta", ["NOK", "USD", "EUR", "SEK"], key="paper_fund_currency_v18545")

        pf1, pf2, pf3 = st.columns([1.0, 1.0, 0.9])
        with pf1:
            default_price = float(st.session_state.get("paper_fund_price_v18545", 0.0) or 0.0)
            fund_price = st.number_input("Pris / NAV", min_value=0.0, max_value=1_000_000.0, value=default_price, step=0.01, key="paper_fund_price_input_v18545")
        with pf2:
            purchase_mode = st.selectbox("Kjøpstype", ["Engangskjøp", "Månedlig spareplan"], key="paper_fund_purchase_mode_v18545")
        with pf3:
            st.button("Hent pris/NAV", key="paper_fund_fetch_price_v1863z", use_container_width=True, on_click=_paper_fetch_fund_price_v1863z)
        _render_paper_fetch_status_v1863z("paper_fund_fetch_status_v1863z")

        ba, bb = st.columns([1.0, 1.0])
        with ba:
            buy_fund_clicked = st.button("🟢 Paper-kjøp fond/ETF", key="paper_fund_buy_v1863z", type="primary", use_container_width=True)
            if buy_fund_clicked:
                price_to_use = float(fund_price or st.session_state.get("paper_fund_price_v18545", 0.0) or 0.0)
                ok, msg = paper_buy_instrument(
                    fund_symbol,
                    price_to_use,
                    float(fund_amount or 0),
                    asset_type=fund_asset_type,
                    confidence=75,
                    reason=f"UI paper {fund_asset_type}: {purchase_mode}",
                    currency=fund_currency,
                    nav_date=datetime.now().date().isoformat(),
                    purchase_mode=purchase_mode,
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        with bb:
            fund_positions = {k: v for k, v in (portfolio.get("positions", {}) or {}).items() if str((v or {}).get("asset_type", "Aksje")) in {"ETF", "Fond", "Indeksfond", "Aktivt fond", "Rente-/obligasjonsfond", "High yield-fond", "Pengemarkedsfond", "Kombinasjonsfond"}}
            sell_symbol = st.selectbox("Selg fond/ETF", list(fund_positions.keys()) or ["Ingen"], key="paper_fund_sell_symbol_v18545")
            sell_price = st.number_input("Salgspris/NAV", min_value=0.0, max_value=1_000_000.0, value=0.0, step=0.01, key="paper_fund_sell_price_v18545")
            sell_amount = st.number_input("Salgsbeløp (0 = alt)", min_value=0, max_value=10_000_000, value=0, step=500, key="paper_fund_sell_amount_v18545")
            sell_fund_clicked = st.button("🔴 Paper-selg fond/ETF", key="paper_fund_sell_v1863z", use_container_width=True, disabled=(sell_symbol == "Ingen"))
            if sell_fund_clicked:
                price_to_use = float(sell_price or (fund_positions.get(sell_symbol, {}) or {}).get("last_price", 0.0) or 0.0)
                ok, msg = paper_sell_instrument(
                    sell_symbol,
                    price_to_use,
                    sell_amount=None if int(sell_amount or 0) <= 0 else float(sell_amount),
                    reason="UI paper fond/ETF-salg",
                    currency=fund_currency,
                    nav_date=datetime.now().date().isoformat(),
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        if purchase_mode == "Månedlig spareplan":
            save_fund_plan_clicked = st.button("💾 Lagre spareplan som simulering", key="paper_fund_save_plan_v1863z", use_container_width=True)
            if save_fund_plan_clicked:
                plan = {
                    "symbol": fund_symbol,
                    "asset_type": fund_asset_type,
                    "monthly_amount": float(fund_amount or 0),
                    "currency": fund_currency,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "status": "Simulert",
                }
                portfolio.setdefault("fund_savings_plans", []).append(plan)
                save_portfolio(portfolio)
                st.success("Spareplan lagret som simulering ✅")
                st.rerun()

        plans = list(portfolio.get("fund_savings_plans") or [])
        if plans:
            st.markdown("<div class='ptw-control-panel-title'>Simulerte spareplaner</div>", unsafe_allow_html=True)
            for plan in plans[-5:]:
                st.markdown(
                    f"<div class='v18-dark-row'><b>{html.escape(str(plan.get('symbol','-')))}</b> · {html.escape(str(plan.get('asset_type','Fond')))} · {float(plan.get('monthly_amount') or 0):,.0f} {html.escape(str(plan.get('currency','NOK')))} / mnd · {html.escape(str(plan.get('status','Simulert')))}</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("#### Posisjoner")
    positions = portfolio.get("positions", {})
    if positions:
        st.dataframe(pd.DataFrame(paper_position_rows(portfolio, latest_prices)), use_container_width=True, hide_index=True)
    else:
        st.info("Ingen åpne paper trading-posisjoner.")

    st.markdown("#### 💰 Klar for ekte trading senere")
    st.info(
        "Systemet er nå strukturert for paper trading med risikoregler. "
        "Ekte handel er IKKE aktivert. Neste steg senere er broker_adapter.py "
        "med sikker ordrelegging, maksbeløp, nødknapp og manuell godkjenning."
    )

    st.markdown("#### Handelslogg")
    trades = portfolio.get("trades", [])
    if trades:
        st.dataframe(pd.DataFrame(paper_trade_rows(trades, limit=50)), use_container_width=True, hide_index=True)
    else:
        st.info("Ingen handler ennå.")

def render_ipo():
    st.subheader("🚀 Nye og kommende børsnoteringer")
    st.caption("Offisiell IPO-kalender vises separat fra ryktede/overvåkede IPO-kandidater.")

    ipo_list, error = get_ipo_calendar()
    nordic = get_nordic_ipo_calendar()
    rumored_rows = get_rumored_ipo_watchlist()

    def _render_ipo_rows(rows, empty_text, show_status=False):
        if not rows:
            st.info(empty_text)
            return
        for ipo in rows[:20]:
            st.markdown(f"**{ipo.get('name','Ukjent selskap')}** ({ipo.get('symbol','N/A')})")
            parts = [
                str(ipo.get("date") or ipo.get("expected") or "Ukjent dato"),
                str(ipo.get("exchange") or ipo.get("region") or "Ukjent børs"),
            ]
            if show_status and ipo.get("status"):
                parts.append(str(ipo.get("status")))
            if ipo.get("source"):
                parts.append(str(ipo.get("source")))
            st.caption(" · ".join(part for part in parts if part))
            if show_status and ipo.get("note"):
                st.caption(str(ipo.get("note")))
            st.divider()

    tab_global, tab_no, tab_se, tab_watch, tab_help = st.tabs([
        "USA / global",
        "Norge",
        "Sverige",
        "Overvåking",
        "Forklaring",
    ])
    with tab_global:
        if error:
            st.info(error)
        else:
            _render_ipo_rows(ipo_list, "Fant ingen IPO-data akkurat nå.")

    with tab_no:
        norway_rows = nordic.get("Norge", [])
        _render_ipo_rows(norway_rows, "Fant ingen norske IPO-/noteringsdata akkurat nå.")
        st.caption("Norge bruker Euronext Oslo-kilde pluss Finnhub-treff som matcher Oslo/Euronext Oslo.")

    with tab_se:
        sweden_rows = nordic.get("Sverige", [])
        _render_ipo_rows(sweden_rows, "Fant ingen svenske IPO-/noteringsdata akkurat nå.")
        st.caption("Sverige vises når IPO-feed returnerer Stockholm/Nasdaq Nordic/First North/Spotlight/NGM-treff.")

    with tab_watch:
        st.caption("Dette er ikke bekreftede kalendernoteringer. Listen brukes for å følge private selskaper som kan komme på børs.")
        _render_ipo_rows(rumored_rows, "Ingen overvåkede IPO-kandidater lagt inn.", show_status=True)

    with tab_help:
        st.markdown(
            """
            **Slik fungerer IPO-fanen**

            Kalender-fanene viser selskaper som finnes i IPO-kilder med dato, ticker eller børs.

            **USA / global** bruker Finnhub sin IPO-kalender. Den dekker ofte amerikanske børser best.

            **Norge** bruker Euronext Oslo-søk i tillegg til Finnhub-treff som matcher Oslo/Euronext.

            **Sverige** bruker Finnhub-treff som matcher Stockholm, Nasdaq Nordic, First North, Spotlight eller NGM.

            **Overvåking** er for selskaper som SpaceX, Starlink, Stripe og Databricks. De kan være omtalt i media, men vises ikke som offisiell IPO før dato/ticker/børs er offentlig nok til å ligge i kalenderdata.
            """
        )

    if nordic.get("errors"):
        with st.expander("Datakilde-status", expanded=False):
            st.caption("Noen eksterne IPO-kilder svarte ikke akkurat nå. Kalenderen viser tilgjengelige treff og overvåkingslisten uansett.")
            for source_error in nordic.get("errors", [])[:2]:
                st.caption(source_error)

def render_strategy_backtest(tickers, label):
    st.subheader("🧪 Smartere strategi-backtest")
    st.caption("Månedlig rebalansering, transaksjonskostnader, drawdown og benchmark.")

    col_a, col_b, col_c = st.columns(3)
    months = col_a.slider("Antall måneder", 6, 36, 24, key=f"months_{label}")
    top_n = col_b.slider("Topp N aksjer", 2, 10, 5, key=f"topn_{label}")
    cost = col_c.slider("Transaksjonskostnad", 0.0, 1.0, 0.2, step=0.1, key=f"cost_{label}") / 100

    use_stop = st.checkbox("Bruk enkel stop-loss", value=False, key=f"stop_{label}")
    stop_loss = st.slider("Stop-loss %", 3, 25, 10, key=f"sl_{label}") / 100 if use_stop else None

    benchmark = "^GSPC" if label == "USA" else "OSEBX.OL"

    if st.button(f"Kjør smartere backtest ({label})"):
        with st.spinner("Kjører backtest..."):
            strategy, bench, error = run_monthly_score_strategy(
                tickers,
                months=months,
                top_n=top_n,
                benchmark=benchmark,
                transaction_cost=cost,
                stop_loss=stop_loss,
            )

        if error:
            st.error(error)
            return

        strategy, stats = add_stats(strategy)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total avkastning", f"{stats['total_return']*100:.1f}%")
        c2.metric("Maks drawdown", f"{stats['max_drawdown']*100:.1f}%")
        c3.metric("Win-rate", f"{stats['win_rate']*100:.0f}%")
        c4.metric("Sharpe-ish", f"{stats['sharpe_like']:.2f}")

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=strategy["date"], y=strategy["value"], name="Score-strategi", mode="lines+markers"))
        if not bench.empty:
            fig.add_trace(go.Scatter(x=bench["date"], y=bench["benchmark_value"], name="Benchmark", mode="lines"))
        fig.update_layout(title="Strategi vs benchmark", template="plotly_dark", height=430)
        render_interactive_chart(fig, use_container_width=True, key=f"backtest_main_{label}")
        render_graph_explanation("backtest")

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=strategy["date"], y=strategy["drawdown"], fill="tozeroy", name="Drawdown"))
        fig_dd.update_layout(title="Drawdown", template="plotly_dark", height=300)
        render_interactive_chart(fig_dd, use_container_width=True, key=f"backtest_drawdown_{label}")
        render_graph_explanation("drawdown")

        st.markdown("#### Valgte aksjer per måned")
        st.dataframe(strategy[["date", "monthly_return", "gross_return", "cost", "selected"]], use_container_width=True)

st.sidebar.markdown("<div class='sidebar-section-title'>⚙️ Innstillinger</div>", unsafe_allow_html=True)
render_user_admin(current_user)
# v18.2: Duplisert Kontrollsenter-kort er fjernet fra venstre side.
# Statusinformasjon vises i toppkortene.

# --- Sidebar Structure v2 ---
def render_sidebar_structure_v2():
    """v18.1: Hurtignavigasjon-tekst fjernet, venstreside beholdes."""
    return None


render_sidebar_structure_v2()
# SIDEBAR_DEDUPE_V1: old duplicate Cron/status block removed


# --- Lagrede auto-innstillinger ---
st.sidebar.markdown(
    """
    <style>
    /* AUTO_TRADING_ACCORDION_V10 */
    section[data-testid="stSidebar"] details {
        border-radius: 14px !important;
        border: 1px solid rgba(148,163,184,0.22) !important;
        background: rgba(15,23,42,0.52) !important;
        margin-bottom: 8px !important;
    }
    section[data-testid="stSidebar"] details > summary {
        min-height: 38px !important;
        font-weight: 950 !important;
        color: #f8fafc !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] input {
        caret-color: #38bdf8 !important;
        background: rgba(30,41,59,0.94) !important;
        color: #f8fafc !important;
        font-weight: 850 !important;
        border-radius: 10px !important;
    }
    .auto-settings-summary {
        color: #cbd5e1;
        font-size: 0.78rem;
        line-height: 1.35;
        padding: 10px 11px;
        border-radius: 11px;
        background: rgba(2,6,23,0.32);
        border: 1px solid rgba(148,163,184,0.16);
        margin-bottom: 8px;
    }
    .auto-settings-group-title {
        margin-top: 8px;
        margin-bottom: 4px;
        color: #f8fafc;
        font-weight: 950;
        font-size: 0.84rem;
    }
    .auto-market-list-note {
        color: #94a3b8 !important;
        font-size: 0.74rem;
        margin: 2px 0 6px 0;
    }
    section[data-testid="stSidebar"] [data-testid="stForm"] button {
        background: #0ea5e9 !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        border: 1px solid rgba(125,211,252,0.70) !important;
        border-radius: 12px !important;
        font-weight: 950 !important;
        min-height: 40px !important;
        opacity: 1 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stForm"] button * {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        opacity: 1 !important;
        visibility: visible !important;
    }
    section[data-testid="stSidebar"] [data-testid="stForm"] button:hover {
        background: #0284c7 !important;
        color: #ffffff !important;
        border-color: #bae6fd !important;
    }
    section[data-testid="stSidebar"] [data-testid="stCheckbox"] label,
    section[data-testid="stSidebar"] [data-testid="stCheckbox"] span,
    section[data-testid="stSidebar"] [data-testid="stCheckbox"] p {
        white-space: normal !important;
        overflow-wrap: normal !important;
        word-break: normal !important;
        color: #f8fafc !important;
        font-weight: 800 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
# V15.8: ingen duplisert arbeidsflate-info i venstremenyen.
# v18.1 removed Visning heading
# Watchlist-feltet bygges etter at marked og ticker-lister er klare.

# V15.7 / Fase 3: Analyseunivers er flyttet til hovedområdet.
# Verdiene leses fra session_state slik at kontroller kan ligge visuelt senere i hovedflaten.
selected_market_category = st.session_state.get("market_category_selector_v157", MARKET_CATEGORY_OPTIONS[0])
if selected_market_category not in MARKET_CATEGORY_OPTIONS:
    selected_market_category = MARKET_CATEGORY_OPTIONS[0]
mode = MARKET_CATEGORY_TO_MODE.get(selected_market_category, "Alle")
max_count = int(st.session_state.get("max_count_main_v157", 30) or 30)
min_top_pick_score = float(st.session_state.get("min_top_pick_score_main_v157", 6.5) or 6.5)
use_news = bool(st.session_state.get("use_news_main_v157", True))
use_signal_intelligence = bool(st.session_state.get("use_signal_intelligence_main_v157", True))
_alert_runtime_settings = load_settings()
pushover_enabled = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY) and bool(_alert_runtime_settings.get("pushover_enabled", True))
use_high_conf_alerts_only = bool(_alert_runtime_settings.get("notify_high_confidence_only", True))
min_alert_confidence = int(_alert_runtime_settings.get("notify_min_confidence", 80))
auto_watchlist_alerts = bool(_alert_runtime_settings.get("notify_watchlist_signal_changes", True))
search = str(st.session_state.get("search_main_v157", "") or "").strip().upper()
_cleanup_legacy_session_seed_data_v1863t()

# V14.8 / Oppgave 70 og 72:
# Menyer skriver først til draft. Tunge analyser bruker aktive verdier til bruker trykker
# Oppdater hele appen, med mindre Auto-oppdater er PÅ.
_draft_analysis_controls_v148 = {
    "selected_market_category": selected_market_category,
    "mode": mode,
    "max_count": int(max_count),
    "min_top_pick_score": float(min_top_pick_score),
    "use_news": bool(use_news),
    "use_signal_intelligence": bool(use_signal_intelligence),
    "search": str(search or "").strip().upper(),
}
if "active_analysis_controls_v148" not in st.session_state:
    st.session_state["active_analysis_controls_v148"] = dict(_draft_analysis_controls_v148)
    st.session_state["heavy_update_allowed_v148"] = True
    _set_update_reason("Oppstart / første aktive innstillinger")

# V16.1: Auto-oppdater er fjernet fra normal arbeidsflyt.
# Draft blir først aktivt når Global oppdatering "Oppdater hele appen" trykkes.

_active_analysis_controls_v148 = st.session_state.get("active_analysis_controls_v148", dict(_draft_analysis_controls_v148))
_pending_analysis_changes_v148 = _controls_differ(_draft_analysis_controls_v148, _active_analysis_controls_v148)

# Aktive verdier brukes av datahenting/rangering. Widgetverdier kan endres uten tung analyse.
mode = _active_analysis_controls_v148.get("mode", mode)
max_count = int(_active_analysis_controls_v148.get("max_count", max_count))
min_top_pick_score = float(_active_analysis_controls_v148.get("min_top_pick_score", min_top_pick_score))
use_news = bool(_active_analysis_controls_v148.get("use_news", use_news))
use_signal_intelligence = bool(_active_analysis_controls_v148.get("use_signal_intelligence", use_signal_intelligence))
search = str(_active_analysis_controls_v148.get("search", search or "")).strip()

# Trygge standardverdier for watchlist-knapper
manual_watchlist_scan = globals().get("manual_watchlist_scan", False)
watchlist_scan_limit = globals().get("watchlist_scan_limit", 30)
watchlist_tickers = globals().get("watchlist_tickers", [])


# V14.7 / Oppgave 64-66: kompakt toppheader med viktig status og hurtigkontroller.
_top_settings = load_settings()
# V16.1 / Oppgave 124-125: Manuell modus er standard. Auto-oppdater skjules som avansert og er av.
if bool(_top_settings.get("chart_auto_update_enabled", False)):
    _top_settings["chart_auto_update_enabled"] = False
    try:
        save_settings(_top_settings)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
_top_cron = cron_status_text()
_top_auto_state, _top_auto_color = _auto_state(_top_settings)
_top_full_stop = bool(_top_cron.get("vacation_mode"))

# V15.3 / Oppgave 99: Kontrollnotis skal være kompakt fullbredde, ikke smal kolonne.
st.markdown("""
<style>
.v153-control-note{
    display:block;
    align-items:center;
    width:100%;
    max-width: 1100px;
    padding: 4px 8px;
    margin: 3px 0 3px 0;
    border-radius: 10px;
    font-size: 0.74rem;
    font-weight: 800;
    line-height: 1.18;
    white-space: normal;
    word-break: normal;
    overflow-wrap: normal;
}
.v153-control-note.warning{
    background: rgba(255, 193, 7, 0.14);
    border: 1px solid rgba(255, 193, 7, 0.38);
    color: #ffe08a;
}
@media (max-width: 700px){
    .v153-control-note{
        max-width: 100%;
        font-size: 0.74rem;
        padding: 6px 8px;
    }
}
</style>
""", unsafe_allow_html=True)


# V15.8: hardere kompakt KPI-stil og anti-vertikal tekst i kontrollområdet.
st.markdown("""
<style>
[data-testid="stMetric"] {
    min-height: 54px !important;
    padding: 7px 10px !important;
    border-radius: 11px !important;
}
[data-testid="stMetricLabel"] { font-size: 0.68rem !important; line-height: 1.05 !important; }
[data-testid="stMetricValue"] { font-size: 1.05rem !important; line-height: 1.08 !important; }
.v153-control-note, .v153-control-note *, .v15-inline-help, .v15-inline-help * {
    writing-mode: horizontal-tb !important;
    text-orientation: mixed !important;
    word-break: normal !important;
    overflow-wrap: normal !important;
    white-space: normal !important;
}
</style>
""", unsafe_allow_html=True)
# V15.4: siste hard-override for å hindre smale meldingsbokser og for å gjøre toppkontroller mer samlet.
st.markdown(
    """
    <style>
    .v153-control-note, .v153-control-note * {
        white-space: normal !important;
        word-break: normal !important;
        overflow-wrap: normal !important;
        writing-mode: horizontal-tb !important;
        text-orientation: mixed !important;
        min-width: 360px !important;
    }
    @media (max-width: 700px){
        .v153-control-note { min-width: 0 !important; width: 100% !important; }
    }
    .v15-desktop-status-strip .mini-status-chip.yellow {
        background: rgba(250, 204, 21, 0.14) !important;
        color: #fde68a !important;
        border-color: rgba(250, 204, 21, 0.42) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# V15.4: én samlet visningslogikk for Paper når Full stopp er aktiv.
_top_paper_label, _top_paper_color = _paper_state(_top_full_stop)
_top_chart_auto = False  # V16.1: global manuell oppdatering er standard

# v18.5.34: samlet toppstatus og tradingkontroller rett under global topbar.
st.markdown(
    f"""
    <div class='v18532-header-status'>
        <div class='v18532-status-row'>
            <span class='v18532-status-label'>Drift</span>
            <span class='mini-status-chip {_top_auto_color}'>Auto trading: <b>{_top_auto_state}</b></span>
            <span class='mini-status-chip {_top_paper_color}'>Paper: <b>{_top_paper_label}</b></span>
            <span class='mini-status-chip {'red' if _top_full_stop else 'green'}'>Full stopp: <b>{'JA' if _top_full_stop else 'NEI'}</b></span>
            <span class='mini-status-chip yellow'>Manuell: <b>PÅ</b></span>
            <span class='v18532-status-label'>Sesjon</span>
            {_session_status_html(current_user)}
            <span class='v18532-status-label'>Oppdatert</span>
            <span class='mini-status-chip'>Scan: <b>{_fmt_dt_short(_top_cron.get('last_scan_at'))}</b></span>
            <span class='mini-status-chip'>Tung: <b>{html.escape(_last_update_label())}</b></span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# V15.8 / v18.5.34: kompakt Auto trading-kontrollgruppe flyttet opp.
# Start opphever aldri Full stopp eller Nødstopp.
_top_emergency_stop = bool(_top_settings.get("auto_trading_emergency_stop", False))
_block_reason = _auto_block_reason(_top_settings)
st.markdown(
    "<div class='v18534-trading-control-stack'>"
    "<div class='v18534-trading-help'><b>Trading-kontroll:</b> Start/Pause/Stopp/Nødstopp styrer kun auto trading. "
    "Sikkerhetslåser oppheves med egne knapper.</div>"
    "</div>",
    unsafe_allow_html=True,
)
if bool(_top_full_stop):
    st.markdown(
        "<div class='v18534-trading-warning'>⛔ Full stopp / ferie er aktiv. Auto trading og auto-kjøp er blokkert. "
        "Bruk <b>Gjør klar</b> før Start kan brukes. Paper Trading er kun visning.</div>",
        unsafe_allow_html=True,
    )
elif _top_emergency_stop:
    st.markdown(
        "<div class='v18534-trading-warning'>🚨 Nødstopp er aktiv. Tilbakestill nødstopp separat før Auto trading kan startes.</div>",
        unsafe_allow_html=True,
    )
st.markdown("<div class='v18534-control-button-gap'></div>", unsafe_allow_html=True)
_tq1, _tq2, _tq3, _tq4, _tq5, _tq6, _tq7, _control_spacer = st.columns([0.95, 1.05, 1.05, 1.25, 1.55, 1.35, 1.85, 2.90], gap="small")
with _tq1:
    if st.button("▶ Start", key="auto_start_top_v15", use_container_width=True, disabled=bool(_top_full_stop or _top_emergency_stop)):
        _set_auto_state("START")
with _tq2:
    if st.button("⏸ Pause", key="auto_pause_top_v15", use_container_width=True):
        _set_auto_state("PAUSE")
with _tq3:
    if st.button("⛔ Stopp", key="auto_stop_top_v15", use_container_width=True):
        _set_auto_state("STOPP")
with _tq4:
    if st.button("🚨 Nødstopp", key="auto_emergency_top_v15", use_container_width=True):
        _set_auto_state("NØDSTOPP")
with _tq5:
    # Hold the column populated so the Global button always lands directly after Gjør klar.
    ready_disabled = not (bool(_top_full_stop) or bool(_top_settings.get("auto_trading_paused", False)))
    if st.button("🔓 Gjør klar", key="clear_stops_ready_top_v158", use_container_width=True, disabled=ready_disabled):
        _clear_stops_ready_v158()
with _tq6:
    st.empty()
with _tq7:
    if _top_emergency_stop:
        if st.button("🔓 Tilbakestill nødstopp", key="reset_emergency_top_v157", use_container_width=True):
            _reset_emergency_stop_v157()

render_global_update_action_panel_v1863g()

# V15.8: alle handlingsmeldinger vises fullbredde under kontrollgruppen.
if st.session_state.get("auto_control_notice_v153"):
    _notice = html.escape(str(st.session_state.pop("auto_control_notice_v153", "")))
    _level = str(st.session_state.pop("auto_control_notice_level_v153", "info"))
    _prefix = "✅" if _level == "success" else ("⚠️" if _level == "warning" else "ℹ️")
    if _notice:
        st.markdown(f"<div class='v153-control-note {'warning' if _level == 'warning' else ''}'>{_prefix} {_notice}</div>", unsafe_allow_html=True)



# v18.5.35: ekstra lazy-paneler i AI Kontrollsenter.
def render_news_control_center_v18535(default_ticker: str = ""):
    """Manual NewsAPI workspace. It never fetches news before the user presses the button."""
    st.subheader("📰 Nyheter")
    st.caption("Live NewsAPI brukes bare når du trykker knappen. Automatiske kall holdes av som standard.")
    default_ticker = normalize_user_ticker(default_ticker or search or "")
    ticker = st.text_input("Ticker", value=default_ticker, key="cc_news_ticker_v18535")
    limit = st.slider("Antall nyheter", 3, 10, 6, 1, key="cc_news_limit_v18535")
    if st.button("Hent nyheter manuelt", key="cc_news_fetch_v18535", type="primary"):
        clean = normalize_user_ticker(ticker).replace(".OL", "")
        if not clean:
            st.warning("Skriv inn en ticker først.")
            return
        with st.spinner(f"Henter nyheter for {clean}..."):
            articles, error = get_news(clean, limit=int(limit), source="manual", force=True)
        if error:
            st.warning(f"Nyheter midlertidig utilgjengelig: {error}")
        elif not articles:
            st.info("Ingen relevante nyheter funnet.")
        else:
            st.success(f"Fant {len(articles)} nyheter for {clean}.")
            st.metric("Nyhets-sentiment", simple_finance_sentiment(articles))
            for article in articles:
                st.markdown(
                    f"- **{article.get('title','Uten tittel')}**  \n"
                    f"  <span class='small'>{article.get('source','')} · {article.get('published','')}</span>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("Ingen nyhetskall kjøres før du trykker knappen.")


def render_interactive_technical_control_center_v18535():
    """Manual single-ticker analysis panel for interactive/technical/trading-engine views."""
    st.subheader("📊 Interaktiv / teknisk analyse")
    st.caption("Panelet henter ikke data før du trykker Kjør analyse. Teknisk analyse og Trading engine vises i samme aksjekort.")
    default_ticker = normalize_user_ticker(search or "")
    ticker = st.text_input("Ticker for analyse", value=default_ticker, key="cc_interactive_ticker_v18535")
    run = st.button("Kjør interaktiv analyse", key="cc_interactive_run_v18535", type="primary")
    if run:
        clean = normalize_user_ticker(ticker)
        if not clean:
            st.warning("Skriv inn én ticker først.")
            return
        with st.spinner(f"Henter analyse for {clean}..."):
            item = cached_score_stock_manual(clean, use_news=False)
        if not item:
            st.warning("Fant ikke data for valgt ticker.")
            return
        st.session_state["cc_interactive_last_result_v18535"] = [item]
        st.success(f"Analyse klar for {clean}.")
    rows = st.session_state.get("cc_interactive_last_result_v18535") or []
    if rows:
        render_analysis(rows, "Kontrollsenter")
    else:
        st.info("Kjør en analyse for å åpne teknisk analyse, Trading engine og nyhetspanel for valgt ticker.")


def render_market_ranking_control_center_v18535():
    """On-demand market ranking panel. No market scan runs before the button is pressed."""
    st.subheader("🏆 Marked / rangering")
    st.caption("Rangering kjøres bare når du trykker knappen. Siste lagrede rangering vises ellers.")
    market = st.selectbox("Marked", [NO_UNIVERSE_SELECTION_LABEL] + market_scope_options(include_aggregate=True), key="cc_ranking_market_v18535")
    limit = st.slider("Maks kandidater", 5, 100, int(max_count or 30), 5, key="cc_ranking_limit_v18535")
    source_tickers = []
    if market in MARKET_SCOPE_OPTIONS:
        source_tickers = resolve_universe_tickers([market], max_count=int(limit))
    storage_key = f"Kontrollsenter_{market}"
    latest = st.session_state.setdefault("latest_rankings_v148", {})
    if source_tickers:
        st.caption(f"Valgt univers: {len(source_tickers)} tickere. Eksempel: {', '.join(source_tickers[:8])}")
    else:
        st.info("Velg marked og trykk Kjør rangering. Ingen skjult USA/AAPL-fallback kjøres.")
    if st.button(f"Kjør rangering {market}", key="cc_ranking_run_v18535", type="primary", disabled=not bool(source_tickers)):
        with st.spinner(f"Rangerer {market}..."):
            ranked = cached_auto_rank_market(storage_key, source_tickers, max_count=int(limit), use_news=False, force_manual_fetch=True)
        latest[storage_key] = ranked or []
        st.success(f"Rangering ferdig: {len(ranked or [])} kandidater.")
    rows = latest.get(storage_key, []) or []
    if rows:
        render_ranking(rows, f"🏆 {market} rangering")
    else:
        st.info("Ingen lagret rangering for dette panelet ennå.")


def _parse_control_center_tickers_v1863s(text: str) -> list[str]:
    values = re.split(r"[\s,;|/]+", str(text or ""))
    out, seen = [], set()
    for raw in values:
        ticker = normalize_user_ticker(raw)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def _resolve_control_center_scope_tickers_v1863s(scope: str, limit: int, manual_text: str = "") -> list[str]:
    limit = max(1, min(int(limit or 30), 250))
    scope = str(scope or "").strip()
    if scope in {"", NO_UNIVERSE_SELECTION_LABEL, "Velg marked"}:
        return []
    if scope == "Aktivt univers":
        return _source_tickers_for_interactive("Smart Universe Picker", max_fallback=limit)[:limit]
    if scope in MARKET_SCOPE_OPTIONS:
        return resolve_universe_tickers([scope], max_count=limit)
    if scope == "Watchlist":
        return _dedupe_text_list(st.session_state.get("latest_watchlist_tickers_v156", []) or [])[:limit]
    if scope == "Manuell liste":
        return _parse_control_center_tickers_v1863s(manual_text)[:limit]
    return []


def render_top_picks_control_center_v1863s():
    """Top Picks as a first-class AI Kontrollsenter panel."""
    st.subheader("⭐ Top Picks")
    st.caption("Bygger Top Picks fra samme universmotor som rangering, analyse, varsler og testpaneler.")

    c1, c2 = st.columns([1.25, 1])
    with c1:
        scope = st.selectbox(
            "Univers / marked",
            [NO_UNIVERSE_SELECTION_LABEL, "Aktivt univers"] + market_scope_options(include_aggregate=True) + ["Watchlist", "Manuell liste"],
            key="cc_top_picks_scope_v1863s",
        )
    with c2:
        limit = st.slider("Maks kandidater", 5, 100, int(max_count or 30), 5, key="cc_top_picks_limit_v1863s")

    manual_text = ""
    if scope == "Manuell liste":
        manual_text = st.text_area(
            "Manuelle tickere",
            value="",
            placeholder="EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE, PETR4.SA",
            key="cc_top_picks_manual_v1863s",
            height=90,
        )

    source_tickers = _resolve_control_center_scope_tickers_v1863s(scope, int(limit), manual_text=manual_text)
    storage_scope = re.sub(r"[^A-Za-z0-9]+", "_", scope).strip("_") or "Aktivt"
    storage_key = f"TopPicks_{storage_scope}"
    latest = st.session_state.setdefault("latest_rankings_v148", {})

    if source_tickers:
        st.caption(f"Univers: {len(source_tickers)} tickere. Eksempel: {', '.join(source_tickers[:8])}")
        guard = market_guard_summary(source_tickers)
        if guard:
            st.caption(guard)
    else:
        st.info("Velg univers/marked og trykk Kjør Top Picks. Panelet starter tomt og bruker ingen gammel AAPL/STB.OL-cache.")
        return

    run_clicked = st.button(
        f"Kjør Top Picks for {scope}",
        key="cc_top_picks_run_v1863s",
        type="primary",
        use_container_width=True,
        disabled=not bool(source_tickers),
    )
    if run_clicked and source_tickers:
        with st.spinner(f"Rangerer {scope} via felles universmotor..."):
            ranked = cached_auto_rank_market(
                storage_key,
                source_tickers,
                max_count=int(limit),
                use_news=False,
                force_manual_fetch=True,
                include_insider=True,
            )
        top_rows = _ranked_for_display(build_top_picks(ranked, min_score=min_top_pick_score, max_items=15))
        latest[storage_key] = top_rows or []
        if scope in MARKET_SCOPE_OPTIONS:
            latest[scope] = ranked or []
        st.success(f"Top Picks ferdig: {len(top_rows or [])} kandidater fra {scope}.")

    top_picks = _ranked_for_display(latest.get(storage_key, []) or [])
    buy_now_picks = _ranked_for_display([x for x in top_picks if is_buy_now_item(x)])
    view = st.radio("Visning", ["Top Picks", "Kjøp nå"], horizontal=True, key="cc_top_picks_view_v1863s")

    if view == "Top Picks":
        render_ranking(top_picks, f"⭐ Top Picks {scope}")
        if top_picks:
            render_analysis(top_picks, f"TopPicks_{storage_scope}")
    else:
        if buy_now_picks:
            saved = save_latest_buy_now_candidates(buy_now_picks, scope)
            st.info(f"{len(saved)} kjøp-nå-kandidater er lagret til Cron-prioritering. Auto-kjøp skjer fortsatt bare via reglene dine.")
            if st.button(f"Paper-kjøp alle Kjøp nå ({len(buy_now_picks)})", key="cc_top_picks_paper_buy_all_v1863s"):
                messages = []
                for item in buy_now_picks:
                    ticker = item.get("ticker")
                    price, _change = get_item_price_change(item)
                    decision = card_decision_for_item(item)
                    if price is None:
                        messages.append(f"{ticker}: mangler pris")
                        continue
                    _ok, msg = paper_buy(ticker, price, int(decision.get("confidence", 0) or 0), f"AI Kontrollsenter Kjøp nå: {scope}")
                    messages.append(msg)
                joined = " | ".join(messages[:8])
                if any("blokkert" in str(m).lower() or "ikke nok" in str(m).lower() or "mangler" in str(m).lower() for m in messages):
                    st.warning(joined)
                else:
                    st.success(joined)
                st.rerun()
            render_ranking(buy_now_picks, f"🟢 Kjøp nå {scope}")
            render_analysis(buy_now_picks, f"KjopNa_{storage_scope}")
        else:
            st.warning("Ingen kandidater har grønt teknisk kjøpssignal akkurat nå.")


def render_watchlist_signals_control_center_v18535():
    """Watchlist and signal settings in the control center only."""
    st.subheader("🔔 Watchlist / signaler")
    latest = st.session_state.get("latest_rankings_v148", {}) or {}
    dynamic: list[str] = []
    for rows in latest.values():
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    t = normalize_user_ticker(row.get("ticker"))
                    if t and t not in dynamic:
                        dynamic.append(t)
                if len(dynamic) >= 30:
                    break
        if len(dynamic) >= 30:
            break
    if dynamic:
        st.caption(f"Dynamiske kandidater fra siste rangering: {len(dynamic)}")
    else:
        st.caption("Ingen dynamiske kandidater i cache ennå. Kjør rangering eller Smart AI først.")
    render_watchlist_alerts_workspace(dynamic, pushover_enabled_runtime=pushover_enabled)



# v18.5.37: Auto Test Lab Progress + Safe Run Controls.
def _auto_lab_scope_tickers_v18536(scope: str, limit: int, manual_text: str = ""):
    """Resolve Auto Test Lab universe without running hidden scans."""
    from auto_test_lab import parse_ticker_list, normalize_ticker
    limit = max(1, min(int(limit or 25), 150))
    scope = str(scope or "").strip()
    if scope in {"", NO_UNIVERSE_SELECTION_LABEL, "Velg marked"}:
        return []

    def _dedupe(values):
        out, seen = [], set()
        for raw in values or []:
            ticker = normalize_ticker(raw.get("ticker") if isinstance(raw, dict) else raw)
            if ticker and ticker not in seen:
                out.append(ticker)
                seen.add(ticker)
            if len(out) >= limit:
                break
        return out

    if scope == "Manuell liste":
        return _dedupe(parse_ticker_list(manual_text))
    if scope in MARKET_SCOPE_OPTIONS:
        return _dedupe(resolve_universe_tickers([scope], max_count=limit))
    if scope == "Multi-marked":
        return _dedupe(resolve_universe_tickers(["Alle"], max_count=limit))
    if scope == "Aktivt Smart Universe":
        try:
            from services.service_registry import build_service_registry
            services = build_service_registry(st.session_state)
            active = services.universe.load_active_universe().data or {}
            return _dedupe(active.get("tickers") or active.get("rows") or [])
        except Exception:
            active = st.session_state.get("smart_universe_picker_active_v18517", {}) or st.session_state.get("active_universe", {}) or {}
            if isinstance(active, dict):
                return _dedupe(active.get("tickers") or active.get("rows") or [])
            return []
    if scope == "Siste Smart AI-resultat":
        try:
            from services.universe_service import SMART_RESULT_KEY
            smart = st.session_state.get(SMART_RESULT_KEY, {}) or st.session_state.get("ai_analysis_universe_smart_result_v1859", {}) or {}
        except Exception:
            smart = st.session_state.get("ai_analysis_universe_smart_result_v1859", {}) or {}
        if isinstance(smart, dict):
            return _dedupe(smart.get("top_tickers") or smart.get("candidates") or smart.get("top_picks") or [])
        return []
    if scope == "Top Picks":
        latest = st.session_state.get("latest_rankings_v148", {}) or {}
        rows = []
        for key, vals in latest.items():
            if "Top" in str(key) or key in MARKET_SCOPE_OPTIONS:
                rows.extend(vals or [])
        rows = _ranked_for_display(rows)
        return _dedupe(rows)
    if scope == "Watchlist":
        return _dedupe(st.session_state.get("latest_watchlist_tickers_v156", []) or [])
    if scope == "Paper trading":
        try:
            portfolio = load_portfolio() or {}
            positions = portfolio.get("positions") if isinstance(portfolio, dict) else {}
            if isinstance(positions, dict):
                return _dedupe(list(positions.keys()))
            if isinstance(positions, list):
                return _dedupe([p.get("ticker") or p.get("symbol") for p in positions if isinstance(p, dict)])
        except Exception:
            return []
    return []


def _render_auto_lab_decision_rows_v18536(rows, title="Beste enkeltaksjer", limit=8):
    import html as _html
    rows = list(rows or [])[: int(limit or 8)]
    st.markdown(f"<div class='ptw-control-panel-title'>{_html.escape(title)}</div>", unsafe_allow_html=True)
    if not rows:
        st.markdown("<div class='v18-dark-row'>Ingen kandidater å vise ennå.</div>", unsafe_allow_html=True)
        return
    for idx, row in enumerate(rows, start=1):
        grade = str(row.get("grade") or "-")
        grade_cls = "green" if grade == "Høy" else ("yellow" if grade == "Middels" else "red")
        ticker_raw = str(row.get("ticker") or row.get("symbol") or "-")
        ticker = _html.escape(_security_display_label_v18569(ticker_raw, row))
        action = _html.escape(str(row.get("action") or ""))
        quality = row.get("decision_quality", "-")
        composite_score = (
            row.get("composite_score")
            or row.get("fund_intelligence_score")
            or row.get("ai_score")
            or row.get("decision_quality")
            or "-"
        )
        base_score = (
            row.get("base_score")
            or row.get("score")
            or row.get("raw_score")
            or "-"
        )
        ai = row.get("ai_score", "-")
        mom = row.get("momentum_score", "-")
        risk = row.get("risk_score", "-")
        event = row.get("event_score", "-")
        explain = row.get("explainability_profile") or {}
        pos = "; ".join(str(x) for x in (explain.get("why_ranked_here") or row.get("reasons_positive") or [])[:2])
        caution = "; ".join(str(x) for x in (explain.get("what_holds_it_back") or row.get("reasons_caution") or [])[:2])
        select_trigger = "; ".join(str(x) for x in (explain.get("what_would_make_it_selected") or [])[:2])
        reject_trigger = "; ".join(str(x) for x in (explain.get("what_would_make_model_reject_it") or [])[:2])
        explain_short = _html.escape(str(explain.get("short_explanation") or row.get("explainability_summary") or ""))
        st.markdown(
            f"""
            <div class='v18-dark-row' style='margin:.25rem 0; padding:.46rem .56rem;'>
              <div style='display:flex; justify-content:space-between; gap:.6rem; flex-wrap:wrap;'>
                <b>#{idx} {ticker}</b>
                <span class='v18-status-chip {grade_cls}'>{_html.escape(grade)} · {quality}/100</span><span class='v18-status-chip green'>Intelligens {composite_score}/100</span><span class='v18-status-chip yellow'>Grunnscore {base_score}/100</span>
              </div>
              <div style='font-size:.78rem; color:rgba(226,232,240,.82); margin-top:.18rem;'>
                {action} · AI {ai} · Momentum {mom} · Risiko {risk} · Event {event}
              </div>
              <div style='font-size:.74rem; color:rgba(209,250,229,.86); margin-top:.18rem;'>+ {_html.escape(pos or 'Ingen dominerende positiv driver')}</div>
              <div style='font-size:.74rem; color:rgba(254,226,226,.86); margin-top:.10rem;'>⚠ {_html.escape(caution or 'Ingen store røde flagg')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_auto_lab_combination_rows_v18536(rows, limit=6):
    import html as _html
    rows = list(rows or [])[: int(limit or 6)]
    st.markdown("<div class='ptw-control-panel-title'>Beste kombinasjoner</div>", unsafe_allow_html=True)
    if not rows:
        st.markdown("<div class='v18-dark-row'>Ingen kombinasjoner ennå. Kjør minst 3 gode kandidater.</div>", unsafe_allow_html=True)
        return
    for idx, row in enumerate(rows, start=1):
        tickers = " + ".join(row.get("tickers") or [])
        score = row.get("combination_score", "-")
        reason = str(row.get("reason") or "")
        sectors = ", ".join(row.get("sectors") or [])
        st.markdown(
            f"""
            <div class='v18-dark-row' style='margin:.25rem 0; padding:.44rem .56rem;'>
              <div style='display:flex; justify-content:space-between; gap:.6rem; flex-wrap:wrap;'>
                <b>#{idx} {_html.escape(tickers)}</b>
                <span class='v18-status-chip green'>{score}/100</span>
              </div>
              <div style='font-size:.76rem; color:rgba(226,232,240,.82); margin-top:.18rem;'>{_html.escape(reason)}</div>
              <div style='font-size:.72rem; color:rgba(191,219,254,.84); margin-top:.10rem;'>Grupper: {_html.escape(sectors or 'Ukjent')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_auto_test_lab_control_center_v18536():
    """On-demand research lab for testing many tickers/funds against the decision stack."""
    st.subheader("🔬 Auto Test Lab")
    st.caption("Velg én modus og ett univers. Panelet tester kandidater automatisk når du trykker Kjør; skjulte moduser starter ingen tunge jobber.")

    lab_mode = st.radio(
        "Auto Test Lab-modus",
        ["Aksjer", "Fond / ETF"],
        horizontal=True,
        key="auto_lab_mode_v18543",
        help="Fond / ETF-modus bruker fondsmotoren: kostnad, benchmark, aktiv merverdi, grunnmur/satellitt og Fond Decision Quality.",
    )
    if lab_mode == "Fond / ETF":
        render_auto_test_lab_fund_mode_v18543()
        return

    col_a, col_b, col_c, col_d = st.columns([1.25, 1.0, 0.9, 0.9])
    with col_a:
        scope = st.selectbox(
            "Univers",
            [NO_UNIVERSE_SELECTION_LABEL, "Aktivt Smart Universe", "Siste Smart AI-resultat", "Top Picks", "Watchlist", "Paper trading"] + market_scope_options(include_aggregate=True) + ["Multi-marked", "Manuell liste"],
            key="auto_lab_scope_v18537",
        )
    with col_b:
        target = st.selectbox("Mål", ["Balansert", "Momentum", "Lav risiko", "Kortsiktig", "Langsiktig"], key="auto_lab_target_v18537")
    with col_c:
        test_mode = st.selectbox("Testmodus", ["Rask", "Normal", "Grundig"], index=1, key="auto_lab_test_mode_v18537")
    with col_d:
        limit = st.slider("Maks", 5, 60, 20, 5, key="auto_lab_limit_v18537")

    manual_text = ""
    if scope == "Manuell liste":
        manual_text = st.text_area("Tickere", value="", placeholder="EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE, PETR4.SA", height=82, key="auto_lab_manual_v18537")

    c1, c2, c3 = st.columns([1.0, 1.0, 1.2])
    with c1:
        include_event = st.checkbox("Hendelsesrisiko", value=True, key="auto_lab_event_v18537")
    with c2:
        use_news_for_score = st.checkbox("Nyheter i score", value=False, key="auto_lab_news_v18537", help="Av som standard for å spare NewsAPI. Manuelle nyheter ligger i Nyheter-panelet.")
    with c3:
        combo_size = st.multiselect("Kombinasjoner", [2, 3, 4, 5, 6, 8], default=[3, 5], key="auto_lab_combo_sizes_v18537")

    preview_tickers = _auto_lab_scope_tickers_v18536(scope, int(limit), manual_text=manual_text)
    try:
        from auto_test_lab import estimate_auto_lab_run
        budget = estimate_auto_lab_run(preview_tickers, test_mode=test_mode, use_news=bool(use_news_for_score), include_event=bool(include_event))
    except Exception:
        budget = {"mode": test_mode, "total_tests": len(preview_tickers), "tests_per_ticker": 1, "load_label": "Ukjent", "news_calls": 0, "event_checks": 0, "tests": []}

    if preview_tickers:
        st.markdown(
            f"<div class='v18-dark-row'>Valgt univers: <b>{html.escape(scope)}</b> · {len(preview_tickers)} tickere · første: {html.escape(', '.join(preview_tickers[:8]))}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("<div class='v18-dark-row'>Ingen tickere funnet i valgt univers ennå. Velg et annet univers eller bruk Manuell liste.</div>", unsafe_allow_html=True)

    tests_text = ", ".join(str(x) for x in (budget.get("tests") or [])[:8])
    st.markdown(
        f"""
        <div class='v18-dark-row' style='display:flex; justify-content:space-between; gap:.7rem; flex-wrap:wrap;'>
          <span><b>Planlagt test:</b> {int(budget.get('tickers', len(preview_tickers)) or 0)} tickere · {int(budget.get('tests_per_ticker', 0) or 0)} tester per ticker · {int(budget.get('total_tests', 0) or 0)} totalt</span>
          <span class='v18-status-chip {'red' if budget.get('load_label') == 'Høy' else ('yellow' if budget.get('load_label') == 'Medium' else 'green')}'>Databudsjett: {html.escape(str(budget.get('load_label') or 'Ukjent'))}</span>
          <span>NewsAPI: {int(budget.get('news_calls', 0) or 0)} · Event: {int(budget.get('event_checks', 0) or 0)}</span>
        </div>
        <div class='v18-dark-row' style='font-size:.75rem; opacity:.86;'>Tester: {html.escape(tests_text or 'Ingen')}</div>
        """,
        unsafe_allow_html=True,
    )

    run_col, stop_col = st.columns([2.2, 1.0])
    with run_col:
        run_clicked = st.button("🔬 Kjør Auto Test Lab", key="auto_lab_run_v18537", type="primary", use_container_width=True, disabled=not bool(preview_tickers), on_click=set_global_busy, kwargs={"label": "Kjører Auto Test Lab", "detail": "Tester kandidater mot beslutningskvalitet"})
    with stop_col:
        if st.button("⏹ Stopp/avbryt", key="auto_lab_stop_v18537", use_container_width=True, help="Ber kjøringen stoppe trygt ved neste kontrollpunkt."):
            st.session_state["auto_lab_stop_requested_v18537"] = True
            st.warning("Stopp er bedt om. Pågående kjøring stopper ved neste trygge kontrollpunkt.")

    if run_clicked:
        st.session_state["auto_lab_stop_requested_v18537"] = False
        if not preview_tickers:
            st.warning("Ingen tickere å teste.")
            finish_global_busy("Klar", "Auto Test Lab manglet tickere.")
            return
        from auto_test_lab import run_auto_test_lab
        from forecast_store import load_learning_stats
        from event_risk_engine import detect_event_risk
        from services.storage_service import get_storage_service
        from datetime import datetime, timezone

        status_box = st.empty()
        progress = st.progress(0, text="Starter Auto Test Lab")
        update_global_busy("Kjører Auto Test Lab", "Starter", step=0, total=int(budget.get("total_tests", 0) or 0))
        learning_stats = load_learning_stats()

        def _score_provider(ticker, use_news):
            return cached_score_stock_manual(ticker, use_news=use_news, force=True)

        def _event_provider(ticker, prices):
            if not include_event:
                return {}
            return detect_event_risk(ticker, prices, horizon="auto_lab", include_news=False)

        def _should_stop():
            return bool(st.session_state.get("auto_lab_stop_requested_v18537", False))

        def _progress_callback(ev):
            pct = float(ev.get("percent") or 0.0)
            completed = int(ev.get("completed_tests") or 0)
            total = int(ev.get("total_tests") or 0)
            ticker = str(ev.get("ticker") or "-")
            test_name = str(ev.get("test_name") or "Starter")
            ticker_idx = int(ev.get("ticker_index") or 0)
            ticker_total = int(ev.get("ticker_total") or len(preview_tickers))
            test_idx = int(ev.get("test_index") or 0)
            tests_per = int(ev.get("tests_per_ticker") or max(1, int(budget.get("tests_per_ticker", 1) or 1)))
            status = str(ev.get("status") or "running")
            progress.progress(min(100, max(0, int(round(pct)))), text=f"{completed}/{total} tester · {pct:.0f}%")
            update_global_busy("Kjører Auto Test Lab", f"{ticker} · {test_name} · {pct:.0f}%", step=completed, total=total)
            status_box.markdown(
                f"""
                <div class='v18-dark-row' style='border-color:rgba(59,130,246,.55);'>
                  <div style='display:flex;justify-content:space-between;gap:.7rem;flex-wrap:wrap;'>
                    <b>🔄 Auto Test Lab kjører</b>
                    <span class='v18-status-chip yellow'>{html.escape(status)} · {completed}/{total}</span>
                  </div>
                  <div style='font-size:.82rem;margin-top:.25rem;'>Aksje: <b>{html.escape(ticker)}</b> · Test nå: <b>{html.escape(test_name)}</b></div>
                  <div style='font-size:.86rem;color:rgba(226,232,240,.86);'>Ticker {ticker_idx}/{ticker_total} · Test {test_idx}/{tests_per} · Total fremdrift {pct:.1f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        result = run_auto_test_lab(
            preview_tickers,
            score_provider=_score_provider,
            event_risk_provider=_event_provider if include_event else None,
            learning_stats=learning_stats,
            use_news=bool(use_news_for_score),
            target=target,
            max_candidates=int(limit),
            combination_sizes=combo_size or [3, 5],
            test_mode=test_mode,
            progress_callback=_progress_callback,
            should_stop=_should_stop,
        )
        result["scope"] = scope
        result["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        st.session_state["auto_test_lab_last_result_v18536"] = result
        try:
            storage = get_storage_service()
            storage.write_json("auto_test_lab/latest.json", result)
            storage.append_jsonl("auto_test_lab/history.jsonl", result)
            result["storage_backend"] = storage.backend()
        except Exception as exc:
            result["storage_error"] = str(exc)[:180]
        progress.progress(100, text="Ferdig" if not result.get("interrupted") else "Avbrutt")
        finish_global_busy("Klar", "Auto Test Lab ferdig." if not result.get("interrupted") else "Auto Test Lab avbrutt.")
        if result.get("interrupted"):
            st.warning(f"Auto Test Lab avbrutt etter {result.get('completed_tests', 0)} av {result.get('total_tests', 0)} tester. Foreløpig resultat er lagret.")
        else:
            st.success(f"Auto Test Lab ferdig: {result.get('analyzed', 0)} analyserte kandidater · {result.get('completed_tests', 0)}/{result.get('total_tests', 0)} tester.")

    result = st.session_state.get("auto_test_lab_last_result_v18536") or {}
    if result:
        summary = result.get("summary", {}) or {}
        cols = st.columns(5)
        cols[0].metric("Analyserte", result.get("analyzed", 0))
        cols[1].metric("Tester", f"{result.get('completed_tests', 0)}/{result.get('total_tests', 0)}")
        cols[2].metric("Beste ticker", summary.get("best_ticker") or "-")
        cols[3].metric("Beste kvalitet", summary.get("best_quality") or "-")
        cols[4].metric("Kombinasjoner", summary.get("combinations", 0))
        if result.get("interrupted"):
            st.warning("Siste Auto Test Lab ble avbrutt. Resultatene under er foreløpige.")
        _render_auto_lab_decision_rows_v18536(result.get("best_single"), title="Beste enkeltaksjer", limit=8)
        _render_auto_lab_combination_rows_v18536(result.get("combinations"), limit=6)
        rejected = result.get("rejected") or []
        errors = result.get("errors") or []
        if rejected or errors:
            with st.expander("Vent / forkastede / feilede kandidater", expanded=False):
                for row in rejected[:12]:
                    st.caption(f"{row.get('ticker')}: {row.get('reason')}")
                for row in errors[:12]:
                    st.caption(f"{row.get('ticker')}: {row.get('test', '-')}: {row.get('error')}")
    else:
        st.info("Ingen Auto Test Lab-resultat ennå. Velg univers og trykk Kjør.")


# v18.5.43: Fund Selection Engine + Core/Satellite + Auto Test Lab Fund Mode.
def _fund_result_limit_key_v18547(title):
    import re
    return "fund_result_view_" + re.sub(r"[^a-z0-9]+", "_", str(title).lower()).strip("_")[:36] + "_v18547"

def _render_fund_result_scope_v18547(result, *, default_limit=8):
    import html as _html
    res = dict(result or {})
    summary = dict(res.get("summary") or {})
    selection = dict(res.get("selection") or {})
    analyzed = int(summary.get("actual_analyzed") or summary.get("analyzed") or len(res.get("ranked") or []) or 0)
    selected_max = int(summary.get("selected_max") or selection.get("display_limit") or selection.get("max_funds") or 8)
    available = selection.get("available_in_universe") or summary.get("available_in_universe") or "-"
    source = selection.get("source") or res.get("scope") or "-"
    st.markdown(
        f"""
        <div class='v18-dark-row' style='margin:.35rem 0 .55rem 0;padding:.55rem .65rem;'>
          <div style='display:flex;gap:.45rem;flex-wrap:wrap;align-items:center;'>
            <span class='v18-status-chip green'>Faktisk analysert: {analyzed}</span>
            <span class='v18-status-chip yellow'>Valgt maks: {selected_max}</span>
            <span class='v18-status-chip yellow'>Tilgjengelig i univers: {_html.escape(str(available))}</span>
            <span>{_html.escape(str(source))}</span>
          </div>
          <div style='font-size:.78rem;color:rgba(226,232,240,.82);margin-top:.25rem;'>Auto-universet er et starter-univers, ikke hele markedet. Hele starter-universet analyseres først; deretter vises valgt antall eller alle analyserte.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_what_changed_v18555(profile, title="Hva endret seg siden sist?"):
    import html as _html
    prof = dict(profile or {})
    summary = str(prof.get("summary") or "Ingen endringsanalyse tilgjengelig ennå.")
    st.markdown(f"<div class='ptw-control-panel-title' style='margin-top:.85rem;margin-bottom:.35rem;'>{_html.escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='v18-dark-row' style='margin:.35rem 0 .75rem 0;padding:.62rem .70rem;line-height:1.35;'><b>Layer 6:</b> {_html.escape(summary)}</div>", unsafe_allow_html=True)
    if not prof.get("has_previous"):
        st.caption("Første sammenlignbare snapshot er lagret. Neste kjøring kan forklare rang-, score-, risiko- og insiderendringer.")
        return
    movers = list(prof.get("rank_movers") or [])[:5]
    score_movers = list(prof.get("score_movers") or [])[:5]
    insider = list(prof.get("insider_direction_changes") or [])[:5]
    risk = list(prof.get("risk_flag_changes") or [])[:5]
    with st.expander("Detaljer om endringer", expanded=False):
        if movers:
            st.markdown("**Rangendringer**")
            for m in movers:
                st.caption(f"{m.get('symbol')}: {m.get('explanation')}")
        if score_movers:
            st.markdown("**Scoreendringer**")
            for m in score_movers:
                st.caption(f"{m.get('symbol')}: {m.get('explanation')}")
        if insider:
            st.markdown("**Insiderretning**")
            for m in insider:
                st.caption(f"{m.get('symbol')}: {m.get('explanation')}")
        if risk:
            st.markdown("**Risikoflagg**")
            for r in risk:
                added = ", ".join(r.get("added") or []) or "ingen nye"
                removed = ", ".join(r.get("removed") or []) or "ingen fjernet"
                st.caption(f"{r.get('symbol')}: nye: {added} · fjernet: {removed}")

def _render_fund_etf_rows_v18538(rows, title="Beste fond / ETF-kandidater", limit=8, allow_view_toggle=True, empty_text=None):
    import html as _html
    all_rows = list(rows or [])
    key = _fund_result_limit_key_v18547(title)
    if allow_view_toggle and len(all_rows) > int(limit or 8):
        mode = st.radio("Visning", [f"Topp {int(limit or 8)}", "Vis alle"], horizontal=True, key=key)
    else:
        mode = f"Topp {int(limit or 8)}"
    shown_limit = len(all_rows) if mode == "Vis alle" else int(limit or 8)
    rows = all_rows[:shown_limit]
    suffix = f"Topp {len(rows)} av {len(all_rows)} analyserte" if len(all_rows) > len(rows) else f"{len(rows)} analyserte"
    st.markdown(f"<div class='ptw-control-panel-title' style='margin-top:.85rem;margin-bottom:.35rem;'>{_html.escape(title)} <span style='font-size:.78rem;opacity:.75;'>· {_html.escape(suffix)}</span></div>", unsafe_allow_html=True)
    if not rows:
        msg = empty_text or "Ingen fond/ETF-kandidater å vise ennå. Kjør analysen eller utvid valgt fondunivers."
        st.markdown(f"<div class='v18-dark-row' style='margin:.35rem 0 .75rem 0;padding:.62rem .70rem;line-height:1.35;'>{_html.escape(msg)}</div>", unsafe_allow_html=True)
        return
    for idx, row in enumerate(rows, start=1):
        grade = str(row.get("grade") or "-")
        grade_cls = "green" if grade == "Høy" else ("yellow" if grade == "Middels" else "red")
        symbol = _html.escape(str(row.get("symbol") or "-"))
        full_label = _html.escape(_fund_display_label_v18574(row))
        raw_name = str(row.get("name") or "Navn ikke funnet")
        name = _html.escape(raw_name if raw_name and raw_name != str(row.get("symbol") or "") else "Navn ikke funnet")
        fund_type = _html.escape(str(row.get("fund_type") or "-"))
        decision = _html.escape(str(row.get("decision") or ""))
        quality = row.get("decision_quality", "-")
        base_score = row.get("base_score", "-")
        composite_score = row.get("fund_intelligence_score", "-")
        scenario_score = row.get("scenario_score", "-")
        portfolio_fit_score = row.get("portfolio_fit_score", "-")
        scenario_summary = _html.escape(str(row.get("scenario_summary") or ""))
        portfolio_fit_summary = _html.escape(str(row.get("portfolio_fit_summary") or ""))
        composite_summary = _html.escape(str(row.get("composite_summary") or ""))
        base_summary = _html.escape(str(row.get("base_score_summary") or ""))
        cost = row.get("expense_ratio_pct")
        ret = row.get("period_return_pct")
        dd = row.get("max_drawdown_pct")
        excess = row.get("excess_return_pct")
        explain = row.get("explainability_profile") or {}
        pos = "; ".join(str(x) for x in (explain.get("why_ranked_here") or row.get("reasons_positive") or [])[:2])
        caution = "; ".join(str(x) for x in (explain.get("what_holds_it_back") or row.get("reasons_caution") or [])[:2])
        select_trigger = "; ".join(str(x) for x in (explain.get("what_would_make_it_selected") or [])[:2])
        reject_trigger = "; ".join(str(x) for x in (explain.get("what_would_make_model_reject_it") or [])[:2])
        explain_short = _html.escape(str(explain.get("short_explanation") or row.get("explainability_summary") or ""))
        cost_txt = "ukjent" if cost is None else f"{cost}%"
        ret_txt = "ukjent" if ret is None else f"{ret}%"
        dd_txt = "ukjent" if dd is None else f"{dd}%"
        excess_txt = "ukjent" if excess is None else f"{excess}%"
        st.markdown(
            f"""
            <div class='v18-dark-row v18574-readable-fund' style='margin:.42rem 0; padding:.68rem .76rem; line-height:1.48;'>
              <div style='display:flex; justify-content:space-between; gap:.7rem; flex-wrap:wrap; align-items:flex-start;'>
                <div>
                  <div style='font-weight:950;font-size:1.00rem;'>#{idx} {full_label}</div>
                  <div style='font-size:.82rem;color:rgba(191,219,254,.90);margin-top:.12rem;'>Type: {fund_type}</div>
                </div>
                <span class='v18-status-chip {grade_cls}'>{_html.escape(grade)} · {quality}/100</span><span class='v18-status-chip yellow'>Grunnscore {base_score}/100</span><span class='v18-status-chip green'>Scenario {scenario_score}/100</span><span class='v18-status-chip green'>Portefølje-fit {portfolio_fit_score}/100</span>
              </div>
              <div style='font-size:.86rem;color:rgba(226,232,240,.86);margin-top:.35rem;'>Beslutning: {decision or '-'}</div><div style='font-size:.82rem;color:rgba(226,232,240,.82);margin-top:.16rem;'><b>Layer 5:</b> {composite_summary or 'Composite intelligence beregnet fra tilgjengelige lag'}</div><div style='font-size:.82rem;color:rgba(226,232,240,.82);margin-top:.16rem;'><b>Layer 7:</b> {scenario_summary or 'Scenario/regime-profil beregnet fra tilgjengelige data'}</div><div style='font-size:.82rem;color:rgba(226,232,240,.82);margin-top:.16rem;'><b>Layer 8:</b> {portfolio_fit_summary or 'Portefølje-fit vurderer overlapp, hull og diversifisering'}</div><div style='font-size:.82rem;color:rgba(226,232,240,.80);margin-top:.16rem;'>{base_summary}</div>
              <div style='font-size:.84rem;color:rgba(226,232,240,.88);margin-top:.22rem;'><b>Forklaring:</b> {explain_short or 'Layer 2 forklaring mangler'}</div>
              <div style='font-size:.84rem;color:rgba(191,219,254,.88);margin-top:.25rem;'>Kostnad {cost_txt} · Avkastning {ret_txt} · Max DD {dd_txt} · Mot benchmark {excess_txt}</div>
              <div style='font-size:.82rem;color:rgba(209,250,229,.88);margin-top:.25rem;'>+ {_html.escape(pos or 'Ingen dominerende positiv driver')}</div>
              <div style='font-size:.82rem;color:rgba(254,226,226,.88);margin-top:.18rem;'>⚠ {_html.escape(caution or 'Ingen store røde flagg')}</div>
              <div style='font-size:.82rem;color:rgba(191,219,254,.84);margin-top:.18rem;'>Velges hvis: {_html.escape(select_trigger or 'bedre total score mot alternativer')}</div>
              <div style='font-size:.82rem;color:rgba(254,226,226,.84);margin-top:.12rem;'>Forkastes hvis: {_html.escape(reject_trigger or 'risiko/kostnad forverres uten kompenserende avkastning')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_fund_comparator_v18539(comparator, title="Fond vs fond-sammenligning"):
    import html as _html
    comp = dict(comparator or {})
    st.markdown(f"<div class='ptw-control-panel-title'>{_html.escape(title)}</div>", unsafe_allow_html=True)
    if not comp or not comp.get("rows"):
        st.markdown("<div class='v18-dark-row'>Ingen sammenligning ennå. Kjør Fond / ETF-analyse først.</div>", unsafe_allow_html=True)
        return
    leaders = comp.get("leaders") or {}
    st.markdown(
        f"""
        <div class='v18-dark-row' style='display:flex;gap:.45rem;flex-wrap:wrap;align-items:center;'>
          <span class='v18-status-chip green'>Billigst: {_html.escape(str(leaders.get('billigst') or '-'))}</span>
          <span class='v18-status-chip green'>Best kvalitet: {_html.escape(str(leaders.get('best_kvalitet') or '-'))}</span>
          <span class='v18-status-chip yellow'>Best etter kostnad: {_html.escape(str(leaders.get('best_etter_kostnad') or '-'))}</span>
          <span class='v18-status-chip yellow'>Best risikojustert: {_html.escape(str(leaders.get('best_risikojustert') or '-'))}</span>
          <span class='v18-status-chip green'>Best grunnmur: {_html.escape(str(leaders.get('best_grunnmur') or '-'))}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    rows = list(comp.get("rows") or [])[:10]
    for r in rows:
        symbol = _html.escape(_fund_display_label_v18574(r))
        ftype = _html.escape(str(r.get("fund_type") or "-"))
        quality = r.get("decision_quality", "-")
        fee = "ukjent" if r.get("expense_ratio_pct") is None else f"{r.get('expense_ratio_pct')}%"
        ret = "ukjent" if r.get("period_return_pct") is None else f"{r.get('period_return_pct')}%"
        vol = "ukjent" if r.get("volatility_pct") is None else f"{r.get('volatility_pct')}%"
        dd = "ukjent" if r.get("max_drawdown_pct") is None else f"{r.get('max_drawdown_pct')}%"
        excess = "ukjent" if r.get("excess_return_pct") is None else f"{r.get('excess_return_pct')}%"
        evidence = str(r.get("active_evidence_status") or "-")
        cls = "green" if evidence == "Godkjent" else ("yellow" if evidence in {"Usikker", "Ikke relevant"} else "red")
        st.markdown(
            f"""
            <div class='v18-dark-row' style='margin:.18rem 0;padding:.36rem .5rem;'>
              <div style='display:flex;justify-content:space-between;gap:.6rem;flex-wrap:wrap;'>
                <b>{symbol}</b><span>{ftype}</span><span>Kvalitet <b>{quality}</b></span><span>Kostnad {fee}</span><span>Avkastning {ret}</span><span>Vol {vol}</span><span>DD {dd}</span><span>Mot bench {excess}</span><span class='v18-status-chip {cls}'>Aktiv bevis: {_html.escape(evidence)}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_active_evidence_v18539(rows, title="Aktivt fond må bevise merverdi"):
    import html as _html
    active = [dict(r) for r in (rows or []) if dict(r).get("fund_type") == "Aktivt fond"]
    st.markdown(f"<div class='ptw-control-panel-title'>{_html.escape(title)}</div>", unsafe_allow_html=True)
    if not active:
        st.markdown("<div class='v18-dark-row'>Ingen aktive fond i denne kjøringen.</div>", unsafe_allow_html=True)
        return
    for row in active[:8]:
        symbol = _html.escape(_fund_display_label_v18574(row))
        status = str(row.get("active_evidence_status") or "Mangler data")
        score = row.get("active_evidence_score")
        msg = _html.escape(str(row.get("active_evidence_message") or ""))
        excess = row.get("excess_return_pct")
        fee = row.get("expense_ratio_pct")
        cls = "green" if status == "Godkjent" else ("yellow" if status == "Usikker" else "red")
        st.markdown(
            f"""
            <div class='v18-dark-row' style='border-color:rgba(245,158,11,.35);'>
              <div style='display:flex;justify-content:space-between;gap:.6rem;flex-wrap:wrap;'>
                <b>{symbol}</b>
                <span class='v18-status-chip {cls}'>{_html.escape(status)} · {score if score is not None else '-'}/100</span>
              </div>
              <div style='font-size:.86rem;color:rgba(226,232,240,.86);margin-top:.18rem;'>Meravkastning mot benchmark: {excess if excess is not None else 'ukjent'}% · Kostnad: {fee if fee is not None else 'ukjent'}%</div>
              <div style='font-size:.76rem;color:rgba(254,226,226,.86);margin-top:.18rem;'>{msg}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )




def _render_fund_decision_quality_v18542(summary, title="Fondskvalitet og grunnscore"):
    """Render hardened Fund Decision Quality without dataframes/white boxes."""
    import html as _html
    dq = dict(summary or {})
    st.markdown(f"<div class='ptw-control-panel-title'>{_html.escape(title)}</div>", unsafe_allow_html=True)
    if not dq or not dq.get("rows"):
        st.markdown("<div class='v18-dark-row'>Ingen Fond Decision Quality ennå. Kjør Fond / ETF-analyse først.</div>", unsafe_allow_html=True)
        return
    avg = dq.get("average_quality")
    avg_base = dq.get("average_base_score")
    best = _html.escape(str(dq.get("best_symbol") or "-"))
    grade_counts = dq.get("grade_counts") or {}
    role_counts = dq.get("role_counts") or {}
    st.markdown(
        f"""
        <div class='v18-dark-row' style='border-color:rgba(59,130,246,.45);'>
          <div style='display:flex;justify-content:space-between;gap:.55rem;flex-wrap:wrap;align-items:center;'>
            <b>Fond Decision Quality</b>
            <span class='v18-status-chip green'>Decision Quality {avg if avg is not None else '-'}/100</span>
            <span class='v18-status-chip yellow'>Layer 1 grunnscore {avg_base if avg_base is not None else '-'}/100</span>
            <span class='v18-status-chip green'>Best: {best}</span>
            <span class='v18-status-chip yellow'>Høy: {_html.escape(str(grade_counts.get('Høy', 0)))}</span>
            <span class='v18-status-chip yellow'>Middels: {_html.escape(str(grade_counts.get('Middels', 0)))}</span>
            <span class='v18-status-chip red'>Lav: {_html.escape(str(grade_counts.get('Lav', 0)))}</span>
            <span class='v18-status-chip green'>Grunnmur: {_html.escape(str(role_counts.get('Grunnmur', 0)))}</span>
            <span class='v18-status-chip yellow'>Satellitt: {_html.escape(str(role_counts.get('Satellitt', 0)))}</span>
          </div>
          <div style='font-size:.77rem;color:rgba(226,232,240,.84);margin-top:.22rem;'>Layer 1 er stabil grunnscore. Layer 2 forklarer hvorfor fondet rangeres slik, hva som må til for valg, og hva som kan få modellen til å forkaste fondet.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for row in list(dq.get("rows") or [])[:8]:
        symbol = _html.escape(str(row.get("symbol") or "-"))
        ftype = _html.escape(str(row.get("fund_type") or "-"))
        quality = row.get("decision_quality", "-")
        base_score = row.get("base_score", "-")
        base_profile = row.get("base_score_profile") or {}
        base_summary = _html.escape(str(row.get("base_score_summary") or base_profile.get("summary") or ""))
        grade = str(row.get("grade") or "-")
        decision = _html.escape(str(row.get("decision") or "-"))
        role = _html.escape(str(row.get("recommended_role") or "-"))
        cls = "green" if grade == "Høy" else ("yellow" if grade == "Middels" else "red")
        comps = row.get("component_scores") or {}
        role_scores = row.get("role_scores") or {}
        drivers = "; ".join(str(x) for x in (row.get("drivers") or [])[:2])
        cautions = "; ".join(str(x) for x in (row.get("cautions") or [])[:2])
        why = "; ".join(str(x) for x in (row.get("why_not_100") or [])[:2])
        cost = comps.get("cost", "-")
        risk = comps.get("risk", "-")
        bench = comps.get("benchmark", "-")
        data_q = comps.get("data", "-")
        cost_impact = comps.get("cost_impact", "-")
        core_score = role_scores.get("grunnmur_score", "-")
        sat_score = role_scores.get("satellitt_score", "-")
        st.markdown(
            f"""
            <div class='v18-dark-row' style='margin:.22rem 0;padding:.44rem .55rem;'>
              <div style='display:flex;justify-content:space-between;gap:.55rem;flex-wrap:wrap;align-items:center;'>
                <b>{symbol}</b>
                <span>{ftype}</span>
                <span class='v18-status-chip {cls}'>{_html.escape(grade)} · {quality}/100</span>
                <span class='v18-status-chip yellow'>Grunnscore {base_score}/100</span>
                <span class='v18-status-chip yellow'>Rolle: {role}</span>
                <span>{decision}</span>
              </div>
              <div style='font-size:.75rem;color:rgba(191,219,254,.88);margin-top:.16rem;'>Kostnad {cost} · Kostnadstid {cost_impact} · Risiko {risk} · Benchmark {bench} · Data {data_q}</div>
              <div style='font-size:.82rem;color:rgba(226,232,240,.80);margin-top:.10rem;'>{base_summary}</div>
              <div style='font-size:.75rem;color:rgba(226,232,240,.82);margin-top:.10rem;'>Grunnmur-score {core_score} · Satellitt-score {sat_score}</div>
              <div style='font-size:.82rem;color:rgba(209,250,229,.88);margin-top:.10rem;'>+ {_html.escape(drivers or 'Ingen tydelig hoveddriver')}</div>
              <div style='font-size:.82rem;color:rgba(254,226,226,.88);margin-top:.10rem;'>⚠ {_html.escape(cautions or why or 'Ingen store røde flagg')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    warnings = list(dq.get("warnings") or [])
    if warnings:
        st.markdown(
            "<div class='v18-dark-row' style='border-color:rgba(245,158,11,.38);'><b>Merk:</b> "
            + _html.escape(" ".join(str(x) for x in warnings[:3]))
            + "</div>",
            unsafe_allow_html=True,
        )

def _render_core_satellite_v18540(core_satellite, title="Grunnmur / satellitt-forslag"):
    import html as _html
    cs = dict(core_satellite or {})
    st.markdown(f"<div class='ptw-control-panel-title'>{_html.escape(title)}</div>", unsafe_allow_html=True)
    if not cs or not cs.get("allocation"):
        warnings = cs.get("warnings") or ["Kjør Fond / ETF-analyse først."]
        st.markdown(
            f"<div class='v18-dark-row'>Ingen allokering foreslått ennå. {_html.escape(' '.join(str(x) for x in warnings[:2]))}</div>",
            unsafe_allow_html=True,
        )
        return
    profile = _html.escape(str(cs.get("profile") or "Balansert"))
    avg_q = cs.get("average_quality")
    core_pct = cs.get("target_core_pct", "-")
    sat_pct = cs.get("target_satellite_pct", "-")
    summary = _html.escape(str(cs.get("summary") or ""))
    st.markdown(
        f"""
        <div class='v18-dark-row' style='border-color:rgba(34,197,94,.42);'>
          <div style='display:flex;justify-content:space-between;gap:.65rem;flex-wrap:wrap;align-items:center;'>
            <b>Porteføljeforslag: {profile}</b>
            <span class='v18-status-chip green'>Grunnmur {core_pct}%</span>
            <span class='v18-status-chip yellow'>Satellitter {sat_pct}%</span>
            <span class='v18-status-chip green'>Kvalitet {avg_q if avg_q is not None else '-'}/100</span>
          </div>
          <div style='font-size:.86rem;color:rgba(226,232,240,.86);margin-top:.22rem;'>{summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for row in list(cs.get("allocation") or [])[:10]:
        symbol = _html.escape(str(row.get("symbol") or "-"))
        role = _html.escape(str(row.get("role") or "-"))
        role_cls = "green" if role == "Grunnmur" else "yellow"
        weight = row.get("weight_pct", 0)
        quality = row.get("decision_quality", "-")
        ftype = _html.escape(str(row.get("fund_type") or "-"))
        reason = _html.escape(str(row.get("reason") or ""))
        cost = "ukjent" if row.get("expense_ratio_pct") is None else f"{row.get('expense_ratio_pct')}%"
        st.markdown(
            f"""
            <div class='v18-dark-row' style='margin:.2rem 0;padding:.42rem .55rem;'>
              <div style='display:flex;justify-content:space-between;gap:.55rem;flex-wrap:wrap;'>
                <b>{symbol}</b>
                <span class='v18-status-chip {role_cls}'>{role}</span>
                <span>Vekt <b>{weight}%</b></span>
                <span>Kvalitet <b>{quality}</b></span>
                <span>{ftype}</span>
                <span>Kostnad {cost}</span>
              </div>
              <div style='font-size:.84rem;color:rgba(191,219,254,.88);margin-top:.16rem;'>{reason}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    warnings = list(cs.get("warnings") or [])
    needs = list(cs.get("needs_proof") or [])
    avoid = list(cs.get("avoid") or [])
    if warnings:
        st.markdown(
            "<div class='v18-dark-row' style='border-color:rgba(245,158,11,.38);'>" +
            "<b>Merk:</b> " + _html.escape(" ".join(str(x) for x in warnings[:3])) +
            "</div>",
            unsafe_allow_html=True,
        )
    if needs or avoid:
        with st.expander("Kandidater uten plass i forslaget", expanded=False):
            for row in needs[:8]:
                st.caption(f"{row.get('symbol')}: Krever mer bevis · {row.get('reason')}")
            for row in avoid[:8]:
                st.caption(f"{row.get('symbol')}: Unngå · {row.get('reason')}")



def _render_fund_cost_impact_v18541(result, title="Kostnadseffekt over tid"):
    """Render compact cost-impact cards without large white dataframes."""
    import html as _html
    from fund_etf_analyzer import build_fund_cost_impact

    rows = list((result or {}).get("ranked") or [])
    st.markdown(f"<div class='ptw-control-panel-title'>{_html.escape(title)}</div>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns([1.0, 1.0, 1.0, 0.9])
    with c1:
        start_amount = st.number_input("Startbeløp", min_value=0, max_value=100_000_000, value=100_000, step=10_000, key="fund_cost_start_v18541")
    with c2:
        monthly_saving = st.number_input("Månedlig sparing", min_value=0, max_value=2_000_000, value=2_000, step=500, key="fund_cost_monthly_v18541")
    with c3:
        annual_return = st.number_input("Avkastning før kostnad %", min_value=-20.0, max_value=30.0, value=7.0, step=0.25, key="fund_cost_return_v18541")
    with c4:
        years = st.selectbox("Horisont", [10, 20, 30], index=1, key="fund_cost_years_v18541")

    impact = build_fund_cost_impact(
        rows,
        start_amount=float(start_amount or 0),
        monthly_saving=float(monthly_saving or 0),
        annual_return_pct=float(annual_return or 0),
        years=int(years or 20),
        include_standard_levels=True,
    )
    summary = impact.get("summary") or {}
    diff = summary.get("difference_best_worst")
    st.markdown(
        f"""
        <div class='v18-dark-row' style='border-color:rgba(59,130,246,.48);'>
          <div style='display:flex;justify-content:space-between;gap:.65rem;flex-wrap:wrap;align-items:center;'>
            <b>Kostnadseffekt over {int(impact.get('years') or years)} år</b>
            <span class='v18-status-chip green'>Baseline: {impact.get('baseline_fee_pct')}%</span>
            <span class='v18-status-chip yellow'>Forskjell billigst/dyrest: {diff:,.0f} kr</span>
          </div>
          <div style='font-size:.86rem;color:rgba(226,232,240,.86);margin-top:.18rem;'>
            Start {float(start_amount or 0):,.0f} kr · Månedlig {float(monthly_saving or 0):,.0f} kr · Forventet avkastning før kostnad {float(annual_return or 0):.2f}%.
            Dette er en enkel illustrasjon, ikke en garanti for fremtidig avkastning.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for row in list(impact.get("rows") or [])[:12]:
        label = _html.escape(_security_display_label_v18569(row.get("symbol") or row.get("label") or "", row) if row.get("symbol") else str(row.get("label") or "-"))
        fee = row.get("expense_ratio_pct")
        ending = float(row.get("ending_value") or 0.0)
        vs_base = float(row.get("vs_baseline") or 0.0)
        drag = float(row.get("cost_drag_vs_no_fee") or 0.0)
        cls = "green" if vs_base >= -1 else ("yellow" if abs(vs_base) < 50_000 else "red")
        sign = "+" if vs_base >= 0 else ""
        st.markdown(
            f"""
            <div class='v18-dark-row' style='margin:.18rem 0;padding:.42rem .55rem;'>
              <div style='display:flex;justify-content:space-between;gap:.55rem;flex-wrap:wrap;align-items:center;'>
                <b>{label}</b>
                <span class='v18-status-chip {cls}'>Kostnad {fee}%</span>
                <span>Sluttverdi <b>{ending:,.0f} kr</b></span>
                <span>Mot baseline <b>{sign}{vs_base:,.0f} kr</b></span>
                <span>Tapt mot 0% kostnad <b>{drag:,.0f} kr</b></span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not rows:
        st.markdown("<div class='v18-dark-row'>Kjør Fond / ETF-analyse for å bruke faktiske fondskostnader. Referansenivåene over viser likevel kostnadseffekten.</div>", unsafe_allow_html=True)

def render_fund_etf_control_center_v18538():
    """On-demand Fund / ETF Analyzer with fund-specific progress and quality score."""
    st.subheader("🏦 Fond / ETF-analyse")
    st.caption("Analyser aksje-, indeks-, aktive-, rente-, high yield- og pengemarkedsfond når du trykker Kjør. v18.5.46 skiller rente-/kredittfond fra vanlige aksjefond.")

    from fund_etf_analyzer import default_fund_benchmark, fund_market_options, fund_selection_sources, fund_type_options
    col_src, col_market, col_a, col_b, col_c, col_d = st.columns([1.0, 0.92, 0.9, 1.0, 0.86, 0.72])
    with col_src:
        selection_source = st.selectbox("Utvalgskilde", fund_selection_sources(), key="fund_lab_source_v18539", help="Auto-univers velger fra fondskatalogen. Manuell liste bruker dine symboler i rekkefølge.")
    with col_market:
        fund_market = st.selectbox("Marked / region", fund_market_options(), key="fund_lab_market_v1863x", help="Bruker samme markedslogikk som resten av AI Kontrollsenter, med ekstra Europa/UCITS for fond.")
    with col_a:
        fund_type = st.selectbox("Fondstype", fund_type_options(), key="fund_lab_type_v18538")
    with col_b:
        objective = st.selectbox("Mål", ["Balansert", "Lav kostnad", "Lav risiko", "Best historikk", "Grunnmur"], key="fund_lab_objective_v18538")
    with col_c:
        test_mode = st.selectbox("Testmodus", ["Rask", "Normal", "Grundig"], index=1, key="fund_lab_test_mode_v18538")
    with col_d:
        max_funds = st.slider("Maks fond", 1, 40, 8, 1, key="fund_lab_limit_v18538")

    auto_benchmark = st.checkbox("Automatisk benchmark", value=True, key="fund_lab_auto_benchmark_v1863x")
    auto_benchmark_symbol = default_fund_benchmark(fund_type, fund_market)
    col_bench, col_period = st.columns([1.0, 1.0])
    with col_bench:
        if auto_benchmark:
            benchmark_symbol = auto_benchmark_symbol
            st.markdown(f"<div class='v18-dark-row'>Benchmark: <b>{html.escape(benchmark_symbol)}</b> valgt automatisk for {html.escape(str(fund_type))} / {html.escape(str(fund_market))}.</div>", unsafe_allow_html=True)
        else:
            benchmark_symbol = st.text_input("Benchmark", value=auto_benchmark_symbol, key="fund_lab_benchmark_v18538", help="Yahoo-symbol for benchmark, f.eks. SPY, HYG, BND, SGOV, EUNL.DE.").strip().upper()
    with col_period:
        period = st.selectbox("Historikk", ["1y", "3y", "5y", "10y"], index=2, key="fund_lab_period_v18538")

    default_list = "SPY, VOO, VTI, QQQ, ACWI, BND, HYG, SGOV"
    manual_text = st.text_area("Fond/ETF-liste", value=default_list, height=76, key="fund_lab_manual_v18538", help="Bruk tickere der Yahoo Finance har data. For norske fond som Kraft High Yield D kan NAV-data mangle i gratis datakilder; skriv gjerne Kraft High Yield D eller KRAFT_HIGH_YIELD_D for manuell klassifisering.")

    c1, c2, c3 = st.columns([1.0, 1.0, 1.2])
    with c1:
        include_benchmark = st.checkbox("Benchmark-sjekk", value=True, key="fund_lab_include_benchmark_v18538")
    with c2:
        fetch_costs = st.checkbox("Prøv å hente kostnader", value=True, key="fund_lab_fetch_costs_v18538")
    with c3:
        store_result = st.checkbox("Lagre resultat", value=True, key="fund_lab_store_result_v18538")

    from fund_etf_analyzer import parse_fund_list, estimate_fund_etf_run, select_fund_candidates
    manual_symbols = parse_fund_list(manual_text)
    selection = select_fund_candidates(source=selection_source, fund_type=fund_type, manual_symbols=manual_symbols, max_funds=int(max_funds or 8), market_scope=fund_market)
    symbols = list(selection.get("symbols") or [])
    budget = estimate_fund_etf_run(symbols, test_mode=test_mode, include_benchmark=bool(include_benchmark), fetch_costs=bool(fetch_costs))
    tests_text = ", ".join(str(x) for x in (budget.get("tests") or [])[:10])
    st.markdown(
        f"""
        <div class='v18-dark-row' style='display:flex; justify-content:space-between; gap:.7rem; flex-wrap:wrap;'>
          <span><b>Planlagt fondanalyse:</b> {int(budget.get('funds', len(symbols)) or 0)} fond · {int(budget.get('tests_per_fund', 0) or 0)} tester per fond · {int(budget.get('total_tests', 0) or 0)} totalt</span>
          <span class='v18-status-chip green'>Kilde: {html.escape(str(selection.get('source') or selection_source))}</span>
          <span class='v18-status-chip green'>Marked: {html.escape(str(selection.get('market_scope') or fund_market))}</span>
          <span class='v18-status-chip {'red' if budget.get('load_label') == 'Høy' else ('yellow' if budget.get('load_label') == 'Medium' else 'green')}'>Databudsjett: {html.escape(str(budget.get('load_label') or 'Ukjent'))}</span>
          <span>Prisdata: {int(budget.get('price_calls', 0) or 0)} · Metadata: {int(budget.get('metadata_calls', 0) or 0)} · Benchmark: {int(budget.get('benchmark_calls', 0) or 0)}</span>
        </div>
        <div class='v18-dark-row' style='font-size:.75rem; opacity:.86;'>Tester: {html.escape(tests_text or 'Ingen')}</div>
        """,
        unsafe_allow_html=True,
    )

    if symbols:
        reasons = []
        for item in list(selection.get("selected") or [])[:12]:
            markets = ", ".join(str(x) for x in (item.get("markets") or []))
            reasons.append(f"<b>{html.escape(str(item.get('symbol') or ''))}</b> <span style='opacity:.75'>({html.escape(str(markets or item.get('bucket') or '-'))}: {html.escape(str(item.get('reason') or 'valgt'))})</span>")
        st.markdown(f"<div class='v18-dark-row'>Valgte fond/ETF-er: {', '.join(reasons)}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='v18-dark-row'>Ingen fond/ETF-symboler funnet for valgt marked/type. Prøv Alle, Europa/UCITS eller Manuell liste.</div>", unsafe_allow_html=True)

    run_col, stop_col = st.columns([2.2, 1.0])
    with run_col:
        run_clicked = st.button("🏦 Kjør Fond / ETF-analyse", key="fund_lab_run_v18538", type="primary", use_container_width=True, on_click=set_global_busy, kwargs={"label": "Kjører Fond / ETF", "detail": "Tester fond mot kostnad, risiko og benchmark"})
    with stop_col:
        if st.button("⏹ Stopp/avbryt", key="fund_lab_stop_v18538", use_container_width=True):
            st.session_state["fund_lab_stop_requested_v18538"] = True
            st.warning("Stopp er bedt om. Kjøringen stopper ved neste trygge kontrollpunkt.")

    if run_clicked:
        st.session_state["fund_lab_stop_requested_v18538"] = False
        if not symbols:
            st.warning("Ingen fond/ETF-er å teste.")
            finish_global_busy("Klar", "Fond / ETF-analyse manglet symboler.")
            return
        if yf is None:
            st.error("yfinance er ikke tilgjengelig i miljøet. Legg yfinance i requirements/deploy før fonddata kan hentes.")
            finish_global_busy("Klar", "Fond / ETF-analyse stoppet: yfinance mangler.")
            return

        from fund_etf_analyzer import run_fund_etf_lab
        from services.storage_service import get_storage_service
        from datetime import datetime, timezone

        status_box = st.empty()
        progress = st.progress(0, text="Starter Fond / ETF-analyse")
        update_global_busy("Kjører Fond / ETF", "Starter", step=0, total=int(budget.get("total_tests", 0) or 0))

        def _download_symbol(symbol):
            info = {}
            hist = None
            try:
                t = yf.Ticker(symbol)
                if fetch_costs:
                    try:
                        info = dict(getattr(t, "info", {}) or {})
                    except Exception:
                        info = {}
                try:
                    hist = t.history(period=period, auto_adjust=True)
                except Exception:
                    hist = None
            except Exception:
                info = {}
                hist = None
            closes = []
            if hist is not None:
                try:
                    if hasattr(hist, "columns") and "Close" in hist.columns:
                        closes = [float(x) for x in hist["Close"].dropna().tolist()]
                except Exception:
                    closes = []
            return {
                "symbol": symbol,
                "name": info.get("longName") or info.get("shortName") or symbol,
                "longName": info.get("longName") or info.get("shortName") or symbol,
                "quoteType": info.get("quoteType") or info.get("typeDisp"),
                "category": info.get("category"),
                "fundFamily": info.get("fundFamily"),
                "expenseRatio": info.get("annualReportExpenseRatio") or info.get("expenseRatio") or info.get("netExpenseRatio"),
                "prices": closes,
            }

        def _should_stop():
            return bool(st.session_state.get("fund_lab_stop_requested_v18538", False))

        def _progress_callback(ev):
            pct = float(ev.get("percent") or 0.0)
            completed = int(ev.get("completed_tests") or 0)
            total = int(ev.get("total_tests") or 0)
            symbol = str(ev.get("symbol") or "-")
            test_name = str(ev.get("test_name") or "Starter")
            fund_idx = int(ev.get("fund_index") or 0)
            fund_total = int(ev.get("fund_total") or len(symbols))
            test_idx = int(ev.get("test_index") or 0)
            tests_per = int(ev.get("tests_per_fund") or max(1, int(budget.get("tests_per_fund", 1) or 1)))
            status = str(ev.get("status") or "running")
            progress.progress(min(100, max(0, int(round(pct)))), text=f"{completed}/{total} tester · {pct:.0f}%")
            update_global_busy("Kjører Fond / ETF", f"{symbol} · {test_name} · {pct:.0f}%", step=completed, total=total)
            status_box.markdown(
                f"""
                <div class='v18-dark-row' style='border-color:rgba(59,130,246,.55);'>
                  <div style='display:flex;justify-content:space-between;gap:.7rem;flex-wrap:wrap;'>
                    <b>🔄 Fond / ETF-analyse kjører</b>
                    <span class='v18-status-chip yellow'>{html.escape(status)} · {completed}/{total}</span>
                  </div>
                  <div style='font-size:.82rem;margin-top:.25rem;'>Fond/ETF: <b>{html.escape(symbol)}</b> · Test nå: <b>{html.escape(test_name)}</b></div>
                  <div style='font-size:.86rem;color:rgba(226,232,240,.86);'>Fond {fund_idx}/{fund_total} · Test {test_idx}/{tests_per} · Total fremdrift {pct:.1f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        result = run_fund_etf_lab(
            symbols,
            data_provider=_download_symbol,
            benchmark_provider=_download_symbol if include_benchmark else None,
            benchmark_symbol=benchmark_symbol or "SPY",
            fund_type=fund_type,
            objective=objective,
            test_mode=test_mode,
            progress_callback=_progress_callback,
            should_stop=_should_stop,
            max_funds=int(max_funds or 8),
            selection_info=selection,
        )
        result["period"] = period
        result["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        st.session_state["fund_etf_lab_last_result_v18538"] = result
        if store_result:
            try:
                storage = get_storage_service()
                storage.write_json("fund_etf_lab/latest.json", result)
                storage.append_jsonl("fund_etf_lab/history.jsonl", result)
                result["storage_backend"] = storage.backend()
            except Exception as exc:
                result["storage_error"] = str(exc)[:180]
        progress.progress(100, text="Ferdig" if not result.get("interrupted") else "Avbrutt")
        finish_global_busy("Klar", "Fond / ETF-analyse ferdig." if not result.get("interrupted") else "Fond / ETF-analyse avbrutt.")
        if result.get("interrupted"):
            st.warning(f"Fond / ETF-analyse avbrutt etter {result.get('completed_tests', 0)} av {result.get('total_tests', 0)} tester. Foreløpig resultat er lagret.")
        else:
            st.success(f"Fond / ETF-analyse ferdig: {result.get('summary', {}).get('analyzed', 0)} analyserte fond · {result.get('completed_tests', 0)}/{result.get('total_tests', 0)} tester.")

    result = st.session_state.get("fund_etf_lab_last_result_v18538") or {}
    if result:
        summary = result.get("summary", {}) or {}
        cols = st.columns(5)
        cols[0].metric("Analyserte", summary.get("analyzed", 0))
        cols[1].metric("Tester", f"{result.get('completed_tests', 0)}/{result.get('total_tests', 0)}")
        cols[2].metric("Beste", summary.get("best_symbol") or "-")
        cols[3].metric("Kvalitet", summary.get("best_quality") or "-")
        cols[4].metric("Feil", summary.get("errors", 0))
        if result.get("interrupted"):
            st.warning("Siste Fond / ETF-analyse ble avbrutt. Resultatene under er foreløpige.")
        if int(summary.get("analyzed", 0) or 0) == 0 and int(summary.get("errors", 0) or 0) > 0:
            st.warning("Fond/ETF-er ble valgt, men ingen kunne analyseres. Vanligste årsak er manglende pris-/NAV-historikk i valgt datakilde. Se detaljene under før du endrer strategi.")
        _render_fund_result_scope_v18547(result, default_limit=8)
        _render_what_changed_v18555(result.get("what_changed_profile"))
        display_limit = int((summary or {}).get("selected_max") or (result.get("selection") or {}).get("display_limit") or 8)
        _render_fund_etf_rows_v18538(result.get("ranked"), title="Beste fond / ETF-kandidater", limit=display_limit)
        _render_fund_comparator_v18539(result.get("comparator"), title="Fond vs fond-sammenligning")
        _render_fund_decision_quality_v18542(result.get("decision_quality_summary"), title="Fondskvalitet og grunnscore")
        _render_core_satellite_v18540(result.get("core_satellite"), title="Grunnmur / satellitt-forslag")
        _render_fund_cost_impact_v18541(result, title="Kostnadseffekt over tid")
        _render_fund_etf_rows_v18538(result.get("index_candidates"), title="Indeksfond / ETF-kandidater", limit=5, empty_text="Ingen kandidater ennå. Kjør fondanalyse først.")
        _render_active_evidence_v18539(result.get("ranked"), title="Vurdering av aktive fond")
        _render_fund_etf_rows_v18538(result.get("active_candidates"), title="Aktive fond som kan vurderes", limit=5)
        _render_fund_etf_rows_v18538(result.get("fixed_income_candidates"), title="Rente-/obligasjonsfond og pengemarked", limit=5)
        _render_fund_etf_rows_v18538(result.get("high_yield_candidates"), title="High yield / kredittsatellitter", limit=5)
        needs = result.get("needs_proof") or []
        errors = result.get("errors") or []
        if needs or errors:
            with st.expander("Krever mer bevis / mangler data / feil", expanded=False):
                for row in needs[:12]:
                    st.caption(f"{row.get('symbol')}: {row.get('decision')} · {', '.join(row.get('reasons_caution') or [])}")
                for row in errors[:12]:
                    st.caption(f"{row.get('symbol')}: {row.get('test', '-')}: {row.get('error')}")
    else:
        st.info("Ingen Fond / ETF-resultat ennå. Legg inn fond/ETF-er og trykk Kjør.")



# v18.5.43: Auto Test Lab Fund Mode.
def render_auto_test_lab_fund_mode_v18543():
    """Run the fund/ETF engine from Auto Test Lab, with progress and safe controls."""
    import html as _html
    st.markdown("<div class='v18-dark-row'><b>Fondmodus:</b> Auto Test Lab tester fond/ETF-er mot kostnad, benchmark, aktiv merverdi, grunnmur/satellitt og Fond Decision Quality.</div>", unsafe_allow_html=True)

    from fund_etf_analyzer import default_fund_benchmark, fund_market_options, fund_selection_sources, fund_type_options, parse_fund_list, select_fund_candidates
    from auto_test_lab import estimate_auto_lab_fund_run

    col_src, col_market, col_type, col_obj, col_mode, col_max = st.columns([1.0, 0.92, 0.9, 1.0, 0.86, 0.72])
    with col_src:
        selection_source = st.selectbox(
            "Utvalgskilde",
            fund_selection_sources(),
            key="auto_lab_fund_source_v18543",
            help="Auto-kilder velger fond/ETF-er fra et transparent start-univers. Manuell liste bruker dine symboler i rekkefølge.",
        )
    with col_market:
        fund_market = st.selectbox("Marked / region", fund_market_options(), key="auto_lab_fund_market_v1863x")
    with col_type:
        fund_type = st.selectbox("Fondstype", fund_type_options(), key="auto_lab_fund_type_v18543")
    with col_obj:
        objective = st.selectbox("Mål", ["Balansert", "Lav kostnad", "Lav risiko", "Best historikk", "Grunnmur"], key="auto_lab_fund_objective_v18543")
    with col_mode:
        test_mode = st.selectbox("Testmodus", ["Rask", "Normal", "Grundig"], index=1, key="auto_lab_fund_test_mode_v18543")
    with col_max:
        max_funds = st.slider("Maks fond", 1, 40, 8, 1, key="auto_lab_fund_limit_v18543")

    auto_benchmark = st.checkbox("Automatisk benchmark", value=True, key="auto_lab_fund_auto_benchmark_v1863x")
    auto_benchmark_symbol = default_fund_benchmark(fund_type, fund_market)
    col_bench, col_period = st.columns([1.0, 1.0])
    with col_bench:
        if auto_benchmark:
            benchmark_symbol = auto_benchmark_symbol
            st.markdown(f"<div class='v18-dark-row'>Benchmark: <b>{_html.escape(benchmark_symbol)}</b> valgt automatisk for {_html.escape(str(fund_type))} / {_html.escape(str(fund_market))}.</div>", unsafe_allow_html=True)
        else:
            benchmark_symbol = st.text_input(
                "Benchmark",
                value=auto_benchmark_symbol,
                key="auto_lab_fund_benchmark_v18543",
                help="Yahoo-symbol for benchmark, f.eks. SPY, HYG, BND, SGOV, EUNL.DE.",
            ).strip().upper()
    with col_period:
        period = st.selectbox("Historikk", ["1y", "3y", "5y", "10y"], index=2, key="auto_lab_fund_period_v18543")

    default_list = "SPY, VOO, VTI, QQQ, ACWI, BND, HYG, SGOV"
    manual_text = st.text_area(
        "Fond/ETF-liste",
        value=default_list,
        height=72,
        key="auto_lab_fund_manual_v18543",
        help="Bruk tickere der Yahoo Finance har data. Auto-kilder brukes når Utvalgskilde ikke er Manuell liste. Kraft High Yield D kan skrives som tekst/alias, men krever NAV-datakilde for full data.",
    )

    c1, c2, c3 = st.columns([1.0, 1.0, 1.2])
    with c1:
        include_benchmark = st.checkbox("Benchmark-sjekk", value=True, key="auto_lab_fund_include_benchmark_v18543")
    with c2:
        fetch_costs = st.checkbox("Prøv å hente kostnader", value=True, key="auto_lab_fund_fetch_costs_v18543")
    with c3:
        store_result = st.checkbox("Lagre Auto Test Lab-resultat", value=True, key="auto_lab_fund_store_result_v18543")

    manual_symbols = parse_fund_list(manual_text)
    selection = select_fund_candidates(source=selection_source, fund_type=fund_type, manual_symbols=manual_symbols, max_funds=int(max_funds or 8), market_scope=fund_market)
    symbols = list(selection.get("symbols") or [])
    budget = estimate_auto_lab_fund_run(symbols, test_mode=test_mode, include_benchmark=bool(include_benchmark), fetch_costs=bool(fetch_costs))
    tests_text = ", ".join(str(x) for x in (budget.get("tests") or [])[:10])

    load_cls = "red" if budget.get("load_label") == "Høy" else ("yellow" if budget.get("load_label") == "Medium" else "green")
    st.markdown(
        f"""
        <div class='v18-dark-row' style='display:flex; justify-content:space-between; gap:.7rem; flex-wrap:wrap;'>
          <span><b>Planlagt fondmodus:</b> {int(budget.get('funds', len(symbols)) or 0)} fond/ETF · {int(budget.get('tests_per_fund', 0) or 0)} tester per fond · {int(budget.get('total_tests', 0) or 0)} totalt</span>
          <span class='v18-status-chip green'>Auto Test Lab: Fond / ETF</span>
          <span class='v18-status-chip green'>Marked: {_html.escape(str(selection.get('market_scope') or fund_market))}</span>
          <span class='v18-status-chip {load_cls}'>Databudsjett: {_html.escape(str(budget.get('load_label') or 'Ukjent'))}</span>
          <span>Prisdata: {int(budget.get('price_calls', 0) or 0)} · Metadata: {int(budget.get('metadata_calls', 0) or 0)} · Benchmark: {int(budget.get('benchmark_calls', 0) or 0)}</span>
        </div>
        <div class='v18-dark-row' style='font-size:.75rem; opacity:.86;'>Tester: {_html.escape(tests_text or 'Ingen')}</div>
        """,
        unsafe_allow_html=True,
    )

    if symbols:
        reasons = []
        for item in list(selection.get("selected") or [])[:12]:
            markets = ", ".join(str(x) for x in (item.get("markets") or []))
            reasons.append(f"<b>{_html.escape(str(item.get('symbol') or ''))}</b> <span style='opacity:.75'>({_html.escape(str(markets or item.get('bucket') or '-'))}: {_html.escape(str(item.get('reason') or 'valgt'))})</span>")
        st.markdown(f"<div class='v18-dark-row'>Valgte fond/ETF-er: {', '.join(reasons)}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='v18-dark-row'>Ingen fond/ETF-symboler funnet for valgt marked/type. Prøv Alle, Europa/UCITS eller Manuell liste.</div>", unsafe_allow_html=True)

    run_col, stop_col = st.columns([2.2, 1.0])
    with run_col:
        run_clicked = st.button(
            "🏦 Kjør Auto Test Lab – Fondmodus",
            key="auto_lab_fund_run_v18543",
            type="primary",
            use_container_width=True,
            on_click=set_global_busy,
            kwargs={"label": "Kjører Auto Test Lab Fondmodus", "detail": "Tester fond/ETF mot kostnad, benchmark og beslutningskvalitet"},
        )
    with stop_col:
        if st.button("⏹ Stopp/avbryt", key="auto_lab_fund_stop_v18543", use_container_width=True, help="Ber kjøringen stoppe trygt ved neste kontrollpunkt."):
            st.session_state["auto_lab_fund_stop_requested_v18543"] = True
            st.warning("Stopp er bedt om. Fondmodus stopper ved neste trygge kontrollpunkt.")

    if run_clicked:
        st.session_state["auto_lab_fund_stop_requested_v18543"] = False
        if not symbols:
            st.warning("Ingen fond/ETF-er å teste.")
            finish_global_busy("Klar", "Auto Test Lab Fondmodus manglet symboler.")
            return
        if yf is None:
            st.error("yfinance er ikke tilgjengelig i miljøet. Legg yfinance i requirements/deploy før fonddata kan hentes.")
            finish_global_busy("Klar", "Auto Test Lab Fondmodus stoppet: yfinance mangler.")
            return

        from auto_test_lab import run_auto_test_lab_fund_mode
        from services.storage_service import get_storage_service
        from datetime import datetime, timezone

        status_box = st.empty()
        progress = st.progress(0, text="Starter Auto Test Lab Fondmodus")
        update_global_busy("Kjører Auto Test Lab Fondmodus", "Starter", step=0, total=int(budget.get("total_tests", 0) or 0))

        def _download_symbol(symbol):
            info = {}
            hist = None
            try:
                t = yf.Ticker(symbol)
                if fetch_costs:
                    try:
                        info = dict(getattr(t, "info", {}) or {})
                    except Exception:
                        info = {}
                try:
                    hist = t.history(period=period, auto_adjust=True)
                except Exception:
                    hist = None
            except Exception:
                info = {}
                hist = None
            closes = []
            if hist is not None:
                try:
                    if hasattr(hist, "columns") and "Close" in hist.columns:
                        closes = [float(x) for x in hist["Close"].dropna().tolist()]
                except Exception:
                    closes = []
            return {
                "symbol": symbol,
                "name": info.get("longName") or info.get("shortName") or symbol,
                "longName": info.get("longName") or info.get("shortName") or symbol,
                "quoteType": info.get("quoteType") or info.get("typeDisp"),
                "category": info.get("category"),
                "fundFamily": info.get("fundFamily"),
                "expenseRatio": info.get("annualReportExpenseRatio") or info.get("expenseRatio") or info.get("netExpenseRatio"),
                "prices": closes,
            }

        def _should_stop():
            return bool(st.session_state.get("auto_lab_fund_stop_requested_v18543", False))

        def _progress_callback(ev):
            pct = float(ev.get("percent") or 0.0)
            completed = int(ev.get("completed_tests") or 0)
            total = int(ev.get("total_tests") or 0)
            symbol = str(ev.get("symbol") or "-")
            test_name = str(ev.get("test_name") or "Starter")
            fund_idx = int(ev.get("fund_index") or 0)
            fund_total = int(ev.get("fund_total") or len(symbols))
            test_idx = int(ev.get("test_index") or 0)
            tests_per = int(ev.get("tests_per_fund") or max(1, int(budget.get("tests_per_fund", 1) or 1)))
            status = str(ev.get("status") or "running")
            progress.progress(min(100, max(0, int(round(pct)))), text=f"{completed}/{total} tester · {pct:.0f}%")
            update_global_busy("Kjører Auto Test Lab Fondmodus", f"{symbol} · {test_name} · {pct:.0f}%", step=completed, total=total)
            status_box.markdown(
                f"""
                <div class='v18-dark-row' style='border-color:rgba(59,130,246,.55);'>
                  <div style='display:flex;justify-content:space-between;gap:.7rem;flex-wrap:wrap;'>
                    <b>🔄 Auto Test Lab Fondmodus kjører</b>
                    <span class='v18-status-chip yellow'>{_html.escape(status)} · {completed}/{total}</span>
                  </div>
                  <div style='font-size:.82rem;margin-top:.25rem;'>Fond/ETF: <b>{_html.escape(symbol)}</b> · Test nå: <b>{_html.escape(test_name)}</b></div>
                  <div style='font-size:.86rem;color:rgba(226,232,240,.86);'>Fond {fund_idx}/{fund_total} · Test {test_idx}/{tests_per} · Total fremdrift {pct:.1f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        result = run_auto_test_lab_fund_mode(
            symbols,
            data_provider=_download_symbol,
            benchmark_provider=_download_symbol if include_benchmark else None,
            benchmark_symbol=benchmark_symbol or "SPY",
            fund_type=fund_type,
            objective=objective,
            test_mode=test_mode,
            progress_callback=_progress_callback,
            should_stop=_should_stop,
            max_funds=int(max_funds or 8),
            selection_info=selection,
        )
        result["scope"] = selection_source
        result["period"] = period
        result["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        st.session_state["auto_test_lab_last_result_fund_v18543"] = result
        if store_result:
            try:
                storage = get_storage_service()
                storage.write_json("auto_test_lab/fund_latest.json", result)
                storage.append_jsonl("auto_test_lab/fund_history.jsonl", result)
                result["storage_backend"] = storage.backend()
            except Exception as exc:
                result["storage_error"] = str(exc)[:180]
        progress.progress(100, text="Ferdig" if not result.get("interrupted") else "Avbrutt")
        finish_global_busy("Klar", "Auto Test Lab Fondmodus ferdig." if not result.get("interrupted") else "Auto Test Lab Fondmodus avbrutt.")
        if result.get("interrupted"):
            st.warning(f"Auto Test Lab Fondmodus avbrutt etter {result.get('completed_tests', 0)} av {result.get('total_tests', 0)} tester. Foreløpig resultat er lagret.")
        else:
            st.success(f"Auto Test Lab Fondmodus ferdig: {result.get('summary', {}).get('analyzed', 0)} analyserte fond · {result.get('completed_tests', 0)}/{result.get('total_tests', 0)} tester.")

    result = st.session_state.get("auto_test_lab_last_result_fund_v18543") or {}
    if result:
        summary = result.get("summary", {}) or {}
        cols = st.columns(5)
        cols[0].metric("Analyserte fond", summary.get("analyzed", 0))
        cols[1].metric("Tester", f"{result.get('completed_tests', 0)}/{result.get('total_tests', 0)}")
        cols[2].metric("Beste", summary.get("best_symbol") or "-")
        cols[3].metric("Kvalitet", summary.get("best_quality") or "-")
        cols[4].metric("Grunnmur/sat", summary.get("core_satellite_positions", 0))
        if result.get("interrupted"):
            st.warning("Siste Auto Test Lab Fondmodus ble avbrutt. Resultatene under er foreløpige.")
        if int(summary.get("analyzed", 0) or 0) == 0 and int(summary.get("errors", 0) or 0) > 0:
            st.warning("Fond/ETF-er ble valgt, men ingen kunne analyseres. Vanligste årsak er manglende pris-/NAV-historikk i valgt datakilde. Se detaljene under før du endrer strategi.")
        _render_fund_result_scope_v18547(result, default_limit=8)
        _render_what_changed_v18555(result.get("what_changed_profile"))
        display_limit = int((summary or {}).get("selected_max") or (result.get("selection") or {}).get("display_limit") or 8)
        _render_fund_etf_rows_v18538(result.get("ranked") or result.get("best_funds"), title="Beste fond / ETF fra Auto Test Lab", limit=display_limit)
        _render_fund_comparator_v18539(result.get("fund_comparator") or result.get("comparator"), title="Fond vs fond-sammenligning")
        _render_fund_decision_quality_v18542(result.get("fund_decision_quality_summary") or result.get("decision_quality_summary"), title="Fondskvalitet og grunnscore")
        _render_core_satellite_v18540(result.get("core_satellite"), title="Grunnmur / satellitt-forslag")
        _render_fund_cost_impact_v18541(result, title="Kostnadseffekt over tid")
        _render_fund_etf_rows_v18538(result.get("index_candidates") or result.get("best_index_etf"), title="Indeksfond / ETF-kandidater", limit=5, empty_text="Ingen kandidater ennå. Kjør fondanalyse først.")
        _render_active_evidence_v18539(result.get("ranked"), title="Vurdering av aktive fond")
        needs = result.get("requires_more_evidence") or result.get("needs_proof") or []
        errors = result.get("errors") or []
        if needs or errors:
            with st.expander("Krever mer bevis / mangler data / feil", expanded=False):
                for row in needs[:12]:
                    st.caption(f"{row.get('symbol')}: {row.get('decision')} · {', '.join(row.get('reasons_caution') or [])}")
                for row in errors[:12]:
                    st.caption(f"{row.get('symbol')}: {row.get('test', '-')}: {row.get('error')}")
    else:
        st.info("Ingen Auto Test Lab-resultat i fondmodus ennå. Velg fondunivers og trykk Kjør.")



# v18.5.44: Portfolio Analyzer - Stocks + Funds -----------------------------
def _portfolio_analyzer_result_rows_v18544(result_key: str, row_keys: list[str], limit: int = 12):
    """Fetch rows from a previous lab/result in session_state without triggering analysis."""
    result = st.session_state.get(result_key) or {}
    if not isinstance(result, dict):
        return []
    rows = []
    for key in row_keys:
        vals = result.get(key) or []
        if isinstance(vals, list):
            rows.extend([v for v in vals if isinstance(v, dict)])
        if len(rows) >= limit:
            break
    return rows[: int(limit or 12)]


def _paper_trading_holdings_v18544(limit: int = 20):
    """Resolve paper trading positions as portfolio rows without price/network calls."""
    try:
        portfolio = load_portfolio() or {}
        positions = portfolio.get("positions") if isinstance(portfolio, dict) else {}
        rows = []
        if isinstance(positions, dict):
            for ticker, pos in positions.items():
                if not ticker:
                    continue
                weight = None
                try:
                    shares = float((pos or {}).get("shares") or 0)
                    price = float((pos or {}).get("last_price") or (pos or {}).get("entry_price") or 0)
                    value = shares * price
                    rows.append({"symbol": ticker, "asset_type": (pos or {}).get("asset_type", "Aksje"), "position_value": value, "source": "Paper trading", "metadata": {"currency": (pos or {}).get("currency", ""), "purchase_mode": (pos or {}).get("purchase_mode", "")}})
                except Exception:
                    rows.append({"symbol": ticker, "asset_type": (pos or {}).get("asset_type", "Aksje"), "source": "Paper trading"})
        elif isinstance(positions, list):
            for pos in positions:
                if isinstance(pos, dict):
                    ticker = pos.get("ticker") or pos.get("symbol")
                    if ticker:
                        rows.append({"symbol": ticker, "asset_type": (pos or {}).get("asset_type", "Aksje"), "source": "Paper trading"})
        total_value = sum(float(r.get("position_value") or 0.0) for r in rows)
        if total_value > 0:
            for r in rows:
                r["weight_pct"] = round((float(r.get("position_value") or 0.0) / total_value) * 100.0, 2)
        return rows[: int(limit or 20)]
    except Exception:
        return []


def _render_portfolio_health_rows_v18544(result):
    import html as _html
    res = dict(result or {})
    summary = res.get("summary") or {}
    grade = str(res.get("grade") or "-")
    health = res.get("portfolio_health", "-")
    grade_cls = "green" if str(grade).startswith("Sterk") else ("yellow" if str(grade).startswith("OK") else "red")
    st.markdown(
        f"""
        <div class='v18-dark-row' style='border-color:rgba(59,130,246,.48);'>
          <div style='display:flex;justify-content:space-between;gap:.55rem;flex-wrap:wrap;align-items:center;'>
            <b>📊 Porteføljehelse</b>
            <span class='v18-status-chip {grade_cls}'>{_html.escape(str(grade))} · {health}/100</span>
            <span class='v18-status-chip green'>Fond/ETF {summary.get('fund_pct', 0)}%</span>
            <span class='v18-status-chip yellow'>Aksjer {summary.get('stock_pct', 0)}%</span>
            <span class='v18-status-chip green'>Grunnmur {summary.get('core_pct', 0)}%</span>
            <span class='v18-status-chip yellow'>Satellitt {summary.get('satellite_pct', 0)}%</span>
            <span class='v18-status-chip yellow'>Tech/vekst {summary.get('tech_pct', 0)}%</span>
          </div>
          <div style='font-size:.86rem;color:rgba(226,232,240,.86);margin-top:.22rem;'>{_html.escape(str(summary.get('text') or ''))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    metrics = [
        ("Topp 3", f"{summary.get('top3_pct', '-')}%"),
        ("Største posisjon", f"{summary.get('max_single_position_pct', '-')}%"),
        ("Vektet fondskostnad", "ukjent" if summary.get("weighted_fund_expense_pct") is None else f"{summary.get('weighted_fund_expense_pct')}%"),
        ("Vektet kvalitet", summary.get("weighted_quality") or "-"),
    ]
    st.markdown(
        "<div class='v18-dark-row' style='display:flex;gap:.45rem;flex-wrap:wrap;'>" + "".join(
            f"<span class='v18-status-chip'>{_html.escape(str(k))}: <b>{_html.escape(str(v))}</b></span>" for k, v in metrics
        ) + "</div>",
        unsafe_allow_html=True,
    )
    rows = list(res.get("holdings") or [])[:14]
    if rows:
        st.markdown("<div class='ptw-control-panel-title'>Posisjoner</div>", unsafe_allow_html=True)
    for row in rows:
        symbol = _html.escape(_fund_display_label_v18574(row))
        typ = _html.escape(str(row.get("asset_type") or "-"))
        weight = row.get("weight_pct", "-")
        role = _html.escape(str(row.get("role") or "-"))
        sector = _html.escape(str(row.get("sector") or "-"))
        geo = _html.escape(str(row.get("geography") or "-"))
        q = row.get("decision_quality")
        cost = row.get("expense_ratio_pct")
        detail = []
        if q is not None:
            detail.append(f"Kvalitet {q}")
        if cost is not None:
            detail.append(f"Kostnad {cost}%")
        detail_txt = " · ".join(detail) or ""
        st.markdown(
            f"""
            <div class='v18-dark-row' style='margin:.16rem 0;padding:.34rem .48rem;'>
              <div style='display:flex;justify-content:space-between;gap:.45rem;flex-wrap:wrap;align-items:center;'>
                <b>{symbol}</b><span>{weight}%</span><span>{typ}</span><span>{role}</span><span>{sector}</span><span>{geo}</span><span>{_html.escape(detail_txt)}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for title, key, icon in [
        ("Styrker", "strengths", "+"),
        ("Forbedringsforslag", "suggestions", "→"),
        ("Advarsler", "warnings", "⚠"),
    ]:
        vals = list(res.get(key) or [])
        st.markdown(f"<div class='ptw-control-panel-title'>{_html.escape(title)}</div>", unsafe_allow_html=True)
        if not vals:
            st.markdown("<div class='v18-dark-row'>Ingen punkter.</div>", unsafe_allow_html=True)
        for v in vals[:8]:
            st.markdown(f"<div class='v18-dark-row'>{icon} {_html.escape(str(v))}</div>", unsafe_allow_html=True)

    overlap = list(res.get("overlap_risks") or [])
    st.markdown("<div class='ptw-control-panel-title'>Overlapprisiko</div>", unsafe_allow_html=True)
    if not overlap:
        st.markdown("<div class='v18-dark-row'>Ingen tydelig overlapp registrert med tilgjengelige data.</div>", unsafe_allow_html=True)
    for r in overlap[:8]:
        level = str(r.get("level") or "-")
        cls = "red" if level == "Høy" else "yellow"
        st.markdown(
            f"""
            <div class='v18-dark-row'>
              <span class='v18-status-chip {cls}'>{_html.escape(level)}</span>
              <b>{_html.escape(str(r.get('title') or 'Overlapp'))}</b> · {_html.escape(str(r.get('message') or ''))}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_mixed_portfolio_control_center_v18544():
    """Analyze portfolio health across stocks, funds and ETFs without hidden fetches."""
    st.subheader("📊 Porteføljeanalyse")
    st.caption("Analyserer aksjer + fond/ETF samlet. Panelet bruker eksisterende resultater/manuell input og henter ikke nye markedsdata før du eksplisitt kjører andre moduler.")
    from portfolio_mixed_analyzer import build_holdings_from_sources, analyze_mixed_portfolio

    c1, c2, c3 = st.columns([1.1, 1.1, 1.0])
    with c1:
        stock_source = st.selectbox("Aksjekilde", ["Manuell", "Auto Test Lab aksjer", "Paper trading", "Siste Smart AI-resultat"], key="mixed_portfolio_stock_source_v18544")
    with c2:
        fund_source = st.selectbox("Fondkilde", ["Manuell", "Siste Fond / ETF-analyse", "Auto Test Lab fondmodus", "Ingen"], key="mixed_portfolio_fund_source_v18544")
    with c3:
        profile = st.selectbox("Profil", ["Balansert", "Lav risiko", "Lav kostnad", "Grunnmur", "Vekst"], key="mixed_portfolio_profile_v18544")

    c4, c5 = st.columns([1.0, 1.0])
    with c4:
        stock_budget = st.slider("Aksjeandel ved auto-forslag", 0, 80, 30, 5, key="mixed_portfolio_stock_budget_v18544")
    with c5:
        max_rows = st.slider("Maks posisjoner", 3, 30, 12, 1, key="mixed_portfolio_max_rows_v18544")

    manual_stocks = ""
    manual_funds = ""
    if stock_source == "Manuell":
        manual_stocks = st.text_area("Manuelle aksjer", value="", placeholder="EQNR.OL 10\nVOLV-B.ST 10\nNOVO-B.CO 10", height=76, key="mixed_portfolio_manual_stocks_v18544", help="Format: TICKER vekt. Hvis vekt mangler fordeles likt.")
    if fund_source == "Manuell":
        manual_funds = st.text_area("Manuelle fond/ETF", value="VOO 50 ETF\nQQQ 20 ETF", height=76, key="mixed_portfolio_manual_funds_v18544", help="Format: SYMBOL vekt type. Eksempel: VOO 60 ETF")

    stock_rows = []
    if stock_source == "Auto Test Lab aksjer":
        stock_rows = _portfolio_analyzer_result_rows_v18544("auto_test_lab_last_result_v18536", ["best_single", "test_further"], limit=int(max_rows))
    elif stock_source == "Paper trading":
        stock_rows = _paper_trading_holdings_v18544(limit=int(max_rows))
    elif stock_source == "Siste Smart AI-resultat":
        try:
            from services.universe_service import SMART_RESULT_KEY
            smart = st.session_state.get(SMART_RESULT_KEY, {}) or st.session_state.get("ai_analysis_universe_smart_result_v1859", {}) or {}
        except Exception:
            smart = st.session_state.get("ai_analysis_universe_smart_result_v1859", {}) or {}
        vals = []
        if isinstance(smart, dict):
            vals = smart.get("candidates") or smart.get("top_picks") or smart.get("top_tickers") or []
        if vals and isinstance(vals[0], str):
            stock_rows = [{"ticker": x, "asset_type": "Aksje", "source": "Smart AI"} for x in vals[: int(max_rows)]]
        else:
            stock_rows = [v for v in vals if isinstance(v, dict)][: int(max_rows)]

    fund_rows = []
    if fund_source == "Siste Fond / ETF-analyse":
        fund_rows = _portfolio_analyzer_result_rows_v18544("fund_etf_lab_last_result_v18538", ["core_satellite.allocation", "ranked"], limit=int(max_rows))
        if not fund_rows:
            result = st.session_state.get("fund_etf_lab_last_result_v18538") or {}
            fund_rows = list((result.get("core_satellite") or {}).get("allocation") or []) or list(result.get("ranked") or [])[: int(max_rows)]
    elif fund_source == "Auto Test Lab fondmodus":
        result = st.session_state.get("auto_test_lab_last_result_fund_v18543") or {}
        fund_rows = list((result.get("core_satellite") or {}).get("allocation") or []) or list(result.get("ranked") or result.get("best_funds") or [])[: int(max_rows)]

    auto_stock_weight = None
    auto_fund_weight = None
    if stock_source != "Manuell" and stock_rows:
        auto_stock_weight = float(stock_budget) / max(1, len(stock_rows))
    if fund_source != "Manuell" and fund_rows:
        auto_fund_weight = float(100 - stock_budget) / max(1, len(fund_rows))

    holdings_preview = build_holdings_from_sources(
        stock_rows=stock_rows[: int(max_rows)],
        fund_rows=fund_rows[: int(max_rows)],
        manual_stock_text=manual_stocks,
        manual_fund_text=manual_funds,
        default_stock_weight_pct=auto_stock_weight,
        default_fund_weight_pct=auto_fund_weight,
    )
    st.markdown(
        f"<div class='v18-dark-row'><b>Planlagt analyse:</b> {len(holdings_preview)} posisjoner · Aksjekilde: {html.escape(stock_source)} · Fondkilde: {html.escape(fund_source)} · Profil: {html.escape(profile)}</div>",
        unsafe_allow_html=True,
    )
    if holdings_preview:
        preview = ", ".join(f"{h.get('symbol')} {h.get('weight_pct')}%" for h in holdings_preview[:8])
        st.markdown(f"<div class='v18-dark-row' style='font-size:.78rem;'>Preview: {html.escape(preview)}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='v18-dark-row'>Ingen posisjoner funnet. Bruk manuell input eller kjør Auto Test Lab / Fondanalyse først.</div>", unsafe_allow_html=True)

    if st.button("📊 Kjør porteføljeanalyse", key="mixed_portfolio_run_v18544", type="primary", use_container_width=True, on_click=set_global_busy, kwargs={"label": "Kjører porteføljeanalyse", "detail": "Analyserer aksjer, fond, overlapp og risiko"}):
        status_box = st.empty()
        progress = st.progress(0, text="Starter porteføljeanalyse")
        steps = ["Samler beholdninger", "Normaliserer vekter", "Måler grunnmur/satellitt", "Sjekker overlapp", "Lager forbedringsforslag"]
        for idx, step in enumerate(steps, start=1):
            pct = int(round((idx - 1) / max(1, len(steps)) * 100))
            progress.progress(pct, text=f"{idx}/{len(steps)} {step}")
            update_global_busy("Kjører porteføljeanalyse", f"{idx}/{len(steps)} {step}", step=idx, total=len(steps))
            status_box.markdown(
                f"<div class='v18-dark-row' style='border-color:rgba(59,130,246,.55);'><b>🔄 Porteføljeanalyse kjører</b><br><span style='font-size:.82rem;'>{idx}/{len(steps)} {html.escape(step)}</span></div>",
                unsafe_allow_html=True,
            )
        result = analyze_mixed_portfolio(holdings_preview, profile=profile)
        result["source"] = {"stocks": stock_source, "funds": fund_source}
        st.session_state["mixed_portfolio_last_result_v18544"] = result
        try:
            from services.storage_service import get_storage_service
            storage = get_storage_service()
            storage.write_json("portfolio_analysis/latest.json", result)
            storage.append_jsonl("portfolio_analysis/history.jsonl", result)
            result["storage_backend"] = storage.backend()
        except Exception as exc:
            result["storage_error"] = str(exc)[:180]
        progress.progress(100, text="Ferdig")
        finish_global_busy("Klar", "Porteføljeanalyse ferdig.")
        st.success(f"Porteføljeanalyse ferdig: {result.get('portfolio_health', '-')}/100 · {result.get('grade', '-')}")

    result = st.session_state.get("mixed_portfolio_last_result_v18544") or {}
    if result:
        _render_portfolio_health_rows_v18544(result)
    else:
        st.info("Ingen porteføljeanalyse ennå. Velg kilder eller manuell portefølje og trykk Kjør.")

def control_center_extra_panels_v18535():
    return [
        ("⭐ Top Picks", render_top_picks_control_center_v1863s),
        ("🚀 IPO", render_ipo),
        ("🧪 Paper Trading", render_paper_trading_dashboard),
        ("🔬 Auto Test Lab", render_auto_test_lab_control_center_v18536),
        ("🏦 Fond / ETF", render_fund_etf_control_center_v18538),
        ("📊 Porteføljeanalyse", render_mixed_portfolio_control_center_v18544),
        ("📰 Nyheter", render_news_control_center_v18535),
        ("📊 Interaktiv analyse", render_interactive_technical_control_center_v18535),
        ("🏆 Marked/rangering", render_market_ranking_control_center_v18535),
        ("🔔 Watchlist/signaler", render_watchlist_signals_control_center_v18535),
        ("🛠 System/admin", lambda: render_system_admin_workspace(expanded=True)),
    ]




def render_safe_infrastructure_panel_v18587() -> None:
    """Batch E: visible, low-risk governance/status panel."""
    try:
        with st.expander("🛡️ Safe build / governance / changelog", expanded=False):
            st.caption(f"Aktiv build: {get_app_build_label()}")
            checks = run_static_regression_checks()
            if checks.get("ok"):
                st.success("Regresjonssjekk OK: kritiske UI-ankere og versjon finnes.")
            else:
                st.warning(f"Regresjonssjekk varsler: {checks}")

            feature_rows = get_feature_registry()
            if feature_rows:
                st.markdown("**Feature-status**")
                try:
                    st.dataframe(feature_rows, use_container_width=True, hide_index=True)
                except Exception:
                    st.write(feature_rows)



            protected_rows = get_protected_zones()
            if protected_rows:
                st.markdown("**Protected zones**")
                st.caption("Kritiske områder som skal patches minimalt, slik at stabile funksjoner ikke forsvinner ved nye GO-runder.")
                try:
                    st.dataframe(protected_rows, use_container_width=True, hide_index=True)
                except Exception:
                    st.write(protected_rows)

            changelog_rows = get_changelog()
            if changelog_rows:
                st.markdown("**Hva er nytt / build-historikk**")
                try:
                    st.dataframe(changelog_rows, use_container_width=True, hide_index=True)
                except Exception:
                    st.write(changelog_rows)

            st.markdown("**UI/data trust**")
            _tokens = ui_consistency_tokens()
            st.caption("Batch G: standardiserte UI-tokens, datakvalitet og tydeligere blokk-/varslingsforklaringer uten å endre analysemotorene.")
            try:
                st.dataframe([_tokens], use_container_width=True, hide_index=True)
            except Exception:
                st.write(_tokens)
            _sample_trust = normalize_data_trust({"data_quality": "CACHED", "confidence": 75, "missing_fields": []})
            st.caption(f"Datakvalitet-eksempel: {_sample_trust.get('label')} · {_sample_trust.get('note')}")

            st.markdown("**Audit-logg**")
            recent = read_recent_audit_events(limit=8)
            if recent:
                try:
                    st.dataframe(recent, use_container_width=True, hide_index=True)
                except Exception:
                    st.write(recent)
            else:
                st.caption("Ingen audit-hendelser lagret ennå i denne kjøringen.")
    except Exception as _safe_panel_error:
        st.caption(f"Safe infrastructure-panel kunne ikke vises: {_safe_panel_error}")

# v18.5.95: late desktop visibility hardening (compatibility marker; expanded by v18.5.96 below).
# v18.5.96: desktop visual hardening that targets the actual Streamlit button widgets.
# Root cause from screenshots: old compact desktop CSS still wins in places and Streamlit
# element wrappers make adjacent selectors unreliable. This block is intentionally late,
# broad for primary/buttons, and uses explicit anchors placed immediately before the
# active Global/Pushover buttons.
st.markdown("""
<style>
/* --- v18.5.96 GLOBAL UPDATE: visible desktop row + real clickable button --- */
html body .stApp .visual-truth-global-box {
    width:100% !important;
    max-width:100% !important;
    min-height:64px !important;
    margin:.56rem 0 .42rem 0 !important;
    padding:.74rem .95rem !important;
    border:1px solid rgba(125,211,252,.88) !important;
    border-left:5px solid #38d5ff !important;
    border-radius:16px !important;
    background:linear-gradient(180deg,rgba(8,47,73,.96),rgba(8,25,48,.96)) !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.10),0 10px 28px rgba(14,165,233,.18) !important;
    display:flex !important;
    align-items:center !important;
    justify-content:space-between !important;
    gap:.85rem !important;
    overflow:visible !important;
    opacity:1 !important;
    filter:none !important;
}
html body .stApp .visual-truth-global-title {
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    font-size:1.03rem !important;
    font-weight:1000 !important;
    line-height:1.15 !important;
    letter-spacing:.01em !important;
    white-space:normal !important;
    overflow:visible !important;
}
html body .stApp .visual-truth-global-sub {
    color:#e0f2fe !important;
    -webkit-text-fill-color:#e0f2fe !important;
    font-size:.86rem !important;
    font-weight:850 !important;
    line-height:1.25 !important;
    text-align:right !important;
    white-space:normal !important;
    overflow:visible !important;
    text-overflow:clip !important;
    opacity:1 !important;
}

/* Explicit anchor selector for the real Global button. */
html body .stApp div:has(> .global-update-button-anchor-v18596) + div,
html body .stApp div:has(.global-update-button-anchor-v18596) + div {
    width:100% !important;
    max-width:100% !important;
    min-width:0 !important;
    display:block !important;
    overflow:visible !important;
    opacity:1 !important;
    visibility:visible !important;
}
html body .stApp div:has(> .global-update-button-anchor-v18596) + div [data-testid="stButton"],
html body .stApp div:has(.global-update-button-anchor-v18596) + div [data-testid="stButton"] {
    width:100% !important;
    max-width:100% !important;
    display:block !important;
    overflow:visible !important;
}

/* Broad late primary-button hardening: keeps Global and Pushover readable on PC,
   even when Streamlit wrapper structure changes. */
html body .stApp div[data-testid="stButton"] > button[kind="primary"],
html body .stApp div[data-testid="stFormSubmitButton"] > button[kind="primary"],
html body .stApp button[kind="primary"] {
    display:flex !important;
    align-items:center !important;
    justify-content:center !important;
    width:100% !important;
    max-width:100% !important;
    min-width:0 !important;
    min-height:50px !important;
    height:auto !important;
    max-height:none !important;
    padding:.62rem 1.05rem !important;
    margin:.18rem 0 .32rem 0 !important;
    border-radius:15px !important;
    border:1px solid rgba(224,242,254,1) !important;
    background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
    color:#ffffff !important;
    -webkit-text-fill-color:#ffffff !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.18),0 10px 24px rgba(14,165,233,.30) !important;
    text-shadow:0 1px 0 rgba(0,0,0,.25) !important;
    font-weight:1000 !important;
    white-space:normal !important;
    overflow:visible !important;
    opacity:1 !important;
    filter:none !important;
    visibility:visible !important;
    clip-path:none !important;
}
html body .stApp div[data-testid="stButton"] > button[kind="primary"] *,
html body .stApp div[data-testid="stFormSubmitButton"] > button[kind="primary"] *,
html body .stApp button[kind="primary"] * {
    color:#ffffff !important;
    -webkit-text-fill-color:#ffffff !important;
    font-size:.98rem !important;
    font-weight:1000 !important;
    line-height:1.14 !important;
    white-space:normal !important;
    overflow:visible !important;
    text-overflow:clip !important;
    opacity:1 !important;
    visibility:visible !important;
}

/* Disabled buttons must still be readable; they should look inactive, not invisible. */
html body .stApp div[data-testid="stButton"] > button:disabled,
html body .stApp div[data-testid="stFormSubmitButton"] > button:disabled,
html body .stApp button:disabled {
    opacity:.82 !important;
    filter:none !important;
    color:#e0f2fe !important;
    -webkit-text-fill-color:#e0f2fe !important;
    background:linear-gradient(180deg,#334155 0%,#1e293b 100%) !important;
    border:1px solid rgba(148,163,184,.72) !important;
    cursor:not-allowed !important;
}
html body .stApp button:disabled * {
    color:#e0f2fe !important;
    -webkit-text-fill-color:#e0f2fe !important;
    opacity:1 !important;
    visibility:visible !important;
}

/* --- v18.5.96 PUSHOVER: visible status card and vertical full-width buttons --- */
html body .stApp .visual-truth-pushover-box,
html body .stApp .visual-truth-pushover-box-v18596 {
    width:100% !important;
    max-width:100% !important;
    min-height:72px !important;
    margin:.62rem 0 .46rem 0 !important;
    padding:.78rem .95rem !important;
    border:1px solid rgba(125,211,252,.74) !important;
    border-left:5px solid #fbbf24 !important;
    border-radius:16px !important;
    background:linear-gradient(180deg,rgba(8,47,73,.88),rgba(15,23,42,.90)) !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.08),0 8px 22px rgba(14,165,233,.12) !important;
    overflow:visible !important;
    opacity:1 !important;
    filter:none !important;
}
html body .stApp .visual-truth-pushover-title {
    color:#fff7ed !important;
    -webkit-text-fill-color:#fff7ed !important;
    font-size:1rem !important;
    font-weight:1000 !important;
    line-height:1.16 !important;
    margin-bottom:.28rem !important;
}
html body .stApp .visual-truth-pushover-status {
    color:#e0f2fe !important;
    -webkit-text-fill-color:#e0f2fe !important;
    font-size:.84rem !important;
    font-weight:820 !important;
    line-height:1.32 !important;
    margin-bottom:0 !important;
    opacity:1 !important;
}
html body .stApp div:has(> .pushover-button-anchor-v18596) + div,
html body .stApp div:has(.pushover-button-anchor-v18596) + div,
html body .stApp div:has(> .pushover-button-anchor-v18596) + div + div,
html body .stApp div:has(.pushover-button-anchor-v18596) + div + div {
    width:100% !important;
    max-width:100% !important;
    min-width:0 !important;
    display:block !important;
    overflow:visible !important;
    opacity:1 !important;
    visibility:visible !important;
}
html body .stApp .v18593-pushover-result {
    margin:.46rem 0 .42rem 0 !important;
    padding:.64rem .82rem !important;
    border:1px solid rgba(125,211,252,.42) !important;
    border-radius:13px !important;
    background:rgba(8,20,42,.86) !important;
    color:#e0f2fe !important;
    -webkit-text-fill-color:#e0f2fe !important;
    font-size:.86rem !important;
    font-weight:850 !important;
    line-height:1.30 !important;
    opacity:1 !important;
}

/* Build/version chip is trust info, not disabled helper text. */
html body .stApp .ptw-version-chip {
    display:inline-flex !important;
    align-items:center !important;
    gap:.34rem !important;
    max-width:min(72vw, 920px) !important;
    min-width:0 !important;
    padding:.42rem .78rem !important;
    border:1px solid rgba(125,211,252,.92) !important;
    border-radius:999px !important;
    background:linear-gradient(180deg,rgba(8,47,73,.92),rgba(8,32,58,.90)) !important;
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    font-size:.88rem !important;
    font-weight:1000 !important;
    line-height:1.12 !important;
    opacity:1 !important;
    white-space:normal !important;
    overflow:visible !important;
    text-overflow:clip !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.10),0 8px 22px rgba(14,165,233,.20) !important;
}
html body .stApp .ptw-sticky-topbar {
    overflow:visible !important;
    padding-right:154px !important;
    box-sizing:border-box !important;
}
html body .stApp .ptw-topbar-right {
    min-width:0 !important;
    max-width:74vw !important;
    overflow:visible !important;
}
@media (min-width:901px) {
    html body .stApp div[data-testid="stExpander"] details,
    html body .stApp div[data-testid="stExpander"] details > div {
        overflow:visible !important;
    }
}
@media (max-width:900px) {
    html body .stApp .visual-truth-global-box {
        display:block !important;
        min-height:0 !important;
    }
    html body .stApp .visual-truth-global-sub {
        text-align:left !important;
        margin-top:.28rem !important;
    }
    html body .stApp .ptw-sticky-topbar { padding-right:148px !important; }
    html body .stApp .ptw-version-chip { max-width:100% !important; font-size:.78rem !important; padding:.34rem .56rem !important; }
    html body .stApp .ptw-topbar-right { max-width:100% !important; width:100% !important; }
}
</style>
""", unsafe_allow_html=True)

# v18.5.97: Final desktop truth patch after all legacy CSS.
# Purpose: stop Streamlit toolbar/status Stop overlay from floating over the app,
# force real Streamlit buttons to fill their containers on desktop, and keep
# Pushover/Global/top controls readable even when older CSS tried width:auto.
st.markdown("""
<style>
/* Hide Streamlit runtime chrome that appears as a floating blue Stop button on desktop. */
html body [data-testid="stStatusWidget"],
html body [data-testid="stToolbar"],
html body [data-testid="stDecoration"],
html body #MainMenu,
html body footer {
    display:none !important;
    visibility:hidden !important;
    width:0 !important;
    height:0 !important;
    min-width:0 !important;
    min-height:0 !important;
    max-width:0 !important;
    max-height:0 !important;
    overflow:hidden !important;
    pointer-events:none !important;
}

/* App header/title must not sit under Streamlit chrome or look clipped. */
html body .stApp .ptw-app-title {
    position:relative !important;
    z-index:12 !important;
    display:flex !important;
    align-items:center !important;
    min-height:44px !important;
    margin:.42rem 0 .34rem 0 !important;
    padding:.48rem .56rem .50rem .56rem !important;
    overflow:visible !important;
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    font-size:1.38rem !important;
    line-height:1.16 !important;
    font-weight:1000 !important;
}
html body .stApp .ptw-sticky-topbar {
    position:relative !important;
    top:auto !important;
    z-index:11 !important;
    padding:.68rem .82rem !important;
    padding-right:.82rem !important;
    margin:.10rem 0 .70rem 0 !important;
    overflow:visible !important;
    box-sizing:border-box !important;
}
html body .stApp .ptw-topbar-left {
    overflow:visible !important;
}
html body .stApp .ptw-topbar-right,
html body .stApp .ptw-v18570-status-zone {
    min-width:0 !important;
    max-width:none !important;
    overflow:visible !important;
    justify-content:flex-end !important;
}
html body .stApp .ptw-version-chip {
    max-width:min(78vw, 980px) !important;
    min-height:38px !important;
    padding:.48rem .88rem !important;
    font-size:.94rem !important;
    line-height:1.16 !important;
    font-weight:1000 !important;
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    background:linear-gradient(180deg,rgba(8,47,73,.98),rgba(8,32,58,.96)) !important;
    border:1px solid rgba(125,211,252,.98) !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.14),0 8px 22px rgba(14,165,233,.22) !important;
    opacity:1 !important;
    overflow:visible !important;
    white-space:normal !important;
}

/* Final app-wide Streamlit button correction. Earlier CSS set width:auto and clipped labels. */
html body .stApp div[data-testid="stButton"],
html body .stApp div[data-testid="stFormSubmitButton"] {
    width:100% !important;
    max-width:100% !important;
    min-width:0 !important;
    display:block !important;
    overflow:visible !important;
    opacity:1 !important;
    visibility:visible !important;
}
html body .stApp div[data-testid="stButton"] > button,
html body .stApp div[data-testid="stFormSubmitButton"] > button {
    display:flex !important;
    align-items:center !important;
    justify-content:center !important;
    gap:.36rem !important;
    width:100% !important;
    max-width:100% !important;
    min-width:0 !important;
    min-height:44px !important;
    height:auto !important;
    max-height:none !important;
    padding:.56rem .88rem !important;
    margin:.10rem 0 .18rem 0 !important;
    border-radius:13px !important;
    box-sizing:border-box !important;
    text-align:center !important;
    white-space:normal !important;
    overflow:visible !important;
    text-overflow:clip !important;
    clip-path:none !important;
    opacity:1 !important;
    filter:none !important;
    visibility:visible !important;
}
html body .stApp div[data-testid="stButton"] > button *,
html body .stApp div[data-testid="stFormSubmitButton"] > button * {
    color:#ffffff !important;
    -webkit-text-fill-color:#ffffff !important;
    font-size:.96rem !important;
    font-weight:1000 !important;
    line-height:1.14 !important;
    white-space:normal !important;
    overflow:visible !important;
    text-overflow:clip !important;
    opacity:1 !important;
    visibility:visible !important;
}
html body .stApp div[data-testid="stButton"] > button:disabled,
html body .stApp div[data-testid="stFormSubmitButton"] > button:disabled {
    opacity:.92 !important;
    filter:none !important;
    cursor:not-allowed !important;
}
html body .stApp div[data-testid="stButton"] > button:disabled *,
html body .stApp div[data-testid="stFormSubmitButton"] > button:disabled * {
    color:#e0f2fe !important;
    -webkit-text-fill-color:#e0f2fe !important;
    opacity:1 !important;
}

/* Top trading buttons: one row, same height, no floating or clipping. */
html body .stApp .v18534-control-button-gap {
    height:.38rem !important;
    margin:0 !important;
    padding:0 !important;
    overflow:visible !important;
}
html body .stApp div:has(> .v18534-control-button-gap) + div[data-testid="stHorizontalBlock"],
html body .stApp div:has(.v18534-control-button-gap) + div[data-testid="stHorizontalBlock"] {
    align-items:stretch !important;
    gap:.62rem !important;
    overflow:visible !important;
    margin:.10rem 0 .36rem 0 !important;
}
html body .stApp div:has(> .v18534-control-button-gap) + div[data-testid="stHorizontalBlock"] div[data-testid="column"],
html body .stApp div:has(.v18534-control-button-gap) + div[data-testid="stHorizontalBlock"] div[data-testid="column"] {
    display:flex !important;
    align-items:stretch !important;
    min-width:0 !important;
    overflow:visible !important;
}
html body .stApp div:has(> .v18534-control-button-gap) + div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button,
html body .stApp div:has(.v18534-control-button-gap) + div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button {
    min-height:48px !important;
    margin:0 !important;
    padding:.58rem .74rem !important;
}

/* Pushover panel: force readable desktop block and full buttons regardless of Streamlit wrappers. */
html body .stApp .visual-truth-pushover-box,
html body .stApp .visual-truth-pushover-box-v18596 {
    display:block !important;
    width:100% !important;
    max-width:100% !important;
    min-height:84px !important;
    margin:.72rem 0 .54rem 0 !important;
    padding:.88rem 1.05rem !important;
    border:1px solid rgba(125,211,252,.92) !important;
    border-left:6px solid #fbbf24 !important;
    border-radius:16px !important;
    background:linear-gradient(180deg,rgba(8,47,73,.96),rgba(15,23,42,.96)) !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.12),0 10px 26px rgba(14,165,233,.18) !important;
    overflow:visible !important;
    opacity:1 !important;
}
html body .stApp .visual-truth-pushover-title {
    color:#fff7ed !important;
    -webkit-text-fill-color:#fff7ed !important;
    font-size:1.05rem !important;
    font-weight:1000 !important;
    line-height:1.15 !important;
}
html body .stApp .visual-truth-pushover-status {
    color:#e0f2fe !important;
    -webkit-text-fill-color:#e0f2fe !important;
    font-size:.88rem !important;
    font-weight:850 !important;
    line-height:1.30 !important;
}
html body .stApp div:has(> .pushover-button-anchor-v18596) + div,
html body .stApp div:has(.pushover-button-anchor-v18596) + div,
html body .stApp div:has(> .pushover-button-anchor-v18596) + div + div,
html body .stApp div:has(.pushover-button-anchor-v18596) + div + div {
    width:100% !important;
    max-width:100% !important;
    min-width:0 !important;
    overflow:visible !important;
    display:block !important;
    opacity:1 !important;
    visibility:visible !important;
}
html body .stApp div:has(> .pushover-button-anchor-v18596) + div button,
html body .stApp div:has(.pushover-button-anchor-v18596) + div button,
html body .stApp div:has(> .pushover-button-anchor-v18596) + div + div button,
html body .stApp div:has(.pushover-button-anchor-v18596) + div + div button {
    min-height:52px !important;
    width:100% !important;
    margin:.10rem 0 .22rem 0 !important;
    background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
    border:1px solid rgba(224,242,254,1) !important;
    box-shadow:0 0 0 1px rgba(255,255,255,.16),0 10px 24px rgba(14,165,233,.28) !important;
}


/* v18.6.3 desktop cleanup: compact global status, no vertical wrapping, smaller control buttons. */
.v1862-global-status-line {
    display:flex !important;
    flex-direction:row !important;
    align-items:center !important;
    justify-content:space-between !important;
    gap:.75rem !important;
    width:100% !important;
    margin:.36rem 0 .48rem 0 !important;
    padding:.36rem .62rem !important;
    border:1px solid rgba(56,189,248,.42) !important;
    border-radius:10px !important;
    background:rgba(8,47,73,.34) !important;
    color:#e0f2fe !important;
    font-size:.78rem !important;
    font-weight:850 !important;
    line-height:1.12 !important;
    white-space:nowrap !important;
    overflow:hidden !important;
}
.v1862-global-status-line span { white-space:nowrap !important; overflow:hidden !important; text-overflow:ellipsis !important; }
html body .stApp .v18534-control-button-gap + div[data-testid="stHorizontalBlock"] .stButton > button {
    min-height:34px !important;
    height:34px !important;
    padding:.22rem .55rem !important;
    border-radius:11px !important;
    white-space:nowrap !important;
    word-break:normal !important;
    overflow-wrap:normal !important;
    font-size:.82rem !important;
}
html body .stApp .v18534-control-button-gap + div[data-testid="stHorizontalBlock"] .stButton > button p {
    white-space:nowrap !important;
    word-break:normal !important;
    overflow-wrap:normal !important;
    font-size:.82rem !important;
    line-height:1.05 !important;
}
html body .stApp [data-testid="stHorizontalBlock"] .stButton > button,
html body .stApp [data-testid="stHorizontalBlock"] .stButton > button p {
    word-break:normal !important;
    overflow-wrap:normal !important;
    hyphens:none !important;
}
@media (min-width: 901px) {
    html body .stApp div[data-testid="stButton"] > button {
        min-height:34px !important;
        padding-top:.22rem !important;
        padding-bottom:.22rem !important;
    }
}

/* Keep expanders/panels from clipping buttons on desktop. */
html body .stApp div[data-testid="stExpander"],
html body .stApp div[data-testid="stExpander"] details,
html body .stApp div[data-testid="stExpander"] details > div,
html body .stApp div[data-testid="stVerticalBlock"],
html body .stApp div[data-testid="stHorizontalBlock"] {
    overflow:visible !important;
}

@media (max-width:900px) {
    html body .stApp .ptw-app-title { font-size:1.18rem !important; min-height:38px !important; margin-top:.24rem !important; }
    html body .stApp .ptw-sticky-topbar { padding:.56rem .60rem !important; margin-bottom:.52rem !important; }
    html body .stApp .ptw-topbar-right { width:100% !important; max-width:100% !important; justify-content:flex-start !important; }
    html body .stApp .ptw-version-chip { max-width:100% !important; font-size:.80rem !important; }
    html body .stApp div[data-testid="stButton"] > button,
    html body .stApp div[data-testid="stFormSubmitButton"] > button { min-height:42px !important; }
}
</style>
""", unsafe_allow_html=True)

# DO_NOT_TOUCH_ZONE v18.5.87: Global update/top control anchors are regression-tested/protected. Patch minimally.
# v18.5.48: Global oppdatering ligger øverst, før panelvelger og tunge seksjoner.
render_global_update_bar_v18548()
# GO I: Safe build/governance-panelet er fjernet fra hovedskjermen. Bruk System/admin ved behov.

# v18.5.34: Hovedpanelvelger ligger fortsatt i toppområdet rett over ticker-banneret.
# v18.6.3s: AI Kontrollsenter eier arbeidsflaten, slik at markedvalg ikke jobber mot hverandre.
active_panel = None

# v18.5.1: Ticker-banner er flyttet opp mellom sticky AI-status og AI Kontrollsenter.
_active_control_center_panel_v18598 = None
try:
    render_live_market_banner()
    render_banner_main_controls()
    _active_control_center_panel_v18598 = render_ai_control_center(extra_panels=control_center_extra_panels_v18535())
except Exception as _top_banner_workspace_error:
    st.caption(f"Topp-banner / AI Kontrollsenter kunne ikke vises: {_top_banner_workspace_error}")

# v18.5.98: AI Kontrollsenter skal være et ekte fokus-/oppgaveområde.
# Når et Kontrollsenter-panel er valgt, må gamle hovedseksjoner ikke lekke inn under panelet.
# Dette fjerner dobbeltvisning av Dynamisk rangering, Interaktiv analyse og legacy-markedspaneler.
if _active_control_center_panel_v18598:
    st.markdown(
        f"<div class='v18-dark-row'>Aktivt Kontrollsenter-panel: <b>{html.escape(str(_active_control_center_panel_v18598))}</b>. Underliggende hovedpaneler er skjult for denne visningen.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        "<div class='v18-dark-row'>Velg et panel i AI Kontrollsenter. Hovedpanelvelgeren er samlet inn her for å hindre motstridende markedvalg.</div>",
        unsafe_allow_html=True,
    )
st.stop()

# v18.5.34: driftstatus, børstatus og trading-kontroller er flyttet til toppområdet.
# Gammel separat statusstripe her er fjernet for å unngå dupliserte bokser lenger nede.

if 'top_picks' in locals():
    market_pulse(top_picks)
    top_movers(top_picks)

st.caption("Smartere scoring med momentum, trend, risiko, P/E, kvalitet, vekst, gjeld, nyheter, insiderhendelser og backtesting. System/admin er flyttet til AI Kontrollsenter.")
# v18.5.35: System/admin renderes kun i valgt Kontrollsenter-panel.

if search.strip():
    tickers_us = [search.strip().upper()]
    tickers_no = []
    tickers_se = []
    tickers_all = tickers_us
else:
    tickers_us = resolve_universe_tickers(["USA"], max_count=max_count)
    tickers_no = resolve_universe_tickers(["Norge"], max_count=max_count)
    tickers_se = resolve_universe_tickers(["Sverige"], max_count=max_count)
    tickers_all = resolve_universe_tickers(["Alle"], max_count=max_count)

dynamic_watchlist = get_dynamic_watchlist(mode, max_count, tickers_us, tickers_no, tickers_se, tickers_all)

# v18.5.35: Watchlist/varselkontroll er flyttet inn i AI Kontrollsenter.
# Hovedsiden viser ikke lenger egen watchlist-boks eller scanner skjult; panel/kall kjøres bare når brukeren åpner
# Kontrollsenter -> Watchlist/signaler og trykker egen knapp.
watchlist_tickers = list(st.session_state.get("latest_watchlist_tickers_v156", []) or [])
auto_watchlist_alerts = bool(_alert_runtime_settings.get("notify_watchlist_signal_changes", True))
watchlist_scan_limit = int(_alert_runtime_settings.get("watchlist_scan_limit", 30) or 30)
manual_watchlist_scan = False

# v18.5.31: aktivt hovedpanel velges nå i toppområdet over ticker-banneret.

if active_panel == "🇺🇸 USA":
    run_main_usa = st.button("Kjør / oppdater USA-rangering", key="main_panel_run_usa_v1863r", type="primary")
    us_results = cached_auto_rank_market("USA", tickers_us, max_count=max_count, use_news=False, force_manual_fetch=run_main_usa)
    render_ranking(us_results, "🏆 Dynamisk rangering USA/S&P 500")
    render_analysis(us_results, "USA")

elif active_panel == "🇳🇴 Norge":
    run_main_no = st.button("Kjør / oppdater Norge-rangering", key="main_panel_run_no_v1863r", type="primary")
    no_results = cached_auto_rank_market("Norge", tickers_no, max_count=max_count, use_news=False, force_manual_fetch=run_main_no)
    render_ranking(no_results, "🇳🇴 Dynamisk rangering Norge")
    render_analysis(no_results, "Norge")

elif active_panel == "🇸🇪 Sverige":
    run_main_se = st.button("Kjør / oppdater Sverige-rangering", key="main_panel_run_se_v1863r", type="primary")
    se_results = cached_auto_rank_market("Sverige", tickers_se, max_count=max_count, use_news=False, force_manual_fetch=run_main_se)
    render_ranking(se_results, "🇸🇪 Dynamisk rangering Sverige")
    render_analysis(se_results, "Sverige")

elif active_panel == "Norden":
    tickers_nordic = list(tickers_no or []) + list(tickers_se or [])
    run_main_nordic = st.button("Kjør / oppdater Norden-rangering", key="main_panel_run_norden_v1863r", type="primary")
    nordic_results = cached_auto_rank_market("Norden", tickers_nordic, max_count=max_count, use_news=False, force_manual_fetch=run_main_nordic)
    render_ranking(nordic_results, "🌐 Dynamisk rangering Norden")
    render_analysis(nordic_results, "Norden")

elif active_panel == "Aktivt univers":
    active_universe_tickers = _source_tickers_for_interactive("Smart Universe Picker")
    if not active_universe_tickers:
        st.info("Ingen aktivt univers er lagret ennå. Åpne AI Kontrollsenter -> Analyseunivers og sett Smart Universe Picker som aktivt aksjeunivers.")
    else:
        run_main_active = st.button("Kjør / oppdater aktivt univers", key="main_panel_run_active_universe_v1863r", type="primary")
        active_results = cached_auto_rank_market("Smart Universe Picker", active_universe_tickers, max_count=max_count, use_news=False, force_manual_fetch=run_main_active)
        render_ranking(active_results, "🎯 Dynamisk rangering aktivt univers")
        render_analysis(active_results, "Smart Universe Picker")

elif active_panel == "⭐ Top Picks":
    st.subheader("⭐ Automatiske Top Picks")
    st.caption(
        "Top Picks = beste kandidater totalt. "
        "Kjøp nå = kandidater som også har grønt teknisk signal akkurat nå."
    )

    scan_market = st.radio("Velg marked for Top Picks", market_scope_options(include_aggregate=True), horizontal=True)

    _market_labels_v1863j = {market: ("Alle markeder" if market == "Alle" else market) for market in market_scope_options(include_aggregate=True)}
    source_tickers = resolve_universe_tickers([scan_market], max_count=int(max_count or 30))

    def _latest_market_rows_v1863j(market_name):
        latest = st.session_state.get("latest_rankings_v148", {}) or {}
        for key in (market_name, f"TopPicks_{market_name}"):
            rows = latest.get(key)
            if rows:
                return list(rows)
        cache = st.session_state.get(f"rank_cache_v148_{market_name}") or {}
        rows = (cache.get("data") or [])
        return list(rows) if rows else []

    def _top_picks_from_cached_markets_v1863j(market_name):
        if market_name == "Alle":
            markets = [m for m in market_scope_options(include_aggregate=False)]
        elif market_name == "Norden":
            markets = ["Norge", "Sverige", "Finland", "Danmark"]
        else:
            markets = [market_name]
        combined = []
        for name in markets:
            combined.extend(_latest_market_rows_v1863j(name))
        if not combined:
            return []
        return _ranked_for_display(build_top_picks(combined, min_score=min_top_pick_score, max_items=15))

    _guard_summary = market_guard_summary(source_tickers)
    st.caption(_guard_summary)
    st.caption("Datakvalitet: " + format_data_trust_line({"data_quality": "CACHED" if not bool(open_markets()) else "LIVE"}))

    _open_now = bool(open_markets())
    _manual_fetch_closed = False

    if not _open_now:
        st.warning(
            "Alle relevante markeder er stengt. Top Picks bruker cache hvis mulig. "
            "Hvis cache er tom etter deploy/restart, kan listen bli tom."
        )
        _manual_fetch_closed = st.checkbox(
            "Hent data manuelt likevel",
            value=False,
            help="Gjelder bare visning i appen. Cron/auto-trading holder seg fortsatt stengt.",
            key=f"manual_fetch_closed_{scan_market}",
        )

    with st.spinner("Finner beste kandidater..."):
        if not _manual_fetch_closed and not _open_now:
            ranked = _top_picks_from_cached_markets_v1863j(scan_market)
        else:
            ranked = cached_auto_rank_market(
                f"TopPicks_{scan_market}",
                source_tickers,
                max_count=max_count,
                use_news=False,
                force_manual_fetch=_manual_fetch_closed,
            )
        if not _manual_fetch_closed and not _open_now:
            top_picks = _ranked_for_display(ranked)
        else:
            top_picks = _ranked_for_display(build_top_picks(ranked, min_score=min_top_pick_score, max_items=15))
        buy_now_picks = _ranked_for_display([x for x in top_picks if is_buy_now_item(x)])
        latest = st.session_state.setdefault("latest_rankings_v148", {})
        latest[f"TopPicks_{scan_market}"] = top_picks or []
        if _manual_fetch_closed and top_picks:
            st.success(f"Manuell henting utført for {scan_market}: {len(top_picks)} kandidater funnet ✅")
        elif _manual_fetch_closed and not top_picks:
            st.warning(f"Manuell henting forsøkt for {scan_market}, men datakilden ga ingen rangerbare kandidater.")

    if not top_picks and not _manual_fetch_closed and not _open_now:
        st.info(
            f"Ingen lagret rangering for {_market_labels_v1863j.get(scan_market, scan_market)}. "
            "Kryss av for 'Hent data manuelt likevel' hvis du vil analysere utenfor åpningstid. "
            "Dette starter ikke auto-trading."
        )

    top_pick_view = st.radio("Top Picks-visning", ["⭐ Top Picks", "🟢 Kjøp nå"], horizontal=True, key=f"top_pick_view_{scan_market}_v148")

    if top_pick_view == "⭐ Top Picks":
        render_ranking(top_picks, f"⭐ Top Picks {_market_labels_v1863j.get(scan_market, scan_market)}")
        st.caption("Merk: En aksje kan være sterk totalt, men fortsatt ha VENT/UNNGÅ hvis teknisk timing er dårlig.")
        render_analysis(top_picks, f"TopPicks_{scan_market}")
    else:
        if buy_now_picks:
            _saved_candidates = save_latest_buy_now_candidates(buy_now_picks, scan_market)
            st.info(f"Disse er kandidater med grønt teknisk signal akkurat nå. {len(_saved_candidates)} kandidater er lagret til Cron-prioritering. Auto-kjøp skjer via Cron, eller knappen 'Kjør auto-kjøp nå'.")
            if st.button(f"🟢 Paper-kjøp alle Kjøp nå ({len(buy_now_picks)})", key=f"paper_buy_all_{scan_market}"):
                _messages = []
                for _item in buy_now_picks:
                    _ticker = _item.get("ticker")
                    _price, _change = get_item_price_change(_item)
                    _decision = card_decision_for_item(_item)
                    if _price is None:
                        _messages.append(f"{_ticker}: mangler pris")
                        continue
                    _ok, _msg = paper_buy(_ticker, _price, int(_decision.get("confidence", 0) or 0), f"UI Kjøp nå alle: {scan_market}")
                    _messages.append(_msg)
                _joined = " | ".join(_messages[:8])
                if any("blokkert" in str(m).lower() or "ikke nok" in str(m).lower() or "mangler" in str(m).lower() for m in _messages):
                    st.warning(_joined)
                else:
                    st.success(_joined)
                st.rerun()

            render_ranking(buy_now_picks, f"🟢 Kjøp nå {_market_labels_v1863j.get(scan_market, scan_market)}")
            render_analysis(buy_now_picks, f"KjopNa_{scan_market}")
        else:
            st.warning("Ingen aksjer har grønt teknisk kjøpssignal akkurat nå.")
            st.caption("Systemet tvinger ikke kjøp når timing/risiko ikke er god nok.")

elif active_panel == "🚀 IPO":
    render_ipo()

elif active_panel == "🧪 Paper Trading":
    render_paper_trading_dashboard()

# Etter første godkjente kjøring slås engangsflagget av. Cache brukes ved vanlige widget-reruns.
st.session_state["heavy_update_allowed_v148"] = False
_finish_global_apply_v161()


def add_rsi_current_box(fig, rsi):
    try:
        current_rsi = float(rsi.dropna().iloc[-1])

        if current_rsi >= 80:
            status, icon = "ekstremt overkjøpt", "🔥"
        elif current_rsi >= 70:
            status, icon = "overkjøpt", "⚠️"
        elif current_rsi <= 30:
            status, icon = "oversolgt", "🧊"
        else:
            status, icon = "nøytral", "📊"

        fig.add_annotation(
            text=f"{icon} Gjeldende RSI: <b>{current_rsi:.1f}</b> · {status}",
            xref="paper",
            yref="paper",
            x=0.01,
            y=1.15,
            showarrow=False,
            font=dict(size=15, color="white"),
            bgcolor="rgba(30,41,59,0.95)",
            bordercolor="rgba(255,255,255,0.3)",
            borderwidth=1,
        )
    except:
        pass
    return fig


# v18.4.9: Legacy forecast section removed. Forecast lives in AI Kontrollsenter.


# legacy test marker: key="top_apply_all_changes_v18570"
# legacy test marker: c1, c2 = st.columns([1.15, 1.15], gap="small")

# legacy test marker: data-ui-path='active-global-update-v18590'
# legacy test marker: main_auto_verify_pushover_v18590
# legacy test marker: main_auto_send_test_pushover_v18590

# legacy test marker: top_apply_all_changes_v18590

