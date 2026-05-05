# BANNER_SAFE_PRO_V7
from ui_components import market_pulse, top_movers
import os
import re
import streamlit as st
from cron_control import cron_status_text, pause_until, clear_pause, activate_full_stop, deactivate_full_stop
from auth import require_login, render_user_admin
from settings_store import load_settings, save_settings, reset_settings
from alert_state import reset_alert_state
from market_hours import open_markets, market_status_lines, market_statuses
from background_guard import market_guard_summary
from trading_settings import load_rules, save_rules
import pandas as pd
import plotly.graph_objects as go
import requests
import html
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

try:
    import yfinance as yf
except Exception:
    yf = None

from technical import calculate_rsi, calculate_macd, calculate_bollinger, detect_trend, technical_signal
from patterns import detect_head_shoulders, detect_inverse_head_shoulders, breakout_scanner, build_signal_alerts

from stocks import get_sp500_tickers, get_norwegian_tickers, get_swedish_tickers, get_all_tickers
from analysis import rank_stocks, score_stock
from market_selector import auto_rank_market, build_top_picks
from backtest_strategy import run_monthly_score_strategy, add_stats
from ipo import get_ipo_calendar
from news import get_news, simple_finance_sentiment
from trading_engine import build_trading_decision, adjusted_score, paper_buy, paper_sell
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
from mobile_analysis_view import render_mobile_analysis_view, fetch_timeframe_data, get_selected_time_settings

st.set_page_config(page_title="AI Aksje Analyzer Pro", page_icon="📈", layout="wide", initial_sidebar_state="auto")

current_user = require_login()

_runtime_settings = load_settings()
UI_REFRESH_MINUTES = int(_runtime_settings.get("ui_refresh_minutes", 5) or 5)
UI_REFRESH_MINUTES = max(1, min(UI_REFRESH_MINUTES, 60))
# V13 / Oppgave 35: Ikke kjør automatisk rerun når auto-oppdatering er slått av.
# Periodisk refresh må aktiveres eksplisitt i banner-innstillingene.
UI_AUTO_REFRESH_ENABLED = bool(_runtime_settings.get("ui_auto_refresh_enabled", False))
if UI_AUTO_REFRESH_ENABLED:
    st_autorefresh(interval=UI_REFRESH_MINUTES * 60 * 1000, key="refresh")


# --- V14.7 helpers: stabilitet, kontrollsenter og status ---
def _save_setting_patch(**updates):
    _s = load_settings()
    _s.update(updates)
    save_settings(_s)
    return _s


def _auto_state(settings=None):
    _s = settings or load_settings()
    if bool(_s.get("auto_trading_emergency_stop", False)):
        return "NØDSTOPP", "red"
    if bool(_s.get("auto_trading_paused", False)):
        return "PAUSET", "yellow"
    if bool(_s.get("auto_trading_enabled", False)):
        return "AKTIV", "green"
    return "AV", "red"


def _set_auto_state(state):
    state = str(state).upper()
    if state == "START":
        _save_setting_patch(auto_trading_enabled=True, auto_trading_paused=False, auto_trading_emergency_stop=False)
    elif state == "PAUSE":
        _save_setting_patch(auto_trading_enabled=False, auto_trading_paused=True, auto_trading_emergency_stop=False)
    elif state == "STOPP":
        _save_setting_patch(auto_trading_enabled=False, auto_trading_paused=False, auto_trading_emergency_stop=False)
    elif state == "NØDSTOPP":
        _save_setting_patch(auto_trading_enabled=False, auto_trading_paused=False, auto_trading_emergency_stop=True)
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


def _last_update_label():
    reason = st.session_state.get("last_update_started_by_v148", "Oppstart / cache")
    at = st.session_state.get("last_update_started_at_v148", "-")
    return f"{reason} · {at}"


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


def _heavy_update_allowed():
    """True bare når bruker har trykket Oppdater / auto-oppdater er aktiv / cache mangler."""
    settings = load_settings()
    return bool(settings.get("chart_auto_update_enabled", False)) or bool(st.session_state.get("heavy_update_allowed_v148", False))


def _rank_cache_store(label, fp, data):
    st.session_state[f"rank_cache_v148_{label}"] = {"fp": fp, "data": data, "updated_at": _now_short()}
    latest = st.session_state.setdefault("latest_rankings_v148", {})
    latest[label] = data or []


def _rank_cache_get(label, fp):
    cache = st.session_state.get(f"rank_cache_v148_{label}") or {}
    if cache.get("fp") == fp:
        return cache.get("data")
    return None


def cached_auto_rank_market(label, tickers, max_count=30, use_news=False, force_manual_fetch=False):
    """Cache rundt auto_rank_market for å hindre tung rangering ved bare menyendringer.

    Når auto-oppdater er AV, kjøres ny rangering bare når bruker trykker
    Oppdater / bruk endringer, eller når cache mangler.
    """
    safe_tickers = list(tickers or [])
    fp = (tuple(safe_tickers[: int(max_count or 0)]), int(max_count or 0), bool(use_news), bool(force_manual_fetch))
    cached = _rank_cache_get(label, fp)
    if cached is not None and not _heavy_update_allowed():
        return cached
    if cached is not None and not bool(load_settings().get("chart_auto_update_enabled", False)) and not st.session_state.get("heavy_update_allowed_v148", False):
        return cached
    data = auto_rank_market(safe_tickers, max_count=max_count, use_news=use_news, force_manual_fetch=force_manual_fetch)
    _rank_cache_store(label, fp, data)
    return data


