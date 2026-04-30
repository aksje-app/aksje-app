from ui_components import market_pulse, top_movers
import os
import streamlit as st
from alert_state import reset_alert_state
from market_hours import open_markets
from trading_settings import load_rules, save_rules
import pandas as pd
import plotly.graph_objects as go
import requests
from streamlit_autorefresh import st_autorefresh

from technical import calculate_rsi, calculate_macd, calculate_bollinger, detect_trend, technical_signal
from patterns import detect_head_shoulders, detect_inverse_head_shoulders, breakout_scanner, build_signal_alerts

from stocks import get_sp500_tickers, get_norwegian_tickers, get_swedish_tickers, get_all_tickers
from analysis import rank_stocks, score_stock
from market_selector import auto_rank_market, build_top_picks
from backtest_strategy import run_monthly_score_strategy, add_stats
from ipo import get_ipo_calendar
from news import get_news, simple_finance_sentiment
from trading_engine import build_trading_decision, adjusted_score
from strategy_engine import run_strategy, strategy_stats, optimize_strategy
from signal_engine import calculate_signal_intelligence
from insider import get_insider_data
from analyst import get_analyst_trend
from earnings import get_earnings
from paper_store import using_postgres
from paper_trading import load_portfolio, portfolio_value, reset_portfolio, performance_stats, STOP_LOSS_PCT, TRAILING_STOP_PCT, MAX_TRADES_PER_DAY

st.set_page_config(page_title="AI Aksje Analyzer Pro", page_icon="📈", layout="wide")
st_autorefresh(interval=300000, key="refresh")

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

</style>
""", unsafe_allow_html=True)


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


def render_decision_banner(decision, item, adj_score):
    decision_text = decision.get("decision", "HOLD / WAIT")
    emoji = decision.get("emoji", "🟡")
    color = decision.get("color", "orange")

    if decision_text == "BUY":
        st.success(f"{emoji} BUY-signal | Confidence: {decision.get('confidence', 'N/A')}%")
    elif decision_text == "SELL / AVOID":
        st.error(f"{emoji} SELL / AVOID | Confidence: {decision.get('confidence', 'N/A')}%")
    else:
        st.warning(f"{emoji} HOLD / WAIT | Confidence: {decision.get('confidence', 'N/A')}%")

    st.markdown(
        f"""
        <div class="card">
            <h3 style="color:{color}; margin-bottom: 0.4rem;">{emoji} {decision_text}</h3>
            <p style="font-size:1.05rem; margin-bottom:0.2rem;">
                Original score: <b>{item['score']}/10</b> · Pattern-justert score: <b>{adj_score}/10</b>
            </p>
            <p class="small">Dette er analysehjelp, ikke investeringsråd.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_ranking(results, title):
    st.subheader(title)

    if not results:
        st.warning("Fant ingen data.")
        return

    best = results[0]
    best_price, best_change = get_item_price_change(best)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Beste aksje", f"{best['ticker']} {best.get('score', 0)}/10")
    c2.metric("Analyserte", len(results))
    c3.metric(
        "Siste kurs",
        f"{best_price:.2f} {currency_suffix(best['ticker'])}" if best_price else "N/A",
        delta=f"{best_change:+.2f}%" if best_change is not None else None,
    )
    c4.metric("Auto-refresh", "1 min")

    st.markdown("### ⚡ Hurtigliste med kurs")
    st.caption("Kurs og prosentendring vises direkte i listen.")

    for idx, item in enumerate(results[:15], start=1):
        ticker = item.get("ticker", "N/A")
        score = item.get("score", 0)
        latest_price, change_pct = get_item_price_change(item)

        price_text = "N/A"
        delta_text = None
        direction_icon = "⚪"

        if latest_price is not None:
            price_text = f"{latest_price:.2f} {currency_suffix(ticker)}"
            delta_text = f"{change_pct:+.2f}%"
            direction_icon = "🟢" if change_pct >= 0 else "🔴"

        with st.container(border=True):
            left, mid, right = st.columns([1.25, 1.0, 2.1])

            with left:
                st.markdown(f"### {direction_icon} {ticker}")
                st.caption(f"#{idx} · {item.get('name', '')}")

            with mid:
                st.metric("Score", f"{score}/10")
                st.metric("Kurs", price_text, delta=delta_text)

            with right:
                st.progress(min(float(score) / 10, 1.0))
                st.caption(
                    f"1y: {item.get('ret_1y', 0)*100:.1f}% · "
                    f"6m: {item.get('ret_6m', 0)*100:.1f}% · "
                    f"3m: {item.get('ret_3m', 0)*100:.1f}% · "
                    f"Vol: {item.get('volatility', 0):.4f} · "
                    f"DD: {item.get('max_drawdown', 0)*100:.1f}%"
                )



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

