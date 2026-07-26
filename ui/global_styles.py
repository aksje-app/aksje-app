"""Global Streamlit style layers extracted from app.py in v19.5.0.

The functions preserve the original injection order. This module contains no
business, strategy, trading, portfolio or risk logic.
"""
from __future__ import annotations

import logging

import streamlit as st

from ui_trust import ui_consistency_tokens

def _inject_global_compact_ui_v18665():
    st.markdown("""
    <style>
[data-testid="stSidebarNav"] { display:none !important; }
    /* v18.6.65 GLOBAL COMPACT UI
       Målet er å redusere svært brede tall-/parameterfelt i hele appen uten å endre motorlogikk. */
    :root {
        --compact-num-w: 170px;
        --compact-text-w: 360px;
        --compact-select-w: 420px;
        --compact-slider-w: 520px;
        --compact-btn-h: 34px;
    }

    /* Tallfelt: prosent, grenser, antall, dager, beløp osv. */
    div[data-testid="stNumberInput"] {
        max-width: var(--compact-num-w) !important;
        min-width: 96px !important;
    }
    div[data-testid="stNumberInput"] input {
        min-height: 34px !important;
        height: 34px !important;
        padding: 0.28rem 0.55rem !important;
        text-align: center !important;
        font-size: 0.92rem !important;
    }
    div[data-testid="stNumberInput"] button {
        min-height: 34px !important;
        height: 34px !important;
        width: 30px !important;
        padding: 0 !important;
    }

    /* Vanlige tekstfelt: ticker, ISIN, korte navn. Ikke textarea/logg. */
    div[data-testid="stTextInput"] {
        max-width: var(--compact-text-w) !important;
    }
    div[data-testid="stTextInput"] input {
        min-height: 34px !important;
        height: 34px !important;
        padding: 0.28rem 0.62rem !important;
        font-size: 0.92rem !important;
    }

    /* Selectbokser: behold mer plass enn tallfelt, men ikke full skjermbredde. */
    div[data-testid="stSelectbox"] {
        max-width: var(--compact-select-w) !important;
    }
    div[data-baseweb="select"] > div {
        min-height: 34px !important;
        height: 34px !important;
        font-size: 0.92rem !important;
    }

    /* Slidere og radio/checkbox får mindre høyde og bedre avstand. */
    div[data-testid="stSlider"] {
        max-width: var(--compact-slider-w) !important;
        padding-top: 0.1rem !important;
        padding-bottom: 0.1rem !important;
    }
    div[data-testid="stCheckbox"] label,
    div[data-testid="stRadio"] label {
        min-height: 26px !important;
        font-size: 0.90rem !important;
    }

    /* Knapper mer kompakte globalt, men fortsatt trykkbare på mobil. */
    .stButton > button {
        min-height: var(--compact-btn-h) !important;
        padding: 0.36rem 0.72rem !important;
        font-size: 0.90rem !important;
        line-height: 1.1 !important;
    }

    /* Metrics/kort litt lavere. */
    div[data-testid="stMetric"] {
        padding: 0.55rem 0.70rem !important;
        min-height: 58px !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.22rem !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
    }

    /* Expander og avsnitt mindre luft. */
    div[data-testid="stExpander"] details > summary {
        min-height: 34px !important;
        padding-top: 0.28rem !important;
        padding-bottom: 0.28rem !important;
    }

    /* Hjelpetekster/labels får mindre vertikal footprint. */
    label, .stCaption, div[data-testid="stMarkdownContainer"] p {
        line-height: 1.25 !important;
    }

    /* Unntak: DataFrames, tekstområder og brede rapport-/loggflater skal fortsatt være brede. */
    div[data-testid="stDataFrame"],
    div[data-testid="stTextArea"],
    div[data-testid="stTextArea"] textarea {
        max-width: none !important;
    }

    /* Mobil: bruk full bredde igjen slik at små felt ikke blir for trange. */
    @media (max-width: 760px) {
        div[data-testid="stNumberInput"],
        div[data-testid="stTextInput"],
        div[data-testid="stSelectbox"],
        div[data-testid="stSlider"] {
            max-width: 100% !important;
            width: 100% !important;
        }
        .stButton > button {
            min-height: 40px !important;
            font-size: 0.95rem !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)


def _inject_information_density_ui_v18667():
    st.markdown("""
    <style>
    /* v18.6.67 INFORMATION DENSITY REFACTOR
       Gjor ikke motorendringer. Reduserer visuell vekt, padding og tomme bokser globalt. */
    :root {
        --density-card-pad-y: .42rem;
        --density-card-pad-x: .58rem;
        --density-border: rgba(148,163,184,.28);
        --density-bg: rgba(15,23,42,.62);
    }

    /* Strammere hovedcontainer og vertikal avstand mellom elementer. */
    div[data-testid="stVerticalBlock"] { gap: .42rem !important; }
    div[data-testid="stHorizontalBlock"] { gap: .52rem !important; }
    div[data-testid="stMarkdownContainer"] p { margin-bottom: .22rem !important; }
    div[data-testid="stMarkdownContainer"] h1,
    div[data-testid="stMarkdownContainer"] h2,
    div[data-testid="stMarkdownContainer"] h3,
    div[data-testid="stMarkdownContainer"] h4 { margin-top: .22rem !important; margin-bottom: .28rem !important; }
    hr { margin: .42rem 0 !important; }

    /* Streamlit alert/statusbokser skal ikke ta full adminpanel-hoyde. */
    div[data-testid="stAlert"] { padding: .38rem .58rem !important; min-height: 0 !important; }
    div[data-testid="stAlert"] p { margin: 0 !important; line-height: 1.22 !important; }

    /* Expander-rader blir mer som kompakte seksjonslinjer. */
    div[data-testid="stExpander"] details {
        margin: .24rem 0 !important;
        border-radius: 13px !important;
    }
    div[data-testid="stExpander"] details > summary {
        min-height: 30px !important;
        padding: .24rem .54rem !important;
        font-size: .88rem !important;
    }
    div[data-testid="stExpander"] details > div {
        padding: .40rem .55rem .48rem .55rem !important;
    }

    /* Metrics og kort: mindre boks, mer tallinformasjon per skjerm. */
    div[data-testid="stMetric"] {
        min-height: 44px !important;
        padding: .35rem .48rem !important;
        border-radius: 10px !important;
    }
    div[data-testid="stMetricValue"] { font-size: 1.02rem !important; line-height: 1.0 !important; }
    div[data-testid="stMetricLabel"] { font-size: .68rem !important; line-height: 1.05 !important; }

    /* Generelle data-/statuskort brukt rundt i appen. */
    .compact-stat-grid { gap: .35rem !important; margin: .20rem 0 .35rem 0 !important; }
    .compact-stat-card,
    .info-mini-card,
    .rsi-box,
    .macd-explain-box,
    .visual-truth-empty-state,
    .visual-truth-pushover-box,
    .data-trust-card {
        padding: var(--density-card-pad-y) var(--density-card-pad-x) !important;
        min-height: 0 !important;
        border-radius: 11px !important;
    }
    .compact-stat-label, .info-mini-title { font-size: .66rem !important; opacity: .78 !important; }
    .compact-stat-value, .info-mini-main { font-size: .98rem !important; line-height: 1.05 !important; }
    .info-mini-sub, .info-mini-small { font-size: .72rem !important; line-height: 1.18 !important; }

    /* Knapper: fullbredde knapper finnes fortsatt, men hoyden reduseres. */
    .stButton > button {
        min-height: 30px !important;
        padding-top: .26rem !important;
        padding-bottom: .26rem !important;
    }

    /* Tomme/store dashboardkort skal bli diskrete når innholdet er kort. */
    .market-card, .kpi-card, .status-card, .signal-card {
        padding: .45rem .62rem !important;
        min-height: 46px !important;
    }

    /* v18.6.67 kompakte analysebadges. */
    .density-badge-row { display:flex; flex-wrap:wrap; gap:.35rem; align-items:center; margin:.20rem 0 .42rem 0; }
    .density-badge {
        display:inline-flex; align-items:center; gap:.25rem;
        padding:.20rem .46rem; border:1px solid var(--density-border);
        border-radius:999px; background:var(--density-bg); font-size:.78rem; line-height:1.05;
    }
    .density-badge b { font-size:.82rem; }
    .density-panel {
        border:1px solid var(--density-border); border-radius:12px;
        background:rgba(15,23,42,.45); padding:.45rem .60rem; margin:.22rem 0;
    }
    .density-panel-title { font-size:.72rem; opacity:.75; text-transform:uppercase; letter-spacing:.02em; margin-bottom:.18rem; }

    /* v18.6.68 Paper Trading Layout Rebuild: compact badges and action cards. */
    .paper-trade-summary-row, .paper-compact-info-row {
        display:flex; flex-wrap:wrap; gap:.35rem; align-items:center; margin:.22rem 0 .45rem 0;
    }
    .paper-pill, .paper-info-badge {
        display:inline-flex; align-items:center; gap:.25rem;
        padding:.22rem .52rem; border:1px solid rgba(148,163,184,.30);
        border-radius:999px; background:rgba(15,23,42,.66);
        font-size:.78rem; line-height:1.05; white-space:nowrap;
    }
    .paper-info-badge b, .paper-pill b { font-size:.82rem; }
    .paper-work-card {
        border:1px solid rgba(148,163,184,.25);
        border-radius:14px; padding:.58rem .70rem;
        background:rgba(15,23,42,.44);
    }

    @media (max-width: 760px) {
        div[data-testid="stVerticalBlock"] { gap: .55rem !important; }
        .density-badge { font-size:.82rem; padding:.28rem .50rem; }
        div[data-testid="stMetric"] { min-height: 50px !important; }
        .paper-pill, .paper-info-badge { font-size:.82rem; padding:.30rem .54rem; }
    }
    </style>
    """, unsafe_allow_html=True)


def _inject_interactive_analysis_rebuild_css_v18669():
    st.markdown("""
    <style>
    /* v18.6.70 INTERAKTIV ANALYSE LAYOUT REBUILD
       Målet er færre store bokser og tydeligere analysearbeidsflate. */
    .ia-hero-row {
        display:flex; flex-wrap:wrap; align-items:flex-start; gap:.45rem .70rem;
        padding:.28rem 0 .35rem 0; margin:.10rem 0 .20rem 0;
    }
    .ia-hero-chip {
        display:inline-flex; flex-direction:column; justify-content:center;
        min-width:92px; max-width:185px; min-height:36px;
        padding:.30rem .55rem; border:1px solid rgba(148,163,184,.28);
        border-radius:12px; background:rgba(15,23,42,.58);
    }
    .ia-hero-chip .k { font-size:.62rem; opacity:.72; line-height:1; text-transform:uppercase; letter-spacing:.03em; }
    .ia-hero-chip .v { font-size:.88rem; font-weight:900; line-height:1.05; margin-top:.12rem; color:#f8fafc; }
    .ia-mini-toolbar {
        display:flex; flex-wrap:wrap; align-items:end; gap:.45rem .60rem;
        padding:.42rem .55rem; margin:.25rem 0 .42rem 0;
        border:1px solid rgba(148,163,184,.20); border-radius:14px;
        background:rgba(15,23,42,.30);
    }
    .ia-toolbar-note {
        display:inline-flex; align-items:center; gap:.30rem;
        padding:.18rem .46rem; border-radius:999px;
        border:1px solid rgba(234,179,8,.45); color:#fde68a;
        background:rgba(113,63,18,.16); font-size:.72rem; font-weight:850;
        margin:.15rem 0 .2rem 0;
    }
    .ia-status-line {
        display:flex; flex-wrap:wrap; gap:.35rem; align-items:center;
        margin:.20rem 0 .30rem 0;
    }
    .ia-status-line span {
        display:inline-flex; align-items:center; gap:.22rem; padding:.17rem .42rem;
        border:1px solid rgba(148,163,184,.25); border-radius:999px;
        background:rgba(15,23,42,.50); font-size:.72rem; font-weight:800;
    }
    .ia-controls-compact div[data-testid="stSelectbox"] { max-width: 210px !important; }
    .ia-controls-compact div[data-testid="stMultiSelect"] { max-width: 100% !important; }
    .ia-controls-compact div[data-testid="stTextInput"] { max-width: 230px !important; }
    .ia-controls-compact .stButton > button { min-height: 30px !important; padding:.26rem .62rem !important; }
    .ia-controls-compact div[data-testid="stVerticalBlock"] { gap:.18rem !important; }
    .ia-controls-compact div[data-testid="stHorizontalBlock"] { gap:.38rem !important; }
    .ia-controls-compact label { font-size:.72rem !important; line-height:1.05 !important; margin-bottom:.08rem !important; }
    .ia-controls-compact div[data-baseweb="select"] > div,
    .ia-controls-compact div[data-testid="stTextInput"] input { min-height:30px !important; height:30px !important; }
    /* Ikke la grafkontroll-former lage svære adminbokser. */
    .ia-controls-compact div[data-testid="stForm"] {
        border:none !important; padding:0 !important; background:transparent !important;
    }
    @media (max-width: 760px) {
        .ia-hero-chip { min-width:48%; max-width:100%; }
        .ia-controls-compact div[data-testid="stSelectbox"],
        .ia-controls-compact div[data-testid="stTextInput"] { max-width:100% !important; }
    }
    </style>
    """, unsafe_allow_html=True)


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
        min-height:36px !important;
        padding:.34rem .72rem !important;
        border-radius:10px !important;
        background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
        border:1px solid rgba(224,242,254,.98) !important;
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
        font-weight:950 !important;
        overflow-wrap:anywhere !important;
        opacity:1 !important;
        filter:none !important;
        box-shadow:0 0 0 1px rgba(255,255,255,.14),0 8px 22px rgba(14,165,233,.24) !important;
        white-space:normal !important;
    }
    .v18590-global-action .stButton > button p {
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
        font-size:.84rem !important;
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
        min-height:36px !important;
        padding:.34rem .72rem !important;
        border-radius:10px !important;
        background:linear-gradient(180deg,#38d5ff 0%,#0284c7 100%) !important;
        border:1px solid rgba(224,242,254,1) !important;
        box-shadow:0 0 0 1px rgba(255,255,255,.18),0 10px 24px rgba(14,165,233,.30) !important;
        opacity:1 !important;
        filter:none !important;
        overflow:visible !important;
        white-space:normal !important;
        overflow-wrap:anywhere !important;
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


def _inject_professional_ui_refactor_v18666():
    st.markdown("""
    <style>
    /* v18.6.67 PROFESSIONAL UI REFACTOR
       Global tetthet: mindre tallfelt, kompakte KPI-er, mindre ekspanderere og mindre tom luft.
       Ingen motorlogikk endres. */
    :root {
        --v66-num-w: 128px;
        --v66-money-w: 148px;
        --v66-date-w: 168px;
        --v66-text-w: 300px;
        --v66-select-w: 320px;
        --v66-slider-w: 420px;
        --v66-control-h: 30px;
        --v66-radius: 10px;
    }

    /* --- Global field density --- */
    html body .stApp div[data-testid="stNumberInput"] {
        max-width: var(--v66-num-w) !important;
        min-width: 78px !important;
        width: fit-content !important;
    }
    html body .stApp div[data-testid="stNumberInput"] input {
        height: var(--v66-control-h) !important;
        min-height: var(--v66-control-h) !important;
        padding: .18rem .40rem !important;
        text-align: center !important;
        font-size: .84rem !important;
        font-weight: 850 !important;
    }
    html body .stApp div[data-testid="stNumberInput"] button {
        height: var(--v66-control-h) !important;
        min-height: var(--v66-control-h) !important;
        width: 24px !important;
        min-width: 24px !important;
        padding: 0 !important;
    }

    html body .stApp div[data-testid="stTextInput"] {
        max-width: var(--v66-text-w) !important;
        min-width: 110px !important;
        width: auto !important;
    }
    html body .stApp div[data-testid="stTextInput"] input {
        height: var(--v66-control-h) !important;
        min-height: var(--v66-control-h) !important;
        padding: .18rem .46rem !important;
        font-size: .84rem !important;
    }

    html body .stApp div[data-testid="stDateInput"] {
        max-width: var(--v66-date-w) !important;
        min-width: 138px !important;
    }
    html body .stApp div[data-testid="stDateInput"] input {
        height: var(--v66-control-h) !important;
        min-height: var(--v66-control-h) !important;
        padding: .18rem .45rem !important;
        font-size: .84rem !important;
    }

    html body .stApp div[data-testid="stSelectbox"] {
        max-width: var(--v66-select-w) !important;
        min-width: 120px !important;
        width: auto !important;
    }
    html body .stApp div[data-baseweb="select"] > div {
        min-height: var(--v66-control-h) !important;
        height: var(--v66-control-h) !important;
        font-size: .84rem !important;
        border-radius: var(--v66-radius) !important;
    }

    html body .stApp div[data-testid="stSlider"] {
        max-width: var(--v66-slider-w) !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    html body .stApp div[data-testid="stSlider"] [role="slider"] {
        width: 14px !important;
        height: 14px !important;
    }

    html body .stApp label,
    html body .stApp .stCaption,
    html body .stApp div[data-testid="stCaptionContainer"],
    html body .stApp div[data-testid="stMarkdownContainer"] p {
        line-height: 1.18 !important;
    }

    html body .stApp .stButton > button,
    html body .stApp div[data-testid="stFormSubmitButton"] button,
    html body .stApp div[data-testid="stDownloadButton"] button {
        min-height: 30px !important;
        height: auto !important;
        padding: .26rem .60rem !important;
        border-radius: 9px !important;
        font-size: .82rem !important;
        line-height: 1.08 !important;
    }
    html body .stApp .stButton > button p,
    html body .stApp div[data-testid="stDownloadButton"] button p {
        font-size: .82rem !important;
        line-height: 1.08 !important;
    }

    /* --- Metrics and KPI cards: much flatter --- */
    html body .stApp div[data-testid="stMetric"] {
        min-height: 42px !important;
        padding: .34rem .48rem !important;
        border-radius: 10px !important;
        margin-bottom: .20rem !important;
    }
    html body .stApp div[data-testid="stMetricLabel"] { font-size: .66rem !important; line-height: 1.05 !important; }
    html body .stApp div[data-testid="stMetricValue"] { font-size: 1.00rem !important; line-height: 1.05 !important; }
    html body .stApp div[data-testid="stMetricDelta"] { font-size: .66rem !important; }

    html body .stApp .compact-stat-grid {
        grid-template-columns: repeat(6, minmax(0, 1fr)) !important;
        gap: .36rem !important;
        margin: .32rem 0 .42rem 0 !important;
    }
    html body .stApp .compact-stat-card,
    html body .stApp .info-mini-card {
        min-height: 38px !important;
        padding: .32rem .44rem !important;
        border-radius: 10px !important;
    }
    html body .stApp .compact-stat-label { font-size: .61rem !important; margin-bottom: .10rem !important; }
    html body .stApp .compact-stat-value { font-size: .90rem !important; }

    html body .stApp .dash2026-kpi-grid {
        display: grid !important;
        grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
        gap: .34rem !important;
        margin: .18rem 0 .20rem 0 !important;
    }
    html body .stApp .dash2026-kpi-card {
        min-height: 46px !important;
        padding: .36rem .48rem !important;
        border-radius: 12px !important;
        box-shadow: none !important;
    }
    html body .stApp .dash2026-kpi-value {
        font-size: 1.03rem !important;
        line-height: 1.0 !important;
        white-space: nowrap !important;
    }
    html body .stApp .dash2026-kpi-label,
    html body .stApp .dash2026-kpi-sub {
        font-size: .58rem !important;
        line-height: 1.05 !important;
    }
    html body .stApp .dash2026-kpi-sub {
        max-height: 1.15em !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
    }

    /* --- Expander and section containers: less admin-panel bulk --- */
    html body .stApp div[data-testid="stExpander"] details {
        border-radius: 10px !important;
        margin-bottom: .28rem !important;
    }
    html body .stApp div[data-testid="stExpander"] details > summary {
        min-height: 30px !important;
        padding: .20rem .52rem !important;
        font-size: .82rem !important;
        line-height: 1.05 !important;
    }
    html body .stApp div[data-testid="stExpander"] details > div {
        padding-top: .32rem !important;
        padding-bottom: .40rem !important;
    }

    html body .stApp .card,
    html body .stApp .analysis-card,
    html body .stApp .quicklist-card,
    html body .stApp .paper-edit-card,
    html body .stApp .paper-trade-box-v18615,
    html body .stApp .control-center-status,
    html body .stApp .trading-engine-details,
    html body .stApp .v18-dark-row {
        padding: .42rem .52rem !important;
        border-radius: 10px !important;
        margin-bottom: .34rem !important;
    }

    html body .stApp .ptw-control-hero,
    html body .stApp .ptw-control-selector-shell,
    html body .stApp .v1863g-global-action-card,
    html body .stApp .v18572-global-update-shell {
        padding: .45rem .58rem !important;
        border-radius: 12px !important;
        margin: .26rem 0 .34rem 0 !important;
    }

    /* Tables keep full width, but reduce row height/font. */
    html body .stApp div[data-testid="stDataFrame"] {
        max-width: none !important;
        font-size: .82rem !important;
    }

    /* Desktop-only: split wide generated columns from stretching tiny controls. */
    @media (min-width: 761px) {
        html body .stApp div[data-testid="column"]:has(div[data-testid="stNumberInput"]) {
            flex: 0 1 auto !important;
            min-width: 96px !important;
        }
        html body .stApp div[data-testid="column"]:has(div[data-testid="stDateInput"]) {
            flex: 0 1 auto !important;
            min-width: 150px !important;
        }
        html body .stApp div[data-testid="column"]:has(div[data-testid="stSelectbox"]) {
            min-width: 150px !important;
        }
    }

    /* Mobile remains touch-friendly and full width. */
    @media (max-width: 760px) {
        html body .stApp div[data-testid="stNumberInput"],
        html body .stApp div[data-testid="stTextInput"],
        html body .stApp div[data-testid="stDateInput"],
        html body .stApp div[data-testid="stSelectbox"],
        html body .stApp div[data-testid="stSlider"] {
            max-width: 100% !important;
            width: 100% !important;
        }
        html body .stApp .stButton > button,
        html body .stApp div[data-testid="stFormSubmitButton"] button,
        html body .stApp div[data-testid="stDownloadButton"] button {
            min-height: 38px !important;
            font-size: .92rem !important;
        }
        html body .stApp .dash2026-kpi-grid,
        html body .stApp .compact-stat-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)


def inject_foundation_styles_v1950() -> None:
    _inject_global_compact_ui_v18665()
    _inject_information_density_ui_v18667()
    _inject_interactive_analysis_rebuild_css_v18669()
    _inject_ui_data_trust_css_v18589()
    _inject_ui_path_cleanup_css_v18590()
    _inject_visual_truth_fix_css_v18591()


def inject_final_density_styles_v1950() -> None:
    _inject_professional_ui_refactor_v18666()