def _sort_ranked_items(items):
    """Sorter rangeringer etter appens egen score, uten å starte ny datainnhenting."""
    def _score(item):
        try:
            return float((item or {}).get("score", 0) or 0)
        except Exception:
            return 0.0
    return sorted([x for x in (items or []) if isinstance(x, dict) and x.get("ticker")], key=_score, reverse=True)


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

    if source_label == "Dynamisk watchlist / best rangerte":
        merged = []
        for key in ["Dynamisk watchlist / best rangerte", "USA", "Norge", "Sverige", "TopPicks_USA", "TopPicks_Norge", "TopPicks_Sverige", "TopPicks_Alle"]:
            merged.extend(latest.get(key, []) or [])
        return _dedupe_ranked_items(merged or fallback_results)

    if source_label in {"USA", "Norge", "Sverige"}:
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

    if source_label == "USA":
        return list(globals().get("tickers_us") or get_sp500_tickers(limit=limit))
    if source_label == "Norge":
        return list(globals().get("tickers_no") or get_norwegian_tickers(limit=limit))
    if source_label == "Sverige":
        return list(globals().get("tickers_se") or get_swedish_tickers(limit=limit))
    if source_label == "Dynamisk watchlist / best rangerte":
        wl = list(globals().get("watchlist_tickers") or [])
        if wl:
            return wl[:limit]
        return list(globals().get("dynamic_watchlist") or [])[:limit]
    if source_label == "Top Picks":
        merged = []
        for seq in [globals().get("tickers_us"), globals().get("tickers_no"), globals().get("tickers_se")]:
            merged.extend(list(seq or [])[: max(5, limit // 3)])
        if not merged:
            merged = get_all_tickers(limit_per_market=max(5, limit // 3))
        return merged[:limit]
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
    else:
        key = source_label
    latest = st.session_state.setdefault("latest_rankings_v148", {})
    latest[key] = data or []
    # Lagre også under normal kildenøkkel når relevant, slik at dropdownen finner listen direkte.
    if source_label in {"USA", "Norge", "Sverige"}:
        latest[source_label] = data or []
    st.session_state[f"rank_cache_v148_{key}"] = {"fp": ("manual_build", tuple(tickers[:limit])), "data": data or [], "updated_at": _now_short()}
    _set_update_reason(f"Interaktiv analyse: bygget {source_label}-liste")
    return data or []


def _clean_manual_ticker_input(value: str) -> str:
    """Rydd manuell ticker. Eksempeltekst og lister skal ikke behandles som aktiv ticker."""
    raw = str(value or "").strip()
    examples = {"STB.OL / EQNR.OL / ABB.ST", "AAPL / EQNR.OL / ABB.ST"}
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
    "scrollZoom": True,
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToAdd": ["pan2d", "zoom2d", "resetScale2d"],
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
    except Exception:
        pass

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
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        z-index: 1000000 !important;
        position: fixed !important;
        top: 0.55rem !important;
        left: 0.55rem !important;
        background: rgba(14,165,233,0.96) !important;
        border: 1px solid rgba(125,211,252,0.70) !important;
        border-radius: 12px !important;
        box-shadow: 0 8px 20px rgba(14,165,233,0.25) !important;
    }
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
    font-size: 0.98rem;
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
    font-size: 0.98rem;
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
    padding: 7px 5px;
    line-height: 1.05;
    overflow: hidden;
    min-height: 50px;
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
    border-radius: 10px;
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
    padding: 10px 12px;
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
    padding: 10px 12px;
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

# V14.5 / Oppgave 44: Global visningsmodus.
# Kompakt gjør status-/analysebokser lavere uten å fjerne informasjon.
APP_VIEW_MODE = st.sidebar.radio(
    "Visningsmodus",
    ["Kompakt", "Normal", "Full"],
    index=0,
    horizontal=True,
    key="global_view_mode_v145",
    help="Kompakt sparer plass. Normal bruker standard. Full viser større kort og mer luft.",
)
st.session_state["app_view_mode"] = APP_VIEW_MODE
st.sidebar.markdown(f"<div class='view-mode-status'>Aktiv visning: {APP_VIEW_MODE}</div>", unsafe_allow_html=True)

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
    st.markdown(
        """
        <style>
        [data-testid="stMetric"] { padding: 18px !important; min-height: 92px !important; }
        [data-testid="stMetricValue"] { font-size: 1.85rem !important; }
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
        except Exception:
            pass

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
    for market in ["USA", "Norge", "Sverige"]:
        if market not in visible_markets:
            continue
        text_value = raw.get(market, "") if isinstance(raw, dict) else ""
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
def fetch_live_banner_snapshot(banner_items):
    if yf is None:
        return []

    cards = []
    for market, ticker, label in banner_items:
        try:
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

    banner_cards = fetch_live_banner_snapshot(banner_items)
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
    refresh_minutes = int(settings.get("ui_refresh_minutes", 5) or 5)
    speed_seconds = int(settings.get("live_banner_speed_seconds", 70) or 70)
    speed_seconds = max(15, min(speed_seconds, 180))

    # IMPORTANT:
    # CSS ligger i vanlig string, ikke f-string, for å unngå SyntaxError fra CSS-klammer.
    banner_html = """
    <style>
    .ticker-tape-wrap {
        width: 100%;
        overflow: hidden;
        margin: 0.55rem 0 1.10rem 0;
        padding: 0;
        border-top: 1px solid rgba(15,23,42,0.10);
        border-bottom: 1px solid rgba(15,23,42,0.14);
        background: #f8fafc;
        border-radius: 10px;
        min-height: 102px;
        box-shadow: inset 0 0 0 1px rgba(15,23,42,0.03);
    }
    .ticker-tape-track {
        display: flex;
        align-items: stretch;
        width: max-content;
        gap: 16px;
        white-space: nowrap;
        animation: tickerTapeScroll __SPEED__s linear infinite;
        padding: 10px 12px;
    }
    .ticker-tape-wrap:hover .ticker-tape-track {
        animation-play-state: paused;
    }
    .ticker-tape-item {
        display: inline-grid;
        grid-template-columns: 146px 112px;
        align-items: center;
        gap: 12px;
        min-width: 274px;
        height: 80px;
        padding: 8px 14px;
        border-radius: 0;
        background: #ffffff;
        border-right: 1px solid rgba(15,23,42,0.10);
    }
    .ticker-info {
        display: flex;
        flex-direction: column;
        justify-content: center;
        line-height: 1.02;
    }
    .ticker-market {
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 2px;
    }
    .ticker-title {
        font-size: 1.02rem;
        font-weight: 900;
        color: #2563eb;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        margin-bottom: 4px;
    }
    .ticker-price {
        font-size: 1.12rem;
        font-weight: 900;
        color: #1f2937;
        margin-top: 0;
    }
    .ticker-change {
        font-size: 0.98rem;
        font-weight: 950;
        margin-top: 5px;
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
        width: 112px;
        height: 42px;
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
            gap: 12px;
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
        .ticker-spark svg { width: 86px; height: 30px; }
    }
    </style>
    <div class='ticker-tape-wrap'>
        <div class='ticker-tape-track'>__CARDS____CARDS__</div>
    </div>
    """
    banner_html = banner_html.replace("__SPEED__", str(speed_seconds)).replace("__CARDS__", cards_html)

    st.markdown(banner_html, unsafe_allow_html=True)
    st.caption(
        f"📡 Ticker-banner: {len(banner_cards)} kort · oppdateres ca. hver {refresh_minutes}. min · "
        f"hastighet {speed_seconds}s. Hold pekeren over for pause. Mini-grafen bruker stiplet referanselinje "
        "som gårsdagens sluttkurs, med grønt/rødt over/under linjen."
    )



def render_banner_sidebar_controls(expanded=False):
    """Synlig kontroll for ticker-banner i sidepanelet."""
    st.sidebar.markdown(
        """
        <style>
        /* BANNER_FORM_FOCUS_AND_MARKET_FILTER_V9 */
        section[data-testid="stSidebar"] textarea,
        section[data-testid="stSidebar"] [data-baseweb="textarea"] textarea {
            caret-color: #38bdf8 !important;
            color: #f8fafc !important;
            background: rgba(15,23,42,0.94) !important;
            border-color: rgba(148,163,184,0.55) !important;
            font-weight: 800 !important;
        }
        section[data-testid="stSidebar"] [data-baseweb="textarea"]:focus-within,
        section[data-testid="stSidebar"] textarea:focus {
            outline: none !important;
            border-color: #38bdf8 !important;
            box-shadow: 0 0 0 2px rgba(56,189,248,0.22) !important;
        }
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
            min-height: 38px !important;
            background: rgba(15,23,42,0.92) !important;
            border: 1px solid rgba(148,163,184,0.42) !important;
            border-radius: 11px !important;
        }
        section[data-testid="stSidebar"] div[data-baseweb="select"]:focus-within > div {
            border-color: rgba(56,189,248,0.92) !important;
            box-shadow: 0 0 0 2px rgba(56,189,248,0.20) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.sidebar.expander("📺 Rediger ticker-banner", expanded=expanded):
        _banner_settings = load_settings()
        _ticker_settings = _banner_settings.get("live_banner_tickers", {}) or {}
        _market_options = ["USA", "Norge", "Sverige"]
        _visible_markets = _banner_settings.get("live_banner_markets_visible", _market_options)
        if isinstance(_visible_markets, str):
            _visible_markets = [m.strip() for m in _visible_markets.replace(";", ",").split(",") if m.strip()]
        _visible_markets = [m for m in (_visible_markets or _market_options) if m in _market_options]
        if not _visible_markets:
            _visible_markets = list(_market_options)

        st.caption("Endringer i banneret er samlet i skjemaet. Rediger flere felt først, og trykk Lagre banner når du er klar.")
        with st.form("banner_settings_form_v9", clear_on_submit=False):
            _banner_enabled = st.checkbox(
                "Vis ticker-banner øverst",
                value=bool(_banner_settings.get("live_banner_enabled", True)),
                key="banner_enabled_form_v9",
            )
            _refresh_options = [1, 5, 15, 30, 60]
            _current_refresh = int(_banner_settings.get("ui_refresh_minutes", 5) or 5)
            if _current_refresh not in _refresh_options:
                _refresh_options.append(_current_refresh)
                _refresh_options = sorted(set(_refresh_options))
            _auto_refresh_enabled = st.checkbox(
                "Auto-oppdater appen periodisk",
                value=bool(_banner_settings.get("ui_auto_refresh_enabled", False)),
                key="ui_auto_refresh_enabled_form_v13",
            )
            _refresh_choice = st.selectbox(
                "Oppdateringsintervall",
                _refresh_options,
                index=_refresh_options.index(_current_refresh),
                format_func=lambda x: f"{x} min",
                key="banner_refresh_form_v9",
            )
            _current_speed = int(_banner_settings.get("live_banner_speed_seconds", 70) or 70)
            _banner_speed = st.slider(
                "Bannerhastighet",
                15,
                180,
                _current_speed,
                5,
                key="banner_speed_form_v9",
            )
            st.caption(f"Bannerhastighet valgt: {_banner_speed}s. Lavere tall = raskere, høyere tall = saktere. Trykk Lagre banner for å bruke verdien.")
            _selected_markets = st.multiselect(
                "Markeder som vises i banner",
                _market_options,
                default=_visible_markets,
                key="banner_markets_visible_form_v9",
            )
            st.caption("Legg til/fjern tickere. Bruk komma. Norske tickere bruker ofte .OL, svenske .ST.")
            _usa_banner = st.text_area("USA", value=str(_ticker_settings.get("USA", "^GSPC, ^IXIC, ^DJI, AAPL, MSFT, NVDA")), height=64, key="banner_usa_form_v9")
            _no_banner = st.text_area("Norge", value=str(_ticker_settings.get("Norge", "EQNR.OL, DNB.OL, NHY.OL, YAR.OL")), height=64, key="banner_no_form_v9")
            _se_banner = st.text_area("Sverige", value=str(_ticker_settings.get("Sverige", "ATCO-A.ST, VOLV-B.ST, ERIC-B.ST, ABB.ST")), height=64, key="banner_se_form_v9")
            _save_banner = st.form_submit_button("💾 Lagre banner", use_container_width=True)

        if _save_banner:
            _banner_settings["live_banner_enabled"] = bool(_banner_enabled)
            _banner_settings["ui_auto_refresh_enabled"] = bool(_auto_refresh_enabled)
            _banner_settings["ui_refresh_minutes"] = int(_refresh_choice)
            _banner_settings["live_banner_speed_seconds"] = int(_banner_speed)
            _banner_settings["live_banner_markets_visible"] = list(_selected_markets or _market_options)
            _banner_settings["live_banner_tickers"] = {"USA": _usa_banner, "Norge": _no_banner, "Sverige": _se_banner}
            save_settings(_banner_settings)
            try:
                fetch_live_banner_snapshot.clear()
            except Exception:
                pass
            st.success("Banner lagret ✅")
            st.rerun()

def render_decision_explanation(decision):
    try:
        reasons = decision.get("reasons", [])
        warnings = decision.get("warnings", [])
        st.markdown("#### 🧠 Hvorfor dette signalet?")
        if reasons:
            for r in reasons:
                st.success(f"✅ {r}")
        if warnings:
            for w in warnings:
                st.warning(f"⚠️ {w}")
    except Exception:
        pass



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

def send_pushover_alert(message, title="AI Aksje Analyzer"):
    """
    Sender Pushover-varsel.
    Krever Environment Variables:
    - PUSHOVER_APP_TOKEN
    - PUSHOVER_USER_KEY
    """
    if not PUSHOVER_APP_TOKEN or not PUSHOVER_USER_KEY:
        return False, "Mangler PUSHOVER_APP_TOKEN eller PUSHOVER_USER_KEY"

    try:
        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_APP_TOKEN,
                "user": PUSHOVER_USER_KEY,
                "title": title,
                "message": message,
            },
            timeout=10,
        )

        if response.status_code == 200:
            return True, None

        return False, response.text

    except Exception as e:
        return False, str(e)


def maybe_send_signal_alert(ticker, decision):
    """
    Deaktivert i Pushover trade-fix:
    Varsler skal kun sendes fra trading_engine.py når faktisk BUY/SELL skjer.
    Dette hindrer mobil-spam ved vanlig signalendring/refresh.
    """
    return None



def get_dynamic_watchlist(mode, max_count, tickers_us, tickers_no, tickers_se, tickers_all):
    """
    Lager automatisk watchlist fra aktivt marked.
    Denne følger universet og antall aksjer du har valgt i sidepanelet.
    """
    if mode == "USA / S&P 500":
        return tickers_us[:max_count]
    if mode == "Norge / Oslo Børs":
        return tickers_no[:max_count]
    if mode == "Sverige / Stockholm":
        return tickers_se[:max_count]
    return tickers_all[:max_count]

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
    except Exception:
        pass

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

    if not results:
        st.warning("Fant ingen data.")
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

    st.markdown("### ⚡ Hurtigliste med kurs")
    st.caption("Top Picks = sterk kandidat totalt. Handling nå = teknisk timing akkurat nå.")

    for idx, item in enumerate(results[:15], start=1):
        ticker = item.get("ticker", "N/A")
        score = item.get("score", 0)
        latest_price, change_pct = get_item_price_change(item)
        card_decision = card_decision_for_item(item)

        price_text = "N/A"
        delta_text = None
        direction_icon = "⚪"

        if latest_price is not None:
            price_text = f"{latest_price:.2f} {currency_suffix(ticker)}"
            delta_text = f"{change_pct:+.2f}%"
            direction_icon = "🟢" if change_pct >= 0 else "🔴"

        with st.container(border=True):
            left, mid, right = st.columns([1.45, 1.0, 2.0])

            with left:
                st.markdown(f"### {direction_icon} {ticker}")
                st.caption(f"#{idx} · {item.get('name', '')}")
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
                    st.markdown(f"<div class='action-explain'>⚠️ {warnings[0]}</div>", unsafe_allow_html=True)
                elif reasons:
                    st.markdown(f"<div class='action-explain'>✅ {reasons[0]}</div>", unsafe_allow_html=True)

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
                        elif st.button(f"🟢 Paper-kjøp {ticker}", key=f"paper_buy_{_btn_key_base}"):
                            _ok, _msg = paper_buy(ticker, latest_price, _conf, f"UI Kjøp nå: {title}")
                            if _ok:
                                st.success(_msg)
                                st.rerun()
                            else:
                                st.warning(_msg)

                    elif latest_price is not None and ("UNNGÅ" in _action_now or "SELL" in _action_now):
                        if _owns and st.button(f"🔴 Paper-selg {ticker}", key=f"paper_sell_{_btn_key_base}"):
                            _ok, _msg = paper_sell(ticker, latest_price, f"UI teknisk signal: {_action_now}")
                            if _ok:
                                st.success(_msg)
                                st.rerun()
                            else:
                                st.warning(_msg)
                except Exception as _e:
                    st.caption(f"Paper-knapp ikke tilgjengelig: {_e}")



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
    except Exception:
        pass
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


def active_ticker_from_inputs(manual_ticker: str, selected_from_list: str) -> str:
    manual = _clean_manual_ticker_input(manual_ticker)
    return manual if manual else normalize_user_ticker(selected_from_list)


def render_analysis(results, label):
    st.subheader("📊 Interaktiv analyse")

    # V14.8 / Oppgave 73: Interaktiv analyse kan hente fra siste lagrede dynamiske rangering,
    # uten å starte en ny scan/rangering bare fordi menyen åpnes.
    source_choice = st.selectbox(
        "Aksjekilde",
        ["Aktuell liste", "Dynamisk watchlist / best rangerte", "Top Picks", "USA", "Norge", "Sverige"],
        index=0,
        key=f"analysis_source_{label}_v148",
        help="Bruker siste lagrede/godkjente rangering. Manuell ticker overstyrer alltid listen.",
    )
    source_results = _latest_ranked_results_for_source(source_choice, results or [], current_label=label)

    # Oppgave 76/76B + 78/79: dynamiske, rangerte valg etter valgt aksjekilde.
    # Standard AAPL-listen brukes bare for Aktuell liste. Andre kilder må ha lagret rangering
    # eller bygges eksplisitt med egen knapp. Ingen stille fallback til AAPL.
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
    fallback_static = ["AAPL", "MSFT", "GOOGL", "AVGO", "NVDA", "AMZN", "EQNR.OL", "DNB.OL", "YAR.OL", "ABB.ST", "VOLV-B.ST"]
    if not options and source_choice == "Aktuell liste":
        options = list(fallback_static)

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
                    st.warning(f"Fant ingen data for {source_choice}. Prøv Oppdater / Scan watchlist eller skriv ticker manuelt.")
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
            placeholder="Skriv én ticker, f.eks. STB.OL",
            key=manual_key,
            help="Manuell ticker overstyrer valgt kilde. For flere tickere bruker du Strategi-test.",
        )
        if st.button("Tøm manuell ticker", key=f"manual_ticker_clear_btn_{label}_v1410", use_container_width=True):
            st.session_state[manual_key] = ""
            st.rerun()
        st.caption("Eksempel: STB.OL, EQNR.OL eller ABB.ST")

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
    if item is None:
        with st.spinner(f"Henter analyse for {selected}..."):
            item = score_stock(selected, use_news=False)

    if not item:
        st.warning("Fant ikke data for valgt ticker. Sjekk ticker-symbol, f.eks. AAPL, EQNR.OL eller ABB.ST.")
        return

    _sync_timeframe, _sync_period = get_selected_time_settings(label, selected)
    _synced_df = fetch_timeframe_data(selected, _sync_timeframe, _sync_period)
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

    insider = get_insider_data(selected)
    analyst = get_analyst_trend(selected)
    earnings = get_earnings(selected)

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
        except Exception:
            pass

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
    except Exception:
        pass
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

    st.markdown("#### 🧪 Strategi-test (historisk simulering)")

    if st.button(f"Kjør strategi-test for {selected}", key=f"strategy_{label}_{selected}"):

        df_strategy = item["hist"].copy()

        # Legg til indikatorer
        df_strategy["rsi"] = calculate_rsi(df_strategy)
        macd_strategy, signal_strategy, _ = calculate_macd(df_strategy)
        df_strategy["macd"] = macd_strategy
        df_strategy["macd_signal"] = signal_strategy

        value, trades, equity = run_strategy(df_strategy)
        stats = strategy_stats(equity, trades)

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Sluttverdi", f"{value:,.0f} kr")
        s2.metric("Total avkastning", f"{stats['total_return']}%")
        s3.metric("Max drawdown", f"{stats['max_drawdown']}%")
        s4.metric("Win rate", f"{stats['win_rate']}%")

        s5, s6, s7 = st.columns(3)
        s5.metric("Antall trades", stats["num_trades"])
        s6.metric("Avg win/loss", f"{stats['avg_win']}% / {stats['avg_loss']}%")
        s7.metric("Profit factor", stats["profit_factor"])

        # HOTFIX v14.1 / Oppgave 38:
        # equity kan være en pandas DataFrame. Da kan den ikke sjekkes med `if equity`,
        # fordi pandas ikke vet om hele tabellen skal tolkes som True/False.
        if equity is not None and not (hasattr(equity, "empty") and equity.empty):
            eq_df = pd.DataFrame(equity, columns=["date", "value"])

            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(
                x=eq_df["date"],
                y=eq_df["value"],
                mode="lines",
                name="Portefølje"
            ))

            # Marker BUY/SELL punkter på grafen
            if trades:
                buy_x = [t["date"] for t in trades if t["type"] == "BUY"]
                buy_y = [t["value"] for t in trades if t["type"] == "BUY"]
                sell_x = [t["date"] for t in trades if t["type"] == "SELL"]
                sell_y = [t["value"] for t in trades if t["type"] == "SELL"]

                if buy_x:
                    fig_eq.add_trace(go.Scatter(
                        x=buy_x,
                        y=buy_y,
                        mode="markers",
                        name="BUY",
                        marker=dict(size=10, symbol="triangle-up")
                    ))

                if sell_x:
                    fig_eq.add_trace(go.Scatter(
                        x=sell_x,
                        y=sell_y,
                        mode="markers",
                        name="SELL",
                        marker=dict(size=10, symbol="triangle-down")
                    ))

            fig_eq.update_layout(
                title="📈 Strategi utvikling (equity curve)",
                template="plotly_dark",
                height=420,
                paper_bgcolor="#0b111c",
                plot_bgcolor="#0b111c",
            )

            render_interactive_chart(fig_eq, use_container_width=True, key=f"equity_chart_{label}_{selected}")
            render_graph_explanation("equity")

        st.markdown("#### Siste trades")
        if trades:
            st.dataframe(pd.DataFrame(trades[-20:]), use_container_width=True)
        else:
            st.info("Ingen trades ble trigget med disse reglene.")

        st.markdown("#### ⚙️ Strategi-optimalisering")
        st.caption("Tester flere RSI/MACD-varianter og rangerer dem etter avkastning, risiko og win-rate.")

        opt_df = optimize_strategy(df_strategy)

        if opt_df.empty:
            st.warning("Klarte ikke å optimalisere strategien.")
        else:
            st.dataframe(opt_df.head(10), use_container_width=True)

            # HOTFIX v14.2 / Oppgave 39:
            # Optimaliseringsresultater har hatt to ulike formater i appen:
            # 1) bredt format: buy_rsi, sell_rsi, use_macd, total_return, max_drawdown
            # 2) langt format: parameter, value, score
            # Appen skal ikke krasje hvis enkelte nøkler mangler.
            def _best_get(row, *keys, default="N/A"):
                for key in keys:
                    try:
                        if key in row.index and pd.notna(row.get(key)):
                            return row.get(key)
                    except Exception:
                        pass
                return default

            if {"parameter", "value"}.issubset(set(opt_df.columns)):
                try:
                    _opt_sorted = opt_df.sort_values("score", ascending=False) if "score" in opt_df.columns else opt_df
                except Exception:
                    _opt_sorted = opt_df
                _top = _opt_sorted.iloc[0]
                _parts = []
                for _, _row in opt_df.head(10).iterrows():
                    _param = _best_get(_row, "parameter", "Parameter")
                    _value = _best_get(_row, "value", "Verdi")
                    if _param != "N/A":
                        _parts.append(f"{_param}: {_value}")
                _score_txt = ""
                _score = _best_get(_top, "score", "Score", default=None)
                if _score is not None:
                    _score_txt = f" | Beste score: {_score}"
                st.success("Beste variant: " + " | ".join(_parts[:6]) + _score_txt)
            else:
                best = opt_df.iloc[0]
                buy_rsi = _best_get(best, "buy_rsi", "max_buy_rsi", "Maks RSI for kjøp", "RSI kjøp")
                sell_rsi = _best_get(best, "sell_rsi", "rsi_exit", "RSI exit", "RSI salg")
                use_macd = _best_get(best, "use_macd", "MACD", default="N/A")
                total_return = _best_get(best, "total_return", "total_return_pct", "Avkastning %")
                max_drawdown = _best_get(best, "max_drawdown", "max_drawdown_pct", "Max drawdown %", "Max DD %")
                st.success(
                    f"Beste variant: BUY RSI < {buy_rsi}, "
                    f"SELL RSI > {sell_rsi}, "
                    f"MACD: {use_macd} | "
                    f"Return: {total_return}% | "
                    f"Max DD: {max_drawdown}%"
                )

    _strategy_default_tickers = []
    for _r in (results or [])[:10]:
        _t = _r.get("ticker") if isinstance(_r, dict) else None
        if _t and _t not in _strategy_default_tickers:
            _strategy_default_tickers.append(_t)
    if selected and selected not in _strategy_default_tickers:
        _strategy_default_tickers.insert(0, selected)
    render_strategy_test_pro(
        selected,
        _strategy_default_tickers,
        load_rules(),
        key_prefix=f"strategy_pro_{label}_{selected}".replace(" ", "_").replace("/", "_").replace(".", "_"),
    )

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
        articles, error = get_news(selected.replace(".OL", ""), limit=6)

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


def render_paper_trading_dashboard():
    st.subheader("🧪 Paper Trading")
    st.caption("Felles lagring: " + ("Postgres/DATABASE_URL ✅" if using_postgres() else "lokal fallback ⚠️"))
    st.caption("Simulert handel med fiktive penger. Brukes for å teste strategien før ekte penger.")
    st.caption("Auto-trading handler bare når relevant marked er åpent. Utenfor åpningstid brukes visning/cache, ikke nye auto-handler.")

    portfolio = load_portfolio()

    latest_prices = {}
    for ticker, pos in portfolio.get("positions", {}).items():
        latest_prices[ticker] = pos.get("last_price", pos.get("avg_price", 0))

    total_value = portfolio_value(portfolio, latest_prices)
    stats = performance_stats(portfolio, latest_prices)

    _paper_rules = load_rules()
    if APP_VIEW_MODE == "Full":
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Cash", f"{portfolio.get('cash', 0):,.0f} kr")
        p2.metric("Porteføljeverdi", f"{total_value:,.0f} kr")
        p3.metric("Total avkastning", f"{stats['total_return_pct']}%")
        p4.metric("Kjøp i dag", f"{stats.get('buys_today', stats.get('trades_today', 0))}/{stats.get('max_buys_per_day', stats.get('max_trades_per_day', 0))}")

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Stop-loss", f"{float(_paper_rules.get('stop_loss_pct', 7.0)):.1f}%")
        r2.metric("Trailing stop", f"{float(_paper_rules.get('trailing_stop_pct', 8.0)):.1f}%")
        r3.metric("Win rate", f"{stats['win_rate']}%")
        r4.metric("Lukkede trades", stats["closed_trades"])
    else:
        render_compact_stat_grid([
            ("Cash", f"{portfolio.get('cash', 0):,.0f} kr"),
            ("Porteføljeverdi", f"{total_value:,.0f} kr"),
            ("Total avkastning", f"{stats['total_return_pct']}%"),
            ("Kjøp i dag", f"{stats.get('buys_today', stats.get('trades_today', 0))}/{stats.get('max_buys_per_day', stats.get('max_trades_per_day', 0))}"),
            ("Stop-loss", f"{float(_paper_rules.get('stop_loss_pct', 7.0)):.1f}%"),
            ("Trailing stop", f"{float(_paper_rules.get('trailing_stop_pct', 8.0)):.1f}%"),
            ("Win rate", f"{stats['win_rate']}%"),
            ("Lukkede trades", stats["closed_trades"]),
        ], columns=4)

    with st.expander("💼 Juster Paper Trading startverdier / porteføljeverdi", expanded=True):
        st.markdown("""
        <div class="paper-edit-card">
            <b>Regulerbare startverdier</b><br>
            Juster startkapital eller ønsket porteføljeverdi. Ved "Bruk porteføljeverdi" justeres cash-delen, mens åpne posisjoner beholdes.
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
            if st.button("💾 Bruk porteføljeverdi", key="paper_apply_total_value_v12"):
                delta = float(new_portfolio_value) - float(total_value)
                portfolio["cash"] = round(float(portfolio.get("cash", 0)) + delta, 2)
                save_portfolio(portfolio)
                _paper_rules["start_cash"] = float(new_start_cash)
                save_rules(_paper_rules)
                st.success("Porteføljeverdi oppdatert ved å justere cash ✅")
                st.rerun()
        with c_reset:
            if st.button("↩️ Reset til startkapital", key="restore_reset_paper_portfolio"):
                _paper_rules["start_cash"] = float(new_start_cash)
                save_rules(_paper_rules)
                reset_portfolio(float(new_start_cash))
                st.success("Paper portfolio nullstilt ✅")
                st.rerun()

    st.markdown("#### Posisjoner")
    positions = portfolio.get("positions", {})
    if positions:
        rows = []
        for ticker, pos in positions.items():
            last_price = pos.get("last_price", pos.get("avg_price", 0))
            avg_price = pos.get("avg_price", 0)
            shares = pos.get("shares", 0)
            value = shares * last_price
            pnl_pct = ((last_price - avg_price) / avg_price * 100) if avg_price else 0
            rows.append({
                "ticker": ticker,
                "shares": round(shares, 4),
                "avg_price": round(avg_price, 2),
                "last_price": round(last_price, 2),
                "value": round(value, 2),
                "pnl_pct": round(pnl_pct, 2),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
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
        st.dataframe(pd.DataFrame(trades[-50:]), use_container_width=True)
    else:
        st.info("Ingen handler ennå.")

def render_ipo():
    st.subheader("🚀 Nye og kommende børsnoteringer")
    ipo_list, error = get_ipo_calendar()
    if error:
        st.info(error)
        return
    if not ipo_list:
        st.info("Fant ingen IPO-data akkurat nå.")
        return
    for ipo in ipo_list[:12]:
        st.markdown(f"**{ipo.get('name','Ukjent selskap')}** ({ipo.get('symbol','N/A')})")
        st.caption(f"{ipo.get('date','Ukjent dato')} · {ipo.get('exchange','Ukjent børs')}")
        st.divider()

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

st.sidebar.title("⚙️ Innstillinger")
render_user_admin(current_user)
try:
    _cc_settings = load_settings()
    _cc_cron = cron_status_text()
    _cc_auto_state, _cc_auto_color = _auto_state(_cc_settings)
    _cc_paper_on = True
    _cc_full_stop = bool(_cc_cron.get("vacation_mode"))
    _cc_chart_auto = bool(_cc_settings.get("chart_auto_update_enabled", False))
    _cc_periodic = bool(_cc_settings.get("ui_auto_refresh_enabled", False))
    st.sidebar.markdown(
        f"""
        <div class='control-center-status'>
            <b>Kontrollsenter</b><br>
            <span class='status-dot {_cc_auto_color}'></span>Auto trading: <b>{_cc_auto_state}</b><br>
            <span class='status-dot {'green' if _cc_paper_on else 'red'}'></span>Paper trading: <b>AKTIV</b><br>
            <span class='status-dot {'red' if _cc_full_stop else 'green'}'></span>Full stopp/ferie: <b>{'JA' if _cc_full_stop else 'NEI'}</b><br>
            <span class='status-dot {'green' if _cc_chart_auto else 'red'}'></span>Auto-oppdater endringer: <b>{'PÅ' if _cc_chart_auto else 'AV'}</b><br>
            Siste scan: <b>{_fmt_dt_short(_cc_cron.get('last_scan_at'))}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _toggle_auto_update = st.sidebar.checkbox(
        "Auto-oppdater ved endringer",
        value=_cc_chart_auto,
        key="sidebar_chart_auto_update_v147",
        help="Av = endringer i graf/indikatorer brukes først når du trykker Oppdater / bruk endringer.",
    )
    if bool(_toggle_auto_update) != _cc_chart_auto:
        _save_setting_patch(chart_auto_update_enabled=bool(_toggle_auto_update))
        st.session_state.pop("top_chart_auto_update_v147", None)
        st.sidebar.success("Auto-oppdatering oppdatert ✅")
        st.rerun()
except Exception:
    pass

# --- Sidebar Structure v2 ---
def render_sidebar_structure_v2():
    st.sidebar.markdown("### 🕒 Børsstatus")
    st.sidebar.markdown(
        "<div class='sidebar-small-note'>Bakgrunnssøk styres av børsstatus. Cache brukes når marked er stengt.</div>",
        unsafe_allow_html=True,
    )

    _statuses = market_statuses()
    _status_cards = []
    for _key, _status in _statuses.items():
        _name = _status.get("name", _key)
        _is_open = bool(_status.get("is_open"))
        _reason = str(_status.get("reason", "ukjent"))
        _closes_at = _status.get("closes_at")

        # Korte navn gjør raden lesbar i Streamlit-sidebar
        _short = {
            "USA": "USA",
            "Norge": "Norge",
            "Sverige": "Sverige",
        }.get(_name, _name)

        if _is_open:
            _main = "Åpent"
            if _closes_at:
                _reason_text = f"til {_closes_at}"
            else:
                _reason_text = ""
            _status_cards.append(
                f"<div class='market-pill open'>"
                f"<div class='market-pill-name'>{_short}</div>"
                f"<div class='market-pill-main open'>{_main} ✅</div>"
                f"<div class='market-pill-reason'>{_reason_text}</div>"
                f"</div>"
            )
        else:
            _status_cards.append(
                f"<div class='market-pill closed'>"
                f"<div class='market-pill-name'>{_short}</div>"
                f"<div class='market-pill-main closed'>Stengt ⚠️</div>"
                f"<div class='market-pill-reason'>{_reason}</div>"
                f"</div>"
            )

    st.sidebar.markdown(
        "<div class='market-pill-row'>" + "".join(_status_cards) + "</div>",
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("<div class='sidebar-tight-hr'></div>", unsafe_allow_html=True)
    st.sidebar.markdown("### ⏱ Cron / bakgrunnssøk")

    _cron_settings = load_settings()
    _cron_status = cron_status_text()
    _is_full_stop = bool(_cron_status.get("vacation_mode"))
    _is_allowed = bool(_cron_status.get("allowed"))

    if _is_full_stop:
        st.sidebar.error("Status: Full stopp ⛔")
    elif not _is_allowed:
        st.sidebar.warning("Status: Pauset / hopper over ⏸")
    else:
        st.sidebar.success("Status: Aktiv ✅")

    st.sidebar.caption(_cron_status.get("reason", ""))

    _cron_enabled = st.sidebar.checkbox(
        "Bakgrunnssøk aktiv",
        value=bool(_cron_settings.get("background_scanning_enabled", True)),
        key="cron_background_enabled_v2",
    )

    _cron_interval = st.sidebar.number_input(
        "Søkintervall minutter",
        min_value=1,
        max_value=1440,
        value=int(_cron_settings.get("scan_interval_minutes", 15)),
        step=1,
        key="cron_scan_interval_v2",
    )

    _pause_choice = st.sidebar.selectbox(
        "Pause søk",
        ["Ingen pause", "30 minutter", "1 time", "2 timer", "Resten av dagen"],
        key="cron_pause_choice_v2",
    )

    if st.sidebar.button("💾 Lagre søk/cron", key="save_cron_control_v2"):
        _new_settings = load_settings()
        _new_settings["background_scanning_enabled"] = bool(_cron_enabled)
        _new_settings["scan_interval_minutes"] = int(_cron_interval)

        if _pause_choice == "30 minutter":
            pause_until(minutes=30)
        elif _pause_choice == "1 time":
            pause_until(minutes=60)
        elif _pause_choice == "2 timer":
            pause_until(minutes=120)
        elif _pause_choice == "Resten av dagen":
            pause_until(rest_of_day=True)
        elif _pause_choice == "Ingen pause":
            _new_settings["pause_scanning_until"] = None
            save_settings(_new_settings)

        _merged = load_settings()
        _merged["background_scanning_enabled"] = bool(_cron_enabled)
        _merged["scan_interval_minutes"] = int(_cron_interval)
        if _pause_choice == "Ingen pause":
            _merged["pause_scanning_until"] = None
        save_settings(_merged)

        st.sidebar.success("Søk/cron lagret ✅")
        st.rerun()

    # Én samlet gjenoppta-knapp erstatter Start igjen + Fjern pause nå.
    if _is_full_stop:
        if st.sidebar.button("▶️ Start systemet igjen", key="resume_from_full_stop_v2"):
            deactivate_full_stop()
            st.sidebar.success("Systemet er startet igjen ✅")
            st.rerun()
    elif _cron_status.get("pause_until"):
        if st.sidebar.button("▶️ Gjenoppta nå", key="resume_from_pause_v2"):
            clear_pause()
            st.sidebar.success("Pause fjernet ✅")
            st.rerun()

    if st.sidebar.button("⛔ Full stopp / ferie", key="activate_full_stop_btn_v2"):
        activate_full_stop()
        st.sidebar.error("Full stopp aktivert ⛔")
        st.rerun()

    # V13 / Oppgave 36: Auto-kjøp skal ligge direkte under Full stopp / ferie.
    st.sidebar.markdown("### ⚡ Auto-kjøp")
    st.sidebar.caption("Tester samme auto-motor som Cron, men manuelt nå.")

    if st.sidebar.button("⚡ Kjør auto-kjøp nå", key="force_auto_buy_now_v2"):
        try:
            from scanner_worker import run_once
            with st.spinner("Kjører auto-kjøp-motor..."):
                _trades = run_once(force=True)
            st.sidebar.success(f"Auto-motor ferdig. Trades: {_trades}")
            st.rerun()
        except Exception as _e:
            st.sidebar.error(f"Auto-kjøp feilet: {_e}")

    if _cron_status.get("last_scan_at"):
        st.sidebar.caption(f"Siste scan: {_cron_status.get('last_scan_at')}")
    if _cron_status.get("pause_until"):
        st.sidebar.caption(f"Pause til: {_cron_status.get('pause_until')}")

    st.sidebar.markdown("<div class='sidebar-tight-hr'></div>", unsafe_allow_html=True)
    render_banner_sidebar_controls(expanded=False)

    st.sidebar.markdown("<div class='sidebar-tight-hr'></div>", unsafe_allow_html=True)
    st.sidebar.markdown("### 🔕 Varselkontroll")

    _alert_settings = load_settings()
    _pushover_env_ok = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)
    _pushover_setting_on = bool(_alert_settings.get("pushover_enabled", True))
    _pushover_ready = _pushover_env_ok and _pushover_setting_on
    _open_markets_now = open_markets()

    st.sidebar.markdown(
        f"""
        <div class="alert-status-pill {'ok' if _pushover_ready else 'bad'}">
            <div class="alert-status-title">Pushover: {'Aktiv ✅' if _pushover_ready else 'Ikke klar ❌'}</div>
            <div class="alert-status-sub">Åpne markeder nå: {_open_markets_now}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _notify_trades = st.sidebar.checkbox(
        "Varsle ved faktisk paper BUY/SELL",
        value=bool(_alert_settings.get("notify_paper_trades", True)),
        key="alert_notify_paper_trades_v1",
    )
    _notify_watchlist = st.sidebar.checkbox(
        "Varsle ved watchlist signalendring",
        value=bool(_alert_settings.get("notify_watchlist_signal_changes", True)),
        key="alert_notify_watchlist_changes_v1",
    )
    _high_conf_only = st.sidebar.checkbox(
        "Varsle kun høy confidence",
        value=bool(_alert_settings.get("notify_high_confidence_only", True)),
        key="alert_high_conf_only_v1",
    )
    _min_alert_conf = st.sidebar.slider(
        "Confidence-grense",
        50,
        95,
        int(_alert_settings.get("notify_min_confidence", 80)),
        1,
        key="alert_min_confidence_v1",
    )

    if st.sidebar.button("💾 Lagre varselkontroll", key="save_alert_control_v1"):
        _merged_alert_settings = load_settings()
        _merged_alert_settings["pushover_enabled"] = bool(_pushover_setting_on)
        _merged_alert_settings["notify_paper_trades"] = bool(_notify_trades)
        _merged_alert_settings["notify_watchlist_signal_changes"] = bool(_notify_watchlist)
        _merged_alert_settings["notify_high_confidence_only"] = bool(_high_conf_only)
        _merged_alert_settings["notify_min_confidence"] = int(_min_alert_conf)
        save_settings(_merged_alert_settings)
        st.sidebar.success("Varselkontroll lagret ✅")
        st.rerun()

    _t1, _t2 = st.sidebar.columns(2)
    with _t1:
        if st.button("Test", key="alert_send_test_v1", disabled=not _pushover_env_ok):
            ok, err = send_pushover_alert("✅ Testvarsel fra AI Aksje Analyzer Pro", title="Testvarsel")
            if ok:
                st.sidebar.success("Test sendt ✅")
            else:
                st.sidebar.error(f"Feil: {err}")
    with _t2:
        if st.button("Nullstill", key="alert_reset_antispam_v1"):
            reset_alert_state()
            st.sidebar.success("Signalhistorikk nullstilt ✅")

    with st.sidebar.expander("Varselinfo", expanded=False):
        st.caption("Paper BUY/SELL-varsler sendes bare når en faktisk paper-handel utføres.")
        st.caption("Watchlist-varsler sendes ved signalendring, og bruker confidence-grensen hvis høy confidence er aktivert.")
        st.write("TOKEN:", "OK" if PUSHOVER_APP_TOKEN else "MISSING")
        st.write("USER:", "OK" if PUSHOVER_USER_KEY else "MISSING")


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
        padding: 7px 9px;
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
st.sidebar.markdown("<div class='sidebar-tight-hr'></div>", unsafe_allow_html=True)
st.sidebar.subheader("🤖 Auto trading")

_settings = load_settings()
_markets_settings = _settings.get("markets", {}) or {}

_auto_state_label, _auto_state_color = _auto_state(_settings)
st.sidebar.markdown(
    f"""
    <div class="auto-command-card">
        <div class="auto-command-title">
            <span>🤖 Auto trading</span>
            <span class="auto-status-badge {'on' if _auto_state_color == 'green' else 'off'}">
                <span class="status-dot {_auto_state_color}"></span>{_auto_state_label}
            </span>
        </div>
        <div class="auto-command-line">
            BUY conf: <b>{int(_settings.get('min_buy_confidence', 70))}%</b> ·
            Score: <b>{float(_settings.get('min_buy_score', 7.2)):.1f}</b> ·
            Max pos: <b>{int(_settings.get('max_open_positions', 5))}</b>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.sidebar.caption("Auto trading-kontroller. Påvirker kun auto trading, ikke systemdrift/full stopp.")
if st.sidebar.button("▶ Start", key="auto_start_sidebar_v1412", use_container_width=True):
    _set_auto_state("START")
if st.sidebar.button("⏸ Pause", key="auto_pause_sidebar_v1412", use_container_width=True):
    _set_auto_state("PAUSE")
if st.sidebar.button("⛔ Stopp", key="auto_stop_sidebar_v1412", use_container_width=True):
    _set_auto_state("STOPP")
if st.sidebar.button("🚨 Nødstopp Auto trading", key="auto_emergency_sidebar_v1412", use_container_width=True):
    _set_auto_state("NØDSTOPP")

with st.sidebar.expander("⚙️ Auto-kjøp parametere", expanded=False):
    st.caption("Samlet i to grupper. Endringer lagres først når du trykker Lagre.")
    with st.form("auto_trading_settings_form_v10", clear_on_submit=False):
        _auto_enabled = st.checkbox(
            "Auto trading aktiv",
            value=bool(_settings.get("auto_trading_enabled", False)),
            key="persist_auto_enabled_v10",
        )
        _safe_edit = st.checkbox(
            "Pause auto trading når parametere lagres",
            value=bool(_settings.get("auto_trading_safe_edit_mode", True)),
            key="persist_safe_edit_mode_v147",
            help="Sikker redigeringsmodus: ved lagring settes auto trading i pause, slik at du kan kontrollere parametere før ny start.",
        )

        st.markdown('<div class="auto-settings-group-title">Kjøpsgrenser</div>', unsafe_allow_html=True)
        _min_conf = st.number_input(
            "Min confidence for BUY",
            0,
            100,
            int(_settings.get("min_buy_confidence", 70)),
            1,
            key="persist_min_conf_v10",
        )
        _min_score = st.number_input(
            "Min score for BUY",
            0.0,
            10.0,
            float(_settings.get("min_buy_score", 7.2)),
            0.1,
            key="persist_min_score_v10",
        )
        _pos_size = st.number_input(
            "Posisjonsstørrelse %",
            1.0,
            100.0,
            float(_settings.get("position_size_pct", 10.0)),
            1.0,
            key="persist_pos_size_v10",
        )
        _cooldown = st.number_input(
            "Cooldown minutter",
            0,
            1440,
            int(_settings.get("cooldown_minutes", 60)),
            5,
            key="persist_cooldown_v10",
        )
        _top_only = st.checkbox(
            "Auto trading kun Top Picks",
            value=bool(_settings.get("scan_top_picks_only", True)),
            key="persist_top_only_v10",
        )

        st.markdown('<div class="auto-settings-group-title">Kapasitet / risiko</div>', unsafe_allow_html=True)
        st.markdown('<div class="auto-market-list-note">Markeder Cron skal bruke</div>', unsafe_allow_html=True)
        # Oppgave 09: ikke bruk tre smale kolonner i sidebar. Da brytes Norge/Sverige bokstavvis.
        _m_usa = st.checkbox("USA", value=bool(_markets_settings.get("USA", True)), key="persist_market_usa_v11")
        _m_no = st.checkbox("Norge", value=bool(_markets_settings.get("NORGE", True)), key="persist_market_no_v11")
        _m_se = st.checkbox("Sverige", value=bool(_markets_settings.get("SVERIGE", True)), key="persist_market_se_v11")

        _max_tickers = st.number_input(
            "Maks aksjer per marked",
            1,
            100,
            int(_settings.get("max_tickers_per_market", 20)),
            1,
            key="persist_max_tickers_v10",
        )
        _max_pos = st.number_input(
            "Maks åpne posisjoner",
            1,
            30,
            int(_settings.get("max_open_positions", 5)),
            1,
            key="persist_max_pos_v10",
        )
        _max_trades = st.number_input(
            "Maks kjøp per dag",
            1,
            50,
            int(_settings.get("max_trades_per_day", 3)),
            1,
            key="persist_max_trades_v10",
        )
        _safety_mode = st.checkbox(
            "Sikkerhetsmodus for auto-kjøp",
            value=bool(_settings.get("auto_buy_safety_mode", True)),
            key="persist_safety_mode_v12",
            help="Når på: salg/exit skal alltid få gå, mens nye kjøp stoppes ved dårlig/ugyldig data eller grensebrudd.",
        )
        _push = st.checkbox(
            "Pushover aktiv",
            value=bool(_settings.get("pushover_enabled", True)),
            key="persist_push_v10",
        )

        _save_auto = st.form_submit_button("💾 Lagre auto-innstillinger", use_container_width=True)
        _reset_auto = st.form_submit_button("↩️ Standard auto-innstillinger", use_container_width=True)

    if _save_auto:
        _current_settings_for_auto_save = load_settings()
        _current_settings_for_auto_save.update({
            "auto_trading_enabled": bool(_auto_enabled) and not bool(_safe_edit),
            "auto_trading_paused": bool(_safe_edit) if bool(_auto_enabled) else False,
            "auto_trading_emergency_stop": False,
            "auto_trading_safe_edit_mode": bool(_safe_edit),
            "markets": {"USA": bool(_m_usa), "NORGE": bool(_m_no), "SVERIGE": bool(_m_se)},
            "max_tickers_per_market": int(_max_tickers),
            "min_buy_confidence": int(_min_conf),
            "min_buy_score": float(_min_score),
            "max_open_positions": int(_max_pos),
            "max_trades_per_day": int(_max_trades),
            "max_buys_per_day": int(_max_trades),
            "position_size_pct": float(_pos_size),
            "cooldown_minutes": int(_cooldown),
            "scan_top_picks_only": bool(_top_only),
            "pushover_enabled": bool(_push),
            "auto_buy_safety_mode": bool(_safety_mode),
        })
        save_settings(_current_settings_for_auto_save)
        # Oppgave 74: én felles verdi for maks kjøp per dag.
        # Auto-/paper-motoren leser trading_rules, derfor speiles verdien dit også.
        try:
            _r = load_rules()
            _r["max_trades_per_day"] = int(_max_trades)
            save_rules(_r)
        except Exception:
            pass
        st.sidebar.success("Auto-innstillinger lagret ✅")
        st.rerun()

    if _reset_auto:
        reset_settings()
        st.sidebar.success("Auto-innstillinger tilbakestilt ✅")
        st.rerun()



st.sidebar.markdown("<div class='sidebar-tight-hr'></div>", unsafe_allow_html=True)
st.sidebar.markdown("### ⚙️ Trading-regler")
_rules = load_rules()

with st.sidebar.expander("📈 Kjøp", expanded=False):
    _rules["min_buy_score"] = st.slider("Min BUY score", 1.0, 10.0, float(_rules["min_buy_score"]), 0.1)
    _rules["min_buy_confidence"] = st.slider("Min BUY confidence", 1, 100, int(_rules["min_buy_confidence"]))
    _rules["max_buy_rsi"] = st.slider("Maks RSI for kjøp", 40, 90, int(_rules["max_buy_rsi"]))
    st.caption("Maks kjøp per dag styres kun i Auto-kjøp parametere (-/+). Gjelder bare nye kjøp, ikke salg/exit.")

with st.sidebar.expander("🟡 Hold", expanded=False):
    _rules["min_hold_days"] = st.slider("Min hold-dager", 0, 30, int(_rules["min_hold_days"]))
    _rules["ignore_small_moves_pct"] = st.slider("Ignorer små svingninger %", 0.0, 10.0, float(_rules["ignore_small_moves_pct"]), 0.5)

with st.sidebar.expander("🔴 Salg", expanded=False):
    _rules["enable_sell_signal_exit"] = st.checkbox("Selg ved SELL/AVOID signal", bool(_rules["enable_sell_signal_exit"]))
    _rules["stop_loss_pct"] = st.slider("Stop-loss %", 1.0, 25.0, float(_rules["stop_loss_pct"]), 0.5)
    _rules["take_profit_pct"] = st.slider("Take-profit %", 1.0, 50.0, float(_rules["take_profit_pct"]), 0.5)
    _rules["trailing_stop_pct"] = st.slider("Trailing stop %", 1.0, 30.0, float(_rules.get("trailing_stop_pct", 8.0)), 0.5)
    _rules["rsi_exit_level"] = st.slider("RSI exit nivå", 60, 90, int(_rules["rsi_exit_level"]))
    _rules["rsi_must_fall"] = st.checkbox("RSI må falle etter topp", bool(_rules["rsi_must_fall"]))

if st.sidebar.button("💾 Lagre trading-regler", key="restore_save_rules"):
    saved_db = save_rules(_rules)
    if saved_db:
        st.sidebar.success("Lagret i database ✅")
    else:
        st.sidebar.warning("Lagret lokalt. DATABASE_URL mangler eller DB feilet.")

st.sidebar.markdown("### 🎨 Visning")
st.sidebar.caption("Mobilvennlig kontrast og større tekst er aktivert.")
# Watchlist-feltet bygges etter at marked og ticker-lister er klare.

st.sidebar.markdown('### 🔎 Analyseunivers')
selected_market_category, mode = render_market_category_selector()
max_count = st.sidebar.slider("Antall aksjer å analysere", 5, 200, 30)
st.sidebar.caption("Flere aksjer gir bedre dekning, men appen kan bli tregere.")
min_top_pick_score = st.sidebar.slider("Minimum score for Top Picks", 4.0, 9.0, 6.5, 0.1)
use_news = st.sidebar.checkbox("Bruk nyheter/sentiment", value=True)
use_signal_intelligence = st.sidebar.checkbox("Bruk Signal Intelligence", value=True)
_alert_runtime_settings = load_settings()
pushover_enabled = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY) and bool(_alert_runtime_settings.get("pushover_enabled", True))
use_high_conf_alerts_only = bool(_alert_runtime_settings.get("notify_high_confidence_only", True))
min_alert_confidence = int(_alert_runtime_settings.get("notify_min_confidence", 80))
auto_watchlist_alerts = bool(_alert_runtime_settings.get("notify_watchlist_signal_changes", True))
search = st.sidebar.text_input("Søk ticker manuelt", placeholder="F.eks. AAPL, EQNR.OL")

# V14.8 / Oppgave 70 og 72:
# Menyer skriver først til draft. Tunge analyser bruker aktive verdier til bruker trykker
# Oppdater / bruk endringer, med mindre Auto-oppdater er PÅ.
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
    _set_update_reason("Oppstart / første aktive innstillinger")

# Auto-oppdater = draft blir aktivt med en gang. Av = behold sist aktive til bruker trykker Oppdater.
if bool(load_settings().get("chart_auto_update_enabled", False)):
    st.session_state["active_analysis_controls_v148"] = dict(_draft_analysis_controls_v148)
    st.session_state["heavy_update_allowed_v148"] = True
    _set_update_reason("Auto-oppdater ved endringer")

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
_top_cron = cron_status_text()
_top_auto_state, _top_auto_color = _auto_state(_top_settings)
_top_full_stop = bool(_top_cron.get("vacation_mode"))
_top_paper = True
_top_chart_auto = bool(_top_settings.get("chart_auto_update_enabled", False))
st.markdown(
    f"""
    <div class="top-app-header">
        <div class="top-app-title">📊 Market Overview – 📈 AI Aksje Analyzer Pro</div>
        <div class="top-app-status">
            <span class="top-chip {_top_auto_color}">Auto trading: <b>{_top_auto_state}</b></span>
            <span class="top-chip {'green' if _top_paper else 'red'}">Paper: <b>AKTIV</b></span>
            <span class="top-chip {'red' if _top_full_stop else 'green'}">Full stopp: <b>{'JA' if _top_full_stop else 'NEI'}</b></span>
            <span class="top-chip {'green' if _top_chart_auto else 'red'}">Auto-oppdater: <b>{'PÅ' if _top_chart_auto else 'AV'}</b></span>
            <span class="top-chip">Siste scan: <b>{_fmt_dt_short(_top_cron.get('last_scan_at'))}</b></span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# V14.12 / Oppgave 81-86 og 89B: ryddig kontrollsenter, ikke duplisert/rotete mobilpanel.
# Hovedsiden viser en kompakt fallback-meny. Ekte Streamlit-sidebar brukes på PC/drawer,
# men denne gir trygg tilgang på mobil uten halv sidebar.
with st.expander("☰ Kontrollsenter / mobil hurtigmeny", expanded=False):
    st.markdown(
        f"""
        <div class='control-center-wide'>
            <div class='control-info-block'>
                <div class='control-info-title'>Driftstatus</div>
                <span class='mini-status-chip {_top_auto_color}'>Auto trading: <b>{_top_auto_state}</b></span>
                <span class='mini-status-chip {'green' if _top_paper else 'red'}'>Paper: <b>AKTIV</b></span>
                <span class='mini-status-chip {'red' if _top_full_stop else 'green'}'>Full stopp: <b>{'JA' if _top_full_stop else 'NEI'}</b></span>
                <span class='mini-status-chip {'green' if _top_chart_auto else 'red'}'>Auto-oppdater: <b>{'PÅ' if _top_chart_auto else 'AV'}</b></span>
            </div>
            <div class='control-info-block'>
                <div class='control-info-title'>Børsstatus</div>
                {_market_status_chips_html()}
            </div>
            <div class='control-info-block'>
                <div class='control-info-title'>Bruker / sesjon</div>
                {_session_status_html(current_user)}
            </div>
            <div class='control-info-block'>
                <div class='control-info-title'>Siste oppdatering</div>
                <span class='mini-status-chip'>Scan: <b>{_fmt_dt_short(_top_cron.get('last_scan_at'))}</b></span>
                <span class='mini-status-chip'>Tung: <b>{html.escape(_last_update_label())}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='auto-control-help'>Auto trading-kontroller: styrer kun auto trading. Salg/exit og vanlig visning av data påvirkes ikke.</div>", unsafe_allow_html=True)
    mc1, mc2, mc3, mc4 = st.columns([0.85, 0.85, 0.85, 1.55])
    with mc1:
        if st.button("▶ Start", key="mobile_auto_start_v1412", use_container_width=True):
            _set_auto_state("START")
    with mc2:
        if st.button("⏸ Pause", key="mobile_auto_pause_v1412", use_container_width=True):
            _set_auto_state("PAUSE")
    with mc3:
        if st.button("⛔ Stopp", key="mobile_auto_stop_v1412", use_container_width=True):
            _set_auto_state("STOPP")
    with mc4:
        if st.button("🚨 Nødstopp Auto trading", key="mobile_auto_emergency_v1412", use_container_width=True):
            _set_auto_state("NØDSTOPP")

    st.markdown("<div class='system-control-help'>System/drift: Full stopp og Start systemet igjen styrer bakgrunnssøk/cron og generell drift, ikke bare Auto trading.</div>", unsafe_allow_html=True)
    vc1, vc2 = st.columns([1, 1])
    with vc1:
        if st.button("⛔ Full stopp / ferie", key="mobile_full_stop_v1412", use_container_width=True):
            activate_full_stop()
            st.rerun()
    with vc2:
        if st.button("▶ Start systemet igjen", key="mobile_resume_system_v1412", use_container_width=True):
            deactivate_full_stop()
            st.rerun()

# Kompakt auto trading-kontrollrad på hovedsiden. Systemknapper vises i Kontrollsenter, ikke blandet her.
st.markdown("<div class='auto-control-help'>Auto trading: ▶ Start · ⏸ Pause · ⛔ Stopp · 🚨 Nødstopp. Full stopp/ferie ligger i Kontrollsenter.</div>", unsafe_allow_html=True)
_tq1, _tq2, _tq3, _tq4, _tq_spacer = st.columns([0.72, 0.72, 0.72, 1.45, 3.2])
with _tq1:
    if st.button("▶ Start", key="auto_start_top_v1412", use_container_width=True):
        _set_auto_state("START")
with _tq2:
    if st.button("⏸ Pause", key="auto_pause_top_v1412", use_container_width=True):
        _set_auto_state("PAUSE")
with _tq3:
    if st.button("⛔ Stopp", key="auto_stop_top_v1412", use_container_width=True):
        _set_auto_state("STOPP")
with _tq4:
    if st.button("🚨 Nødstopp Auto trading", key="auto_emergency_top_v1412", use_container_width=True):
        _set_auto_state("NØDSTOPP")

_uc1, _uc2, _uc3 = st.columns([1.35, 1.45, 3.2])
with _uc1:
    _top_toggle_auto_update = st.checkbox(
        "Auto-oppdater ved endringer",
        value=_top_chart_auto,
        key="top_chart_auto_update_v147",
        help="Av = graf/indikator-endringer brukes først når du trykker Oppdater / bruk endringer.",
    )
    if bool(_top_toggle_auto_update) != _top_chart_auto:
        _save_setting_patch(chart_auto_update_enabled=bool(_top_toggle_auto_update))
        st.session_state.pop("sidebar_chart_auto_update_v147", None)
        st.rerun()
with _uc2:
    if not _top_chart_auto:
        if st.button("🔄 Oppdater / bruk endringer", key="top_apply_changes_v147", use_container_width=True):
            st.session_state["active_analysis_controls_v148"] = dict(_draft_analysis_controls_v148)
            st.session_state["heavy_update_allowed_v148"] = True
            _set_update_reason("Oppdater-knapp / bruk endringer")
            st.rerun()
    else:
        st.caption("Auto-oppdatering på")

st.markdown(f"<div class='update-debug-line'>Siste tunge oppdatering: <b>{html.escape(_last_update_label())}</b></div>", unsafe_allow_html=True)
if (not _top_chart_auto) and _pending_analysis_changes_v148:
    st.markdown("<div class='pending-changes-box'>⚠️ Endringer i menyene er ikke brukt ennå. Trykk Oppdater / bruk endringer for ny analyse/graf/rangering.</div>", unsafe_allow_html=True)

if 'top_picks' in locals():
    market_pulse(top_picks)
    top_movers(top_picks)

st.caption("Smartere scoring med momentum, trend, risiko, P/E, kvalitet, vekst, gjeld, nyheter og backtesting.")
render_live_market_banner()

if search.strip():
    tickers_us = [search.strip().upper()]
    tickers_no = []
    tickers_se = []
    tickers_all = tickers_us
else:
    tickers_us = get_sp500_tickers(limit=max_count)
    tickers_no = get_norwegian_tickers(limit=max_count)
    tickers_se = get_swedish_tickers(limit=max_count)
    tickers_all = get_all_tickers(limit_per_market=max(5, max_count // 3))

dynamic_watchlist = get_dynamic_watchlist(mode, max_count, tickers_us, tickers_no, tickers_se, tickers_all)

st.sidebar.markdown("### 👀 Watchlist alerts")
use_dynamic_watchlist = st.sidebar.checkbox(
    "Bruk dynamisk watchlist fra markedet",
    value=True,
    help="Når aktiv: watchlisten følger valgt marked og antall aksjer automatisk.",
)

if use_dynamic_watchlist:
    watchlist_tickers = dynamic_watchlist
    st.sidebar.info(f"Dynamisk watchlist aktiv: {len(watchlist_tickers)} aksjer")
    with st.sidebar.expander("Vis dynamisk watchlist"):
        st.write(", ".join(watchlist_tickers))
else:
    watchlist_text = st.sidebar.text_area(
        "Aksjer å overvåke",
        value=", ".join(dynamic_watchlist[:30]),
        help="Skriv tickere separert med komma. Norske aksjer må ofte ha .OL og svenske .ST",
    )
    watchlist_tickers = parse_watchlist(watchlist_text)

auto_watchlist_alerts = st.sidebar.checkbox(
    "Auto-scan watchlist ved refresh",
    value=False,
    help="Sender varsel bare når BUY/SELL-signalet endrer seg.",
)
_watchlist_default_limit = min(30, max(5, len(watchlist_tickers or [])))
watchlist_scan_limit = st.sidebar.slider(
    "Maks aksjer å scanne for varsler",
    5, 100, _watchlist_default_limit
)
manual_watchlist_scan = st.sidebar.button("Scan watchlist nå")

# V14.7 / Oppgave 58, 63 og 66: kompakt watchlist-/scanstatus høyt oppe.
_watch_count = len(watchlist_tickers or [])
_watch_status = "PÅ" if bool(auto_watchlist_alerts) else "AV"
_watch_push = "PÅ" if bool(pushover_enabled) else "AV"
_watch_scan = _fmt_dt_short(cron_status_text().get("last_scan_at"))
st.markdown(
    f"""
    <div class="watchlist-compact">
        <div class="watchlist-row">
            <div class="watchlist-title">🔔 Watchlist signaler</div>
            <div class="watchlist-meta">
                <span class="top-chip">Tickere: <b>{_watch_count}</b></span>
                <span class="top-chip {'green' if auto_watchlist_alerts else 'red'}">Auto-scan: <b>{_watch_status}</b></span>
                <span class="top-chip {'green' if pushover_enabled else 'red'}">Varsler: <b>{_watch_push}</b></span>
                <span class="top-chip">Siste scan: <b>{_watch_scan}</b></span>
            </div>
        </div>
        {"<div class='watchlist-empty'>Watchlist tom – legg til tickere i venstre panel eller bruk dynamisk watchlist.</div>" if _watch_count == 0 else ""}
    </div>
    """,
    unsafe_allow_html=True,
)

if auto_watchlist_alerts or manual_watchlist_scan:
    if not pushover_enabled:
        st.warning("Pushover er ikke aktivert, så appen kan ikke sende mobilvarsler.")
    elif not watchlist_tickers:
        st.info("Watchlist er tom. Legg inn minst én ticker, eller slå på dynamisk watchlist.")
    else:
        with st.spinner("Scanner watchlist..."):
            watch_results = scan_watchlist_and_alert(watchlist_tickers[:watchlist_scan_limit])
        if watch_results:
            st.dataframe(pd.DataFrame(watch_results), use_container_width=True)
            st.caption("Varsel sendes bare når et tidligere registrert signal endrer seg til BUY eller SELL / AVOID.")
        else:
            st.info("Ingen nye watchlist-signaler akkurat nå.")

st.caption("Velg panel. Bare valgt panel beregnes tungt, slik at skjulte faner ikke starter nye analyser.")
st.markdown("<div class='panel-radio-label'>Aktivt hovedpanel</div>", unsafe_allow_html=True)
_panel_options_v1412 = ["🇺🇸 USA", "🇳🇴 Norge", "🇸🇪 Sverige", "⭐ Top Picks", "🚀 IPO", "🧪 Backtesting", "🧪 Paper Trading"]
if "active_main_panel_v148" not in st.session_state:
    st.session_state["active_main_panel_v148"] = st.session_state.get("active_main_panel_persist_v1412", "🇺🇸 USA")
if st.session_state.get("active_main_panel_v148") not in _panel_options_v1412:
    st.session_state["active_main_panel_v148"] = "🇺🇸 USA"
active_panel = st.radio(
    "Aktivt hovedpanel",
    _panel_options_v1412,
    horizontal=True,
    label_visibility="collapsed",
    key="active_main_panel_v148",
)
st.session_state["active_main_panel_persist_v1412"] = active_panel

if active_panel == "🇺🇸 USA":
    us_results = cached_auto_rank_market("USA", tickers_us, max_count=max_count, use_news=False)
    render_ranking(us_results, "🏆 Dynamisk rangering USA/S&P 500")
    render_analysis(us_results, "USA")

elif active_panel == "🇳🇴 Norge":
    no_results = cached_auto_rank_market("Norge", tickers_no, max_count=max_count, use_news=False)
    render_ranking(no_results, "🇳🇴 Dynamisk rangering Norge")
    render_analysis(no_results, "Norge")

elif active_panel == "🇸🇪 Sverige":
    se_results = cached_auto_rank_market("Sverige", tickers_se, max_count=max_count, use_news=False)
    render_ranking(se_results, "🇸🇪 Dynamisk rangering Sverige")
    render_analysis(se_results, "Sverige")

elif active_panel == "⭐ Top Picks":
    st.subheader("⭐ Automatiske Top Picks")
    st.caption(
        "Top Picks = beste kandidater totalt. "
        "Kjøp nå = kandidater som også har grønt teknisk signal akkurat nå."
    )

    scan_market = st.radio("Velg marked for Top Picks", ["USA", "Norge", "Sverige", "Alle"], horizontal=True)

    if scan_market == "USA":
        source_tickers = tickers_us
    elif scan_market == "Norge":
        source_tickers = tickers_no
    elif scan_market == "Sverige":
        source_tickers = tickers_se
    else:
        source_tickers = tickers_all

    _guard_summary = market_guard_summary(source_tickers)
    st.caption(_guard_summary)

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
        ranked = cached_auto_rank_market(
            f"TopPicks_{scan_market}",
            source_tickers,
            max_count=max_count,
            use_news=False,
            force_manual_fetch=_manual_fetch_closed,
        )
        top_picks = build_top_picks(ranked, min_score=min_top_pick_score, max_items=15)
        buy_now_picks = [x for x in top_picks if is_buy_now_item(x)]
        latest = st.session_state.setdefault("latest_rankings_v148", {})
        latest[f"TopPicks_{scan_market}"] = top_picks or []

    if not top_picks and not _manual_fetch_closed and not _open_now:
        st.info(
            "Ingen cache-data funnet. Kryss av for 'Hent data manuelt likevel' hvis du vil analysere utenfor åpningstid. "
            "Dette starter ikke auto-trading."
        )

    top_pick_view = st.radio("Top Picks-visning", ["⭐ Top Picks", "🟢 Kjøp nå"], horizontal=True, key=f"top_pick_view_{scan_market}_v148")

    if top_pick_view == "⭐ Top Picks":
        render_ranking(top_picks, f"⭐ Top Picks {scan_market}")
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
                st.success(" | ".join(_messages[:8]))
                st.rerun()

            render_ranking(buy_now_picks, f"🟢 Kjøp nå {scan_market}")
            render_analysis(buy_now_picks, f"KjopNa_{scan_market}")
        else:
            st.warning("Ingen aksjer har grønt teknisk kjøpssignal akkurat nå.")
            st.caption("Systemet tvinger ikke kjøp når timing/risiko ikke er god nok.")

elif active_panel == "🚀 IPO":
    render_ipo()

elif active_panel == "🧪 Backtesting":
    bt_market = st.radio("Backtest-marked", ["USA", "Norge", "Sverige"], horizontal=True)
    if bt_market == "USA":
        bt_tickers = tickers_us
    elif bt_market == "Norge":
        bt_tickers = get_norwegian_tickers(limit=max_count)
    else:
        bt_tickers = get_swedish_tickers(limit=max_count)

    render_strategy_backtest(bt_tickers, bt_market)

elif active_panel == "🧪 Paper Trading":
    render_paper_trading_dashboard()

# Etter første godkjente kjøring slås engangsflagget av. Cache brukes ved vanlige widget-reruns.
st.session_state["heavy_update_allowed_v148"] = False


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