def render_analysis(results, label):
    st.subheader("📊 Interaktiv analyse")
    if not results:
        return

    selected = st.selectbox(f"Velg aksje ({label})", [r["ticker"] for r in results], key=f"select_{label}")
    item = next(r for r in results if r["ticker"] == selected)
    df = item["hist"].copy()

    st.plotly_chart(plot_price(df, f"{selected} - prisutvikling"), use_container_width=True, key=f"price_chart_{label}_{selected}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Score", f"{item['score']}/10")
    m2.metric("P/E", item.get("forward_pe") or item.get("trailing_pe") or "N/A")
    m3.metric("Revenue growth", f"{item['revenue_growth']*100:.1f}%" if isinstance(item.get("revenue_growth"), (int,float)) else "N/A")
    m4.metric("Max drawdown", f"{item['max_drawdown']*100:.1f}%")

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
        decision["confidence"] = signal_intelligence["confidence"]
        decision["decision_score"] = signal_intelligence["final_score"]
        decision["reasons"] = decision.get("reasons", []) + signal_intelligence.get("reasons", [])

    if (not use_high_conf_alerts_only) or decision.get("confidence", 0) >= min_alert_confidence:
        maybe_send_signal_alert(selected, decision)

    st.markdown("#### 🤖 Trading engine")
    d1, d2, d3 = st.columns(3)
    d1.metric("Beslutning", f"{decision['emoji']} {decision['decision']}")
    d2.metric("Signal-score", decision["decision_score"])
    d3.metric("Confidence", f"{decision['confidence']}%")

    render_decision_banner(decision, item, adj_score)

    if signal_intelligence:
        st.markdown("#### 🧠 Signal Intelligence")
        si1, si2, si3, si4 = st.columns(4)
        si1.metric("Smart score", f"{signal_intelligence['final_score']}/10")
        si2.metric("Bonus", signal_intelligence["bonus"])
        si3.metric("Risk", signal_intelligence["risk"])
        si4.metric("Confidence", f"{signal_intelligence['confidence']}%")

        i1, i2, i3 = st.columns(3)
        with i1:
            st.markdown("**🕵️ Insider**")
            if insider.get("error"):
                st.caption(insider["error"])
            st.write(f"Score: {insider.get('score', 'N/A')}")
            st.caption(f"Kjøp: {insider.get('buy_shares', 0)} · Salg: {insider.get('sell_shares', 0)}")

        with i2:
            st.markdown("**📈 Analyst**")
            if analyst.get("error"):
                st.caption(analyst["error"])
            st.write(f"Trend: {analyst.get('trend', 'N/A')}")
            st.caption(f"Buy: {analyst.get('buy', 0)} · Hold: {analyst.get('hold', 0)} · Sell: {analyst.get('sell', 0)}")

        with i3:
            st.markdown("**⏰ Earnings**")
            if earnings.get("error"):
                st.caption(earnings["error"])
            if earnings.get("date"):
                st.write(f"Dato: {earnings.get('date')}")
                st.caption(f"Dager igjen: {earnings.get('days_until')}")
            else:
                st.write("Ingen nær dato funnet")

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
    st.plotly_chart(fig_ta, use_container_width=True, key=f"ta_chart_{label}_{selected}")

    fig_macd = go.Figure()
    fig_macd.add_trace(go.Scatter(x=df.index, y=macd, name="MACD", mode="lines"))
    fig_macd.add_trace(go.Scatter(x=df.index, y=macd_signal, name="Signal", mode="lines"))
    fig_macd.add_trace(go.Bar(x=df.index, y=macd_hist, name="Histogram"))
    fig_macd.update_layout(
        title=f"{selected} - MACD",
        template="plotly_dark",
        height=300,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
    )
    st.plotly_chart(fig_macd, use_container_width=True, key=f"macd_chart_{label}_{selected}")

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
    st.plotly_chart(add_rsi_level_labels(fig_rsi, rsi), use_container_width=True, key=f"rsi_chart_{label}_{selected}")

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

        if equity:
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

            st.plotly_chart(fig_eq, use_container_width=True, key=f"equity_chart_{label}_{selected}")

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

            best = opt_df.iloc[0]
            st.success(
                f"Beste variant: BUY RSI < {best['buy_rsi']}, "
                f"SELL RSI > {best['sell_rsi']}, "
                f"MACD: {best['use_macd']} | "
                f"Return: {best['total_return']}% | "
                f"Max DD: {best['max_drawdown']}%"
            )

    st.markdown("#### 🧠 Score-forklaring")
    parts = item.get("score_parts", {})
    if parts:
        for k, v in parts.items():
            st.progress(float(v))
            st.caption(f"{k}: {v}")

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

    portfolio = load_portfolio()

    latest_prices = {}
    for ticker, pos in portfolio.get("positions", {}).items():
        latest_prices[ticker] = pos.get("last_price", pos.get("avg_price", 0))

    total_value = portfolio_value(portfolio, latest_prices)
    stats = performance_stats(portfolio, latest_prices)

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Cash", f"{portfolio.get('cash', 0):,.0f} kr")
    p2.metric("Porteføljeverdi", f"{total_value:,.0f} kr")
    p3.metric("Total avkastning", f"{stats['total_return_pct']}%")
    p4.metric("Trades i dag", f"{stats['trades_today']}/{stats['max_trades_per_day']}")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Stop-loss", f"{STOP_LOSS_PCT*100:.1f}%")
    r2.metric("Trailing stop", f"{TRAILING_STOP_PCT*100:.1f}%")
    r3.metric("Win rate", f"{stats['win_rate']}%")
    r4.metric("Lukkede trades", stats["closed_trades"])

    if st.button("Reset paper portfolio", key="restore_reset_paper_portfolio"):
        reset_portfolio()
        st.success("Paper portfolio nullstilt. Refresh siden.")

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
        st.plotly_chart(fig, use_container_width=True, key=f"backtest_main_{label}")

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=strategy["date"], y=strategy["drawdown"], fill="tozeroy", name="Drawdown"))
        fig_dd.update_layout(title="Drawdown", template="plotly_dark", height=300)
        st.plotly_chart(fig_dd, use_container_width=True, key=f"backtest_drawdown_{label}")

        st.markdown("#### Valgte aksjer per måned")
        st.dataframe(strategy[["date", "monthly_return", "gross_return", "cost", "selected"]], use_container_width=True)

st.sidebar.title("⚙️ Innstillinger")


st.sidebar.markdown("### 🔕 Varselkontroll")
st.sidebar.caption(f"Åpne markeder nå: {open_markets()}")
if st.sidebar.button("Nullstill anti-spam signalhistorikk", key="restore_reset_antispam"):
    db_reset = reset_alert_state()
    st.sidebar.success("Signalhistorikk nullstilt ✅")

st.sidebar.markdown("### ⚙️ Trading-regler")
_rules = load_rules()

with st.sidebar.expander("📈 Kjøp", expanded=False):
    _rules["min_buy_score"] = st.slider("Min BUY score", 1.0, 10.0, float(_rules["min_buy_score"]), 0.1)
    _rules["min_buy_confidence"] = st.slider("Min BUY confidence", 1, 100, int(_rules["min_buy_confidence"]))
    _rules["max_buy_rsi"] = st.slider("Maks RSI for kjøp", 40, 90, int(_rules["max_buy_rsi"]))
    _rules["max_trades_per_day"] = st.slider("Maks trades per dag", 1, 10, int(_rules["max_trades_per_day"]))

with st.sidebar.expander("🟡 Hold", expanded=False):
    _rules["min_hold_days"] = st.slider("Min hold-dager", 0, 30, int(_rules["min_hold_days"]))
    _rules["ignore_small_moves_pct"] = st.slider("Ignorer små svingninger %", 0.0, 10.0, float(_rules["ignore_small_moves_pct"]), 0.5)

with st.sidebar.expander("🔴 Salg", expanded=False):
    _rules["enable_sell_signal_exit"] = st.checkbox("Selg ved SELL/AVOID signal", bool(_rules["enable_sell_signal_exit"]))
    _rules["stop_loss_pct"] = st.slider("Stop-loss %", 1.0, 25.0, float(_rules["stop_loss_pct"]), 0.5)
    _rules["take_profit_pct"] = st.slider("Take-profit %", 1.0, 50.0, float(_rules["take_profit_pct"]), 0.5)
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
st.sidebar.markdown("### 📱 Varsler")
st.session_state.enable_ui_signal_alerts = st.sidebar.checkbox("Aktiver UI-signalvarsler", value=False)
pushover_enabled = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)
st.sidebar.write("Pushover:", "✅ Aktiv" if pushover_enabled else "❌ Ikke konfigurert")
with st.sidebar.expander("Debug varsler"):
    st.write("TOKEN:", "OK" if PUSHOVER_APP_TOKEN else "MISSING")
    st.write("USER:", "OK" if PUSHOVER_USER_KEY else "MISSING")
if pushover_enabled and st.sidebar.button("Send test-varsel", key="restore_test_pushover"):
    ok, err = send_pushover_alert("✅ Testvarsel fra AI Aksje Analyzer")
    if ok:
        st.sidebar.success("Testvarsel sendt")
    else:
        st.sidebar.error(f"Feil: {err}")
st.sidebar.caption("Legg PUSHOVER_APP_TOKEN og PUSHOVER_USER_KEY i Render Environment Variables.")

# Watchlist-feltet bygges etter at marked og ticker-lister er klare.

mode = st.sidebar.radio("Marked", ["USA / S&P 500", "Norge / Oslo Børs", "Sverige / Stockholm", "Alle"])
max_count = st.sidebar.slider("Antall aksjer å analysere", 5, 200, 30)
st.sidebar.caption("Flere aksjer gir bedre dekning, men appen kan bli tregere.")
min_top_pick_score = st.sidebar.slider("Minimum score for Top Picks", 4.0, 9.0, 6.5, 0.1)
use_news = st.sidebar.checkbox("Bruk nyheter/sentiment", value=True)
use_signal_intelligence = st.sidebar.checkbox("Bruk Signal Intelligence", value=True)
use_high_conf_alerts_only = st.sidebar.checkbox("Varsle kun høy confidence", value=True)
min_alert_confidence = st.sidebar.slider("Min alert confidence", 50, 95, 70)
search = st.sidebar.text_input("Søk ticker manuelt", placeholder="F.eks. AAPL, EQNR.OL")

# Trygge standardverdier for watchlist-knapper
auto_watchlist_alerts = globals().get("auto_watchlist_alerts", False)
manual_watchlist_scan = globals().get("manual_watchlist_scan", False)
watchlist_scan_limit = globals().get("watchlist_scan_limit", 30)
watchlist_tickers = globals().get("watchlist_tickers", [])


st.markdown("## 📊 Market Overview")
if 'top_picks' in locals():
    market_pulse(top_picks)
    top_movers(top_picks)

st.title("📈 AI Aksje Analyzer Pro — Restore")
st.caption("Smartere scoring med momentum, trend, risiko, P/E, kvalitet, vekst, gjeld, nyheter og backtesting.")

if auto_watchlist_alerts or manual_watchlist_scan:
    st.markdown("### 🔔 Watchlist signaler")
    if not pushover_enabled:
        st.warning("Pushover er ikke aktivert, så appen kan ikke sende mobilvarsler.")
    elif not watchlist_tickers:
        st.info("Legg inn minst én ticker i watchlist.")
    else:
        with st.spinner("Scanner watchlist..."):
            watch_results = scan_watchlist_and_alert(watchlist_tickers[:watchlist_scan_limit])

        if watch_results:
            st.dataframe(pd.DataFrame(watch_results), use_container_width=True)
            st.caption("Varsel sendes bare når et tidligere registrert signal endrer seg til BUY eller SELL / AVOID.")

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
watchlist_scan_limit = st.sidebar.slider(
    "Maks aksjer å scanne for varsler",
    5, 100, min(30, len(watchlist_tickers))
)
manual_watchlist_scan = st.sidebar.button("Scan watchlist nå")

tabs = st.tabs(["🇺🇸 USA", "🇳🇴 Norge", "🇸🇪 Sverige", "⭐ Top Picks", "🚀 IPO", "🧪 Backtesting", "🧪 Paper Trading"])

with tabs[0]:
    if mode in ["USA / S&P 500", "Alle"] or search.strip():
        us_results = auto_rank_market(tickers_us, max_count=max_count, use_news=False)
        render_ranking(us_results, "🏆 Dynamisk rangering USA/S&P 500")
        render_analysis(us_results, "USA")
    else:
        st.info("USA er slått av i sidepanelet.")

with tabs[1]:
    if mode in ["Norge / Oslo Børs", "Alle"] and not search.strip():
        no_results = auto_rank_market(tickers_no, max_count=max_count, use_news=False)
        render_ranking(no_results, "🇳🇴 Dynamisk rangering Norge")
        render_analysis(no_results, "Norge")
    else:
        st.info("Velg Norge eller Alle i sidepanelet.")

with tabs[2]:
    if mode in ["Sverige / Stockholm", "Alle"] and not search.strip():
        se_results = auto_rank_market(tickers_se, max_count=max_count, use_news=False)
        render_ranking(se_results, "🇸🇪 Dynamisk rangering Sverige")
        render_analysis(se_results, "Sverige")
    else:
        st.info("Velg Sverige eller Alle i sidepanelet.")

with tabs[3]:
    st.subheader("⭐ Automatiske Top Picks")
    st.caption("Top Picks velges automatisk basert på score. Listen og rekkefølgen kan endre seg når markedet endrer seg.")

    scan_market = st.radio("Velg marked for Top Picks", ["USA", "Norge", "Sverige", "Alle"], horizontal=True)

    if scan_market == "USA":
        source_tickers = tickers_us
    elif scan_market == "Norge":
        source_tickers = tickers_no
    elif scan_market == "Sverige":
        source_tickers = tickers_se
    else:
        source_tickers = tickers_all

    with st.spinner("Finner beste kandidater..."):
        ranked = auto_rank_market(source_tickers, max_count=max_count, use_news=False)
        top_picks = build_top_picks(ranked, min_score=min_top_pick_score, max_items=15)

    render_ranking(top_picks, f"⭐ Top Picks {scan_market}")
    render_analysis(top_picks, f"TopPicks_{scan_market}")

with tabs[4]:
    render_ipo()

with tabs[5]:
    bt_market = st.radio("Backtest-marked", ["USA", "Norge", "Sverige"], horizontal=True)
    if bt_market == "USA":
        bt_tickers = tickers_us
    elif bt_market == "Norge":
        bt_tickers = get_norwegian_tickers(limit=max_count)
    else:
        bt_tickers = get_swedish_tickers(limit=max_count)

    render_strategy_backtest(bt_tickers, bt_market)

with tabs[6]:
    render_paper_trading_dashboard()


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
